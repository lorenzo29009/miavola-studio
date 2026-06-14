#!/usr/bin/env python3
"""Script Animator page: Gemini-powered script -> Veo/Omni Flash prompts,
with the floating segment panel and its worker threads."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import (Qt, Signal, QTimer, QObject, QThread, Slot)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QComboBox, QPlainTextEdit, QFrame, QScrollArea, QGraphicsDropShadowEffect,
)

from design import (
    IRIS_FG, TEXT, TEXT_DIM, OK_COLOR, ERR_COLOR, TOOL_ACCENTS,
    svg_icon, primary_button_style,
)

from core import (
    APP_DIR, EXPORTS_DIR, chevron_icon, read_env_value,
)
from widgets import (
    Card, AppBar,
)

# ---------------------------------------------------------------------------
# Script Animator — Gemini-powered script → Veo/Omni Flash prompts

ANIMATOR_SLOTS = (4, 6, 8, 10)
ANIMATOR_LOG_FILE = APP_DIR / "exports" / "animator_log.json"

# Approximate character rate (chars/sec) at natural spoken pace per language.
# Used to derive the duration table shown to Gemini.
_LANG_CHAR_RATE: dict[str, int] = {
    "German": 12, "English": 14, "Spanish": 15, "French": 12, "Italian": 15,
}


def _animator_segmenter_prompt(raw_script: str, language_name: str,
                                with_emotions: bool) -> str:
    rate = _LANG_CHAR_RATE.get(language_name, 13)
    d = {s: s * rate for s in ANIMATOR_SLOTS}
    emotion_clause = (
        '\n5. For EVERY segment include an "emotion" field — a 1–4 word phrase '
        'describing the emotional tone of the delivery (e.g. "angry frustration", '
        '"calm reflection", "urgent excitement", "warm reassurance").'
    ) if with_emotions else ""
    emotion_field = ', "emotion": "..."' if with_emotions else ""
    n = 6 if with_emotions else 5
    translate_clause = (
        f'\n{n}. For EVERY segment add an "en" field: a natural, fluent English '
        f'translation of the spoken line. Not word-for-word literal — idiomatic.'
    ) if language_name != "English" else ""
    translate_field = ', "en": "..."' if language_name != "English" else ""

    return f"""You are an expert short-form video ad director. Parse the {language_name} ad script below carefully, even if formatting is messy or inconsistent.

Script structure (labels may be in {language_name} or English, may have typos, or be missing — infer from content):
• Hook variations (H1–H5): independent alternative opening lines, NOT consecutive content.
• Body (Problem / Agitation / Solution): one continuous story in script order. Label as B1, B2, …
• Two CTA variants (CTA1, CTA2): alternative endings. Label as CTA1-1, CTA1-2, … / CTA2-1, CTA2-2, …

Task — split into video segments:

1. Each segment fits one of {{4, 6, 8, 10}} SECOND vertical-video clips. Use the SMALLEST slot that comfortably fits natural delivery.
2. Duration calibration for {language_name} (~{rate} chars/sec at natural spoken pace):
     4 s  → up to {d[4]} characters
     6 s  → {d[4]+1}–{d[6]} characters
     8 s  → {d[6]+1}–{d[8]} characters
    10 s  → {d[8]+1}–{d[10]} characters
   Count only visible spoken characters (no labels, no brackets).
   Emotional / slow / emphatic delivery → add one tier. Fast / punchy / excited → consider one tier down.
   Always pick the SMALLEST comfortable tier. Do NOT pad to fill the slot.
3. Never break mid-thought. Cut only at sentence ends, em-dashes, or semicolons.
4. Hooks stay as their own segments. Only split if genuinely > 10 s (then use H1-1, H1-2, …).{emotion_clause}{translate_clause}

Output order: all H* → all B* → all CTA1-* → all CTA2-*

Return JSON array only (no markdown, no preamble):
{{"label": "H1", "text": "...", "duration": 8{emotion_field}{translate_field}}}

"text": the spoken line exactly as delivered (no labels, no brackets).
"duration": integer ∈ {{4, 6, 8, 10}}.

Script:
---
{raw_script.strip()}
---"""


def _animator_refine_prompt(segments: list[dict], language_name: str) -> str:
    import json as _json
    segs_in = [
        {
            "label": s["label"],
            "text": s["text"],
            "duration": s["duration"],
            "emotion": s.get("emotion") or "",
            "user_note": s.get("user_note") or "",
        }
        for s in segments
    ]
    return f"""You are a video director writing Veo / Omni Flash generation prompts.

For each segment below, write a concise English video-generation prompt (1–3 sentences, ready to paste).
It must cover: visual scene or setting, talent action, emotional delivery, voiceover line (verbatim), clip duration.
When "user_note" is present, use it as the scene context or talent action.
When "emotion" is present, describe the delivery tone.

Return a JSON array — same segments, each with an added "video_prompt" field (string, English).
No other fields need to change. No markdown, no preamble.

Original script language: {language_name}

Segments:
{_json.dumps(segs_in, ensure_ascii=False, indent=2)}"""


def _animator_build_prompt(segment: dict, language_name: str = "German") -> str:
    """Build the video generation prompt for a segment (used by the float panel)."""
    if segment.get("video_prompt"):
        return segment["video_prompt"]
    parts: list[str] = []
    note = (segment.get("user_note") or "").strip()
    if note:
        parts.append(note.rstrip("."))
    emo = (segment.get("emotion") or "").strip()
    if emo:
        parts.append(f"The delivery is {emo}")
    if language_name == "English":
        parts.append(f'She says: "{segment["text"]}"')
    else:
        parts.append(f'She says in {language_name}: "{segment["text"]}"')
    parts.append(f"Duration: {segment['duration']} seconds")
    return ". ".join(parts) + "."


def _animator_save_log(segments: list, language: str, with_emotions: bool,
                        script: str) -> None:
    try:
        import json as _json, datetime as _dt
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "timestamp": _dt.datetime.now().isoformat(timespec="seconds"),
            "language": language,
            "with_emotions": with_emotions,
            "script": script,
            "segments": segments,
        }
        ANIMATOR_LOG_FILE.write_text(
            _json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def _animator_load_log() -> "dict | None":
    try:
        import json as _json
        if ANIMATOR_LOG_FILE.exists():
            return _json.loads(ANIMATOR_LOG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


# ─── Workers ─────────────────────────────────────────────────────────────────

class GeminiSegmenterWorker(QObject):
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, api_key: str, prompt: str,
                  model: str = "gemini-2.5-flash"):
        super().__init__()
        self.api_key = api_key
        self.prompt = prompt
        self.model = model

    @Slot()
    def run(self):
        try:
            import json, urllib.request, urllib.error
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{self.model}:generateContent?key={self.api_key}")
            body = json.dumps({
                "contents": [{"parts": [{"text": self.prompt}]}],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 8000,
                    "thinkingConfig": {"thinkingBudget": 0},
                    "response_mime_type": "application/json",
                },
            }).encode("utf-8")
            req = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            cands = payload.get("candidates") or []
            if not cands:
                self.failed.emit("Gemini returned no candidates.")
                return
            parts = (cands[0].get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts).strip()
            try:
                segments = json.loads(text)
            except Exception as e:
                self.failed.emit(f"Couldn't parse JSON: {e}\n{text[:400]}")
                return
            if not isinstance(segments, list) or not segments:
                self.failed.emit("Gemini returned an empty or invalid list.")
                return
            cleaned: list[dict] = []
            for seg in segments:
                if not isinstance(seg, dict):
                    continue
                label = str(seg.get("label", "")).strip().upper()
                line = str(seg.get("text", "")).strip()
                try:
                    duration = int(seg.get("duration", 0))
                except (TypeError, ValueError):
                    continue
                if not label or not line or duration not in ANIMATOR_SLOTS:
                    continue
                out: dict = {"label": label, "text": line, "duration": duration}
                emo = seg.get("emotion")
                if isinstance(emo, str) and emo.strip():
                    out["emotion"] = emo.strip()
                en = seg.get("en")
                if isinstance(en, str) and en.strip():
                    out["en"] = en.strip()
                cleaned.append(out)
            if not cleaned:
                self.failed.emit("Gemini response had no valid segments.")
                return
            self.done.emit(cleaned)
        except urllib.error.HTTPError as e:
            try:
                body_txt = e.read().decode("utf-8", "ignore")[:400]
            except Exception:
                body_txt = ""
            self.failed.emit(f"HTTP {e.code}: {body_txt}")
        except Exception as e:
            self.failed.emit(str(e))


class GeminiRefineWorker(QObject):
    """Second-pass Gemini call: adds a video_prompt field to each segment."""
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, api_key: str, prompt: str, original_segments: list,
                  model: str = "gemini-2.5-flash"):
        super().__init__()
        self.api_key = api_key
        self.prompt = prompt
        self.original_segments = original_segments
        self.model = model

    @Slot()
    def run(self):
        try:
            import json, urllib.request, urllib.error
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{self.model}:generateContent?key={self.api_key}")
            body = json.dumps({
                "contents": [{"parts": [{"text": self.prompt}]}],
                "generationConfig": {
                    "temperature": 0.4,
                    "maxOutputTokens": 10000,
                    "thinkingConfig": {"thinkingBudget": 0},
                    "response_mime_type": "application/json",
                },
            }).encode("utf-8")
            req = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            cands = payload.get("candidates") or []
            if not cands:
                self.failed.emit("Gemini returned no candidates.")
                return
            parts_data = (cands[0].get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts_data).strip()
            try:
                refined = json.loads(text)
            except Exception as e:
                self.failed.emit(f"Couldn't parse JSON: {e}\n{text[:400]}")
                return
            if not isinstance(refined, list):
                self.failed.emit("Expected a JSON array from Gemini.")
                return
            label_to_prompt: dict[str, str] = {}
            for item in refined:
                if isinstance(item, dict):
                    lbl = str(item.get("label", "")).strip().upper()
                    vp = item.get("video_prompt", "")
                    if lbl and isinstance(vp, str) and vp.strip():
                        label_to_prompt[lbl] = vp.strip()
            merged = []
            for seg in self.original_segments:
                s = dict(seg)
                vp = label_to_prompt.get(seg["label"])
                if vp:
                    s["video_prompt"] = vp
                merged.append(s)
            self.done.emit(merged)
        except urllib.error.HTTPError as e:
            try:
                body_txt = e.read().decode("utf-8", "ignore")[:400]
            except Exception:
                body_txt = ""
            self.failed.emit(f"HTTP {e.code}: {body_txt}")
        except Exception as e:
            self.failed.emit(str(e))


# ─── Always-visible floating panel ───────────────────────────────────────────

class AnimatorFloatPanel(QWidget):
    closed = Signal()

    def __init__(self, segments: list[dict], language_name: str):
        super().__init__()
        # Qt.Tool → NSPanel on macOS. NSPanel is non-activating by default:
        # clicking it does NOT raise or activate the main application window.
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
        )
        # Keep visible across Spaces and when the app is inactive / backgrounded.
        try:
            self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)
        except Exception:
            pass
        # Prevent activation when the panel is shown programmatically.
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(460, 490)
        self.setWindowTitle("Script Animator")

        self.segments = segments
        self.language_name = language_name
        self.idx = 0
        self._drag_pos = None

        scr = QApplication.primaryScreen().availableGeometry()
        self.move(scr.right() - self.width() - 24, scr.top() + 80)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._container = QFrame(self)
        self._container.setObjectName("FloatPanel")
        outer.addWidget(self._container)
        c = QVBoxLayout(self._container)
        c.setContentsMargins(0, 0, 0, 0)
        c.setSpacing(0)

        # ── Header (drag handle) ──────────────────────────────────────────
        header = QFrame()
        header.setObjectName("FloatHeader")
        header.setFixedHeight(40)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(18, 0, 10, 0)
        hl.setSpacing(8)
        title = QLabel("SCRIPT ANIMATOR")
        title.setObjectName("FloatTitle")
        hl.addWidget(title)
        hl.addStretch(1)
        self.counter_lbl = QLabel()
        self.counter_lbl.setObjectName("FloatCounter")
        hl.addWidget(self.counter_lbl)
        close = QPushButton("×")
        close.setObjectName("FloatClose")
        close.setCursor(Qt.PointingHandCursor)
        close.setFixedSize(26, 26)
        close.clicked.connect(self.close)
        hl.addWidget(close)
        c.addWidget(header)

        # ── Body ─────────────────────────────────────────────────────────
        body = QFrame()
        body.setObjectName("FloatBodyArea")
        bv = QVBoxLayout(body)
        bv.setContentsMargins(22, 16, 22, 12)
        bv.setSpacing(10)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(10)
        self.label_lbl = QLabel()
        self.label_lbl.setObjectName("FloatLabel")
        meta_row.addWidget(self.label_lbl)
        meta_row.addStretch(1)
        self.duration_chip = QLabel()
        self.duration_chip.setObjectName("FloatChip")
        meta_row.addWidget(self.duration_chip)
        bv.addLayout(meta_row)

        # Original spoken line — primary text
        self.text_lbl = QLabel()
        self.text_lbl.setObjectName("FloatText")
        self.text_lbl.setWordWrap(True)
        self.text_lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.text_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.text_lbl.setMinimumHeight(72)
        bv.addWidget(self.text_lbl)

        # English translation — secondary, visible only when "en" field present
        self.trans_lbl = QLabel()
        self.trans_lbl.setObjectName("FloatTranslation")
        self.trans_lbl.setWordWrap(True)
        self.trans_lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.trans_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.trans_lbl.setVisible(False)
        bv.addWidget(self.trans_lbl)

        bv.addStretch(1)

        # Emotion chip
        self.emotion_chip = QLabel()
        self.emotion_chip.setObjectName("FloatMetaChip")
        self.emotion_chip.setWordWrap(True)
        self.emotion_chip.setVisible(False)
        bv.addWidget(self.emotion_chip)

        # Note / video-prompt indicator chip
        self.prompt_chip = QLabel()
        self.prompt_chip.setObjectName("FloatMetaChip")
        self.prompt_chip.setWordWrap(True)
        self.prompt_chip.setVisible(False)
        bv.addWidget(self.prompt_chip)

        c.addWidget(body, 1)

        # ── Progress bar ─────────────────────────────────────────────────
        prog_wrap = QFrame()
        prog_wrap.setObjectName("FloatProgressWrap")
        prog_wrap.setFixedHeight(28)
        pl = QHBoxLayout(prog_wrap)
        pl.setContentsMargins(22, 4, 22, 4)
        pl.setSpacing(10)
        self.progress_track = QFrame()
        self.progress_track.setObjectName("ProgressTrack")
        self.progress_track.setFixedHeight(4)
        self.progress_fill = QFrame(self.progress_track)
        self.progress_fill.setObjectName("ProgressFill")
        self.progress_fill.setGeometry(0, 0, 0, 4)
        pl.addWidget(self.progress_track, 1)
        self.progress_lbl = QLabel()
        self.progress_lbl.setObjectName("FloatCounter")
        pl.addWidget(self.progress_lbl)
        c.addWidget(prog_wrap)

        # ── Action bar ───────────────────────────────────────────────────
        ab = QFrame()
        ab.setObjectName("FloatActions")
        ab.setFixedHeight(72)
        abl = QHBoxLayout(ab)
        abl.setContentsMargins(18, 14, 18, 18)
        abl.setSpacing(10)
        self.prev_btn = QPushButton("Prev")
        self.prev_btn.setObjectName("GhostBtn")
        self.prev_btn.setCursor(Qt.PointingHandCursor)
        self.prev_btn.setIcon(chevron_icon("left", TEXT_DIM, 12))
        self.prev_btn.clicked.connect(self._go_prev)
        abl.addWidget(self.prev_btn)
        self.skip_btn = QPushButton("Skip")
        self.skip_btn.setObjectName("GhostBtn")
        self.skip_btn.setCursor(Qt.PointingHandCursor)
        self.skip_btn.clicked.connect(self._advance)
        abl.addWidget(self.skip_btn)
        abl.addStretch(1)
        self.copy_btn = QPushButton("Copy & Next")
        self.copy_btn.setObjectName("PrimaryBtn")
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setIcon(chevron_icon("right", "white", 14))
        self.copy_btn.setLayoutDirection(Qt.RightToLeft)
        self.copy_btn.clicked.connect(self._copy_and_advance)
        abl.addWidget(self.copy_btn)
        c.addWidget(ab)

        sh = QGraphicsDropShadowEffect()
        sh.setBlurRadius(50)
        sh.setColor(QColor(0, 0, 0, 220))
        sh.setOffset(0, 14)
        self._container.setGraphicsEffect(sh)

        header.mousePressEvent = self._start_drag
        header.mouseMoveEvent = self._do_drag
        header.mouseReleaseEvent = self._end_drag

        self._show_current()

    def update_segments(self, segments: list[dict]) -> None:
        """Replace segment data (e.g. after re-elaborate) and refresh display."""
        self.segments = segments
        self.idx = min(self.idx, max(len(segments) - 1, 0))
        self._show_current()

    def _show_current(self):
        n = len(self.segments)
        if not self.segments:
            self.label_lbl.setText("—")
            self.text_lbl.setText("Nothing to show.")
            return

        if self.idx < 0:
            self.idx = 0
        if self.idx >= n:
            self.idx = n

        if self.idx == n:
            self.label_lbl.setText("All done")
            self.duration_chip.setVisible(False)
            self.text_lbl.setText(
                "You've stepped through every segment.\n"
                "Close this panel or hit Prev to revisit."
            )
            self.trans_lbl.setVisible(False)
            self.emotion_chip.setVisible(False)
            self.prompt_chip.setVisible(False)
            self.copy_btn.setEnabled(False)
            self.skip_btn.setEnabled(False)
            self.prev_btn.setEnabled(True)
            self.counter_lbl.setText(f"{n} / {n}")
            self.progress_lbl.setText(f"{n}/{n}")
            self._paint_progress(1.0)
            return

        seg = self.segments[self.idx]
        self.label_lbl.setText(seg["label"])
        self.duration_chip.setText(f"{seg['duration']}s")
        self.duration_chip.setVisible(True)
        self.text_lbl.setText(seg["text"])

        en = seg.get("en")
        if en:
            self.trans_lbl.setText(en)
            self.trans_lbl.setVisible(True)
        else:
            self.trans_lbl.setVisible(False)

        emo = seg.get("emotion")
        if emo:
            self.emotion_chip.setText(f"◌  Emotion · {emo}")
            self.emotion_chip.setVisible(True)
        else:
            self.emotion_chip.setVisible(False)

        if seg.get("video_prompt"):
            self.prompt_chip.setText("⊕  Custom video prompt ready")
            self.prompt_chip.setVisible(True)
        elif seg.get("user_note"):
            note = seg["user_note"]
            self.prompt_chip.setText(f"⊕  {note[:60]}{'…' if len(note) > 60 else ''}")
            self.prompt_chip.setVisible(True)
        else:
            self.prompt_chip.setVisible(False)

        self.copy_btn.setEnabled(True)
        self.skip_btn.setEnabled(True)
        self.prev_btn.setEnabled(self.idx > 0)
        self.counter_lbl.setText(f"{self.idx + 1} / {n}")
        self.progress_lbl.setText(f"{self.idx + 1}/{n}")
        self._paint_progress((self.idx + 1) / n)

    def _paint_progress(self, frac: float):
        frac = max(0.0, min(1.0, frac))
        w = max(1, int(self.progress_track.width() * frac))
        self.progress_fill.setGeometry(0, 0, w, self.progress_track.height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, lambda: self._paint_progress(
            (self.idx + 1) / max(len(self.segments), 1)
            if self.idx < len(self.segments) else 1.0
        ))

    def _current_prompt(self) -> str:
        if self.idx >= len(self.segments):
            return ""
        return _animator_build_prompt(self.segments[self.idx], self.language_name)

    def _copy_and_advance(self):
        text = self._current_prompt()
        if text:
            QApplication.clipboard().setText(text)
        self._advance()

    def _advance(self):
        if self.idx < len(self.segments):
            self.idx += 1
            self._show_current()

    def _go_prev(self):
        if self.idx > 0:
            self.idx -= 1
            self._show_current()

    def _start_drag(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _do_drag(self, e):
        if self._drag_pos and (e.buttons() & Qt.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def _end_drag(self, _e):
        self._drag_pos = None

    def closeEvent(self, e):
        self.closed.emit()
        super().closeEvent(e)


# ─── Tool page ────────────────────────────────────────────────────────────────

class AnimatorPage(QWidget):
    title = "Script Animator"
    subtitle = "Paste a script → Build → customize per segment → open the floating window."
    tool_key = "animator"

    LANG_NAMES = ["German", "English", "Spanish", "French", "Italian"]

    def __init__(self, on_back: Callable[[], None]):
        super().__init__()
        self.segments: list[dict] = []
        self._panel: Optional[AnimatorFloatPanel] = None
        self._thread: Optional[QThread] = None
        self._worker: Optional[GeminiSegmenterWorker] = None
        self._refine_thread: Optional[QThread] = None
        self._refine_worker: Optional[GeminiRefineWorker] = None
        self._note_fields: list[tuple[str, QLineEdit]] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── App bar ──────────────────────────────────────────────────────
        self.app_bar = AppBar(self.title, self.tool_key, on_back)
        outer.addWidget(self.app_bar)

        # ── Scrollable body (scroll only appears when customize is expanded) ──
        body_scroll = QScrollArea()
        body_scroll.setObjectName("BodyScroll")
        body_scroll.setWidgetResizable(True)
        body_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body_scroll.setFrameShape(QFrame.NoFrame)
        body_inner = QWidget()
        v = QVBoxLayout(body_inner)
        v.setContentsMargins(24, 14, 24, 16)
        v.setSpacing(10)
        body_scroll.setWidget(body_inner)
        outer.addWidget(body_scroll, 1)

        # ── Script card ───────────────────────────────────────────────────
        script_card = Card()
        lc = QVBoxLayout(script_card)
        lc.setContentsMargins(14, 12, 14, 12)
        lc.setSpacing(8)
        sl = QLabel("SCRIPT")
        sl.setObjectName("SectionLabel")
        lc.addWidget(sl)
        self.script_input = QPlainTextEdit()
        self.script_input.setPlaceholderText(
            "Paste the script — Gemini handles any format.\n\n"
            "It looks for hooks (H1–H5), body (Problem / Agitation / Solution), and CTAs."
        )
        self.script_input.setMinimumHeight(140)
        lc.addWidget(self.script_input, 1)
        v.addWidget(script_card, 3)

        # ── Settings strip (Language + Emotions — always visible) ─────────
        settings_card = Card()
        sc = QHBoxLayout(settings_card)
        sc.setContentsMargins(16, 10, 16, 10)
        sc.setSpacing(20)
        ll_lang = QLabel("Language")
        ll_lang.setObjectName("FieldLabel")
        sc.addWidget(ll_lang)
        self.language = QComboBox()
        self.language.addItems([
            "German (Deutsch)", "English", "Spanish (Español)",
            "French (Français)", "Italian (Italiano)",
        ])
        self.language.setMinimumWidth(180)
        sc.addWidget(self.language)
        sc.addSpacing(8)
        ll_emo = QLabel("Emotions")
        ll_emo.setObjectName("FieldLabel")
        sc.addWidget(ll_emo)
        self.emotions_toggle = QComboBox()
        self.emotions_toggle.addItems(["Off", "AI-generated per segment"])
        self.emotions_toggle.setMinimumWidth(180)
        sc.addWidget(self.emotions_toggle)
        sc.addStretch(1)
        v.addWidget(settings_card)

        # ── Process row ───────────────────────────────────────────────────
        process_row = QHBoxLayout()
        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("FloatCounter")
        process_row.addWidget(self.status_lbl)

        self.restore_btn = QPushButton("Restore last session")
        self.restore_btn.setObjectName("GhostBtn")
        self.restore_btn.setCursor(Qt.PointingHandCursor)
        self.restore_btn.setVisible(False)
        self.restore_btn.clicked.connect(self._restore_log)
        process_row.addWidget(self.restore_btn)

        process_row.addStretch(1)

        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setObjectName("GhostBtn")
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn.clicked.connect(self._reset)
        process_row.addWidget(self.reset_btn)

        self.process_btn = QPushButton("Build")
        self.process_btn.setObjectName("PrimaryBtn")
        self.process_btn.setStyleSheet(primary_button_style(TOOL_ACCENTS["animator"]))
        self.process_btn.setCursor(Qt.PointingHandCursor)
        self.process_btn.setIcon(svg_icon("sparkles", IRIS_FG, 15))
        self.process_btn.setLayoutDirection(Qt.RightToLeft)
        self.process_btn.clicked.connect(self._on_process)
        process_row.addWidget(self.process_btn)
        v.addLayout(process_row)

        # ── Segments card (hidden until first successful build) ────────────
        self.segments_card = Card()
        pv = QVBoxLayout(self.segments_card)
        pv.setContentsMargins(14, 12, 14, 12)
        pv.setSpacing(8)
        seg_head = QHBoxLayout()
        ptl = QLabel("SEGMENTS")
        ptl.setObjectName("SectionLabel")
        seg_head.addWidget(ptl)
        self.count_lbl = QLabel("0")
        self.count_lbl.setObjectName("SectionCount")
        seg_head.addWidget(self.count_lbl)
        seg_head.addStretch(1)
        self.customize_btn = QPushButton("Customize")
        self.customize_btn.setObjectName("GhostBtn")
        self.customize_btn.setCursor(Qt.PointingHandCursor)
        self.customize_btn.setIcon(svg_icon("sliders", TEXT_DIM, 13))
        self.customize_btn.clicked.connect(self._toggle_customize)
        seg_head.addWidget(self.customize_btn)
        self.open_panel_btn = QPushButton("Open floating window")
        self.open_panel_btn.setObjectName("SecondaryBtn")
        self.open_panel_btn.setCursor(Qt.PointingHandCursor)
        self.open_panel_btn.setIcon(chevron_icon("right", TEXT, 12))
        self.open_panel_btn.setLayoutDirection(Qt.RightToLeft)
        self.open_panel_btn.setEnabled(False)
        self.open_panel_btn.clicked.connect(self._open_panel)
        seg_head.addWidget(self.open_panel_btn)
        pv.addLayout(seg_head)
        self.segments_view = QPlainTextEdit()
        self.segments_view.setReadOnly(True)
        self.segments_view.setObjectName("Console")
        self.segments_view.setPlaceholderText("Segments appear here after processing.")
        self.segments_view.setFixedHeight(120)
        pv.addWidget(self.segments_view)
        self.segments_card.setVisible(False)
        v.addWidget(self.segments_card, 2)

        # ── Customize card (hidden until "Customize" clicked) ──────────────
        self.customize_card = Card()
        cv = QVBoxLayout(self.customize_card)
        cv.setContentsMargins(14, 12, 14, 12)
        cv.setSpacing(8)
        cust_head = QHBoxLayout()
        ctl = QLabel("CUSTOMIZE")
        ctl.setObjectName("SectionLabel")
        cust_head.addWidget(ctl)
        cust_head.addStretch(1)
        self.refine_status_lbl = QLabel("")
        self.refine_status_lbl.setObjectName("FloatCounter")
        cust_head.addWidget(self.refine_status_lbl)
        self.refine_btn = QPushButton("Re-elaborate with Gemini")
        self.refine_btn.setObjectName("PrimaryBtn")
        self.refine_btn.setStyleSheet(primary_button_style(TOOL_ACCENTS["animator"]))
        self.refine_btn.setCursor(Qt.PointingHandCursor)
        self.refine_btn.setIcon(svg_icon("sparkles", IRIS_FG, 14))
        self.refine_btn.setLayoutDirection(Qt.RightToLeft)
        self.refine_btn.clicked.connect(self._on_refine)
        cust_head.addWidget(self.refine_btn)
        cv.addLayout(cust_head)

        cust_hint = QLabel("Add a note per segment — scene context, talent action, extra direction.")
        cust_hint.setObjectName("FieldLabel")
        cv.addWidget(cust_hint)

        # Scroll area for the dynamic per-segment rows
        self.seg_scroll = QScrollArea()
        self.seg_scroll.setWidgetResizable(True)
        self.seg_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.seg_scroll.setFrameShape(QFrame.NoFrame)
        self.seg_scroll.setMinimumHeight(80)
        self.seg_scroll.setMaximumHeight(180)
        self._seg_rows_widget = QWidget()
        self._seg_rows_layout = QVBoxLayout(self._seg_rows_widget)
        self._seg_rows_layout.setContentsMargins(0, 2, 0, 2)
        self._seg_rows_layout.setSpacing(6)
        self._seg_rows_layout.addStretch(1)
        self.seg_scroll.setWidget(self._seg_rows_widget)
        cv.addWidget(self.seg_scroll, 1)
        self.customize_card.setVisible(False)
        v.addWidget(self.customize_card, 2)

        # Check for a saved log — offer restore
        log = _animator_load_log()
        if log and isinstance(log.get("segments"), list) and log["segments"]:
            self.restore_btn.setVisible(True)
            ts = log.get("timestamp", "")
            if ts:
                self.restore_btn.setToolTip(f"Last session: {ts}")

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _language_name(self) -> str:
        return self.LANG_NAMES[self.language.currentIndex()]

    def _set_status(self, text: str, ok: bool = False, err: bool = False):
        color = OK_COLOR if ok else (ERR_COLOR if err else TEXT_DIM)
        self.status_lbl.setText(text)
        self.status_lbl.setStyleSheet(
            f"color: {color}; background: transparent; font-size: 11.5px;"
        )

    def _set_refine_status(self, text: str, ok: bool = False, err: bool = False):
        color = OK_COLOR if ok else (ERR_COLOR if err else TEXT_DIM)
        self.refine_status_lbl.setText(text)
        self.refine_status_lbl.setStyleSheet(
            f"color: {color}; background: transparent; font-size: 11.5px;"
        )

    # ── Build flow ────────────────────────────────────────────────────────────

    def _on_process(self):
        if self._thread is not None:
            return
        raw = self.script_input.toPlainText().strip()
        if not raw:
            self._set_status("Paste a script first.", err=True)
            return
        key = read_env_value("GEMINI_API_KEY")
        if not key:
            self._set_status("No Gemini key — set it in Settings.", err=True)
            return

        with_emotions = self.emotions_toggle.currentIndex() == 1
        language_name = self._language_name()
        prompt = _animator_segmenter_prompt(raw, language_name, with_emotions)

        self._set_status("Calling Gemini — splitting into segments…")
        self.process_btn.setEnabled(False)
        self.process_btn.setText("Building…")

        thread = QThread(self)
        worker = GeminiSegmenterWorker(key, prompt)
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
        self.process_btn.setText("Rebuild")
        self.process_btn.setEnabled(True)

    @Slot(list)
    def _on_gemini_done(self, segments: list):
        self.segments = segments
        self.count_lbl.setText(str(len(segments)))
        self.open_panel_btn.setEnabled(True)
        self.customize_card.setVisible(False)
        self._note_fields = []
        self._populate_segments_view(segments)
        self.segments_card.setVisible(True)
        self._set_status(
            f"Done — {len(segments)} segment{'s' if len(segments) != 1 else ''}.", ok=True
        )
        lang = self._language_name()
        with_emo = self.emotions_toggle.currentIndex() == 1
        _animator_save_log(segments, lang, with_emo, self.script_input.toPlainText())
        self.restore_btn.setVisible(False)

    @Slot(str)
    def _on_gemini_failed(self, err: str):
        self.segments = []
        self.segments_view.setPlainText(f"✗ Gemini error\n{err}")
        self.segments_card.setVisible(True)
        self.open_panel_btn.setEnabled(False)
        self._set_status("Failed.", err=True)

    def _populate_segments_view(self, segments: list):
        lines = []
        for s in segments:
            tag = f"[{s['duration']:>2}s] {s['label']:<8}"
            extras = ""
            if s.get("emotion"):
                extras += f"  · {s['emotion']}"
            if s.get("video_prompt"):
                extras += "  ✓"
            lines.append(f"{tag}  {s['text']}{extras}")
        self.segments_view.setPlainText("\n".join(lines))

    # ── Customize / refine ────────────────────────────────────────────────────

    def _toggle_customize(self):
        if not self.segments:
            return
        if not self.customize_card.isVisible():
            self._build_customize_rows()
            self.customize_card.setVisible(True)
        else:
            self.customize_card.setVisible(False)

    def _build_customize_rows(self):
        # Remove old rows (keep the trailing stretch)
        while self._seg_rows_layout.count() > 1:
            item = self._seg_rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._note_fields = []

        for seg in self.segments:
            row = QFrame()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(4, 3, 4, 3)
            rl.setSpacing(10)

            chip = QLabel(f"{seg['label']}  {seg['duration']}s")
            chip.setObjectName("FloatChip")
            chip.setFixedWidth(70)
            chip.setAlignment(Qt.AlignCenter)
            rl.addWidget(chip)

            snippet_text = seg["text"]
            snippet = QLabel(snippet_text[:42] + ("…" if len(snippet_text) > 42 else ""))
            snippet.setObjectName("FieldLabel")
            snippet.setFixedWidth(155)
            snippet.setToolTip(snippet_text)
            rl.addWidget(snippet)

            note_field = QLineEdit()
            note_field.setPlaceholderText("Scene, action, extra direction…")
            note_field.setText(seg.get("user_note", ""))
            rl.addWidget(note_field, 1)

            self._note_fields.append((seg["label"], note_field))
            self._seg_rows_layout.insertWidget(
                self._seg_rows_layout.count() - 1, row
            )

    def _collect_user_notes(self) -> list[dict]:
        note_map = {lbl: field.text().strip() for lbl, field in self._note_fields}
        updated = []
        for seg in self.segments:
            s = dict(seg)
            note = note_map.get(seg["label"], "")
            if note:
                s["user_note"] = note
            else:
                s.pop("user_note", None)
            updated.append(s)
        return updated

    def _on_refine(self):
        if self._refine_thread is not None:
            return
        if not self.segments:
            return
        key = read_env_value("GEMINI_API_KEY")
        if not key:
            self._set_refine_status("No Gemini key.", err=True)
            return
        updated_segments = self._collect_user_notes()
        self.segments = updated_segments
        language_name = self._language_name()
        prompt = _animator_refine_prompt(updated_segments, language_name)

        self._set_refine_status("Re-elaborating…")
        self.refine_btn.setEnabled(False)
        self.refine_btn.setText("Re-elaborating…")

        thread = QThread(self)
        worker = GeminiRefineWorker(key, prompt, updated_segments)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_refine_done)
        worker.failed.connect(self._on_refine_failed)
        worker.done.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_refine_finished)
        self._refine_thread = thread
        self._refine_worker = worker
        thread.start()

    def _on_refine_finished(self):
        self._refine_thread = None
        self._refine_worker = None
        self.refine_btn.setText("Re-elaborate with Gemini")
        self.refine_btn.setEnabled(True)

    @Slot(list)
    def _on_refine_done(self, segments: list):
        self.segments = segments
        n_prompts = sum(1 for s in segments if s.get("video_prompt"))
        self._set_refine_status(f"Done — {n_prompts} prompts generated.", ok=True)
        self._populate_segments_view(segments)
        lang = self._language_name()
        with_emo = self.emotions_toggle.currentIndex() == 1
        _animator_save_log(segments, lang, with_emo, self.script_input.toPlainText())
        if self._panel is not None:
            try:
                self._panel.update_segments(segments)
            except Exception:
                pass

    @Slot(str)
    def _on_refine_failed(self, err: str):
        self._set_refine_status(f"Failed: {err[:80]}", err=True)

    # ── Panel ─────────────────────────────────────────────────────────────────

    def _open_panel(self):
        if not self.segments:
            return
        if self._note_fields:
            self.segments = self._collect_user_notes()
        if self._panel is not None:
            try:
                self._panel.close()
            except Exception:
                pass
            self._panel = None
        self._panel = AnimatorFloatPanel(
            segments=self.segments,
            language_name=self._language_name(),
        )
        self._panel.closed.connect(self._on_panel_closed)
        self._panel.show()

    def _on_panel_closed(self):
        self._panel = None

    # ── Log restore ───────────────────────────────────────────────────────────

    def _restore_log(self):
        log = _animator_load_log()
        if not log or not isinstance(log.get("segments"), list):
            self.restore_btn.setVisible(False)
            return
        self.segments = log["segments"]
        lang = log.get("language", "German")
        if lang in self.LANG_NAMES:
            self.language.setCurrentIndex(self.LANG_NAMES.index(lang))
        self.emotions_toggle.setCurrentIndex(1 if log.get("with_emotions") else 0)
        script = log.get("script", "")
        if script:
            self.script_input.setPlainText(script)
        self.count_lbl.setText(str(len(self.segments)))
        self._populate_segments_view(self.segments)
        self.segments_card.setVisible(True)
        self.open_panel_btn.setEnabled(True)
        self.restore_btn.setVisible(False)
        self._set_status(
            f"Restored {len(self.segments)} segments from last session.", ok=True
        )

    # ── Reset ─────────────────────────────────────────────────────────────────

    def _reset(self):
        self.script_input.clear()
        self.segments_view.clear()
        self.segments = []
        self.segments_card.setVisible(False)
        self.customize_card.setVisible(False)
        self.open_panel_btn.setEnabled(False)
        self.count_lbl.setText("0")
        self._note_fields = []
        self.process_btn.setText("Build")
        self._set_status("")
        self._set_refine_status("")
        if self._panel:
            self._panel.close()
        log = _animator_load_log()
        if log and isinstance(log.get("segments"), list) and log["segments"]:
            self.restore_btn.setVisible(True)

