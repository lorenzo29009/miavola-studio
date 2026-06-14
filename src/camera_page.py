#!/usr/bin/env python3
"""Camera Prompts page: a searchable gallery of shot/angle references that
composes a Gemini prompt."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import (Qt, QSize, Signal, QTimer, QPropertyAnimation, QEasingCurve,
                            QRect, QPoint, QObject, QThread,
                            Slot)
from PySide6.QtGui import (QColor, QPainter, QPixmap, QPainterPath)
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QFrame, QSizePolicy, QScrollArea, QGraphicsOpacityEffect, QToolButton,
    QGridLayout, QButtonGroup, QLayout,
)

from design import (
    INK_PANEL, TXT_HI, IRIS_FG, TEXT_DIM, TOOL_ACCENTS, svg_icon,
    primary_button_style,
)

from core import (
    CAMERA_PROMPT_DIR, read_env_value,
)
from widgets import (
    AppBar,
)

# ---------------------------------------------------------------------------
# Camera Prompts

CATEGORY_LABELS = {
    "angles":      "Angles",
    "shots":       "Shots",
    "composition": "Composition",
    "movement":    "Movement",
    "lens":        "Lens",
    "special":     "POV / Special",
}


def _load_camera_prompts() -> dict:
    p = CAMERA_PROMPT_DIR / "prompts.json"
    if not p.exists():
        return {}
    try:
        import json as _json
        return _json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _tag_to_image(tag: str) -> Path:
    return CAMERA_PROMPT_DIR / "images" / f"{tag.replace(' ', '_')}.webp"


CATEGORY_ORDER = ["angles", "shots", "composition", "movement", "lens", "special"]


def _clean_description(d: str) -> str:
    """Strip the '[SUBJECT](...)' wrapper that the source data uses."""
    d = (d or "").strip()
    if d.startswith("[SUBJECT]"):
        d = d[len("[SUBJECT]"):].lstrip()
    if d.startswith("(") and d.endswith(")"):
        d = d[1:-1]
    return d.strip()


def _short_description(d: str, max_chars: int = 90) -> str:
    """First descriptive phrase of a prompt — short, human, sentence case."""
    d = _clean_description(d)
    # Use the segment before the first ":" if present (tends to be the camera label),
    # otherwise the first sentence.
    if ":" in d:
        d = d.split(":", 1)[1].strip()
    first = d.split(".")[0].strip()
    if not first:
        return ""
    if first and first[0].islower():
        first = first[0].upper() + first[1:]
    if len(first) > max_chars:
        first = first[: max_chars - 1].rsplit(" ", 1)[0] + "…"
    return first


class RoundedImage(QWidget):
    """A widget that paints a pixmap with rounded top corners, centre-cropped."""
    def __init__(self, image_path: Path, width: int, height: int, radius: int = 10):
        super().__init__()
        self.setFixedSize(width, height)
        self._radius = radius
        self._pixmap = None
        if image_path.exists():
            pm = QPixmap(str(image_path))
            if not pm.isNull():
                self._pixmap = pm.scaled(
                    width, height,
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                )

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        r = self._radius
        # Rounded all corners (sits cleanly inside its parent card padding)
        path.addRoundedRect(0, 0, self.width(), self.height(), r, r)
        p.setClipPath(path)
        if self._pixmap:
            ox = max(0, (self._pixmap.width() - self.width()) // 2)
            oy = max(0, (self._pixmap.height() - self.height()) // 2)
            p.drawPixmap(-ox, -oy, self._pixmap)
        else:
            p.fillRect(0, 0, self.width(), self.height(), QColor(INK_PANEL))
        p.end()


class PromptCard(QFrame):
    clicked = Signal(dict)
    CARD_W = 196
    CARD_H = 232
    THUMB_H = 124

    def __init__(self, entry: dict, category: str):
        super().__init__()
        self.setObjectName("PromptCard")
        self.entry = entry
        self.category = category
        self.tag = entry.get("tag", "")
        self.description = entry.get("description", "")
        self.clean_description = _clean_description(self.description)
        self.short_description = _short_description(self.description)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setFixedSize(self.CARD_W, self.CARD_H)
        self._selected = False

        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 10)  # padding keeps image inside the rounded border
        v.setSpacing(8)

        # Image, rounded
        thumb_w = self.CARD_W - 12
        self.thumb_wrap = QWidget()
        self.thumb_wrap.setFixedSize(thumb_w, self.THUMB_H)
        self.thumb = RoundedImage(_tag_to_image(self.tag), thumb_w, self.THUMB_H, radius=10)
        thumb_lay = QVBoxLayout(self.thumb_wrap)
        thumb_lay.setContentsMargins(0, 0, 0, 0)
        thumb_lay.addWidget(self.thumb)
        # Selection badge floats over the image
        self.badge = QLabel("✓", self.thumb_wrap)
        self.badge.setObjectName("CardBadge")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setFixedSize(24, 24)
        self.badge.move(thumb_w - 24 - 6, 6)
        self.badge.hide()
        v.addWidget(self.thumb_wrap)

        tag_lbl = QLabel(self.tag)
        tag_lbl.setObjectName("PromptCardTag")
        tag_lbl.setWordWrap(True)
        tag_lbl.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        v.addWidget(tag_lbl)

        if self.short_description:
            desc_lbl = QLabel(self.short_description)
            desc_lbl.setObjectName("PromptCardDesc")
            desc_lbl.setWordWrap(True)
            desc_lbl.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            v.addWidget(desc_lbl)
        v.addStretch(1)

    def set_selected(self, on: bool):
        if on == self._selected:
            return
        self._selected = on
        self.setProperty("selected", on)
        self.style().unpolish(self)
        self.style().polish(self)
        self.badge.setVisible(on)

    def mouseReleaseEvent(self, e):
        self.clicked.emit({"tag": self.tag, "description": self.description,
                           "category": self.category})
        super().mouseReleaseEvent(e)


class FlowLayout(QLayout):
    """Lays out children left-to-right, wrapping to the next line when needed."""
    def __init__(self, parent=None, h_spacing: int = 8, v_spacing: int = 8):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self._items: list = []
        self._h_space = h_spacing
        self._v_space = v_spacing

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        if 0 <= i < len(self._items):
            return self._items[i]
        return None

    def takeAt(self, i):
        if 0 <= i < len(self._items):
            return self._items.pop(i)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for item in self._items:
            s = s.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        s += QSize(m.left() + m.right(), m.top() + m.bottom())
        return s

    def _do_layout(self, rect: QRect, test_only: bool):
        m = self.contentsMargins()
        x = rect.x() + m.left()
        y = rect.y() + m.top()
        line_h = 0
        right = rect.right() - m.right()
        for item in self._items:
            w = item.widget()
            # Skip widgets the app has explicitly hidden, but not ones that are
            # merely "not shown yet" (a freshly-added chip is in this state).
            if w is not None and w.isHidden():
                continue
            sh = item.sizeHint()
            next_x = x + sh.width() + self._h_space
            if next_x - self._h_space > right and line_h > 0:
                x = rect.x() + m.left()
                y += line_h + self._v_space
                next_x = x + sh.width() + self._h_space
                line_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), sh))
            x = next_x
            line_h = max(line_h, sh.height())
        return y + line_h + m.bottom() - rect.y()


class CategorySection(QWidget):
    """A titled section with a grid of cards inside the camera prompts page."""

    def __init__(self, category: str, label: str):
        super().__init__()
        self.category = category
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(10)
        title = QLabel(label.upper())
        title.setObjectName("SectionTitle")
        head.addWidget(title)
        line = QFrame()
        line.setObjectName("SectionRule")
        line.setFixedHeight(1)
        line.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        head.addWidget(line, 1)
        self.count_lbl = QLabel("")
        self.count_lbl.setObjectName("SectionCount")
        head.addWidget(self.count_lbl)
        v.addLayout(head)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(14)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        v.addWidget(self.grid_host)

        self.cards: list[PromptCard] = []
        self._visible_cards: list[PromptCard] = []

    def add_card(self, card: PromptCard):
        self.cards.append(card)

    def reflow(self, viewport_width: int, query: str):
        # Determine which cards survive the query, then place them in the grid.
        visible = []
        for c in self.cards:
            if not query:
                visible.append(c)
            elif (query in c.tag.lower()
                  or query in c.clean_description.lower()):
                visible.append(c)
        # Clear grid
        while self.grid.count():
            it = self.grid.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
        # Hide cards that aren't in this round
        for c in self.cards:
            if c not in visible:
                c.setParent(None)
        cols = max(2, (viewport_width - 12) // (PromptCard.CARD_W + 14))
        for i, c in enumerate(visible):
            r, col = divmod(i, cols)
            self.grid.addWidget(c, r, col)
            c.show()
        self._visible_cards = visible
        self.count_lbl.setText(f"{len(visible)}")
        self.setVisible(bool(visible))


# ---------------------------------------------------------------------------
# SSL helper — works on macOS Python.org builds, Windows, and regular Linux.

def _make_ssl_ctx():
    """Return an ssl.SSLContext that can verify Google's certificate chain.

    Priority order:
      1. certifi (if installed) — most reliable, bundles Mozilla's CA list.
      2. macOS system CA bundle at /etc/ssl/cert.pem.
      3. Windows system certificate store (ROOT + CA stores).
      4. Python's default context as last resort (works on most Linux distros
         and Homebrew Python, but may fail on Python.org macOS/Windows builds).
    """
    import ssl, sys

    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass

    ctx = ssl.create_default_context()

    if sys.platform == "darwin":
        import os
        for _bundle in (
            "/etc/ssl/cert.pem",
            "/opt/homebrew/etc/ca-certificates/cert.pem",
            "/usr/local/etc/ca-certificates/cert.pem",
        ):
            if os.path.exists(_bundle):
                try:
                    ctx.load_verify_locations(_bundle)
                except Exception:
                    pass
                break

    elif sys.platform == "win32":
        # Load Windows system cert stores so Python can verify Google's chain.
        import base64
        for _store in ("ROOT", "CA"):
            try:
                for _cert_der, _enc, _trust in ssl.enum_certificates(_store):
                    if _enc == "x509_asn":
                        import textwrap
                        _b64 = textwrap.fill(
                            base64.b64encode(_cert_der).decode("ascii"), 64
                        )
                        _pem = (
                            "-----BEGIN CERTIFICATE-----\n"
                            + _b64
                            + "\n-----END CERTIFICATE-----\n"
                        )
                        try:
                            ctx.load_verify_locations(cadata=_pem)
                        except Exception:
                            pass
            except Exception:
                pass

    return ctx


# Background worker that talks to Gemini ------------------------------------

class GeminiWorker(QObject):
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, api_key: str, prompt: str, model: str = "gemini-2.5-flash"):
        super().__init__()
        self.api_key = api_key
        self.prompt = prompt
        self.model = model

    @Slot()
    def run(self):
        try:
            import json, ssl, sys, os, urllib.request, urllib.error
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{self.model}:generateContent?key={self.api_key}")
            data = json.dumps({
                "contents": [{"parts": [{"text": self.prompt}]}],
                "generationConfig": {
                    "temperature": 0.6,
                    "maxOutputTokens": 1500,
                    # Disable 2.5-flash "thinking" pass for faster responses.
                    "thinkingConfig": {"thinkingBudget": 0},
                },
            }).encode("utf-8")
            req = urllib.request.Request(url, data=data,
                                          headers={"Content-Type": "application/json"})
            ctx = _make_ssl_ctx()
            with urllib.request.urlopen(req, timeout=45, context=ctx) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            cands = payload.get("candidates") or []
            if not cands:
                self.failed.emit(f"No candidates returned. Raw: {payload}")
                return
            parts = (cands[0].get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts).strip()
            if not text:
                self.failed.emit(f"Empty response. Raw: {payload}")
                return
            self.done.emit(text)
        except urllib.error.HTTPError as e:  # type: ignore[name-defined]
            try:
                body = e.read().decode("utf-8", "ignore")[:400]
            except Exception:
                body = ""
            self.failed.emit(f"HTTP {e.code}: {body}")
        except Exception as e:
            self.failed.emit(str(e))


# The page ------------------------------------------------------------------

class CameraPromptsPage(QWidget):
    title = "Camera Prompts"
    subtitle = ('Your reference deck of camera shots. Click = copy the prompt. '
                'Switch to "Combine" to stack shots and let Gemini fuse them.')
    tool_key = "camera"

    def __init__(self, on_back: Callable[[], None]):
        super().__init__()
        self.selections: dict[str, dict] = {}
        self._thread: Optional[QThread] = None
        self._worker: Optional[GeminiWorker] = None
        self._scroll_spy_lock = False
        self._multi = False  # single-click mode by default

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- OS app bar with the Single | Multi mode toggle ----
        self.app_bar = AppBar(self.title, self.tool_key, on_back)

        mode_wrap = QFrame()
        mode_wrap.setObjectName("ModeToggle")
        mw = QHBoxLayout(mode_wrap)
        mw.setContentsMargins(3, 3, 3, 3)
        mw.setSpacing(0)
        self.mode_single = QPushButton("Single")
        self.mode_multi  = QPushButton("Combine")
        for b in (self.mode_single, self.mode_multi):
            b.setObjectName("ModeBtn")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            mw.addWidget(b)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.mode_single)
        self.mode_group.addButton(self.mode_multi)
        self.mode_single.setChecked(True)
        self.mode_single.toggled.connect(
            lambda on: self._set_multi(False) if on else None
        )
        self.mode_multi.toggled.connect(
            lambda on: self._set_multi(True) if on else None
        )
        self.app_bar.add_right(mode_wrap)
        outer.addWidget(self.app_bar)

        # ---- Sticky header: subtitle + chips + Generate ----
        self.header = QFrame()
        self.header.setObjectName("PromptsHeader")
        hv = QVBoxLayout(self.header)
        hv.setContentsMargins(28, 14, 28, 14)
        hv.setSpacing(10)

        self.sub_label = QLabel(self.subtitle)
        self.sub_label.setObjectName("PageSubtitle")
        self.sub_label.setWordWrap(True)
        hv.addWidget(self.sub_label)

        # The selection block only appears in multi-select mode.
        self.sel_row_wrap = QWidget()
        self.sel_row_wrap.setObjectName("SelRowWrap")
        # Use an ID selector so only SelRowWrap itself is transparent, not its
        # child QPushButtons (which would become invisible with a generic rule).
        self.sel_row_wrap.setStyleSheet(
            "QWidget#SelRowWrap { background: transparent; }"
        )
        sel_outer = QVBoxLayout(self.sel_row_wrap)
        sel_outer.setContentsMargins(0, 0, 0, 0)
        sel_outer.setSpacing(8)

        # The selected-shot chips sit on the SAME row as Clear + Combine so the
        # whole stack reads as one aligned control. Chips wrap to a second line
        # if there are too many; the buttons stay pinned to the right.
        self.chips_host = QWidget()
        self.chips_host.setObjectName("ChipsHost")
        self.chips_host.setStyleSheet(
            "QWidget#ChipsHost { background: transparent; }"
        )
        self.chips_layout = FlowLayout(self.chips_host, h_spacing=6, v_spacing=6)
        self.chips_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Everything in this row is vertically centred so the chips and the two
        # (differently-tall) buttons share a centre line instead of stepping
        # down from a common top edge ("staircase" effect).
        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        action_row.addWidget(self.chips_host, 1, Qt.AlignVCenter)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("GhostBtn")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self._clear_selections)
        action_row.addWidget(self.clear_btn, 0, Qt.AlignVCenter)
        self.gen_btn = QPushButton("Combine")
        self.gen_btn.setObjectName("PrimaryBtn")
        self.gen_btn.setStyleSheet(primary_button_style(TOOL_ACCENTS["camera"]))
        self.gen_btn.setCursor(Qt.PointingHandCursor)
        self.gen_btn.setIcon(svg_icon("sparkles", IRIS_FG, 15))
        self.gen_btn.setLayoutDirection(Qt.RightToLeft)  # icon shows after the text
        self.gen_btn.clicked.connect(self._on_generate)
        action_row.addWidget(self.gen_btn, 0, Qt.AlignVCenter)
        sel_outer.addLayout(action_row)

        hv.addWidget(self.sel_row_wrap)
        outer.addWidget(self.header)

        # ---- Filter pills + search (sticky) ----
        controls = QFrame()
        controls.setObjectName("PromptsControls")
        cv = QHBoxLayout(controls)
        cv.setContentsMargins(28, 8, 28, 10)
        cv.setSpacing(8)

        self.pill_group = QButtonGroup(self)
        self.pill_group.setExclusive(True)
        self._pills: dict[str, QPushButton] = {}
        self._make_pill("All", "all", cv, default=True)
        for key in CATEGORY_ORDER:
            self._make_pill(CATEGORY_LABELS[key], key, cv)
        cv.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search shots…")
        self.search.setFixedWidth(200)
        self.search.textChanged.connect(lambda *_: self._reflow())
        cv.addWidget(self.search)
        outer.addWidget(controls)

        # ---- Scroll area (the gallery) ----
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        outer.addWidget(self.scroll, 1)

        wrap = QWidget()
        self.scroll.setWidget(wrap)
        self.scroll_content = wrap
        wv = QVBoxLayout(wrap)
        wv.setContentsMargins(28, 12, 28, 28)
        wv.setSpacing(28)
        self.scroll_layout = wv

        self.empty_msg = QLabel("No shots match your search.")
        self.empty_msg.setStyleSheet(f"color: {TEXT_DIM}; padding: 18px 0;")
        self.empty_msg.setVisible(False)
        wv.addWidget(self.empty_msg)

        # ---- Build per-category sections ----
        data = _load_camera_prompts()
        self.cards: list[PromptCard] = []
        self.sections: dict[str, CategorySection] = {}
        for cat in CATEGORY_ORDER:
            section = CategorySection(cat, CATEGORY_LABELS[cat])
            for entry in data.get(cat, []):
                c = PromptCard(entry, cat)
                c.clicked.connect(self._on_card_clicked)
                section.add_card(c)
                self.cards.append(c)
            self.sections[cat] = section
            wv.addWidget(section)
        wv.addStretch(1)

        # ---- Sticky result bar at the bottom (only shown after a generation) ----
        self.result_bar = QFrame()
        self.result_bar.setObjectName("ResultBar")
        rl = QHBoxLayout(self.result_bar)
        rl.setContentsMargins(28, 12, 28, 12)
        rl.setSpacing(10)
        rlabel = QLabel("Prompt")
        rlabel.setObjectName("ResultBarLabel")
        rl.addWidget(rlabel)
        self.result = QLineEdit()
        self.result.setObjectName("ResultLine")
        self.result.setReadOnly(True)
        self.result.setPlaceholderText(
            "Your ready-to-paste prompt will appear here."
        )
        rl.addWidget(self.result, 1)
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setObjectName("SecondaryBtn")
        self.copy_btn.setIcon(svg_icon("copy", TXT_HI, 14))
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self._copy_result)
        rl.addWidget(self.copy_btn)
        outer.addWidget(self.result_bar)
        self.result_bar.setVisible(False)  # only after first generation

        # Toast
        self.toast = QLabel(self)
        self.toast.setObjectName("Toast")
        self.toast.setAlignment(Qt.AlignCenter)
        self.toast.hide()
        self._toast_anim = None

        self._filter = "all"
        self._update_chips()
        self._update_generate_btn()
        self._set_multi(False)
        QTimer.singleShot(0, self._reflow)

    # ---- Mode toggle ----------------------------------------------------

    def _set_multi(self, on: bool):
        self._multi = on
        # Sync toggle buttons silently in case this was called programmatically.
        for b in (self.mode_single, self.mode_multi):
            b.blockSignals(True)
        self.mode_multi.setChecked(on)
        self.mode_single.setChecked(not on)
        for b in (self.mode_single, self.mode_multi):
            b.blockSignals(False)

        self.sel_row_wrap.setVisible(on)
        if not on:
            # Drop selections, hide result bar — back to a clean gallery.
            self.selections.clear()
            self._sync_card_states()
            self.result_bar.setVisible(False)
            self.result.clear()
            self.copy_btn.setEnabled(False)
            self.sub_label.setText(
                "Click any shot to copy its prompt. "
                "Switch to Combine to stack several and let Gemini fuse them."
            )
        else:
            self.sub_label.setText(self.subtitle)
            self._update_chips()
            self._update_generate_btn()

    # ---- Filter pills ----------------------------------------------------

    def _make_pill(self, label: str, key: str, layout: QHBoxLayout, default=False):
        btn = QPushButton(label)
        btn.setObjectName("PillBtn")
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setProperty("filterKey", key)
        if default:
            btn.setChecked(True)
        self.pill_group.addButton(btn)
        btn.toggled.connect(self._on_pill_toggled)
        layout.addWidget(btn)
        self._pills[key] = btn

    def _on_pill_toggled(self, on: bool):
        if not on:
            return
        btn = self.sender()
        new_filter = btn.property("filterKey")
        if new_filter == self._filter:
            return
        self._filter = new_filter
        if new_filter != "all" and new_filter in self.sections:
            self._reflow()
            # Scroll to that section
            sect = self.sections[new_filter]
            target = sect.mapTo(self.scroll_content, QPoint(0, 0)).y()
            self._scroll_spy_lock = True
            self.scroll.verticalScrollBar().setValue(max(0, target - 8))
            QTimer.singleShot(150, lambda: setattr(self, "_scroll_spy_lock", False))
        else:
            self._reflow()

    def _set_pill_active(self, key: str):
        btn = self._pills.get(key)
        if btn and not btn.isChecked():
            for k, b in self._pills.items():
                b.blockSignals(True)
                b.setChecked(k == key)
                b.blockSignals(False)

    def _reflow(self):
        q = self.search.text().strip().lower()
        viewport_w = max(self.scroll.viewport().width(),
                         self.width() - 56, 600)
        any_visible = False
        for cat in CATEGORY_ORDER:
            sect = self.sections[cat]
            if self._filter != "all" and self._filter != cat:
                # Hide non-active sections quickly
                sect.reflow(viewport_w, q)
                sect.setVisible(False)
                continue
            sect.reflow(viewport_w, q)
            if sect.isVisible():
                any_visible = True
        self.empty_msg.setVisible(not any_visible)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self._reflow)
        if self.toast.isVisible():
            self._reposition_toast()

    def _on_scroll(self, _v: int):
        if self._scroll_spy_lock or self._filter != "all":
            return
        # Find the section whose top is just at/below the viewport top.
        viewport_top = self.scroll.verticalScrollBar().value()
        threshold = viewport_top + 24
        active = "all"
        for cat in CATEGORY_ORDER:
            sect = self.sections[cat]
            if not sect.isVisible():
                continue
            top = sect.mapTo(self.scroll_content, QPoint(0, 0)).y()
            if top <= threshold:
                active = cat
            else:
                break
        self._set_pill_active(active if active != "all" else "all")

    # ---- Selection logic -------------------------------------------------

    def _on_card_clicked(self, entry: dict):
        if not self._multi:
            # Single-click mode: copy the shot's clean description immediately.
            text = _clean_description(entry["description"])
            QApplication.clipboard().setText(text)
            self._show_toast(f"Copied · {entry['tag']}")
            return
        cat = entry["category"]
        current = self.selections.get(cat)
        if current and current["tag"] == entry["tag"]:
            self.selections.pop(cat, None)
            self._show_toast(f"Removed · {entry['tag']}")
        else:
            self.selections[cat] = {"tag": entry["tag"],
                                    "description": entry["description"]}
            self._show_toast(f"Added · {CATEGORY_LABELS[cat]}: {entry['tag']}")
        self._sync_card_states()
        self._update_chips()
        self._update_generate_btn()

    def _sync_card_states(self):
        for c in self.cards:
            sel = (c.category in self.selections
                   and self.selections[c.category]["tag"] == c.tag)
            c.set_selected(sel)

    def _update_chips(self):
        # Drop existing chip widgets
        while self.chips_layout.count():
            it = self.chips_layout.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        n = len(self.selections)
        if n == 0:
            self.chips_host.setVisible(False)
            self.clear_btn.setVisible(False)
            return
        self.chips_host.setVisible(True)
        self.clear_btn.setVisible(True)

        for cat in CATEGORY_ORDER:
            if cat not in self.selections:
                continue
            e = self.selections[cat]
            chip = QFrame()
            chip.setObjectName("SelectionChip")
            chip.setToolTip(f"{CATEGORY_LABELS[cat]}: {e['tag']}")
            hl = QHBoxLayout(chip)
            hl.setContentsMargins(12, 5, 6, 5)
            hl.setSpacing(8)

            dot = QLabel("●")
            dot.setObjectName("ChipDot")
            hl.addWidget(dot)
            tag_lbl = QLabel(e["tag"])
            tag_lbl.setObjectName("ChipTag")
            hl.addWidget(tag_lbl)
            rm = QToolButton()
            rm.setObjectName("ChipRemove")
            rm.setText("×")
            rm.setCursor(Qt.PointingHandCursor)
            rm.setFixedSize(22, 22)
            rm.clicked.connect(lambda _=False, c=cat: self._remove_selection(c))
            hl.addWidget(rm)
            self.chips_layout.addWidget(chip)
            chip.show()  # ensure the new chip participates in the next layout pass
        # Force a re-layout pass after the chips changed
        self.chips_layout.invalidate()
        self.chips_host.updateGeometry()
        self.chips_host.adjustSize()

    def _remove_selection(self, cat: str):
        self.selections.pop(cat, None)
        self._sync_card_states()
        self._update_chips()
        self._update_generate_btn()
        # If they removed everything, also tear the result down.
        if not self.selections:
            self._dismiss_result()

    def _clear_selections(self):
        had_any = bool(self.selections) or self.result_bar.isVisible()
        self.selections.clear()
        self._sync_card_states()
        self._update_chips()
        self._update_generate_btn()
        self._dismiss_result()
        if had_any:
            self._show_toast("Cleared")

    def _dismiss_result(self):
        self.result.clear()
        self.copy_btn.setEnabled(False)
        self.result_bar.setVisible(False)

    def _update_generate_btn(self):
        n = len(self.selections)
        self.gen_btn.setEnabled(n > 0)
        self.gen_btn.setText("Combine" if n == 0 else f"Combine ({n})")

    # ---- Generation ------------------------------------------------------

    def _on_generate(self):
        if not self.selections or self._thread is not None:
            return
        key = read_env_value("GEMINI_API_KEY")
        if not key:
            self.result_bar.setVisible(True)
            self.result.setText(
                "✗ No Gemini key — open Settings (gear icon on Home) and save your key first."
            )
            self.copy_btn.setEnabled(False)
            return

        bullets = []
        for cat in CATEGORY_ORDER:
            if cat in self.selections:
                e = self.selections[cat]
                clean = _clean_description(e["description"])
                bullets.append(f"- {CATEGORY_LABELS[cat]} → {e['tag']}: {clean}")
        bullets_text = "\n".join(bullets)

        user_prompt = (
            "You are a senior cinematographer writing a single, ready-to-paste prompt "
            "for an AI image / video generator. You will receive a set of camera "
            "elements, each with a tag and a technical description.\n\n"
            "Your job is to fuse them into ONE coherent, vivid, EXHAUSTIVE prompt that "
            "preserves EVERY technical cue from the inputs. Specifically:\n"
            "• Keep every camera position, height, angle, distance to subject, lens "
            "behaviour, motion, perspective effect, and composition rule that is "
            "mentioned in the inputs. Do not drop any of them.\n"
            "• Smoothly integrate the elements as if a real cinematographer "
            "pre-visualised one shot.\n"
            "• Do NOT invent new subject matter, location, lighting, colour grade, "
            "mood, props, or wardrobe that is not implied by the inputs. Use "
            "\"the subject\" if no subject is given.\n"
            "• Output a single flowing paragraph, 2 to 5 sentences, ~70–180 words. "
            "No bullets, no headings, no preamble, no quotes, no labels like "
            "\"Final prompt:\". Output ONLY the prompt itself.\n\n"
            f"Camera elements:\n{bullets_text}\n\n"
            "Now write the final prompt:"
        )

        self.result_bar.setVisible(True)
        self.result.setText("Generating…")
        self.copy_btn.setEnabled(False)
        self.gen_btn.setEnabled(False)
        self.gen_btn.setText("Generating…")

        thread = QThread(self)
        worker = GeminiWorker(key, user_prompt)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_gemini_done)
        worker.failed.connect(self._on_gemini_failed)
        worker.done.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_thread_finished(self):
        self._thread = None
        self._worker = None
        self._update_generate_btn()

    @Slot(str)
    def _on_gemini_done(self, text: str):
        compact = " ".join(text.split())  # collapse internal newlines
        self.result_bar.setVisible(True)
        self.result.setText(compact)
        self.result.setCursorPosition(0)
        self.result.setToolTip(compact)
        self.copy_btn.setEnabled(True)
        self._show_toast("Ready · hit Copy to use it")

    @Slot(str)
    def _on_gemini_failed(self, err: str):
        self.result_bar.setVisible(True)
        self.result.setText(f"✗ Gemini error: {err}")
        self.result.setToolTip(err)
        self.copy_btn.setEnabled(False)
        self._show_toast("Generation failed")

    def _copy_result(self):
        text = self.result.text().strip()
        if text and not text.startswith("✗") and text != "Generating…":
            QApplication.clipboard().setText(text)
            self._show_toast("Copied to clipboard")

    # ---- Toast -----------------------------------------------------------

    def _reposition_toast(self):
        self.toast.adjustSize()
        x = (self.width() - self.toast.width()) // 2
        y = self.height() - self.toast.height() - 28
        self.toast.move(max(10, x), max(10, y))

    def _show_toast(self, message: str):
        self.toast.setText(message)
        self._reposition_toast()
        self.toast.show()
        self.toast.raise_()
        eff = self.toast.graphicsEffect()
        if not isinstance(eff, QGraphicsOpacityEffect):
            eff = QGraphicsOpacityEffect(self.toast)
            self.toast.setGraphicsEffect(eff)
        if self._toast_anim:
            self._toast_anim.stop()
        eff.setOpacity(0.0)
        fade_in = QPropertyAnimation(eff, b"opacity", self)
        fade_in.setDuration(160)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.OutCubic)
        fade_in.start()
        self._toast_anim = fade_in
        QTimer.singleShot(1500, lambda: self._fade_toast_out())

    def _fade_toast_out(self):
        eff = self.toast.graphicsEffect()
        if not isinstance(eff, QGraphicsOpacityEffect):
            self.toast.hide()
            return
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(260)
        anim.setStartValue(eff.opacity())
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.InCubic)
        anim.finished.connect(lambda: self.toast.hide())
        anim.start()
        self._toast_anim = anim


