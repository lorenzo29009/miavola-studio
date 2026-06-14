#!/bin/bash
set -e
cd "$(dirname "$0")"

clear
echo "===================================================="
echo " Flow Cropper — Installer for macOS"
echo "===================================================="
echo ""
echo "This will install:"
echo "  • Homebrew (if missing)"
echo "  • ffmpeg (video crop engine)"
echo ""
echo "Press Enter to continue, or Ctrl+C to cancel."
read

if ! command -v brew &> /dev/null; then
    echo ""
    echo ">> Installing Homebrew. You may be asked for your Mac password."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    if [ -x /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
fi

if ! command -v ffmpeg &> /dev/null; then
    echo ""
    echo ">> Installing ffmpeg..."
    brew install ffmpeg
else
    echo ""
    echo ">> ffmpeg is already installed."
fi

# Python 3 ships with macOS, no install needed.

echo ""
echo "===================================================="
echo " ✓ Done!"
echo "===================================================="
echo ""
echo "To crop a campaign:"
echo "  • Double-click 'crop.command'"
echo ""
read -p "Press Enter to close this window..."
