import argparse
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "content" / "docs" / "tech" / "ai-agents-and-applications"


def main():
    parser = argparse.ArgumentParser(
        description="Run the Python examples extracted from the AI Agents articles."
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chapters", type=int, nargs="+", default=range(1, 15))
    args = parser.parse_args()
    work = args.output.resolve()
    if not work.is_relative_to(ROOT) or work == ROOT:
        parser.error("Output must be a new directory inside this repository")
    work.mkdir(parents=True, exist_ok=False)
    environment = {**os.environ, "LANGSMITH_TRACING": "false", "PYTHONUTF8": "1"}
    failures = []
    for chapter in args.chapters:
        if not 1 <= chapter <= 14:
            parser.error("Chapter must be between 1 and 14")
        article = next(SOURCE.glob(f"{chapter:02d}-*.md"))
        blocks = re.findall(
            r"```python\n(.*?)\n```", article.read_text(encoding="utf-8"), re.S
        )
        names = (
            ["ch13_server.py", "ch13.py"] if chapter == 13
            else [f"ch{chapter:02d}.py"]
        )
        if len(blocks) != len(names):
            raise ValueError(f"Unexpected Python blocks in {article.name}")
        for name, code in zip(names, blocks):
            (work / name).write_text(code, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, names[-1]], cwd=work, env=environment,
            capture_output=True, text=True, encoding="utf-8", timeout=300,
        )
        (work / f"ch{chapter:02d}.stdout.txt").write_text(
            result.stdout, encoding="utf-8"
        )
        (work / f"ch{chapter:02d}.stderr.txt").write_text(
            result.stderr, encoding="utf-8"
        )
        print(f"Chapter {chapter}: {'passed' if result.returncode == 0 else 'FAILED'}")
        print(result.stdout[-2500:], flush=True)
        if result.returncode:
            failures.append(chapter)
            print(result.stderr[-3500:], file=sys.stderr, flush=True)
    if failures:
        raise RuntimeError(f"Failed chapters: {failures}")


if __name__ == "__main__":
    main()
