#!/usr/bin/env python3
"""Build the distributable release zip for Mariposa Studio.

Run on the DEV machine (a git checkout) to produce the artifact you attach to a
GitHub Release and that the in-app updater downloads:

    ./venv/bin/python scripts/make_release_zip.py
    -> dist/Mariposa-Studio-v<VERSION>.zip

It uses `git archive` so the zip contains exactly the tracked files at the top
level (no wrapper directory) — venv/, exports/ and .env are gitignored and so
are correctly excluded. The layout matches what updater._extract_root expects.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def main() -> None:
    if subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                      cwd=ROOT, capture_output=True).returncode != 0:
        sys.exit("Not a git checkout — run this from the development repo.")

    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    out = dist / f"Mariposa-Studio-v{VERSION}.zip"

    print(f"Building {out.name} from HEAD…")
    subprocess.run(
        ["git", "archive", "--format=zip", "-o", str(out), "HEAD"],
        cwd=ROOT, check=True,
    )

    print(f"OK: {out}")
    print()
    print("Next:")
    print(f"  1. git tag v{VERSION} && git push --tags")
    print(f"  2. Create a GitHub Release for tag v{VERSION}")
    print(f"  3. Attach {out.name} as a release asset")
    print("The app will offer this version to anyone on an older VERSION.")


if __name__ == "__main__":
    main()
