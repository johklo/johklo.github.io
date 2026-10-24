import ast
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "content" / "docs" / "tech" / "ai-agents-and-applications"


def blocks(chapter):
    source = next(SOURCE.glob(f"{chapter:02d}-*.md")).read_text(encoding="utf-8")
    return re.findall(r"```python\n(.*?)\n```", source, re.S)


class PublishedExamplesTest(unittest.TestCase):
    def test_all_chapter_examples_are_complete_python(self):
        for chapter in range(1, 15):
            examples = blocks(chapter)
            with self.subTest(chapter=chapter):
                self.assertEqual(len(examples), 2 if chapter == 13 else 1)
                for code in examples:
                    ast.parse(code)

    @unittest.skipUnless(
        importlib.util.find_spec("langgraph"), "Study LangGraph dependencies required"
    )
    def test_control_flow_and_approval_examples_execute(self):
        for chapter in (5, 14):
            with self.subTest(chapter=chapter), tempfile.TemporaryDirectory(
                prefix=".agent-study-test-", dir=ROOT
            ) as directory:
                script = Path(directory) / "study.py"
                script.write_text(blocks(chapter)[0], encoding="utf-8")
                result = subprocess.run(
                    [sys.executable, str(script)], cwd=directory,
                    env={**os.environ, "LANGSMITH_TRACING": "false"},
                    capture_output=True, text=True, encoding="utf-8", timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                if chapter == 5:
                    self.assertIn("2 insufficient_evidence", result.stdout)
                else:
                    self.assertIn("rejected-study rejected queued: False", result.stdout)
