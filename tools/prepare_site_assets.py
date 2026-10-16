import argparse
import base64
import json
from pathlib import Path
import shutil


ROOT_FILES = {
    ".nojekyll", "favicon.svg", "icons.svg", "index.html",
    "manifest.webmanifest", "robots.txt", "sw.js", "vault.enc", "vault.meta.json",
}
ASSET_SUFFIXES = {".css", ".js", ".otf", ".svg", ".ttf", ".txt", ".woff", ".woff2"}


def prepare_assets(source, destination):
    source, destination = Path(source), Path(destination)
    if source.is_symlink() or not source.is_dir():
        raise ValueError("Site asset source must be a regular directory.")
    for entry in source.rglob("*"):
        relative = entry.relative_to(source)
        if entry.is_symlink():
            raise ValueError("Site assets cannot contain symbolic links.")
        if entry.is_dir():
            if relative.parts[0] not in {"assets", "licenses"}:
                raise ValueError("Site assets contain an unapproved directory.")
        elif len(relative.parts) == 1:
            if relative.name not in ROOT_FILES:
                raise ValueError("Site assets contain an unapproved file.")
        elif relative.parts[0] == "assets":
            if entry.suffix.lower() not in ASSET_SUFFIXES:
                raise ValueError("Site assets contain an unapproved asset type.")
        elif relative.parts[0] != "licenses" or entry.suffix.lower() != ".txt":
            raise ValueError("Site assets contain an unapproved file.")

    for name in ("index.html", "vault.enc", "vault.meta.json"):
        if not (source / name).is_file():
            raise ValueError("Site assets are missing required application files.")
    metadata = json.loads((source / "vault.meta.json").read_text(encoding="utf-8"))
    if (
        metadata.get("algorithm") != "AES-256-GCM / PBKDF2-SHA256"
        or not isinstance(metadata.get("iterations"), int)
        or metadata["iterations"] < 310000
        or len(base64.b64decode(metadata.get("salt", ""), validate=True)) != 16
        or len(base64.b64decode(metadata.get("iv", ""), validate=True)) != 12
        or (source / "vault.enc").stat().st_size <= 16
    ):
        raise ValueError("Site asset encryption metadata is invalid.")
    shutil.copytree(source, destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    prepare_assets(args.source, args.destination)
    print("Site assets prepared.")
