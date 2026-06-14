#!/bin/bash
set -e
cd "$(dirname "$0")"

clear
echo "===================================================="
echo " Captions DE — Installer for macOS"
echo "===================================================="
echo ""
echo "This will install:"
echo "  • Homebrew (if missing)"
echo "  • Python 3 and ffmpeg"
echo "  • WhisperX (German speech-to-text, ~3 GB)"
echo ""
echo "Press Enter to continue, or Ctrl+C to cancel."
read

# 1. Homebrew
if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
elif [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
fi

if ! command -v brew >/dev/null 2>&1; then
    echo ""
    echo ">> Installing Homebrew. You may be asked for your password."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    if [ -x /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [ -x /usr/local/bin/brew ]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi
fi

# 2. Python and ffmpeg
echo ""
echo ">> Installing Python and ffmpeg..."
brew install python ffmpeg || true

# 2b. If an existing ~/whisperx venv has the wrong arch (e.g. x86_64 under
#     Rosetta on an arm64 Mac), wipe it so we can rebuild cleanly.
SYS_ARCH="$(uname -m)"
if [ -x "$HOME/whisperx/bin/python" ]; then
    VENV_ARCH="$(file "$HOME/whisperx/bin/python" 2>/dev/null \
        | grep -oE 'arm64|x86_64' | head -n1)"
    if [ -n "$VENV_ARCH" ] && [ "$VENV_ARCH" != "$SYS_ARCH" ]; then
        echo ""
        echo ">> Existing ~/whisperx is $VENV_ARCH but this Mac is $SYS_ARCH."
        echo "   Removing it so it can be rebuilt for the right architecture..."
        rm -rf "$HOME/whisperx"
    fi
fi

# 3. Create venv and install whisperx — force a native-arch Python.
echo ""
echo ">> Setting up Python environment for WhisperX..."
PYBIN=""
for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$candidate" >/dev/null 2>&1 || [ -x "$candidate" ]; then
        PYBIN="$candidate"; break
    fi
done
[ -z "$PYBIN" ] && PYBIN=python3
echo "   Using $PYBIN  ($("$PYBIN" --version 2>&1))"
"$PYBIN" install.py

# 4. Ask for the Gemini API key
echo ""
echo "===================================================="
echo " Gemini API key (free)"
echo "===================================================="
echo ""
echo "Open this link in your browser:"
echo "  https://aistudio.google.com/apikey"
echo ""
echo "Sign in with a Google account, click 'Create API key',"
echo "and copy the key."
echo ""
read -p "Paste your key here (or press Enter to skip): " key

if [ -n "$key" ]; then
    echo "GEMINI_API_KEY=$key" > .env
    echo "✓ Key saved to .env"
else
    echo "Skipped. You can add it later by editing .env"
    [ ! -f .env ] && cp .env.example .env
fi

echo ""
echo "===================================================="
echo " ✓ Done!"
echo "===================================================="
echo ""
echo "To create captions for a video:"
echo "  • Double-click 'caption.command' and choose your video"
echo ""
echo "The .srt file appears next to your video."
echo ""
read -p "Press Enter to close this window..."
