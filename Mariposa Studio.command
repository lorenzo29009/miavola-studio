#!/bin/bash
cd "$(dirname "$0")"
STUDIO_DIR="$(pwd)"

if [ ! -x "./venv/bin/python" ]; then
    clear
    echo "===================================================="
    echo " Mariposa Studio is not installed yet."
    echo "===================================================="
    echo ""
    echo " Right-click  install-mac.command  →  Open"
    echo " (the first time, so macOS lets you run it)"
    echo ""
    read -p "Press Enter to close..."
    exit 1
fi

# Run the app without keeping the terminal window around. Absolute paths so the
# interpreter never needs getcwd() (which fails under some Finder/iCloud launch
# contexts and crashes CPython's getpath before any app code runs).
exec "$STUDIO_DIR/venv/bin/python" "$STUDIO_DIR/src/studio.py"
