import contextlib
import importlib.util
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CHAPTERS = ROOT / "content" / "docs" / "tech" / "machine-learning-platform-engineering"


def examples(chapter):
    source = next(CHAPTERS.glob(f"{chapter:02d}-*.md")).read_text(encoding="utf-8")
    return re.findall(r"```python\n(.*?)\n```", source, re.DOTALL)


class StudyDecisionTest(unittest.TestCase):
    def test_lineage_example_detects_changed_contents_at_the_same_path(self):
        with tempfile.TemporaryDirectory(prefix=".lineage-test-", dir=ROOT) as directory:
            script = Path(directory) / "lineage_study.py"
            script.write_text(examples(1)[0], encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(script)], cwd=directory,
                capture_output=True, text=True, check=True,
            )
            self.assertIn("Matches before change: True", result.stdout)
            self.assertIn("Matches after change: False", result.stdout)

    def test_cost_example_explains_the_two_operating_points(self):
        namespace = {}
        with contextlib.redirect_stdout(io.StringIO()):
            exec(examples(2)[0], namespace)
        cost = namespace["error_cost"]
        self.assertEqual(cost(40, 20), 4040)
        self.assertEqual(cost(10, 50), 1100)
        with self.assertRaises(ValueError):
            cost(-1, 20)

    def test_gate_rejects_bad_data_slow_candidates_and_invalid_metrics(self):
        namespace = {}
        with contextlib.redirect_stdout(io.StringIO()):
            exec(examples(2)[1], namespace)
        decide = namespace["release_decision"]
        report = namespace["candidate"]
        self.assertTrue(decide(report)["eligible"])
        for change in (
            {"missing_rate": 0.08}, {"validation_auc": 0.79},
            {"p95_latency_ms": 260}, {"schema_valid": False},
        ):
            result = decide({**report, **change})
            self.assertFalse(result["eligible"])
            self.assertTrue(result["reasons"])
        for change in ({"validation_auc": float("nan")}, {"missing_rate": -0.1}):
            with self.assertRaises(ValueError):
                decide({**report, **change})


@unittest.skipUnless(
    os.name != "nt"
    and all(importlib.util.find_spec(name) for name in ("mlflow", "feast", "kfp", "pandas")),
    "Native study examples require the pinned ML dependencies and a POSIX shell",
)
class NativeStudyTest(unittest.TestCase):
    def test_asof_features_and_fixed_model_flow_through_the_actual_pipeline(self):
        import pandas as pd

        with tempfile.TemporaryDirectory(prefix=".book-study-test-", dir=ROOT) as directory:
            work = Path(directory)
            for chapter, names in (
                (4, ("income_study.py", "feature_study.py")),
                (5, ("pipeline_study.py", "run_pipeline_study.py")),
            ):
                blocks = examples(chapter)
                self.assertEqual(len(blocks), len(names))
                for name, code in zip(names, blocks):
                    (work / name).write_text(code, encoding="utf-8")
                    result = subprocess.run(
                        [sys.executable, str(work / name)],
                        cwd=work, capture_output=True, text=True,
                        encoding="utf-8", timeout=180,
                    )
                    self.assertEqual(
                        result.returncode, 0,
                        f"{name}\n{result.stdout[-4000:]}\n{result.stderr[-4000:]}",
                    )
            outputs = [
                path for path in (work / "kfp-local-output").rglob("result")
                if path.is_file()
            ]
            self.assertEqual(len(outputs), 1)
            frame = pd.read_parquet(outputs[0])
            self.assertEqual(frame["user_id"].tolist(), [42])
            self.assertEqual(frame["hours_per_week"].tolist(), [36.0])
            self.assertEqual(frame["workclass"].tolist(), ["private"])
            self.assertTrue(frame["probability_gt_50k"].between(0, 1).all())
            fixed_uri = (work / "selected_model_uri.txt").read_text(encoding="utf-8")
            self.assertEqual(frame["model_uri"].tolist(), [fixed_uri])
