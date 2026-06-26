#!/usr/bin/env python3
"""PROTOTYPE — Approach B: Gemini-based caption QA pass.

Compares FINISHED captions (an .srt) against the source BRIEFING (the Notion
script) and flags likely WhisperX mistranscriptions: words faithfully transcribed
from misspoken audio, garbled brand/technical terms, wrong words that slipped past
because Whisper hears exactly what was said. The briefing is the source of truth,
but it also contains NON-SPOKEN stage directions (whiteboard layouts, parenthetical
notes) — the model is told to ignore those and only judge the spoken voiceover.

Unlike the old browser SRT-checker this does NOT do a literal token diff (which
floods on stage directions and breaks on German umlauts). It asks Gemini, which
understands what is spoken vs a production note and knows domain vocabulary.

EXPERIMENTAL / DISCARDABLE: lives OUTSIDE the production pipeline (caption.py is
untouched) on its own git branch. To revert: delete this file or drop the branch.
Not wired into the app yet — run it standalone:

    ../../venv/bin/python caption_qa.py <captions.srt> <briefing.txt> [--language de]

Reuses caption.py's Gemini plumbing (.env loading, retry/backoff, JSON parsing).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Reuse the existing Gemini infrastructure + .env loading from caption.py.
# Importing caption.py runs its top-level .env loader, so GEMINI_API_KEY /
# CAPTION_BRAND / CAPTION_TERMS are picked up exactly as in production.
import caption


# --------------------------------------------------------------------------- #
# SRT parsing (caption.py writes SRT but never reads it back, so we parse here) #
# --------------------------------------------------------------------------- #
_TIME_RE = re.compile(
    r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})"
)


def parse_srt(text: str) -> list:
    """Parse an .srt into [{idx, start, end, text}]. `text` is the caption with
    its internal line break flattened to a single space (the voiceover content is
    what we judge, not the on-screen layout)."""
    text = text.replace("﻿", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    out = []
    for block in re.split(r"\n\s*\n", text):
        lines = [l for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        i = 0
        idx = None
        if lines[0].strip().isdigit():
            idx = lines[0].strip()
            i = 1
        if i >= len(lines) or not _TIME_RE.search(lines[i]):
            continue
        m = _TIME_RE.search(lines[i])
        start, end = m.group(1), m.group(2)
        body = "\n".join(lines[i + 1:])
        body = re.sub(r"<[^>]+>", "", body)
        body = caption.join_soft_hyphens(body)   # undo "Schilddrüsen-\nhormone" line splits
        body = re.sub(r"\s+", " ", body).strip()
        out.append({
            "idx": idx or str(len(out) + 1),
            "start": start,
            "end": end,
            "text": body,
        })
    return out


# --------------------------------------------------------------------------- #
# The QA pass                                                                  #
# --------------------------------------------------------------------------- #
def _build_qa_prompt(captions: list, briefing: str, language: str) -> str:
    name = caption.LANGUAGE_META.get(language, {}).get("name", language)
    listing = "\n".join(f"[{i}] {c}" for i, c in enumerate(captions))
    last = len(captions) - 1

    # Canonical brand/domain spellings, if configured — gives the model the
    # correct target for terms it might otherwise not know (miavola, L-Thyroxin).
    canon = caption._canonical_terms() if hasattr(caption, "_canonical_terms") else []
    canon_line = (
        f"\nKNOWN CORRECT SPELLINGS (a caption that garbles one of these is an error): "
        f"{', '.join(canon)}.\n" if canon else ""
    )

    return f"""You are a meticulous QA reviewer for {name} TikTok captions.

The CAPTIONS below were produced by automatic speech recognition (WhisperX) of a
voiceover. ASR transcribes exactly what it HEARS, so when the speaker misspoke, or
a brand / technical / medical term was mis-heard, the wrong word silently entered
the captions. Your job: find those LIKELY MISTRANSCRIPTIONS.

The BRIEFING is the script the voiceover was based on — your source of truth for
the intended words and the correct spelling of names and terms.
{canon_line}
CRITICAL RULES:
- The briefing contains NON-SPOKEN STAGE DIRECTIONS: parenthetical notes, whiteboard
  layouts, instructions to the editor ("steht an dem Whiteboard…", "(Das Blatt
  aufdecken)", arrows, diagrams). These are NEVER spoken. IGNORE them completely —
  a word missing from the captions because it was only a stage direction is NOT an error.
- The voiceover may legitimately differ from the briefing (improvisation, reordering,
  dropped filler). Do NOT flag a paraphrase or a legitimately different-but-valid word.

Flag these kinds of issue (and ONLY these). Give each a "type":
- "spelling"  — a garbled/misspelled word, or a mangled brand/technical/medical term
                or name (compare against the briefing's correct spelling).
- "wrong-word"— a different word that sounds like the intended one (ASR soundalike),
                e.g. "Lieber" for "Leber".
- "capitalization" — a German capitalization error: a noun or proper name written
                lowercase, or a word clearly wrongly capitalized. IMPORTANT house-style
                caveat: these captions DELIBERATELY lowercase the FIRST word of a
                fragment when it is a function word (article, pronoun, preposition,
                conjunction, adverb, verb) — that is CORRECT, do NOT flag it. Only flag
                genuinely wrong German casing (a common noun or proper name that should
                be capital but isn't, anywhere in the caption). Only report it if your
                corrected casing actually DIFFERS from what is already in the caption.
- "missing"   — a word that was clearly SPOKEN (it appears in the spoken briefing text)
                but is ABSENT from the captions, AND whose omission makes the caption
                grammatically broken or changes the meaning — especially a NEGATION
                ("nicht", "kein", "ohne") or a key noun/verb. Put the word to add in
                "suggestion" and a short slice of the caption where it belongs in "suspect".
                STRICT: do NOT flag a word that only appears in a stage direction, a
                dropped filler, or anything covered by normal paraphrasing — only a
                genuine, meaning-changing omission of spoken content.
- When unsure, DO NOT flag it — favour precision over recall.
- Do NOT flag punctuation or line-break differences.

CAPTIONS (numbered):
{listing}

BRIEFING (source of truth; contains stage directions to ignore):
\"\"\"
{briefing}
\"\"\"

Return a JSON array (possibly empty) of findings, each an object:
{{"caption": <int 0..{last}>, "type": "spelling"|"wrong-word"|"capitalization"|"missing"|"other", "suspect": "<the wrong word/phrase exactly as it appears in the caption>", "suggestion": "<the corrected/missing word, or null if unknown>", "confidence": "high"|"medium"|"low", "reason": "<short, why it looks wrong>"}}
Return ONLY the JSON array, nothing else."""


def qa_check(captions: list, briefing: str, language: str = "de") -> list:
    """Ask Gemini to flag likely mistranscriptions. Returns a cleaned list of
    finding dicts (validated + clamped to real caption indices), or [] on no
    findings / any failure."""
    if not captions or not briefing.strip():
        return []
    data = caption._call_gemini(_build_qa_prompt(captions, briefing, language))
    if not isinstance(data, list):
        print("QA pass: no usable response from Gemini.")
        return []

    cleaned = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            ci = int(item.get("caption"))
        except (TypeError, ValueError):
            ci = None
        suspect = item.get("suspect")
        if not isinstance(suspect, str) or not suspect.strip():
            continue
        if ci is None or ci < 0 or ci >= len(captions):
            ci = None  # keep the finding but mark its anchor unknown
        conf = item.get("confidence")
        if conf not in ("high", "medium", "low"):
            conf = "low"
        ftype = item.get("type")
        if ftype not in ("spelling", "wrong-word", "capitalization", "missing", "other"):
            ftype = "other"
        sugg = item.get("suggestion")
        cleaned.append({
            "caption": ci,
            "type": ftype,
            "suspect": suspect.strip(),
            "suggestion": sugg.strip() if isinstance(sugg, str) and sugg.strip() else None,
            "confidence": conf,
            "reason": (item.get("reason") or "").strip(),
        })

    # Deterministic precision guards — the model is noisy on these dimensions, so
    # we never trust its self-consistency. Drop a finding when:
    #   * (non-missing) its "suspect" isn't actually present in the cited caption
    #     — kills hallucinated words (e.g. an invented typo that isn't there);
    #   * (non-missing) the suggestion equals the suspect — a no-op "fix";
    #   * (missing) the supposedly-missing word is already in the caption.
    filtered = []
    for fnd in cleaned:
        ci = fnd["caption"]
        cap = captions[ci] if isinstance(ci, int) and 0 <= ci < len(captions) else ""
        susp, sugg, typ = fnd["suspect"], fnd["suggestion"], fnd["type"]
        if typ == "missing":
            if not sugg:
                continue
            if cap and sugg.lower() in cap.lower():
                continue  # not actually missing
        else:
            if cap and susp.lower() not in cap.lower():
                continue  # suspect not in the caption → hallucination / mis-citation
            if sugg is not None and sugg.strip() == susp.strip():
                continue  # no-op correction
        filtered.append(fnd)
    return filtered


# --------------------------------------------------------------------------- #
# CLI harness                                                                  #
# --------------------------------------------------------------------------- #
_CONF_ORDER = {"high": 0, "medium": 1, "low": 2}


def main() -> None:
    import json as _json
    ap = argparse.ArgumentParser(description="PROTOTYPE caption QA vs briefing (Gemini).")
    ap.add_argument("srt", help="Path to the captions .srt")
    ap.add_argument("briefing", help="Path to the briefing/script text file")
    ap.add_argument("--language", default="de", choices=["de", "en", "es", "fr", "it"])
    ap.add_argument("--json", action="store_true",
                    help="Emit {cues, findings} as JSON on stdout (used by the app).")
    args = ap.parse_args()

    srt_path = Path(args.srt).expanduser()
    brief_path = Path(args.briefing).expanduser()
    if not srt_path.exists():
        sys.exit(f"SRT not found: {srt_path}")
    if not brief_path.exists():
        sys.exit(f"Briefing not found: {brief_path}")

    cues = parse_srt(srt_path.read_text(encoding="utf-8"))
    captions = [c["text"] for c in cues]
    briefing = brief_path.read_text(encoding="utf-8")

    if args.json:
        # Machine mode for the app: stdout MUST be pure JSON. The Gemini helpers
        # print diagnostics (retry/error notices) that would otherwise prefix and
        # corrupt it — route those to stderr while computing, then emit only JSON.
        import contextlib
        with contextlib.redirect_stdout(sys.stderr):
            findings = qa_check(captions, briefing, language=args.language)
        sys.stdout.write(_json.dumps({"cues": cues, "findings": findings}))
        return

    print(f"Parsed {len(cues)} cues. Asking Gemini to flag mistranscriptions…\n")

    findings = qa_check(captions, briefing, language=args.language)
    if not findings:
        print("No likely mistranscriptions flagged. ✅")
        return

    findings.sort(key=lambda f: (_CONF_ORDER.get(f["confidence"], 3),
                                 f["caption"] if f["caption"] is not None else 1e9))
    print(f"{len(findings)} possible issue(s):\n")
    for f in findings:
        ci = f["caption"]
        loc = f"#{cues[ci]['idx']} [{cues[ci]['start']}]" if ci is not None else "#?"
        ctx = cues[ci]["text"] if ci is not None else ""
        arrow = f'  →  "{f["suggestion"]}"' if f["suggestion"] else "  (no suggestion)"
        print(f"[{f['confidence'].upper():6}] {f['type']:14} {loc}")
        if ctx:
            print(f"         caption : {ctx}")
        print(f'         suspect : "{f["suspect"]}"{arrow}')
        if f["reason"]:
            print(f"         reason  : {f['reason']}")
        print()


if __name__ == "__main__":
    main()
