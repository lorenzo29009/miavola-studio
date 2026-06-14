#!/bin/bash
cd "$(dirname "$0")"

clear
echo "===================================================="
echo " Flow Cropper — 9:16 → 4:5"
echo "===================================================="
echo ""

if ! command -v python3 &> /dev/null; then
    echo "✗ Python 3 not found. Install it with:"
    echo "    brew install python"
    echo ""
    read -p "Press Enter to close..."
    exit 1
fi

python3 crop.py

echo ""
read -p "Press Enter to close..."
