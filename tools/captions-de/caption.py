#!/usr/bin/env python3
"""
Generate TikTok-style German captions (SRT) from a video file.

Usage:
    python caption.py video.mp4
    python caption.py video.mp4 --out custom_name.srt
    python caption.py video.mp4 --no-ai           # skip Gemini, use heuristic only
    python caption.py video.mp4 --model medium    # use smaller Whisper model
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Windows consoles default to the legacy cp1252 codec, which can't encode the
# non-ASCII characters we print (arrows, accented language names, …). Force
# UTF-8 on our own streams so output never crashes mid-job, regardless of how
# the script was launched (app or shell).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

_SCRIPT_DIR = Path(__file__).resolve().parent
_ENV_PATH = _SCRIPT_DIR / ".env"
if _ENV_PATH.exists():
    for _line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        _k = _k.strip()
        _v = _v.strip().strip('"').strip("'")
        if _k and _v and _k not in os.environ:
            os.environ[_k] = _v

LINE_MAX = 20
LEAD_MAX = 0.150
TRAIL_MIN = 0.0

# ─── Real-screen line width model ────────────────────────────────────────────
# The .srt is rendered as a CapCut-style caption: bold black text on a white
# rounded box, centred, 1–2 lines, on a 9:16 / 4:5 vertical video. Measuring
# rendered boxes in a finished video (720-px-wide frame) gave a clean fit:
# box width ≈ 26 px per "width unit" + ~15 px padding/side, and the style wraps
# once a line passes ~80% of frame width — the widest rendered lines were
# "Stoffwechsel wieder läuft" (25 chars) and "Behandlungs-regeln für die"
# (26 chars), both ≈ 21 units. So we budget a line by *real width*, not by raw
# character count: narrow German letters (i, l, t, r, f, …) cost ~half a wide
# letter (m, w), and a line of 25–26 average chars fits where 20 was the old,
# too-conservative cap.
NARROW_CHARS = set("iIlj.,'!:;|ftr ()[]-")
WIDE_CHARS = set("mwMW—")
LINE_W_MAX = 22.5     # max width units on one visible line (~84% of frame width)
ORPHAN_W_MAX = 7.0    # a single word this narrow is too short to stand alone


def text_width(s: str) -> float:
    """Approximate the rendered width of a string in proportional "units"
    (1.0 ≈ one average glyph). Used everywhere a raw len() used to gate the
    line length, so packing reflects real on-screen space."""
    total = 0.0
    for c in s:
        if c in NARROW_CHARS:
            total += 0.5
        elif c in WIDE_CHARS:
            total += 1.4
        else:
            total += 1.0
    return total

# Closed-class German function words for the TikTok house-style "lowercase even
# at caption start" rule (used by normalize_case). Intentionally EVERGREEN: only
# closed classes (articles, pronouns, possessives, demonstratives, question /
# relative words, conjunctions, prepositions, modal & auxiliary verbs, and
# function particles/adverbs). Open-class words — nouns, lexical verbs,
# adjectives — are deliberately NOT listed: German grammar already lowercases
# them and the Gemini prompt (rule V) enforces it, so enumerating them would
# only overfit to one video's vocabulary.
GERMAN_LOWERCASE = {
    # articles & negation determiners
    "der","die","das","den","dem","des","ein","eine","einen","einem","eines","einer",
    "kein","keine","keinen","keinem","keiner","keines",
    # personal pronouns
    "ich","du","er","es","wir","sie","man",
    "mich","dich","sich","mir","dir","ihm","ihn","uns","euch","ihnen",
    # possessive pronouns
    "mein","meine","meinen","meinem","meiner","meines",
    "dein","deine","deinen","deinem","deiner","deines",
    "sein","seine","seinen","seinem","seiner","seines",
    "ihr","ihre","ihren","ihrem","ihrer","ihres",
    "unser","unsere","unseren","unserem","unserer","unseres",
    "euer","eure","euren","eurem","eurer","eures",
    # demonstratives & quantifying determiners
    "diese","dieser","dieses","diesen","diesem",
    "jene","jener","jenes","jenen","jenem",
    "alle","allen","aller","allem","beide","beiden",
    "manche","mancher","manches","manchen","manchem",
    "einige","einiger","einigen","mehrere","mehreren",
    "viel","viele","vielen","wenig","wenige","selber","selbst",
    # question / relative words
    "wer","wen","wem","was","wie","wo","wann","warum","wieso","weshalb",
    "welche","welcher","welches","welchen","welchem","wohin","woher",
    "worüber","worauf","wozu","wofür","womit",
    # conjunctions
    "und","oder","aber","denn","doch","sondern","weil","dass","wenn","als","ob",
    "obwohl","während","bevor","nachdem","damit","sodass","falls","sofern","indem",
    # prepositions & contracted prepositions
    "an","auf","aus","bei","durch","für","gegen","in","mit","nach","ohne",
    "seit","über","um","unter","vor","zu","zwischen","zum","zur","vom",
    "ins","ans","aufs","beim","im","am",
    # da-/wo- pronominal adverbs
    "dadurch","dafür","davon","darum","dabei","dazu","daran","darauf","darin",
    # function particles / adverbs
    "ja","nein","nicht","auch","nur","schon","noch","immer","nie","niemals",
    "dann","jetzt","hier","da","dort","heute","gestern","morgen","bitte","danke",
    "also","zwar","eben","halt","mal","wohl","etwa","etwas","alles","nichts",
    "vielleicht","natürlich","leider","endlich","trotzdem","einfach",
    "sehr","ganz","ziemlich","so","wirklich","überhaupt","sogar","gerade",
    "mehr","weniger","meist","genug","wieder","oft","manchmal","fast","kaum","gleich",
    # auxiliary & modal verbs
    "bin","bist","ist","sind","seid","war","warst","waren","wart","sei","wäre","wären",
    "habe","hast","hat","haben","habt","hatte","hattest","hatten","hattet","hätte","hätten",
    "werde","wirst","wird","werden","werdet","wurde","wurden","würde","würden",
    "kann","kannst","können","könnt","konnte","konnten","könnte","könnten",
    "muss","musst","müssen","müsst","musste","mussten",
    "darf","darfst","dürfen","dürft","durfte","durften",
    "soll","sollst","sollen","sollt","sollte","sollten",
    "will","willst","wollen","wollt","wollte","wollten",
    "mag","magst","mögen","mögt","möchte","möchten",
}

# Optional per-project overrides to hyphenate specific long words at a chosen
# boundary. Empty by default (evergreen) — auto_hyphenate falls back to the
# generic compound-prefix split below.
FORCE_HYPHEN: dict = {}

# First-elements used to hyphenate an over-long German compound at a meaningful
# boundary ("Geschwindigkeits-begrenzung"). A mix of GENERIC high-frequency
# German compound stems (so this works for any video) plus the brand's health
# domain (intentional — the brand is thyroid-focused). It only ever affects
# words longer than one line, so extra entries are harmless.
COMPOUND_PREFIXES = [
    # generic high-frequency German compound first-elements
    "Lebens", "Arbeits", "Zukunfts", "Sicherheits", "Wirtschafts",
    "Gesellschafts", "Geschwindigkeits", "Versicherungs", "Verantwortungs",
    "Erfahrungs", "Behandlungs", "Untersuchungs", "Entscheidungs",
    "Ernährungs", "Bewegungs", "Gewohnheits", "Bedürfnis",
    "Haupt", "Grund", "Gesamt", "Gemeinschafts",
    # health / brand domain (thyroid)
    "Gesundheits", "Schilddrüsen", "Schilddrüse", "Stoffwechsel",
    "Stoffwechselstörung", "Umwandlungs", "Umwandlung",
    "Wassereinlag", "Wasserein", "Konzentrations", "Konzentration",
    "Hormon", "Hormonhaushalt", "Gewichts", "Gewichtsverlust",
    "Gewichtszunahme", "Blutdruck", "Antriebs", "Energie",
    "Magen", "Darm", "Leber", "Nieren", "Knochen", "Gelenks", "Muskel", "Herz",
    "Hashimoto",
]


def auto_hyphenate(word: str) -> str:
    if "\n" in word or len(word) <= LINE_MAX - 4:
        return word
    if word in FORCE_HYPHEN:
        return FORCE_HYPHEN[word]
    if "-" in word:
        return word
    for prefix in sorted(COMPOUND_PREFIXES, key=len, reverse=True):
        for cand in (prefix, prefix.lower()):
            if word.startswith(cand) and len(word) > len(cand) + 4:
                return word[:len(cand)] + "-" + word[len(cand):]
    return word


def apply_auto_hyphenation(text: str) -> str:
    if ACTIVE_LANG != "de":
        return text
    parts = []
    for chunk in text.split("\n"):
        words = chunk.split()
        words = [auto_hyphenate(w) for w in words]
        parts.append(" ".join(words))
    return "\n".join(parts)


def strip_punct(w: str) -> str:
    # \w in UNICODE mode covers letters from all the languages we care about
    # (ä, é, ñ, à, ç, ü, ...).
    return re.sub(r"[^\w'\-]", "", w, flags=re.UNICODE)


def clean_for_output(w: str) -> str:
    # Allow Unicode word characters + the punctuation we want to preserve.
    # ¿¡ kept for Spanish; everything else common across DE/EN/ES/FR/IT.
    return re.sub(r'[^\w\'\-?%/&"¿¡]', "", w, flags=re.UNICODE)


# Active language is set by main() at startup. Default is German so existing
# call sites and tests behave as before.
ACTIVE_LANG = "de"

# Caption length mode, set by main() at startup. "hybrid" (default) is the
# long-standing behaviour: a natural mix of 1- and 2-line captions. "1" asks
# the segmenter for one line per caption (shorter, more numerous units); the
# packing safety nets are unchanged, so an indivisible unit that can't fit one
# line (e.g. a long German compound) still falls back to its required 2-line
# form. Default "hybrid" keeps existing call sites / tests bit-for-bit.
LINE_MODE = "hybrid"


def normalize_case(word: str) -> str:
    out = clean_for_output(word)
    if not out:
        return out
    # German-only: lowercase function words even at the start of a caption
    # (TikTok-German house style).
    if ACTIVE_LANG == "de":
        lookup = strip_punct(word)
        if lookup and lookup.lower() in GERMAN_LOWERCASE and out[0].isupper():
            return out[0].lower() + out[1:]
    return out


def insert_compound_hyphens(text: str) -> str:
    # Compound-noun hyphenation is a German-specific concern. Other languages
    # don't have the long-compound problem and shouldn't get auto-hyphens.
    if ACTIVE_LANG != "de":
        return text
    return " ".join(auto_hyphenate(w) for w in text.split())


def tokenize_for_packing(text: str):
    tokens = []
    for word in text.split():
        parts = re.findall(r"[^-]+-?", word)
        merged = []
        for p in parts:
            if merged and merged[-1].endswith("-") and len(merged[-1].rstrip("-")) < 5:
                merged[-1] += p
            else:
                merged.append(p)
        for j, p in enumerate(merged):
            sep = " " if j == len(merged) - 1 else ""
            tokens.append((p, sep))
    return tokens


def pack_lines(text: str) -> str:
    if text_width(text) <= LINE_W_MAX:
        return text
    tokens = tokenize_for_packing(text)
    n = len(tokens)
    if n < 2:
        return text

    def build(start, end):
        out = ""
        for i in range(start, end):
            t, s = tokens[i]
            out += t
            if i < end - 1:
                out += s
        return out

    strict, relaxed = [], []
    for split in range(1, n):
        a = build(0, split).rstrip()
        b = build(split, n).rstrip()
        wa, wb = text_width(a), text_width(b)
        max_w = max(wa, wb)
        diff = abs(wa - wb)
        if max_w <= LINE_W_MAX:
            strict.append((a, b, diff))
        elif max_w <= LINE_W_MAX * 1.35:
            relaxed.append((a, b, diff))

    pool = strict or relaxed
    if pool:
        pool.sort(key=lambda x: x[2])
        return pool[0][0] + "\n" + pool[0][1]

    lines, current = [], ""
    for t, sep in tokens:
        prospective = (current + t).rstrip()
        if not current:
            current = t + sep
        elif text_width(prospective) <= LINE_W_MAX:
            current += t + sep
        else:
            lines.append(current.rstrip())
            current = t + sep
    if current:
        lines.append(current.rstrip())
    return "\n".join(lines)


def format_caption(text: str) -> str:
    return pack_lines(insert_compound_hyphens(text))


def fmt_time(t: float) -> str:
    if t < 0:
        t = 0
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def get_video_duration(video_path: Path) -> float:
    result = subprocess.run(
        ["ffmpeg", "-i", str(video_path)],
        capture_output=True, text=True,
    )
    m = re.search(r"Duration:\s+(\d+):(\d+):(\d+\.\d+)", result.stderr)
    if not m:
        raise RuntimeError(f"Could not read duration from {video_path}")
    h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mi * 60 + s


def _is_apple_silicon() -> bool:
    """True on Apple Silicon hardware — even when this process is itself running
    translated under Rosetta (where platform.machine() lies and reports x86_64).
    hw.optional.arm64 reflects the CPU, not the running architecture."""
    try:
        out = subprocess.run(
            ["sysctl", "-in", "hw.optional.arm64"],
            capture_output=True, text=True,
        )
        return out.stdout.strip() == "1"
    except Exception:
        return False


def run_whisperx(video_path: Path, model: str, output_dir: Path,
                  language: str = "de") -> Path:
    whisperx_bin = shutil.which("whisperx")
    if not whisperx_bin:
        venv_whisperx = Path.home() / "whisperx" / "bin" / "whisperx"
        if venv_whisperx.exists():
            whisperx_bin = str(venv_whisperx)
        else:
            venv_whisperx = Path.home() / "whisperx" / "Scripts" / "whisperx.exe"
            if venv_whisperx.exists():
                whisperx_bin = str(venv_whisperx)
    if not whisperx_bin:
        sys.exit("Error: whisperx not found. Run install.py first.")

    print(f"Transcribing {video_path.name} with WhisperX ({model}, lang={language})...")
    cmd = [
        whisperx_bin, str(video_path),
        "--model", model,
        "--language", language,
        "--device", "cpu",
        "--compute_type", "int8",
        "--vad_method", "silero",
        "--output_format", "json",
        "--output_dir", str(output_dir),
    ]
    # The ~/whisperx interpreter is a *universal* binary, but torch is installed
    # arm64-only. If anything in our launch chain runs under Rosetta (a Terminal
    # opened with Rosetta, an x86_64 parent process, a stale "Open using Rosetta"
    # flag…), the universal python inherits that preference and starts as x86_64
    # -> torch's dylibs fail to load ("incompatible architecture, have arm64,
    # need x86_64"). Pin the encode to the native slice so it always matches the
    # installed torch. We probe the *hardware* via sysctl rather than
    # platform.machine(), because the latter reports "x86_64" when we ourselves
    # are running translated — exactly the case we need to catch.
    if sys.platform == "darwin" and _is_apple_silicon():
        cmd = ["arch", "-arm64", *cmd]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        sys.exit(
            "Error: WhisperX failed to load the model. If the log above shows "
            "'mkl_malloc: failed to allocate memory', the machine ran out of "
            "RAM for the large-v3 model — close other apps and try again, or "
            "use a machine with more memory (large-v3 needs ~3–4 GB free)."
        )
    # WhisperX writes <stem>.json. Move it to a per-language cache file so
    # switching the language doesn't reuse the wrong transcription.
    default_path = output_dir / (video_path.stem + ".json")
    target = output_dir / f"{video_path.stem}.{language}.json"
    if default_path.exists() and default_path != target:
        if target.exists():
            target.unlink()
        default_path.rename(target)
    if not target.exists():
        raise RuntimeError(f"WhisperX did not produce {target}")
    return target


def load_words(json_path: Path):
    data = json.load(open(json_path, encoding="utf-8"))
    words = []
    for seg in data["segments"]:
        for w in seg.get("words", []):
            if "start" in w and "end" in w:
                words.append(w)
    return words


# ─── Per-language Gemini prompts ─────────────────────────────────────────────
LANGUAGE_META = {
    "de": {"name": "German"},
    "en": {
        "name": "English",
        "aux_examples": '"has gone", "is making", "will run", "have been"',
        "modal_examples": '"can go", "should know", "must finish", "would help"',
        "neg_examples": '"never had", "didn\'t think", "no idea", "nothing left"',
        "prep_examples": '"with the doctor", "for people with", "in the city"',
        "art_examples": '"the problem", "a doctor", "this medicine", "my idea"',
        "idiom_examples": '"Brain Fog", "L-Tyroxin", "Health Journey", "Funfact"',
        "conjunctions": "and, but, or, so, because, when, if, while, although",
        "list_example": '"cold hands, brain fog, hair loss"',
        "capitalization": (
            "Standard English capitalization: capitalize proper nouns and the "
            "first word of a sentence. Mid-sentence captions can start lowercase "
            "if grammatically appropriate. Never capitalize random words."
        ),
        "punctuation_extra": "",
    },
    "es": {
        "name": "Spanish",
        "aux_examples": '"ha hecho", "está haciendo", "va a correr", "han ido"',
        "modal_examples": '"puede ir", "debería saber", "tengo que terminar"',
        "neg_examples": '"nunca tuve", "no pensé", "ninguna idea", "nada más"',
        "prep_examples": '"con el médico", "para personas con", "en la ciudad"',
        "art_examples": '"el problema", "una doctora", "estos medicamentos", "mi idea"',
        "idiom_examples": '"Brain Fog", "L-Tiroxina", "fun fact"',
        "conjunctions": "y, pero, o, porque, cuando, si, mientras, aunque",
        "list_example": '"manos frías, niebla mental, caída del cabello"',
        "capitalization": (
            "Standard Spanish capitalization: capitalize proper nouns and "
            "sentence starts only. Days, months, nationalities and languages "
            "stay lowercase. Don't capitalize words randomly."
        ),
        "punctuation_extra": ", inverted ¿ and ¡ at clause openings (only if they were spoken)",
    },
    "fr": {
        "name": "French",
        "aux_examples": '"a fait", "est allé", "va courir", "ont été"',
        "modal_examples": '"peut aller", "devrait savoir", "doit finir"',
        "neg_examples": '"n\'ai jamais", "pas du tout", "rien à faire"',
        "prep_examples": '"chez le médecin", "pour les gens avec", "dans la ville"',
        "art_examples": '"le problème", "une doctrice", "ces médicaments", "mon idée"',
        "idiom_examples": '"Brain Fog", "L-Thyroxine", "fun fact"',
        "conjunctions": "et, mais, ou, donc, parce que, quand, si, bien que",
        "list_example": '"mains froides, brouillard mental, perte de cheveux"',
        "capitalization": (
            "Standard French capitalization: capitalize proper nouns and "
            "sentence starts only. Days, months, nationalities and languages "
            "stay lowercase. Don't capitalize words randomly."
        ),
        "punctuation_extra": "",
    },
    "it": {
        "name": "Italian",
        "aux_examples": '"ha fatto", "è andato", "sta correndo", "sono stati"',
        "modal_examples": '"può andare", "dovrebbe sapere", "devo finire"',
        "neg_examples": '"non ho mai", "per niente", "nessuna idea"',
        "prep_examples": '"dal medico", "per le persone con", "in città"',
        "art_examples": '"il problema", "una dottoressa", "questi medicinali", "la mia idea"',
        "idiom_examples": '"Brain Fog", "L-Tiroxina", "fun fact"',
        "conjunctions": "e, ma, o, perché, quando, se, mentre, anche se",
        "list_example": '"mani fredde, nebbia mentale, caduta dei capelli"',
        "capitalization": (
            "Standard Italian capitalization: capitalize proper nouns and "
            "sentence starts only. Days, months, nationalities and languages "
            "stay lowercase. Don't capitalize words randomly."
        ),
        "punctuation_extra": "",
    },
}


def build_generic_prompt(lang_code: str, words: list, video_context: str) -> str:
    meta = LANGUAGE_META[lang_code]
    numbered = "\n".join(f"[{i}] {w['word']}" for i, w in enumerate(words))
    ctx_line = f"Context: {video_context}" if video_context else ""
    prompt = f"""You are a TikTok-style {meta['name']} caption editor. Split the transcription below into short, well-paced captions for a vertical 9:16 video.

LAYOUT (hard — CapCut renders captions at large font; lines wider than ~24 chars wrap awkwardly):
A. Group words into NATURAL caption units (a short clause / breath group, ~4–7 words). Render a unit on 1 line if it fits ~22 chars, else on 2 lines (literal "\\n"). Aim for a natural mix of 1- and 2-line captions — don't force one line, don't pad short units into two, and avoid 1–2 word fragments.
B. Each visible line: AT MOST ~24 characters (including spaces). Wide letters (m, w) take more room than narrow ones (i, l, t); keep wide-letter lines shorter.
C. Each caption: AT MOST ~48 characters total visible text.
D. NEVER break a word in the middle. Words stay intact.
E. A long single word (>24 chars) goes alone in its own caption.

INSEPARABLE SEMANTIC UNITS (these phrases MUST NEVER be split across a caption boundary OR across a "\\n" inside a caption — both apply equally):
F. Article / possessive / demonstrative + noun: e.g., {meta['art_examples']}. Never end a caption with an article, possessive or demonstrative.
G. Preposition + its noun phrase: e.g., {meta['prep_examples']}. Never end a caption with a preposition.
H. Adjective + noun, adverb + adjective/verb.
I. Auxiliary + participle: e.g., {meta['aux_examples']}.
J. Modal + infinitive: e.g., {meta['modal_examples']}.
K. Negation + element it negates: e.g., {meta['neg_examples']}.
L. Idiomatic units, product names and English borrowings: e.g., {meta['idiom_examples']}.

CAPTION BOUNDARY RULES:
M. A caption MUST end at a natural prosodic/clause boundary: end of sentence, end of clause, after a comma that opens a new clause, or before a coordinating conjunction ({meta['conjunctions']}) when the caption already has ≥3 words.
N. Lists are MANDATORY one-item-per-caption. Example: {meta['list_example']} → each item its own caption. Never combine list items.
O. GROUP INTO NATURAL UNITS (~4–7 words): a caption is a breath group / short clause, not a 1–2 word fragment. Combine adjacent words and inseparable units until a natural pause (clause/sentence boundary). Render on 1 line if short, 2 lines if longer — a natural mix is expected, neither forced to one line nor padded to two.
O2. NEVER leave a single short word (e.g. "to", "and", "is", "so", a 1–4 letter word) alone as its own caption. Attach it to the adjacent caption it belongs with. EXCEPTIONS that DO stand alone: a word the speaker repeats for emphasis, and each item of a list.

TEXT RULES:
P. Fix obvious Whisper transcription errors. Never add or skip words.
Q. {meta['capitalization']}
R. Remove periods, commas, semicolons, colons, exclamation marks. KEEP question marks, percent signs (%), slashes (/), ampersands (&), quotation marks{meta['punctuation_extra']}.
{project_terms_block()}
Input (numbered words):
{numbered}

{ctx_line}

Return JSON array only, no markdown. Each element:
{{"start": <word_index>, "end": <word_index_inclusive>, "text": "<caption text with \\n if needed>"}}

word_index refers to the [N] numbers above. Indices must be inside 0..{len(words) - 1}.
"""
    return _single_line(prompt, "Input (numbered words):", _SINGLE_LINE_GENERIC)


def segment_with_ai(words: list, video_context: str = "", language: str = "de") -> list:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import urllib.request
        import urllib.error
    except ImportError:
        return None

    if language != "de":
        prompt = build_generic_prompt(language, words, video_context)
    else:
        prompt = _build_german_prompt(words, video_context)

    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0, "response_mime_type": "application/json"},
    }).encode("utf-8")

    model_id = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})

    print(f"Calling Gemini for {LANGUAGE_META[language]['name']} semantic segmentation...")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"Gemini API error: {e.code} {e.reason}")
        print(e.read().decode("utf-8", errors="replace"))
        return None
    except Exception as e:
        print(f"Gemini call failed: {e}")
        return None

    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        segments = json.loads(text)
        if not isinstance(segments, list):
            return None
        cleaned = []
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            s = seg.get("start")
            e = seg.get("end")
            t = seg.get("text")
            if not isinstance(s, int) or not isinstance(e, int) or not isinstance(t, str):
                continue
            if s < 0 or e >= len(words) or s > e:
                continue
            cleaned.append({"start": s, "end": e, "text": t})
        return cleaned or None
    except Exception as e:
        print(f"Could not parse Gemini response: {e}")
        return None


def _call_gemini(prompt: str):
    """POST a prompt to Gemini and return the JSON value the model emitted, or
    None on any error. Shared by segmentation and the grouping-review pass."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    import urllib.request
    import urllib.error
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0, "response_mime_type": "application/json"},
    }).encode("utf-8")
    model_id = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except urllib.error.HTTPError as e:
        print(f"Gemini API error: {e.code} {e.reason}")
        return None
    except Exception as e:
        print(f"Gemini review/call failed: {e}")
        return None


def _build_review_prompt(draft: list, language: str) -> str:
    name = LANGUAGE_META[language]["name"]
    listing = "\n".join(f"[{i}] {_flat_text(s)}" for i, s in enumerate(draft))
    last = len(draft) - 1
    prompt = f"""You are refining the GROUPING of TikTok-style {name} captions for a vertical video. Below is a DRAFT caption list (already correctly worded). Regroup it into natural caption units by MERGING consecutive draft captions that belong to the same spoken phrase / breath group, so the result reads naturally instead of as choppy 1–2 word fragments.

STRICT — you may ONLY merge consecutive draft captions, or keep a caption as-is. You CANNOT split, reorder, add, remove or change ANY word; you only choose where caption boundaries fall.

Make each final caption a natural unit:
- A short clause / breath group, usually 4–7 words, that reads well as 1 OR 2 on-screen lines (roughly ≤ 45 characters total). Do NOT merge so much that a caption would need more than two lines.
- End each caption at a natural pause (clause end, sentence end, or just before a new clause). Do not end a caption on a conjunction, preposition or article — group it with what follows.
- ALWAYS merge a boundary that splits a tight pair: a number from its unit/noun, an article/possessive/preposition from its noun, or an auxiliary/modal from its verb.
- Never leave a single short word as its own caption — merge it with its phrase.
- KEEP SEPARATE (do not merge): a word repeated for emphasis (it must stand alone), and each item of a list (one per caption).

DRAFT captions:
{listing}

Return JSON array only, no markdown. Each element merges one consecutive range of draft captions:
{{"from": <first_draft_index>, "to": <last_draft_index_inclusive>}}
The ranges MUST be sorted, non-overlapping and contiguous, covering every index from 0 to {last}: the first "from" is 0, the last "to" is {last}, and each "from" equals the previous "to" + 1."""
    return _single_line(prompt, "DRAFT captions:", _SINGLE_LINE_REVIEW)


def review_grouping(segments: list, language: str = "de") -> list:
    """Second AI pass: re-group the draft captions into natural units so the
    output is less choppy. Merge-ONLY and index-based — it can never change a
    word, and timing stays exact because merged captions inherit the draft's
    word-index ranges. Returns the regrouped segments, or the original draft
    unchanged on any failure (network, bad JSON, or a partition that doesn't
    exactly cover the draft)."""
    if len(segments) < 2:
        return segments
    data = _call_gemini(_build_review_prompt(segments, language))
    if not isinstance(data, list) or not data:
        return segments
    ranges = []
    for el in data:
        if not isinstance(el, dict):
            return segments
        a, b = el.get("from"), el.get("to")
        if not isinstance(a, int) or not isinstance(b, int) or a > b:
            return segments
        ranges.append((a, b))
    # The ranges must be a contiguous partition of 0..N-1, or we don't trust it.
    if ranges[0][0] != 0 or ranges[-1][1] != len(segments) - 1:
        return segments
    for (_, b), (c, _) in zip(ranges, ranges[1:]):
        if c != b + 1:
            return segments
    merged = []
    for a, b in ranges:
        group = segments[a:b + 1]
        if len(group) == 1:
            merged.append(dict(group[0]))
        else:
            merged.append({
                "start": group[0]["start"],
                "end": group[-1]["end"],
                "text": " ".join(_flat_text(s) for s in group),
            })
    return merged


# ─── Single-line mode override blocks ───────────────────────────────────────
# Injected into the prompts ONLY when LINE_MODE == "1" (see _single_line). They
# OVERRIDE the "natural 1-2 line mix" guidance with "one line per caption", while
# leaving every inseparable-unit / boundary rule fully in force. Hybrid never
# sees these, so its prompts stay byte-for-byte unchanged.
_SINGLE_LINE_DE = """SINGLE-LINE MODE — this OVERRIDES the line-count guidance above (rules A, S and the examples):
- Produce captions that each fit on ONE line (≤ ~22 characters of visible text). Do NOT aim for a mix of 1- and 2-line captions; aim for ONE line every single time.
- To achieve this, segment into SHORTER, MORE NUMEROUS captions (typically 2–4 words each). Break a long breath group into several short captions at natural word boundaries — after a clause, before a conjunction, or between one inseparable unit and the next.
- EVERY inseparable-unit rule above (F–O) still applies with FULL force: never split an article/possessive/demonstrative+noun, preposition+noun phrase, adverb+adjective/verb, auxiliary+participle, modal+infinitive, negation, separable particle+verb, comparative/quantifier+noun, or an idiom/product/borrowing. Keep each such unit whole inside one caption.
- THE ONLY allowed 2-line caption is a single indivisible unit that is itself wider than one line: a long German compound (rule E) on its required hyphen split. Do NOT emit a "\\n" in any other case.
- Still NEVER strand a lone function word as its own caption — attach it per the rules. Emphasis repeats and list items still stand alone, one per caption.

"""

_SINGLE_LINE_GENERIC = """SINGLE-LINE MODE — this OVERRIDES the line-count guidance above (rules A and O):
- Produce captions that each fit on ONE line (≤ ~22 characters of visible text). Do NOT aim for a mix of 1- and 2-line captions; aim for ONE line every single time.
- To achieve this, segment into SHORTER, MORE NUMEROUS captions (typically 2–4 words each), breaking long groups at natural word boundaries.
- EVERY inseparable-unit rule above (F–L) still applies with FULL force — never split an inseparable unit; keep each one whole inside one caption.
- The ONLY allowed 2-line caption is a single indivisible unit wider than one line (rule E). Do NOT emit a "\\n" in any other case.
- Still NEVER strand a lone short function word as its own caption. Emphasis repeats and list items still stand alone.

"""

_SINGLE_LINE_REVIEW = """SINGLE-LINE MODE — this OVERRIDES the grouping guidance above:
Keep each final caption to ONE line (≤ ~22 characters). Merge ONLY when a draft caption is an incomplete fragment that splits an inseparable unit or strands a single function word; otherwise keep the drafts SEPARATE. Do NOT merge fragments together merely to reach 4–7 words, and never produce a caption that needs two lines (except a single indivisible unit that cannot fit one line).

"""


def _single_line(prompt: str, anchor: str, block: str) -> str:
    """Inject a single-line override `block` just before `anchor` in `prompt`,
    but only in single-line mode. In hybrid mode the prompt is returned
    unchanged (byte-for-byte), so existing behaviour is preserved exactly."""
    if LINE_MODE != "1":
        return prompt
    return prompt.replace(anchor, block + anchor, 1)


def _build_german_prompt(words: list, video_context: str = "") -> str:
    """German caption prompt. Domain-agnostic ("evergreen"): every example is an
    everyday German phrase, so nothing primes the model toward one topic — only
    the grammar rules carry over to any video."""
    numbered = "\n".join(f"[{i}] {w['word']}" for i, w in enumerate(words))
    prompt = f"""You are a TikTok-style German caption editor. Split the transcription below into short, well-paced captions for a vertical video.

Hard constraints (CapCut renders captions at large font on vertical 9:16 video; lines wider than ~24 chars wrap awkwardly):

LAYOUT:
A. Group words into NATURAL caption units — a short complete clause or breath group, usually 4–7 words. Render a unit on 1 line when it fits one line (~22 chars), and on 2 lines (literal "\\n") when the unit is longer. Aim for a NATURAL MIX of 1- and 2-line captions: do NOT force everything onto one line, and do NOT pad a genuinely short unit into two. Avoid 1–2 word fragments — they read as choppy.
B. Each visible line: AT MOST ~24 characters (including spaces). German has many narrow letters (i, l, t, r, f, ä) that take little room, so a line of 24 narrow chars is fine; lines full of wide letters (m, w) should be a little shorter.
C. Therefore each caption: AT MOST ~48 characters total visible text. Going under is fine; going over is not.
D. NEVER break a word in the middle of letters. Words that are NOT German compound nouns stay intact ("Entscheidung", "Erfahrung", "Computer", "Nachbarin" — never split).
E. A German compound word > 24 chars (e.g., "Geschwindigkeitsbegrenzung", "Versicherungsgesellschaft", "Lebensmittelgeschäft", "100-Meter-Staffellauf") goes alone in its own caption and is broken at a meaningful compound boundary, hyphen at end of line 1: "Geschwindigkeits-\\nbegrenzung", "Versicherungs-\\ngesellschaft". This mid-word two-line split of a long compound is REQUIRED and must be kept.

INSEPARABLE SEMANTIC UNITS (these phrases MUST NEVER be split across a caption boundary OR across a "\\n" line break inside a caption — both apply EQUALLY):
The "\\n" line break within a caption is just as much a "split" as starting a new caption. ALL inseparable-unit rules below apply to BOTH.
Example check: "es liegt an diesem Problem" (26 chars).
  ❌ Wrong: "es liegt an diesem\\nProblem" — splits "diesem Problem" (demonstrative + noun).
  ✅ Right: "es liegt an\\ndiesem Problem" — line break between clauses, semantic unit intact.
Always ask: would breaking here separate two words that belong together grammatically? If yes, find another break point (a different word boundary within the caption, or split into 2 separate captions).
F. Adverb + adjective/participle: "sehr glücklich", "extrem müde", "ziemlich groß", "wirklich schön", "ganz schön".
G. Adverb + verb form: "dachte immer", "habe nie", "geht gut", "ist auch".
H. Auxiliary + participle: "habe gemacht", "ist gegangen", "wird gebaut", "wurde gefunden".
I. Modal + infinitive: "kann gehen", "muss arbeiten", "sollte helfen", "möchte schlafen".
J. Negation + element it negates: "nie wieder", "nicht gut", "kein Geld", "niemals".
K. Separable verb particle + verb root: "rufe an", "fängt an", "steht auf", "hört zu", "macht mit". The particle stays in the same caption as the verb stem even if they appear in different positions in the sentence.
L. Preposition + its noun phrase (article+adj+noun): "mit dem Auto", "in der Stadt", "bei der Arbeit", "an Weihnachten", "für meine Familie". Never end a caption with a preposition. Never split between preposition and its object.
M. Article/possessive/demonstrative + noun: "der Mann", "eine Idee", "meine Tasche", "diese Sache", "das große Haus". Never end a caption with an article/possessive/demonstrative.
N. Comparative/quantifier + noun: "mehr Geld", "weniger Zeit", "viel Wasser", "20% Rabatt", "zwei Stunden".
O. Tight idiomatic units, product names and English borrowings stay as ONE token: "Social Media", "Fun Fact", "Best Friend", "Work-Life-Balance", brand names.

CAPTION BOUNDARY RULES:
P. A caption MUST end at a natural prosodic/clause boundary: end of sentence, end of clause (after subordinator's verb), after a comma that introduces a new clause, before a coordinating conjunction (und/aber/oder/denn) that starts a new clause.
Q. Lists (items separated by commas, e.g., "Brot, Milch, Eier") → each item its own caption.
R. If forced to choose between a 2-line caption with an unnatural break (e.g., splitting "extrem | müde") and TWO 1-line captions (one with "und das Wetter war", one with "extrem kalt"), CHOOSE THE TWO 1-LINE CAPTIONS.
S. **GROUP INTO NATURAL UNITS (≈4–7 words).** A caption is a natural breath group / short clause — NOT a 1–2 word fragment. Combine adjacent words and inseparable units until you reach a natural pause (clause end, sentence end, or right before a new clause). Render the unit on 1 line if it is short (~22 chars) or on 2 lines (\\n) if it is longer — a natural mix of 1- and 2-line captions is expected, neither forced to one line nor padded to two. NEVER leave a single short word ("tun", "und", "ist", "doch", any 1–4 letter word) alone as its own caption — attach it to the caption it grammatically belongs with. EXCEPTIONS that DO stand alone: a word the speaker repeats for emphasis (e.g. "Nie … Nie", "Endlich … Endlich"), and each item of a list.
   The "inseparable unit" rule means UNITS DON'T SPLIT INTERNALLY — it does NOT mean every unit must be its own caption. Multiple units CAN be combined in one caption.
   Example: "und trotzdem kommst du morgens" (5 words, 30 chars) → ONE caption: "und trotzdem\\nkommst du morgens" (line 1: 12c, line 2: 17c). NOT two captions.
   Example: "immer müder und müder" (4 words) → ONE caption: "immer müder\\nund müder". NOT two captions of one unit each.
   Example: "du fährst seit Jahren jeden Tag zur Arbeit" (8 words) — too long, split into 2 captions at a clause pause, e.g. "du fährst seit Jahren" + "jeden Tag zur Arbeit".
   Rule of thumb: build a natural breath group (~4–7 words) up to a clause/sentence pause, then start a new caption. Short unit → 1 line; longer unit → 2 lines.

TEXT RULES:
T. Fix obvious Whisper transcription errors (only clear ones): wrong word boundaries ("im Stande" → "imstande"), obvious homophones that make no sense in context, and misheard number words (a stray word where a number was clearly spoken). Write spoken cardinal numbers as DIGITS ("sechs Kilo" → "6 Kilo", "achtzig Euro" → "80 Euro").
U. Never add or skip words. EXCEPTION: when the speaker repeats a word for emphasis (e.g. "Nie … Nie"), KEEP the repeated word and give it its OWN caption — do not drop it and do not merge it into the neighbouring caption.
V. German grammar capitalization: nouns and proper names capitalized; pronouns/verbs/articles/conjunctions/adverbs lowercase EVEN AT CAPTION START. Preserve formal address "Sie/Ihr/Ihre/Ihnen" (capitalized).
W. Remove periods, commas, semicolons, colons, exclamation marks. KEEP question marks, percent signs (%), slashes (/), ampersands (&), quotation marks.

Editorial rules:
1. Lists are MANDATORY one-item-per-caption. If words are read out as a list (any enumeration, e.g. "Brot, Milch, Eier"), EACH item becomes its OWN caption — even single-word items. Never combine list items.
2. Split before subordinating/coordinating conjunctions ("und", "aber", "oder", "weil", "dass", "denn", "doch", "sondern", "wenn", "als", "ob", "obwohl") when the caption already has ≥3 words.
3. Split after commas, periods, question marks.
4. Keep meaningful units together as ONE token: product/brand names and English borrowings ("Social Media", "Fun Fact", "Best Friend").
5. Never add or skip words. Only correct spelling/word-boundary errors as above. EXCEPTION: an emphatic repetition is kept and gets its own caption.
6. German grammar capitalization: nouns and proper names capitalized; pronouns/verbs/articles/conjunctions/adverbs lowercase EVEN AT CAPTION START. Preserve formal address "Sie/Ihr/Ihre/Ihnen" (capitalized).
7. Remove periods, commas, semicolons, colons, exclamation marks. KEEP question marks, percent signs (%), slashes (/), ampersands (&), quotation marks.
{project_terms_block()}
Examples of good captions (1 or 2 lines, each line ≤ ~24 chars, semantic units intact):
- "ich war gestern\\nim Supermarkt"          ← 2 lines, ok
- "Fun Fact"                                  ← 1 line, borrowing
- "mit dem Auto"                              ← 1 line, prep+noun
- "extrem müde"                               ← 1 line, adv+adj must stay together
- "und das Wetter war"                        ← 1 line, complete clause start
- "Geschwindigkeits-\\nbegrenzung"            ← long compound alone, split at boundary
- "100-Meter-\\nStaffellauf"                  ← long compound alone
- "warum bin ich\\ndann so müde"              ← 2 lines, ok
- "wirklich schön"                            ← 1 line, adv+adj
- "und ich habe leider"                       ← 1 line, then "nie genug Zeit\\ndafür gehabt" follows
- "nie genug Zeit\\ndafür gehabt"             ← 2 lines, negation kept with noun phrase

Examples of BAD splits (NEVER produce these):
- "und das Wetter\\nwar extrem" + "schön"     ← BAD: splits "extrem schön"
- "ich war auch sehr" + "müde"                ← BAD: splits "sehr müde"
- "weil ich dachte\\nimmer"                   ← BAD: splits "dachte immer"
- "seit Jahren in" + "Berlin"                 ← BAD: splits "in Berlin"
- "und ich habe leider\\nnie genug" + "Zeit dafür gehabt"   ← BAD: splits "nie ... Zeit gehabt"

Input (numbered words):
{numbered}

{f"Context: {video_context}" if video_context else ""}

Return JSON array only, no markdown. Each element:
{{"start": <word_index>, "end": <word_index_inclusive>, "text": "<caption text with \\n if needed>"}}

word_index refers to the [N] numbers above. Indices must be inside 0..{len(words)-1}.
"""
    return _single_line(prompt, "Input (numbered words):", _SINGLE_LINE_DE)


BREAK_BEFORE = {"und", "aber", "oder", "denn", "doch", "sondern",
                "weil", "dass", "wenn", "als", "ob", "obwohl", "während",
                "bevor", "nachdem", "damit", "sodass", "falls"}


def segment_heuristic(words: list, max_words: int = 6) -> list:
    groups = []
    cur = []
    for i, w in enumerate(words):
        cur.append(i)
        raw = w["word"].strip()
        hard_end = bool(re.search(r"[.!?]$", raw))
        soft_end = raw.endswith(",") or raw.endswith(";") or raw.endswith(":")
        nxt = words[i + 1] if i + 1 < len(words) else None
        next_clause = nxt and strip_punct(nxt["word"]).lower() in BREAK_BEFORE
        should_break = (
            hard_end
            or (soft_end and len(cur) >= 2)
            or (next_clause and len(cur) >= 3)
            or len(cur) >= max_words
        )
        if should_break:
            groups.append(cur)
            cur = []
    if cur:
        if groups and len(cur) == 1:
            groups[-1].extend(cur)
        else:
            groups.append(cur)
    out = []
    for g in groups:
        text_words = [normalize_case(words[i]["word"]) for i in g if strip_punct(words[i]["word"])]
        out.append({"start": g[0], "end": g[-1], "text": " ".join(text_words)})
    return out


def compute_boundaries(segments: list, words: list, video_end: float):
    n = len(segments)
    boundaries = [0.0]
    for i in range(1, n):
        prev_end = words[segments[i - 1]["end"]]["end"]
        next_start = words[segments[i]["start"]]["start"]
        cand = max(prev_end + TRAIL_MIN, next_start - LEAD_MAX)
        cand = min(cand, next_start)
        boundaries.append(cand)
    boundaries.append(video_end)
    return boundaries


LINE_BREAK_BAD_LAST = {
    "der", "die", "das", "den", "dem", "des",
    "ein", "eine", "einen", "einem", "eines", "einer",
    "kein", "keine", "keinen", "keinem", "keiner", "keines",
    "mein", "meine", "meinen", "meinem", "meiner", "meines",
    "dein", "deine", "deinen", "deinem", "deiner", "deines",
    "sein", "seine", "seinen", "seinem", "seiner", "seines",
    "ihr", "ihre", "ihren", "ihrem", "ihrer", "ihres",
    "unser", "unsere", "unseren", "unserem", "unserer", "unseres",
    "euer", "eure", "euren", "eurem", "eurer", "eures",
    "dieser", "diese", "dieses", "diesen", "diesem",
    "jener", "jene", "jenes", "jenen", "jenem",
    "welcher", "welche", "welches", "welchen", "welchem",
    "manche", "mancher", "manches", "manchen", "manchem",
    "viele", "vieler", "vielen", "vielem",
    "alle", "aller", "allen", "allem",
}


def fix_line_break(text: str) -> str:
    if "\n" not in text:
        return text
    parts = text.split("\n", 1)
    if len(parts) != 2:
        return text
    line1_words = parts[0].split()
    line2_words = parts[1].split()
    all_words = line1_words + line2_words
    if not line1_words or not line2_words:
        return text

    def clean(w):
        return re.sub(r"[^\wäöüÄÖÜß-]", "", w, flags=re.UNICODE).lower()

    if clean(line1_words[-1]) not in LINE_BREAK_BAD_LAST:
        return text

    current_break = len(line1_words)
    for new_break in range(current_break - 1, 0, -1):
        new_line1 = " ".join(all_words[:new_break])
        new_line2 = " ".join(all_words[new_break:])
        last = clean(all_words[new_break - 1])
        if last in LINE_BREAK_BAD_LAST:
            continue
        if max(text_width(new_line1), text_width(new_line2)) <= LINE_W_MAX:
            return new_line1 + "\n" + new_line2

    return text


def normalize_text_preserve_breaks(text: str) -> str:
    lines = text.split("\n")
    out = []
    for line in lines:
        parts = line.split()
        cleaned = [normalize_case(w) for w in parts]
        cleaned = [w for w in cleaned if w]
        out.append(" ".join(cleaned))
    return "\n".join(l for l in out if l)


def _brand_config():
    """The canonical brand spelling, configured per project via the env var
    CAPTION_BRAND (loaded from tools/captions-de/.env). Empty by default, so
    nothing is hard-coded into the tool — opt in by setting CAPTION_BRAND."""
    return os.environ.get("CAPTION_BRAND", "").strip()


def _brand_re(brand: str):
    # Match the brand even when WhisperX split or hyphenated it ("Mia Vola",
    # "mia-vola", "Mariposa"), allowing an optional space/hyphen between letters.
    letters = [re.escape(c) for c in brand if not c.isspace()]
    return re.compile(r"\b" + r"[\s\-]?".join(letters) + r"\b", re.IGNORECASE)


def apply_brand(text: str) -> str:
    """Normalize mis-transcriptions of the configured brand to its canonical
    spelling. No-op unless CAPTION_BRAND is set — the tool ships brand-agnostic."""
    brand = _brand_config()
    if not brand:
        return text
    return _brand_re(brand).sub(brand, text)


def project_terms_block() -> str:
    """An optional prompt section listing project-specific spellings (brand +
    CAPTION_TERMS), injected only when configured. Keeps the base prompt neutral
    and unbiased; Gemini applies these only when the audio matches."""
    brand = _brand_config()
    terms = [t.strip() for t in os.environ.get("CAPTION_TERMS", "").split(",") if t.strip()]
    items = ([brand] if brand else []) + terms
    if not items:
        return ""
    return ("\nPROJECT-SPECIFIC SPELLINGS: when the audio clearly says one of "
            "these, spell it EXACTLY like this (otherwise ignore this line): "
            f"{', '.join(items)}.\n")


def finalize_caption(text: str) -> str:
    normalized = apply_brand(normalize_text_preserve_breaks(text))
    # Prefer ONE line. Test the fit on the UN-hyphenated text, so a compound that
    # fits a line stays whole (no mid-line hyphen): auto-hyphenation only exists
    # to break a word ACROSS two lines, never to show a hyphen inside one line.
    flat = " ".join(normalized.replace("\n", " ").split())
    if text_width(flat) <= LINE_W_MAX:
        return flat
    # Two lines are needed: now hyphenate long compounds so the break can fall at
    # a compound boundary. Respect the model's own line break when both halves fit
    # (it reflects semantic units, e.g. keeping "im Wartezimmer" together); only
    # re-pack by width when the model gave no usable break.
    hyphenated = apply_auto_hyphenation(normalized)
    if "\n" in hyphenated:
        parts = hyphenated.split("\n")
        if len(parts) == 2 and all(text_width(p) <= LINE_W_MAX for p in parts):
            return fix_line_break(hyphenated)
    return fix_line_break(pack_lines(hyphenated))


def _flat_text(seg: dict) -> str:
    """Caption text as a single line (line breaks removed)."""
    return " ".join(seg["text"].replace("\n", " ").split())


def _fits_two_lines(text: str) -> bool:
    """True if `text` packs into at most two lines that each fit the width
    budget — i.e. it can absorb a merged orphan without overflowing."""
    packed = pack_lines(text)
    lines = packed.split("\n")
    return len(lines) <= 2 and all(text_width(l) <= LINE_W_MAX for l in lines)


def _seg_tokens(seg: dict) -> list:
    return _flat_text(seg).split()


def _norm_word(w: str) -> str:
    return strip_punct(w).lower()


def _is_orphan(seg: dict) -> bool:
    """A caption that is a single word. Any lone word is a merge candidate — we
    don't want a word stranded on its own caption. The exceptions (emphasis
    repetition, list items) are protected in merge_orphans; a long compound that
    can't be combined with a neighbour within two lines simply stays put, since
    no merge will fit it."""
    return len(_seg_tokens(seg)) == 1


# A caption must not END on a word that grammatically binds to the FOLLOWING
# word — it gets moved to the start of the next caption ("so gut dass" + "mein
# Arzt" → "so gut" + "dass mein Arzt"; "…bist für" + "Hosen" → "…bist" + "für
# Hosen"). Two groups:
#   • subordinating conjunctions (open a dependent clause);
#   • forward-binding prepositions/contractions + the intensifier "so".
# Deliberately EXCLUDES coordinating und/oder/aber/denn (often a natural final
# pause, "Klingt super oder?"), "als" (ambiguous), and every separable-verb
# particle (an, auf, aus, ab, zu, vor, nach, ein, um, über, unter, durch) —
# moving those broke verbs like "fallen … aus" and cascaded.
MOVE_TRAILING_CONJ = {
    "dass", "weil", "ob", "wenn", "damit", "sodass",
    "obwohl", "während", "bevor", "nachdem", "falls", "sondern",
}
MOVE_TRAILING_FWD = {
    "für", "mit", "bei", "ohne", "gegen", "zwischen", "wegen", "trotz",
    "statt", "seit", "von", "vom", "zur", "zum", "ins", "im", "am", "beim",
    "ans", "aufs", "so",
}
MOVE_TRAILING = MOVE_TRAILING_CONJ | MOVE_TRAILING_FWD


def move_trailing_binders(segments: list) -> list:
    """Never end a caption on a forward-binding word (subordinating conjunction,
    a binding preposition, or "so"). Move the trailing one to the START of the
    next caption so the bound pair stays together — but only when the next
    caption still fits two lines afterwards, and never for a sentence-final
    token (e.g. "oder?"). Word index ranges shift with it so timing stays
    correct."""
    segs = [dict(s) for s in segments]
    for i in range(len(segs) - 1):
        toks = _seg_tokens(segs[i])
        last = toks[-1] if toks else ""
        if not (len(toks) >= 2 and _norm_word(last) in MOVE_TRAILING
                and not re.search(r"[?!.]", last)):
            continue
        nxt = segs[i + 1]
        candidate = last + " " + _flat_text(nxt)
        if not _fits_two_lines(candidate):
            continue  # moving it would overflow the next caption — leave as is
        word_idx = segs[i]["end"]
        segs[i]["text"] = " ".join(toks[:-1])
        segs[i]["end"] = max(segs[i]["start"], word_idx - 1)
        nxt["text"] = candidate
        nxt["start"] = word_idx
    return segs


def split_emphasis_repeats(segments: list) -> list:
    """Isolate an emphatic repetition the segmenter glued to the end of a
    caption. When a caption's LAST word is a short CONTENT word that also appears
    in the PREVIOUS caption — a deliberate repeat like "… zweimal extra" / "…
    anpasst Zweimal" — peel that last word onto its own caption so the repeat
    lands standalone for emphasis. The peeled word is protected from re-merging
    by merge_orphans (it sets "_keep").

    Guards against false positives: the word must be short (≤ORPHAN_W_MAX) and a
    CONTENT word — function words (in GERMAN_LOWERCASE: und, die, nicht, mehr, …)
    repeat constantly and are never peeled. For non-German we fall back to the
    narrow "repeats the previous caption's first word" bracket, since the
    German function-word list can't filter other languages safely."""
    out: list = []
    for i, seg in enumerate(segments):
        toks = _seg_tokens(seg)
        prev = segments[i - 1] if i > 0 else None
        prev_toks = _seg_tokens(prev) if prev else []
        last = _norm_word(toks[-1]) if toks else ""
        is_repeat = False
        if (len(toks) >= 2 and prev_toks and last
                and text_width(toks[-1]) <= ORPHAN_W_MAX):
            if ACTIVE_LANG == "de" and last not in GERMAN_LOWERCASE:
                is_repeat = last in {_norm_word(t) for t in prev_toks}
            else:
                is_repeat = last == _norm_word(prev_toks[0])
        if is_repeat:
            head = dict(seg)
            head["text"] = " ".join(toks[:-1])
            head["end"] = max(seg["start"], seg["end"] - 1)
            tail = dict(seg)
            tail["text"] = toks[-1]
            tail["start"] = seg["end"]
            tail["end"] = seg["end"]
            tail["_keep"] = True  # don't let merge_orphans glue it back
            out.append(head)
            out.append(tail)
            continue
        out.append(seg)
    return out


def merge_orphans(segments: list) -> list:
    """Tetris pass: never strand a meaningless single short word ("tun", "und",
    "ist") on its own caption. Merge it into an adjacent multi-word caption —
    preferring the previous one, falling back to the next — as long as the
    merged text still fits in ≤2 lines of real width. Word index ranges are
    extended so timing stays correct, and the text is re-packed in
    finalize_caption().

    Two kinds of deliberate single-word captions are KEPT standalone, never
    merged:
      • emphasis repetition — the lone word repeats a word in an adjacent
        caption (the creator said it twice on purpose, e.g. "Zweimal");
      • list items — a run of single-word captions (ingredient/symptom lists
        are one item per caption: "Artischocke" / "Selen" / …).
    A deliberately-standalone long compound is also preserved (it isn't an
    orphan), so the German two-line compound split is untouched."""
    if len(segments) < 2:
        return segments
    segs = [dict(s) for s in segments]
    n = len(segs)

    for i, seg in enumerate(segs):
        if not _is_orphan(seg):
            continue
        word = _norm_word(_flat_text(seg))
        prev = segs[i - 1] if i > 0 else None
        nxt = segs[i + 1] if i + 1 < n else None
        neighbour_words = set()
        if prev:
            neighbour_words |= {_norm_word(t) for t in _seg_tokens(prev)}
        if nxt:
            neighbour_words |= {_norm_word(t) for t in _seg_tokens(nxt)}
        is_repeat = word in neighbour_words
        in_list = (prev is not None and len(_seg_tokens(prev)) == 1) or \
                  (nxt is not None and len(_seg_tokens(nxt)) == 1)
        if is_repeat or in_list:
            seg["_keep"] = True

    def mergeable(seg: dict) -> bool:
        return _is_orphan(seg) and not seg.get("_keep")

    # Pass 1 — pull a mergeable orphan back into the previous multi-word caption.
    out: list = []
    for seg in segs:
        if out and mergeable(seg) and len(_seg_tokens(out[-1])) >= 2:
            prev = out[-1]
            combined = _flat_text(prev) + " " + _flat_text(seg)
            if _fits_two_lines(combined):
                prev["text"] = combined
                prev["end"] = seg["end"]
                continue
        out.append(seg)

    # Pass 2 — otherwise join it to the next multi-word caption.
    res: list = []
    i = 0
    while i < len(out):
        seg = out[i]
        if mergeable(seg) and i + 1 < len(out) and len(_seg_tokens(out[i + 1])) >= 2:
            nxt = out[i + 1]
            combined = _flat_text(seg) + " " + _flat_text(nxt)
            if _fits_two_lines(combined):
                merged = dict(nxt)
                merged["text"] = combined
                merged["start"] = seg["start"]
                res.append(merged)
                i += 2
                continue
        res.append(seg)
        i += 1

    for seg in res:
        seg.pop("_keep", None)
    return res


# Words after which a trailing number is a LABEL/ordinal (a complete unit), not
# a quantity that binds to a following noun — so "Nummer 1" must NOT be glued to
# the next sentence.
NUMBER_LABELS = {
    "nummer", "nr", "teil", "punkt", "schritt", "kapitel", "tag", "woche",
    "folge", "runde", "phase", "level", "tipp", "grund", "regel", "platz",
}


def merge_split_numbers(segments: list) -> list:
    """Keep a number with its unit/noun. If a caption ends on a bare number and
    merging it with the next caption fits two lines, merge them: "ich habe 6" +
    "Kilo abgenommen" → "ich habe 6 Kilo abgenommen". A number used as a label
    ("Nebenwirkung Nummer 1") is left alone."""
    out: list = []
    i = 0
    while i < len(segments):
        seg = dict(segments[i])
        toks = _seg_tokens(seg)
        if (toks and re.fullmatch(r"\d+([.,]\d+)?", _norm_word(toks[-1]))
                and not (len(toks) >= 2 and _norm_word(toks[-2]) in NUMBER_LABELS)
                and i + 1 < len(segments)):
            nxt = segments[i + 1]
            combined = _flat_text(seg) + " " + _flat_text(nxt)
            if _fits_two_lines(combined):
                merged = dict(nxt)
                merged["text"] = combined
                merged["start"] = seg["start"]
                out.append(merged)
                i += 2
                continue
        out.append(seg)
        i += 1
    return out


def merge_short_durations(segments: list, words: list, min_dur: float = 0.6) -> list:
    """Merge a multi-word caption that would be on screen for less than min_dur
    seconds into a neighbour, so it stays long enough to read. Tries the NEXT
    caption first (a too-brief caption is usually the start of the upcoming
    phrase — e.g. "einen Mann" → "einen Mann der nicht mehr mitkommt"), then the
    previous one. Single-word captions are left to merge_orphans, so emphasis
    repeats / list items aren't touched here."""
    if len(segments) < 2:
        return segments

    def dur(seg: dict) -> float:
        try:
            d = words[seg["end"]]["end"] - words[seg["start"]]["start"]
            return d if d > 0 else min_dur
        except Exception:
            return min_dur  # unknown timing → treat as fine, never merge

    def too_short(seg: dict) -> bool:
        return len(_seg_tokens(seg)) >= 2 and dur(seg) < min_dur

    # Pass 1 — fold a too-brief caption into the NEXT one when it fits.
    out: list = []
    i = 0
    while i < len(segments):
        seg = dict(segments[i])
        if too_short(seg) and i + 1 < len(segments):
            nxt = segments[i + 1]
            combined = _flat_text(seg) + " " + _flat_text(nxt)
            if _fits_two_lines(combined):
                merged = dict(nxt)
                merged["text"] = combined
                merged["start"] = seg["start"]
                out.append(merged)
                i += 2
                continue
        out.append(seg)
        i += 1

    # Pass 2 — otherwise fold any still-too-brief caption into the previous one.
    res: list = []
    for seg in out:
        if res and too_short(seg):
            prev = res[-1]
            combined = _flat_text(prev) + " " + _flat_text(seg)
            if _fits_two_lines(combined):
                prev["text"] = combined
                prev["end"] = seg["end"]
                continue
        res.append(seg)
    return res


def write_srt(segments: list, boundaries: list, out_path: Path):
    with open(out_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments):
            txt = finalize_caption(seg["text"])
            f.write(f"{i+1}\n{fmt_time(boundaries[i])} --> {fmt_time(boundaries[i+1])}\n{txt}\n\n")


def main():
    global ACTIVE_LANG, LINE_MODE
    parser = argparse.ArgumentParser(
        description="Generate TikTok-style captions from a video.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("video", help="Path to video file (mp4, mov, etc.)")
    parser.add_argument("--out", default=None, help="Output SRT path (default: <video>.srt)")
    parser.add_argument("--no-ai", action="store_true", help="Skip Gemini, use heuristic only")
    parser.add_argument("--model", default="large-v3", help="Whisper model (default: large-v3)")
    parser.add_argument("--context", default="", help="Optional context hint for Gemini")
    parser.add_argument("--language", default="de",
                        choices=["de", "en", "es", "fr", "it"],
                        help="Language: de (default), en, es, fr, it")
    parser.add_argument("--lines", default="hybrid", choices=["hybrid", "1"],
                        help="Caption length: hybrid (default, natural 1-2 line "
                             "mix) or 1 (one line per caption)")
    args = parser.parse_args()

    ACTIVE_LANG = args.language
    LINE_MODE = args.lines

    video_path = Path(args.video).expanduser().resolve()
    if not video_path.exists():
        sys.exit(f"Video not found: {video_path}")

    out_path = Path(args.out).expanduser().resolve() if args.out else video_path.with_suffix(".srt")
    out_dir = video_path.parent

    duration = get_video_duration(video_path)
    print(f"Video duration: {duration:.2f}s")
    print(f"Language       : {LANGUAGE_META[args.language]['name']} ({args.language})")
    print(f"Caption length : {'one line per caption' if LINE_MODE == '1' else 'hybrid (1-2 lines)'}")

    # Per-language cache so switching language doesn't reuse the wrong transcription.
    json_path = out_dir / f"{video_path.stem}.{args.language}.json"
    if not json_path.exists():
        json_path = run_whisperx(video_path, args.model, out_dir, language=args.language)
    else:
        print(f"Reusing existing transcription: {json_path.name}")

    words = load_words(json_path)
    print(f"Loaded {len(words)} words.")

    segments = None
    used_ai = False
    if not args.no_ai:
        segments = segment_with_ai(words, args.context, language=args.language)
        used_ai = segments is not None

    if segments is None:
        if not args.no_ai:
            print("Falling back to heuristic segmentation.")
        else:
            print("Using heuristic segmentation.")
        # Single-line mode wants shorter, more numerous captions, so cap the
        # heuristic groups tighter; hybrid keeps the long-standing default of 6.
        segments = segment_heuristic(words, max_words=3 if LINE_MODE == "1" else 6)

    # Second AI pass: re-group the draft into natural units (merge-only, never
    # changes words). Skipped for the heuristic fallback / --no-ai.
    if used_ai:
        print("Reviewing caption grouping with Gemini...")
        segments = review_grouping(segments, language=args.language)

    segments = move_trailing_binders(segments)
    segments = merge_split_numbers(segments)
    segments = split_emphasis_repeats(segments)
    segments = merge_orphans(segments)
    segments = merge_short_durations(segments, words)
    boundaries = compute_boundaries(segments, words, duration)
    write_srt(segments, boundaries, out_path)
    print(f"Wrote {len(segments)} captions to {out_path}")


if __name__ == "__main__":
    main()
