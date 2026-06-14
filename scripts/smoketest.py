#!/usr/bin/env python3
"""Headless smoke test: construct and show MainWindow offscreen, then quit.

Catches import errors, missing names, and crashes during widget construction —
without needing a display. Used after each refactor step to confirm the app
still launches.

    QT_QPA_PLATFORM=offscreen ./venv/bin/python scripts/smoketest.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# The app modules live in src/; put it on the path so they import cleanly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import studio  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
window = studio.MainWindow()
window.show()
QTimer.singleShot(1200, app.quit)
app.exec()
print("BOOT OK — MainWindow constructed and shown")
