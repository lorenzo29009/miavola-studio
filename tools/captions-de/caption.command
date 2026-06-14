#!/bin/bash
cd "$(dirname "$0")"

VIDEO="$1"

if [ -z "$VIDEO" ]; then
    VIDEO=$(osascript <<'AS' 2>/dev/null
try
    POSIX path of (choose file with prompt "Choose a video file to caption:" of type {"public.movie","public.video","public.audio"})
on error
    ""
end try
AS
)
fi

if [ -z "$VIDEO" ]; then
    echo ""
    echo "No file selected. Exiting."
    sleep 2
    exit 0
fi

NAME=$(basename "$VIDEO")

clear
echo "===================================================="
echo " Captions DE"
echo "===================================================="
echo ""
echo "Processing:  $NAME"
echo ""

if [ ! -x "$HOME/whisperx/bin/python" ]; then
    echo "✗ WhisperX is not installed yet."
    echo "  Run install-mac.command first."
    echo ""
    read -p "Press Enter to close..."
    exit 1
fi

"$HOME/whisperx/bin/python" caption.py "$VIDEO"

echo ""
echo "===================================================="
echo " ✓ Done!"
echo "===================================================="
echo ""
echo "Your .srt file is next to the video:"
echo "  $(dirname "$VIDEO")"
echo ""
read -p "Press Enter to close..."
