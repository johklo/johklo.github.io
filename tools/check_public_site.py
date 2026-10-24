import re
import subprocess
import sys


def unexpected_static_files(paths):
    allowed = re.compile(
        r"static/(?:robots\.txt|google[0-9a-f]+\.html|"
        r"downloads/ml-platform-engineering/kfp-cluster/"
        r"(?:Dockerfile|submit_cluster\.py|object-store-patch\.yaml|executor-patch\.yaml)|"
        r"images/(?:\.gitkeep|.+\.(?:avif|gif|ico|jpeg|jpg|png|svg|webp)))"
    )
    return [
        path
        for path in paths
        if (path.startswith("static/") and not allowed.fullmatch(path))
        or path.startswith(("notes/", "s/"))
    ]


def main():
    result = subprocess.run(
        ["git", "ls-files", "-z"], check=True, capture_output=True
    )
    paths = result.stdout.decode("utf-8").split("\0")
    if unexpected_static_files(paths):
        print(
            "Public file check failed: unapproved application or data files. "
            "Keep private files outside this repository.",
            file=sys.stderr,
        )
        return 1
    print("Public file check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
