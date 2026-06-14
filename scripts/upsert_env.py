#!/usr/bin/env python3
"""Upsert a KEY=VALUE into tools/captions-de/.env, preserving every other line.

Used by both installers (install-mac.command / install-windows.bat) so the
Gemini key is collected once, at the top level, and lands in the single .env
that Captions, Camera Prompts and the Animator all read.

    python scripts/upsert_env.py GEMINI_API_KEY YOUR_KEY

If the .env doesn't exist yet it's seeded from .env.example so the optional
CAPTION_BRAND / CAPTION_TERMS template lines and their comments survive.
"""

from __future__ import annotations

import sys
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / "tools" / "captions-de" / ".env"
ENV_EXAMPLE = ENV_PATH.with_name(".env.example")


def upsert(key: str, value: str) -> None:
    if not ENV_PATH.exists() and ENV_EXAMPLE.exists():
        ENV_PATH.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")

    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    out, found = [], False
    for line in lines:
        if line.lstrip().startswith(f"{key}="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}")

    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit("usage: upsert_env.py KEY VALUE")
    upsert(sys.argv[1], sys.argv[2])
    print(f"OK: {sys.argv[1]} written to {ENV_PATH}")


if __name__ == "__main__":
    main()
