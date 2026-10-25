"""Publish the executable lab guides beneath the MLOps lab overview."""

import argparse
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "https://github.com/johklo/ml-platform-engineering-labs"
DATE = "2026-10-24T15:00:00+09:00"


def slug(stem):
    return f"ml-platform-labs-{stem}"


def render_guide(source, guides):
    text = source.read_text(encoding="utf-8")
    title, separator, body = text.partition("\n")
    if not separator or not title.startswith("# "):
        raise ValueError(f"Expected an H1 title in {source}")
    title = title[2:].strip()

    def replace_link(match):
        label, target = match.group(1), match.group(2)
        if target == "../README.md":
            target = "../"
        elif "://" not in target and not target.startswith(("#", "/")):
            filename, anchor_mark, anchor = target.partition("#")
            path = (source.parent / filename).resolve()
            if path in guides:
                target = f"../{slug(path.stem)}/"
                if anchor_mark:
                    target += f"#{anchor}"
            else:
                target = f"{REPOSITORY}/blob/main/{filename.lstrip('./')}"
        return f"[{label}]({target})"

    body = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", replace_link, body)
    return (
        "---\n"
        f'title: "ML 플랫폼 실습 {title}"\n'
        f'description: "{title} 실행 절차, 결과 확인과 실패 실험"\n'
        f"date: {DATE}\nlastmod: {DATE}\n"
        f"weight: {110 + int(source.stem[:2]) * 10}\n"
        f'aliases: ["/docs/tech/{slug(source.stem)}/", '
        f'"/docs/tech/ml-platform-engineering-labs/{slug(source.stem)}/"]\n'
        'tags: ["ml-platform-labs", "mlops", "hands-on"]\n'
        "---\n\n"
        f"{body}"
        f"\n\n실행 코드는 [실습 저장소]({REPOSITORY})에서 내려받습니다. "
        f"[원본 가이드]({REPOSITORY}/blob/main/docs/{source.name})\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path,
        default=ROOT / ".lab-work" / "ml-platform-engineering-labs" / "docs",
    )
    args = parser.parse_args()
    sources = sorted(args.source.glob("[0-9][0-9]-*.md"))
    if not sources:
        parser.error("No numbered lab guides found.")
    guides = {path.resolve() for path in sources}
    for source in sources:
        target = (
            ROOT / "content" / "docs" / "tech" / "ops" / "mlops" / "labs"
            / f"{slug(source.stem)}.md"
        )
        target.write_text(render_guide(source, guides), encoding="utf-8")
    print(f"Published {len(sources)} guides beneath the integrated lab overview.")


if __name__ == "__main__":
    main()
