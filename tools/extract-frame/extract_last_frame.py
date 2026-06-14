#!/usr/bin/env python3
"""Extract frames from a video.

Usage:
    extract_last_frame.py VIDEO MODE VALUE OUT_DIR [SUBFOLDER]

MODE     meaning of VALUE
-----    ------------------------------------------
last     number of last frames to grab
first    number of first frames to grab
random   number of random frames to grab
every    interval in seconds between grabs (float)

If SUBFOLDER is given it is used verbatim. Otherwise a unique
'<stem>_frames_<hex>' folder is created under OUT_DIR.
"""
import cv2
import uuid
import sys
import random
from pathlib import Path


def extract(video_path: str, mode: str, value: str,
            out_dir: Path, subfolder: str = "") -> None:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError("Cannot open video file.")

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total < 1:
        raise ValueError("Video has no frames.")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    if mode == "last":
        n = max(1, min(int(value), total))
        indices = [total - n + i for i in range(n)]
    elif mode == "first":
        n = max(1, min(int(value), total))
        indices = list(range(n))
    elif mode == "random":
        n = max(1, min(int(value), total))
        indices = sorted(random.sample(range(total), n))
    elif mode == "every":
        interval = float(value)
        if interval <= 0:
            raise ValueError("Interval must be > 0 seconds.")
        step = max(1, int(round(fps * interval)))
        indices = list(range(0, total, step))
    else:
        raise ValueError(f"Unknown mode: {mode}")

    if not subfolder:
        subfolder = Path(video_path).stem + "_frames_" + uuid.uuid4().hex[:6]
    result_dir = out_dir / subfolder
    result_dir.mkdir(parents=True, exist_ok=True)

    stem = Path(video_path).stem.replace(" ", "_")
    written = 0
    for i, idx in enumerate(indices):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue
        tcode = idx / fps if fps else 0
        mm = int(tcode // 60); ss = int(tcode % 60); ms = int((tcode - int(tcode)) * 1000)
        if mode in ("random", "every"):
            label = f"{i+1:02d}_t{mm:02d}m{ss:02d}s{ms:03d}_frame{idx:06d}"
        elif mode == "first":
            label = f"{stem}_first_{i+1:02d}"
        else:  # last
            label = f"{stem}_last_{i+1:02d}"
        cv2.imwrite(str(result_dir / f"{label}.png"), frame)
        written += 1

    cap.release()
    print(f"Wrote {written} frame(s) to:")
    print(str(result_dir))


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) not in (4, 5):
        print("Usage: extract_last_frame.py VIDEO MODE VALUE OUT_DIR [SUBFOLDER]")
        sys.exit(1)
    try:
        sub = args[4] if len(args) == 5 else ""
        extract(args[0], args[1], args[2], Path(args[3]), subfolder=sub)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
