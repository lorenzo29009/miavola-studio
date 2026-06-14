#!/usr/bin/env python3
"""
Cross-platform installer for the caption tool.

Run once on a fresh machine:
    python install.py

This will:
  1. Verify Python >= 3.9 and ffmpeg are installed
  2. Create a virtualenv in ~/whisperx
  3. Install WhisperX and dependencies into the venv
  4. Print next steps (Gemini API key setup)
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def section(title):
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def check_python():
    # WhisperX's pinned ctranslate2/torch ship wheels for 3.10–3.12 only; 3.13+
    # fails with a cryptic "no matching distribution". Fail fast and clearly.
    v = sys.version_info[:2]
    if not ((3, 10) <= v < (3, 13)):
        sys.exit(
            f"WhisperX needs Python 3.10–3.12 (you have {sys.version.split()[0]}). "
            "Run the Studio installer, which selects a compatible Python for you."
        )
    print(f"OK: Python {sys.version.split()[0]}")


def check_ffmpeg():
    if shutil.which("ffmpeg"):
        print("OK: ffmpeg found on PATH")
        return
    print("ERROR: ffmpeg not found on PATH.")
    system = platform.system()
    if system == "Darwin":
        print("Install with Homebrew:")
        print("  /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
        print("  brew install ffmpeg")
    elif system == "Windows":
        print("Install via winget (PowerShell):")
        print("  winget install Gyan.FFmpeg")
        print("Or download from: https://www.gyan.dev/ffmpeg/builds/")
        print("Add the bin/ folder to your PATH, restart your terminal.")
    else:
        print("Install via your package manager, e.g.:")
        print("  sudo apt install ffmpeg")
    sys.exit(1)


def _venv_py_version(venv_path: Path) -> str:
    try:
        out = subprocess.run(
            [str(venv_python(venv_path)), "-c",
             "import sys;print('%d.%d'%sys.version_info[:2])"],
            capture_output=True, text=True,
        )
        return out.stdout.strip()
    except Exception:
        return ""


def make_venv():
    venv_path = Path.home() / "whisperx"
    if venv_path.exists():
        ver = _venv_py_version(venv_path)
        if ver in ("3.10", "3.11", "3.12"):
            print(f"OK: venv already exists at {venv_path} (Python {ver})")
            return venv_path
        # A leftover venv on the wrong Python (e.g. a failed 3.13/3.14 run) would
        # just fail again — rebuild it with the compatible interpreter.
        print(f"Existing {venv_path} uses Python {ver or '?'} "
              "(WhisperX needs 3.10–3.12) — recreating it...")
        shutil.rmtree(venv_path, ignore_errors=True)
    print(f"Creating venv at {venv_path}...")
    subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
    return venv_path


def venv_python(venv_path: Path) -> Path:
    if platform.system() == "Windows":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def install_whisperx(venv_path: Path):
    py = venv_python(venv_path)
    print("Upgrading pip...")
    subprocess.run([str(py), "-m", "pip", "install", "--upgrade", "pip"], check=True)
    print("Installing whisperx (this takes a few minutes the first time)...")
    subprocess.run([str(py), "-m", "pip", "install", "whisperx"], check=True)
    print("OK: WhisperX installed.")


def write_env_example():
    here = Path(__file__).resolve().parent
    env_example = here / ".env.example"
    if not env_example.exists():
        env_example.write_text(
            "# Get a free Gemini API key at https://aistudio.google.com/apikey\n"
            "# Then copy this file to .env and fill in the key.\n"
            "GEMINI_API_KEY=\n"
        )
    print(f"OK: API key template at {env_example}")


def main():
    section("Caption tool setup")
    check_python()
    check_ffmpeg()
    venv_path = make_venv()
    install_whisperx(venv_path)
    write_env_example()

    section("Next steps")
    print("1. Get a free Gemini API key: https://aistudio.google.com/apikey")
    print("2. Set it in your shell:")
    if platform.system() == "Windows":
        print('     setx GEMINI_API_KEY "your-key-here"   (then restart terminal)')
    else:
        print('     export GEMINI_API_KEY="your-key-here"   (add to ~/.zshrc or ~/.bashrc)')
    print("3. Run on a video:")
    print("     python caption.py path/to/video.mp4")
    print()
    print("First run downloads ~3GB of Whisper models. Be patient.")


if __name__ == "__main__":
    main()
