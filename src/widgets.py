#!/usr/bin/env python3
"""Reusable UI widgets for Mariposa Studio (cards, drop zones, controls,
console view, app bar). Shared by every page."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import (Qt, Signal, QPointF)
from PySide6.QtGui import (QFont, QColor, QPainter, QPixmap, QImage)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QFileDialog, QPlainTextEdit, QFrame, QGraphicsDropShadowEffect, QButtonGroup,
)

from design import (
    INK_PANEL, INK_BORDER2, TXT_HI, TXT_DIM, TXT_FAINT, IRIS, IRIS_FG,
    TOOL_ACCENTS, SHADOW_CARD, svg_icon,
    svg_pixmap,
)

# ---------------------------------------------------------------------------
# Reusable widgets

class Card(QFrame):
    """A rounded card with a soft shadow."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        sh = QGraphicsDropShadowEffect()
        sh.setBlurRadius(SHADOW_CARD["blur"])
        sh.setColor(QColor(*SHADOW_CARD["color"]))
        sh.setOffset(0, SHADOW_CARD["y"])
        self.setGraphicsEffect(sh)


class FormRow(QWidget):
    """A label + field laid out cleanly. setVisible hides cleanly."""
    def __init__(self, label: str, field: QWidget, label_width: int = 130):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        self._label = QLabel(label)
        self._label.setObjectName("FieldLabel")
        self._label.setFixedWidth(label_width)
        self._label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.field = field
        lay.addWidget(self._label)
        lay.addWidget(field, 1)


_VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm")


def _video_thumb_and_meta(path: Path):
    """Best-effort first-frame thumbnail (QPixmap) + 'meta' string for a video,
    using OpenCV (already a dependency). Returns (pixmap|None, meta|None)."""
    try:
        import cv2
        cap = cv2.VideoCapture(str(path))
        ok, frame = cap.read()
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        cap.release()
        meta = None
        if w and h:
            meta = f"{w}×{h}"
            if fps and n:
                secs = int(n / fps)
                meta += f"  ·  {secs // 60}:{secs % 60:02d}"
        if not ok:
            return None, meta
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        fh, fw, _ = frame.shape
        img = QImage(frame.data, fw, fh, 3 * fw, QImage.Format_RGB888).copy()
        return QPixmap.fromImage(img), meta
    except Exception:
        return None, None


class DropZone(QFrame):
    """The primary input of a tool: a generous drop target that shows a live
    thumbnail + metadata once filled. Keeps PathPicker's value()/changed API so
    tool logic is untouched."""
    changed = Signal(str)

    def __init__(self, prompt: str, *, is_folder: bool = False,
                 file_filter: str = "All files (*)", media: bool = False):
        super().__init__()
        self.setObjectName("DropZone")
        self.is_folder = is_folder
        self.file_filter = file_filter
        self.media = media
        self._path = ""
        self._prompt = prompt
        self.setProperty("filled", False)
        self.setCursor(Qt.PointingHandCursor)
        self.setAcceptDrops(True)
        self.setFixedHeight(96)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(14)

        self.thumb = QLabel()
        self.thumb.setObjectName("DropThumb")
        self.thumb.setFixedSize(70, 70)
        self.thumb.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.thumb)

        col = QVBoxLayout(); col.setSpacing(3); col.setContentsMargins(0, 0, 0, 0)
        col.addStretch(1)
        self.title = QLabel(prompt); self.title.setObjectName("DropTitle")
        self.meta = QLabel("Drop it here, or click to browse"); self.meta.setObjectName("DropMeta")
        col.addWidget(self.title); col.addWidget(self.meta)
        col.addStretch(1)
        lay.addLayout(col, 1)

        self.action = QPushButton("Browse")
        self.action.setObjectName("GhostBtn")
        self.action.setCursor(Qt.PointingHandCursor)
        self.action.setIcon(svg_icon("folder-open" if is_folder else "folder", TXT_DIM, 14))
        self.action.clicked.connect(self._pick)
        lay.addWidget(self.action)
        for w in (self.thumb, self.title, self.meta):
            w.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._render_empty()

    # ---- visuals ----
    def _render_empty(self):
        self.thumb.setPixmap(svg_pixmap("folder" if self.is_folder else "file-video", TXT_FAINT, 26))
        self.thumb.setStyleSheet(f"background: {INK_PANEL}; border-radius: 12px;")
        self.title.setText(self._prompt)
        self.title.setStyleSheet("")  # falls back to #DropTitle (dim)
        self.meta.setText("Drop it here, or click to browse")

    def _render_filled(self, p: Path):
        name = p.name
        self.title.setText(name)
        self.title.setStyleSheet(f"color: {TXT_HI};")
        pm, meta = (None, None)
        if self.is_folder:
            try:
                clips = [f for f in p.iterdir() if f.suffix.lower() in _VIDEO_EXTS]
                meta = f"{len(clips)} clip" + ("" if len(clips) == 1 else "s")
            except Exception:
                meta = str(p)
        elif self.media:
            pm, meta = _video_thumb_and_meta(p)
        if pm and not pm.isNull():
            scaled = pm.scaled(70, 70, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            # center-crop to 70×70
            x = max(0, (scaled.width() - 70) // 2); y = max(0, (scaled.height() - 70) // 2)
            self.thumb.setPixmap(scaled.copy(x, y, 70, 70))
            self.thumb.setStyleSheet("border-radius: 12px;")
        else:
            self.thumb.setPixmap(svg_pixmap("folder-open" if self.is_folder else "film",
                                            TOOL_ACCENTS.get(getattr(self, '_hue_key', ''), IRIS), 26))
            self.thumb.setStyleSheet(f"background: {INK_PANEL}; border-radius: 12px;")
        self.meta.setText(meta or str(p))
        self.action.setText("Change")

    # ---- drag & drop ----
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            self.setProperty("hover", True); self._restyle(); e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.setProperty("hover", False); self._restyle()

    def dropEvent(self, e):
        self.setProperty("hover", False); self._restyle()
        for url in e.mimeData().urls():
            p = Path(url.toLocalFile())
            if not p.exists():
                continue
            self.set_value(str(p if not (self.is_folder and p.is_file()) else p.parent))
            e.acceptProposedAction()
            return

    def _restyle(self):
        self.style().unpolish(self); self.style().polish(self)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._pick()
        super().mouseReleaseEvent(e)

    def _pick(self):
        start = self._path or str(Path.home() / "Desktop")
        if self.is_folder:
            p = QFileDialog.getExistingDirectory(self, "Choose a folder", start)
        else:
            p, _ = QFileDialog.getOpenFileName(self, "Choose a file", start, self.file_filter)
        if p:
            self.set_value(p)

    # ---- value API (compatible with PathPicker) ----
    def value(self) -> str:
        return self._path.strip()

    def set_value(self, v: str):
        self._path = v or ""
        if self._path:
            self.setProperty("filled", True); self._restyle()
            self._render_filled(Path(self._path))
        else:
            self.setProperty("filled", False); self._restyle()
            self._render_empty()
        self.changed.emit(self._path)


class Segmented(QFrame):
    """A horizontal segmented control (exclusive). Mirrors the ModeToggle look."""
    currentChanged = Signal(int)

    def __init__(self, options: list[str], icons: Optional[list[str]] = None):
        super().__init__()
        self.setObjectName("ModeToggle")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)   # free-floating pill chips, not a fused segment bar
        self._options = list(options)
        self._icons = list(icons) if icons else None
        self._group = QButtonGroup(self); self._group.setExclusive(True)
        self._buttons: list[QPushButton] = []
        for i, label in enumerate(options):
            b = QPushButton(("  " + label) if icons else label)
            b.setObjectName("ModeBtn"); b.setCheckable(True); b.setCursor(Qt.PointingHandCursor)
            self._group.addButton(b, i)
            self._buttons.append(b)
            lay.addWidget(b)
        self._buttons[0].setChecked(True)
        self._group.idClicked.connect(self.currentChanged.emit)
        # Keep the icon color in step with the text: white on the checked
        # (green) pill, dim otherwise.
        self._group.idClicked.connect(self._refresh_icons)
        self._refresh_icons()

    def _refresh_icons(self, *_):
        if not self._icons:
            return
        for i, b in enumerate(self._buttons):
            name = self._icons[i] if i < len(self._icons) else None
            if name:
                b.setIcon(svg_icon(name, IRIS_FG if b.isChecked() else TXT_DIM, 14))

    def currentIndex(self) -> int:
        return self._group.checkedId()

    def currentText(self) -> str:
        return self._options[self.currentIndex()]

    def setCurrentIndex(self, i: int):
        if 0 <= i < len(self._buttons):
            self._buttons[i].setChecked(True)
            self._refresh_icons()

    def setCurrentText(self, t: str):
        if t in self._options:
            self.setCurrentIndex(self._options.index(t))


class Field(QWidget):
    """A label-on-top field — denser and more modern than a left-label row,
    and it tiles cleanly into 2-column grids."""
    def __init__(self, label: str, widget: QWidget):
        super().__init__()
        self.setObjectName("TransparentPanel")
        self.setStyleSheet("QWidget#TransparentPanel { background: transparent; }")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(5)
        lbl = QLabel(label)
        lbl.setObjectName("FieldLabel")
        v.addWidget(lbl)
        v.addWidget(widget)
        self.widget = widget


def _panel(layout) -> QWidget:
    """A transparent container so layouts inside Cards don't paint the canvas
    background. The selector scopes the rule to the container itself — an
    unscoped `background: transparent` would cascade to every descendant and
    kill styled fills (e.g. the checked pill's green)."""
    w = QWidget()
    w.setObjectName("TransparentPanel")
    w.setStyleSheet("QWidget#TransparentPanel { background: transparent; }")
    w.setLayout(layout)
    return w


class ChipGroup(QWidget):
    """An editable value with quick-fill preset chips (for counts / intervals)."""
    def __init__(self, presets: list[str], default: str = ""):
        super().__init__()
        lay = QHBoxLayout(self)
        # A little vertical breathing room (and centre alignment) so the round
        # 36px preset pills never get their bottom edge clipped by sub-pixel
        # rounding on Retina displays.
        lay.setContentsMargins(0, 3, 0, 3); lay.setSpacing(8)
        lay.setAlignment(Qt.AlignVCenter)
        self.setMinimumHeight(42)
        self.edit = QLineEdit(); self.edit.setFixedWidth(84); self.edit.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.edit)
        self._chips_box = QHBoxLayout(); self._chips_box.setSpacing(6)
        lay.addLayout(self._chips_box); lay.addStretch(1)
        self._chips: list[QPushButton] = []
        self.set_presets(presets, default)
        self.edit.textEdited.connect(self._sync_chips)

    def set_presets(self, presets: list[str], default: str = ""):
        for b in self._chips:
            self._chips_box.removeWidget(b)
            b.setParent(None)
            b.deleteLater()
        self._chips = []
        for v in presets:
            b = QPushButton(v); b.setObjectName("PillBtn"); b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor); b.setFixedHeight(36)
            b.clicked.connect(lambda _=False, val=v: self._choose(val))
            self._chips_box.addWidget(b); self._chips.append(b)
        self.edit.setText(default or (presets[0] if presets else ""))
        self._sync_chips()

    def _choose(self, v: str):
        self.edit.setText(v); self._sync_chips()

    def _sync_chips(self, *_):
        cur = self.edit.text().strip()
        for b in self._chips:
            b.setChecked(b.text() == cur)

    def currentText(self) -> str:
        return self.edit.text().strip()

    value = currentText


class Switch(QWidget):
    """A painted on/off toggle."""
    toggled = Signal(bool)

    def __init__(self, checked: bool = False, hue: str = IRIS):
        super().__init__()
        self._on = checked
        self._hue = QColor(hue)
        self.setFixedSize(52, 30)
        self.setCursor(Qt.PointingHandCursor)

    def isChecked(self) -> bool:
        return self._on

    def setChecked(self, v: bool):
        self._on = bool(v); self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._on = not self._on
            self.update(); self.toggled.emit(self._on)
        super().mouseReleaseEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        track = QColor(self._hue) if self._on else QColor(INK_BORDER2)
        p.setBrush(track); p.setPen(Qt.NoPen)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = r.right() - d - 3 if self._on else r.left() + 3
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QPointF(x + d / 2, r.center().y() + 0.5), d / 2, d / 2)
        p.end()


class ConsoleView(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setObjectName("Console")
        f = QFont("SF Mono", 11)
        if not f.exactMatch():
            f = QFont("Menlo", 11)
        self.setFont(f)
        self.setPlaceholderText("Output appears here…")

    def append_line(self, s: str, *, color: Optional[str] = None):
        s = s.rstrip()
        if not s:
            return
        if color:
            self.appendHtml(f'<span style="color:{color}">{self._escape(s)}</span>')
        else:
            self.appendPlainText(s)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    @staticmethod
    def _escape(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# OS app bar — shared by every tool "app" (Home button + per-app accent + title)

class AppBar(QFrame):
    """The top chrome of an opened app: a Home button, the app's accent dot, the
    title, and a right-hand slot for actions. Used by every tool screen."""
    def __init__(self, title: str, tool_key: str, on_home: Callable[[], None]):
        super().__init__()
        self.setObjectName("AppBar")
        self.setFixedHeight(64)   # fits the 44px primary action comfortably
        hue = TOOL_ACCENTS.get(tool_key, IRIS)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(12)

        self.home_btn = QPushButton("  Home")
        self.home_btn.setObjectName("HomeBtn")
        self.home_btn.setIcon(svg_icon("house", TXT_HI, 15))
        self.home_btn.setCursor(Qt.PointingHandCursor)
        self.home_btn.setToolTip("Back to Home  (Esc)")
        self.home_btn.clicked.connect(lambda: on_home())
        lay.addWidget(self.home_btn)

        dot = QLabel()
        dot.setFixedSize(9, 9)
        dot.setStyleSheet(f"background: {hue}; border-radius: 4px;")
        lay.addSpacing(4)
        lay.addWidget(dot)

        ttl = QLabel(title)
        ttl.setObjectName("AppTitle")
        lay.addWidget(ttl)
        lay.addStretch(1)
        self._lay = lay

    def add_right(self, w: QWidget):
        self._lay.addWidget(w)


__all__ = [
    "Card", "FormRow", "DropZone", "Segmented", "Field", "ChipGroup",
    "Switch", "ConsoleView", "AppBar", "_panel", "_video_thumb_and_meta",
]
