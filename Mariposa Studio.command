#!/bin/bash
cd "$(dirname "$0")"

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

# Run the app without keeping the terminal window around.
exec ./venv/bin/python src/studio.py
