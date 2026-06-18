#!/usr/bin/env python3
"""
Flow Cropper — 9:16 → 4:5 batch crop + smart rename.

AI and UGC creatives share ONE naming convention:

    {ad_format} - {avatar} - 9x16[_{creator}]_{id}-{i} - {awareness} - {product}.mp4
    {ad_format} - {avatar} - 9x16[_{creator}]_{id}-{CTA}-{i} - {awareness} - {product}.mp4

`id` is the full creative id, verbatim (e.g. C893, AI78, Cr906). `creator` is
optional — AI creatives usually have none.

e.g.  UGC - GeGe - 9x16_Marco_Schlegelmilch_C893-2 - Problem Aware - Umwandler.mp4
      WB - GeGe - 9x16_AI78-4 - Problem Aware - Umwandler.mp4

The "Videoformat" segment (9x16 / 4x5) and the per-clip index ("-{i}", the
"Hook") are filled in by the tool; in the generic briefing tag they appear as
the literal placeholders "Videoformat" and "Hook".

The creative id is auto-detected from the folder name:
    folder named "AI63"            → id AI63
    folder named "C807" / "C807-1" → id C807
    anything else                  → user is asked

Usage:
    crop.py                        (interactive — uses system dialogs)
    crop.py [--dry-run] --creative FOLDER ID AD_FORMAT AVATAR CREATOR AWARENESS PRODUCT
    crop.py --undo FOLDER          (CREATOR may be an empty string)
"""

import json
import os
import platform
import re
import subprocess
import sys
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

IS_MAC = platform.system() == "Darwin"
IS_WINDOWS = platform.system() == "Windows"

# Windows consoles default to the legacy cp1252 codec, which can't encode the
# characters we print in progress lines (e.g. "→", "·"). Without this, a job
# crashes with UnicodeEncodeError mid-rename. Force UTF-8 on our own streams so
# output is safe regardless of how the script was launched (app or shell).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

FFMPEG_CANDIDATES_MAC = [
    os.path.expanduser("~/.local/bin/ffmpeg"),
    "/opt/homebrew/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/usr/bin/ffmpeg",
]
FFMPEG_CANDIDATES_WIN = [
    r"C:\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "ffmpeg", "bin", "ffmpeg.exe"),
]

AWARENESS_STAGES = ["Problem Aware", "Solution Aware", "Product Aware"]
DEFAULT_PRODUCT = "Umwandler"
# One worker is the robust default: each ffmpeg encode already uses ~all CPU
# cores, so parallel encodes mostly fight over the same cores. On long clips
# extra workers hurt a lot (4x82s clip: 48s at 1 worker vs 107s at 4); on short
# clips they're a wash (10x10s clip: within ~5% across 1/2/4). 1 wins or ties
# everywhere, so it's the safe default — the selector still offers 2-4.
DEFAULT_WORKERS = 1

# Non-decomposable characters that need an explicit mapping for transliteration.
_TRANSLIT_EXTRA = {
    "ß": "ss", "ẞ": "SS",
    "ø": "o", "Ø": "O",
    "æ": "ae", "Æ": "AE",
    "œ": "oe", "Œ": "OE",
    "đ": "d", "Đ": "D",
    "ł": "l", "Ł": "L",
}


def transliterate(s: str) -> str:
    """Replace accented/Umlauts/etc with plain ASCII equivalents."""
    if not s:
        return s
    for k, v in _TRANSLIT_EXTRA.items():
        s = s.replace(k, v)
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def normalize_creator(value: str) -> str:
    """Replaces spaces with underscores and strips accents/Umlauts."""
    v = (value or "").strip()
    if not v:
        return v
    v = transliterate(v)
    v = re.sub(r"\s+", "_", v)
    return v

_PRINT_LOCK = threading.Lock()


def safe_print(*args, **kwargs):
    with _PRINT_LOCK:
        print(*args, **kwargs)
        sys.stdout.flush()


def find_ffmpeg():
    candidates = FFMPEG_CANDIDATES_WIN if IS_WINDOWS else FFMPEG_CANDIDATES_MAC
    for p in candidates:
        if p and os.path.isfile(p):
            if IS_WINDOWS or os.access(p, os.X_OK):
                return p
    try:
        which_cmd = "where" if IS_WINDOWS else "which"
        result = subprocess.run(
            [which_cmd, "ffmpeg.exe" if IS_WINDOWS else "ffmpeg"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip().splitlines()[0].strip()
    except Exception:
        pass
    return None


def detect_creative_id(folder_name: str):
    """Leading letter prefix + number, kept verbatim:
    'A10' → 'A10', 'AI63' → 'AI63', 'C807'/'C807-1' → 'C807', 'Cr906' → 'Cr906';
    else None."""
    m = re.match(r"\s*([A-Za-z]{1,4})[\s_-]*(\d+)", folder_name)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    return None


def crop_to_4x5(src: Path, dst: Path, ffmpeg: str):
    result = subprocess.run(
        [
            ffmpeg, "-y", "-i", str(src),
            "-vf", "crop=iw:iw*5/4:0:(ih-iw*5/4)/2",
            # The crop forces a re-encode (it changes the frames), and that
            # re-encode is ~80% of the runtime. "faster" cuts a single clip
            # from ~19.5s to ~11.7s vs the libx264 default ("medium") while
            # staying visually equivalent (VMAF 94.7 vs 95.3) and the same
            # file size. Software/cross-platform — no per-OS branching.
            "-preset", "faster",
            "-c:a", "copy",
            str(dst),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed for {src.name}:\n{result.stderr[-600:]}")


# ── Naming ────────────────────────────────────────────────────────────────────
def normalize_creative_id(value: str) -> str:
    """A bare number defaults to a C id: '857' → 'C857'. Anything starting with
    a letter (C893, AI78, Cr906…) is kept verbatim."""
    v = (value or "").strip()
    if v and v[0].isdigit():
        return f"C{v}"
    return v


def creative_name(aspect: str, creative_id: str, i: int, *, ad_format: str,
                  avatar: str, creator: str, awareness: str, product: str,
                  cta: str = "") -> str:
    """The shared AI/UGC convention. `creative_id` is the full id (C893, AI78,
    Cr906…), used verbatim. `creator` is optional (AI creatives have none)."""
    creator_part = f"_{creator}" if creator else ""
    cta_part = f"-{cta}" if cta else ""
    return (
        f"{ad_format} - {avatar} - {aspect}{creator_part}_{creative_id}{cta_part}-{i} "
        f"- {awareness} - {product}.mp4"
    )


# ── Processing ────────────────────────────────────────────────────────────────
def _natural_key(p: Path):
    """Natural sort key: 'h5.mp4' < 'h10.mp4'."""
    parts = re.split(r"(\d+)", p.name.lower())
    return [int(t) if t.isdigit() else t for t in parts]


def _build_index_pattern(name_for, cta: str) -> "re.Pattern[str]":
    """Build a regex matching the 9x16 names produced by name_for at any index.

    The trick: render a sentinel name at index 99991, escape it, then put a
    capture group where the index used to be. Works for both AI and UGC.
    """
    sample = name_for("9x16", 99991, cta)
    placeholder = "__INDEX_PLACEHOLDER__"
    sample = sample.replace("-99991", f"-{placeholder}")
    pat = re.escape(sample).replace(re.escape(placeholder), r"(\d+)")
    return re.compile("^" + pat + "$")


def process_folder(folder: Path, name_for, ffmpeg: str, cta: str = "",
                   workers: int = 1, dry_run: bool = False,
                   actions: list = None, on_action=None):
    nine16 = folder / "9x16"
    four5 = folder / "4x5"
    files = [f for f in nine16.iterdir() if f.suffix.lower() == ".mp4"]
    if not files:
        raise RuntimeError(f"No .mp4 files in {nine16}")
    prefix = f"{cta}: " if cta else ""
    indent = "  " if cta else ""
    if not dry_run:
        four5.mkdir(exist_ok=True)

    pattern = _build_index_pattern(name_for, cta)

    keep: list[tuple[int, Path]] = []
    new_files: list[Path] = []
    for f in files:
        m = pattern.match(f.name)
        if m:
            keep.append((int(m.group(1)), f))
        else:
            new_files.append(f)

    # Assign new (not-yet-renamed) files to the LOWEST free indices first, so
    # gaps left by already-renamed files get filled instead of new files being
    # appended past the highest index. E.g. with H1/H3/H4 already named (indices
    # 1,3,4) and H2/H5 still to do, H2→2 (fills the gap) and H5→5 — not 5 and 6.
    used = {idx for idx, _ in keep}
    new_files.sort(key=_natural_key)
    next_i = 1
    assigned: list[tuple[int, Path]] = []
    for f in new_files:
        while next_i in used:
            next_i += 1
        assigned.append((next_i, f))
        used.add(next_i)
        next_i += 1

    all_jobs = sorted(keep + assigned, key=lambda x: x[0])
    total = len(all_jobs)
    tag = "PREVIEW · " if dry_run else ""
    print(f"{prefix}{tag}Found {total} video(s)  "
          f"({len(keep)} already named, {len(assigned)} to rename)")

    jobs = []
    for pos, (i, vid) in enumerate(all_jobs, 1):
        n9 = name_for("9x16", i, cta)
        n4 = name_for("4x5", i, cta)
        p9 = nine16 / n9
        p4 = four5 / n4
        if vid.name != n9:
            if dry_run:
                print(f"{indent}[{pos}/{total}] would rename {vid.name} → {n9}")
            else:
                print(f"{indent}[{pos}/{total}] rename {vid.name} → {n9}")
                vid.rename(p9)
                if actions is not None:
                    actions.append({
                        "type": "rename",
                        "dir": str(nine16),
                        "from": vid.name,
                        "to": n9,
                    })
                    if on_action:
                        on_action()
        if p4.exists():
            print(f"{indent}[{pos}/{total}] 4x5 already exists — skipping")
            continue
        jobs.append((pos, i, p9, p4))

    if not jobs:
        print(f"{indent}Nothing to crop — all 4x5 files already exist.")
        return

    def worker(job):
        pos, _i, p9, p4 = job
        if dry_run:
            safe_print(f"{indent}[{pos}/{total}] would crop {p9.name} → {p4.name}")
            return
        safe_print(f"{indent}[{pos}/{total}] cropping {p9.name} ...")
        crop_to_4x5(p9, p4, ffmpeg)
        safe_print(f"{indent}[{pos}/{total}] ✓ {p4.name}")
        if actions is not None:
            actions.append({"type": "create", "path": str(p4)})
            if on_action:
                on_action()

    if dry_run or workers <= 1 or len(jobs) == 1:
        for job in jobs:
            worker(job)
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for _ in ex.map(worker, jobs):
                pass


def detect_structure(folder: Path) -> str:
    subs = [d.name for d in folder.iterdir() if d.is_dir()]
    if "9x16" in subs:
        return "simple"
    if any(s.upper().startswith("CTA") for s in subs):
        return "cta"
    for d in folder.iterdir():
        if d.is_dir():
            inner = [x.name for x in d.iterdir() if x.is_dir()]
            if "9x16" in inner:
                return "cta"
    raise RuntimeError(
        f"Unknown folder structure in '{folder.name}'.\n"
        f"Expected a 9x16/ subfolder, or CTA*/9x16/ subfolders.\n"
        f"Found: {', '.join(subs) or '(empty)'}"
    )


LOG_FILENAME = ".flow-cropper-log.json"


def _log_path(folder: Path) -> Path:
    return folder / LOG_FILENAME


def _load_log(folder: Path) -> dict:
    p = _log_path(folder)
    if not p.exists():
        return {"runs": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"runs": []}


def _save_log(folder: Path, data: dict):
    _log_path(folder).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def run(folder: Path, fields: dict, ffmpeg: str,
        workers: int = DEFAULT_WORKERS, dry_run: bool = False,
        actions: list = None, on_action=None) -> list:
    if actions is None:
        actions = []
    name_for = lambda aspect, i, cta: creative_name(
        aspect, fields["creative_id"], i,
        ad_format=fields["ad_format"], avatar=fields["avatar"],
        creator=fields["creator"], awareness=fields["awareness"],
        product=fields["product"], cta=cta,
    )

    structure = detect_structure(folder)
    print(f"Structure: {structure}")
    print(f"Workers  : {workers}")
    if dry_run:
        print("Mode     : DRY RUN (no files will be changed)")
    print()
    if structure == "simple":
        process_folder(folder, name_for, ffmpeg, workers=workers,
                       dry_run=dry_run, actions=actions, on_action=on_action)
    else:
        cta_subs = sorted(
            d for d in folder.iterdir()
            if d.is_dir() and d.name.upper().startswith("CTA")
        )
        for cta_dir in cta_subs:
            process_folder(cta_dir, name_for, ffmpeg,
                           cta=cta_dir.name.upper(), workers=workers,
                           dry_run=dry_run, actions=actions, on_action=on_action)
    return actions


def undo_last(folder: Path):
    log = _load_log(folder)
    runs = log.get("runs", [])
    if not runs:
        print("Nothing to undo — no log entries.")
        return
    entry = runs.pop()
    print(f"Undoing run from {entry.get('timestamp', '?')} "
          f"({len(entry.get('actions', []))} actions)")
    # Reverse in reverse order
    for a in reversed(entry.get("actions", [])):
        try:
            if a["type"] == "create":
                p = Path(a["path"])
                if p.exists():
                    p.unlink()
                    print(f"  - removed {p.name}")
            elif a["type"] == "rename":
                d = Path(a["dir"])
                src = d / a["to"]
                dst = d / a["from"]
                if src.exists() and not dst.exists():
                    src.rename(dst)
                    print(f"  - reverted {a['to']} → {a['from']}")
                else:
                    print(f"  ! skipped rename (missing or conflict): {a['to']} → {a['from']}")
        except Exception as e:
            print(f"  ! error undoing {a}: {e}")
    _save_log(folder, log)
    print("✓ Undo complete.")


# ── Native dialogs (osascript on Mac, PowerShell on Windows) ──────────────────
# Convention: returning None means the user cancelled.
def _osa(script: str):
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def _ps(script: str):
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return None
    out = r.stdout.strip()
    # PowerShell InputBox returns empty string on Cancel — treat as None.
    return out if out else None


def pick_folder():
    if IS_MAC:
        out = _osa(
            'POSIX path of (choose folder with prompt "Select campaign folder")'
        )
        return out.rstrip("/") if out else None
    if IS_WINDOWS:
        return _ps(
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
            "$f.Description = 'Select campaign folder'; "
            "$f.RootFolder = [System.Environment+SpecialFolder]::Desktop; "
            "if ($f.ShowDialog() -eq 'OK') { Write-Output $f.SelectedPath }"
        )
    raw = input("Folder: ").strip()
    return raw or None


def ask_text(prompt: str, default: str = ""):
    if IS_MAC:
        safe_prompt = prompt.replace('"', '\\"')
        safe_default = default.replace('"', '\\"')
        # No try/on error — Cancel propagates as a non-zero osascript exit.
        return _osa(
            f'text returned of (display dialog "{safe_prompt}" '
            f'default answer "{safe_default}" with title "Flow Cropper")'
        )
    if IS_WINDOWS:
        safe_prompt = prompt.replace("'", "''")
        safe_default = default.replace("'", "''")
        return _ps(
            "Add-Type -AssemblyName Microsoft.VisualBasic; "
            f"[Microsoft.VisualBasic.Interaction]::InputBox('{safe_prompt}', "
            f"'Flow Cropper', '{safe_default}')"
        )
    raw = input(f"{prompt} [{default}]: ").strip()
    if not raw and default:
        return default
    return raw or None


def ask_choice(prompt: str, choices: list, default: str = None):
    if IS_MAC:
        items = ", ".join(f'"{c}"' for c in choices)
        default_clause = (
            f' default items {{"{default}"}}' if default and default in choices else ""
        )
        out = _osa(
            f'set ans to (choose from list {{{items}}} with prompt "{prompt}"'
            f'{default_clause})\n'
            f'if ans is false then error number -128\n'
            f'item 1 of ans'
        )
        return out
    if IS_WINDOWS:
        ps_choices = ",".join(f"'{c}'" for c in choices)
        out = _ps(
            "Add-Type -AssemblyName System.Windows.Forms; "
            f"$form = New-Object System.Windows.Forms.Form; "
            f"$form.Text = 'Flow Cropper'; "
            f"$form.Size = New-Object System.Drawing.Size(360, 200); "
            f"$lbl = New-Object System.Windows.Forms.Label; "
            f"$lbl.Text = '{prompt}'; $lbl.Location = '20,15'; $lbl.Size = '320,20'; "
            f"$form.Controls.Add($lbl); "
            f"$cb = New-Object System.Windows.Forms.ComboBox; "
            f"$cb.Location = '20,40'; $cb.Size = '320,30'; "
            f"$cb.DropDownStyle = 'DropDownList'; "
            f"@({ps_choices}) | %{{ [void]$cb.Items.Add($_) }}; "
            + (f"$cb.SelectedItem = '{default}'; " if default else "$cb.SelectedIndex = 0; ")
            + "$form.Controls.Add($cb); "
            "$ok = New-Object System.Windows.Forms.Button; "
            "$ok.Text = 'OK'; $ok.Location = '180,90'; "
            "$ok.DialogResult = 'OK'; $form.AcceptButton = $ok; "
            "$cancel = New-Object System.Windows.Forms.Button; "
            "$cancel.Text = 'Cancel'; $cancel.Location = '90,90'; "
            "$cancel.DialogResult = 'Cancel'; $form.CancelButton = $cancel; "
            "$form.Controls.Add($ok); $form.Controls.Add($cancel); "
            "if ($form.ShowDialog() -eq 'OK') { Write-Output $cb.SelectedItem }"
        )
        return out
    raw = input(f"{prompt} ({'/'.join(choices)}) [{default}]: ").strip()
    return raw or default


def alert(msg: str):
    if IS_MAC:
        _osa(
            f'display alert "Flow Cropper" message "{msg.replace(chr(34), chr(92)+chr(34))}"'
        )
    elif IS_WINDOWS:
        safe = msg.replace("'", "''")
        _ps(
            "[System.Windows.Forms.MessageBox]::Show("
            f"'{safe}', 'Flow Cropper', 'OK', 'Information')"
        )
    else:
        print(f"ALERT: {msg}")


# ── Interactive flow ──────────────────────────────────────────────────────────
def _bail():
    print("Cancelled.")
    sys.exit(0)


def _require(value):
    """If value is None (user pressed Cancel), exit cleanly."""
    if value is None:
        _bail()
    return value


def interactive(workers: int = DEFAULT_WORKERS):
    folder = pick_folder()
    if not folder:
        _bail()
    folder_path = Path(folder).expanduser().resolve()
    if not folder_path.is_dir():
        alert(f"Folder not found: {folder_path}")
        sys.exit(1)

    detected_id = detect_creative_id(folder_path.name)

    creative_id = _require(ask_text(
        "Creative id (e.g. C857 or AI78):", default=detected_id or ""))
    if not creative_id.strip():
        _bail()
    ad_format = _require(ask_text("Ad format Kürzel (e.g. UGC):"))
    if not ad_format.strip():
        _bail()
    avatar = _require(ask_text("Avatar Kürzel (e.g. GeGe):"))
    if not avatar.strip():
        _bail()
    # Creator is optional — AI creatives have none. Empty answer is allowed.
    creator = normalize_creator(_require(ask_text(
        "Creator (optional, e.g. Marco Schlegelmilch):")))
    awareness = _require(ask_choice(
        "Awareness stage:", AWARENESS_STAGES, default="Problem Aware"
    ))
    product = _require(ask_text("Product:", default=DEFAULT_PRODUCT))
    if not product.strip():
        _bail()
    fields = {
        "creative_id": creative_id.strip(),
        "ad_format": ad_format.strip(), "avatar": avatar.strip(),
        "creator": creator, "awareness": awareness.strip(),
        "product": product.strip(),
    }

    run_with(folder_path, fields, workers=workers)


def run_with(folder: Path, fields: dict,
             workers: int = DEFAULT_WORKERS, dry_run: bool = False):
    if not folder.is_dir():
        print(f"Folder not found: {folder}")
        sys.exit(1)

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        hint = "winget install Gyan.FFmpeg" if IS_WINDOWS else "brew install ffmpeg"
        print(f"FFmpeg not found. Install it first:\n  {hint}")
        sys.exit(1)

    fields = {**fields, "creative_id": normalize_creative_id(fields["creative_id"])}
    print(f"Folder    : {folder}")
    print(f"Id        : {fields['creative_id']}")
    print(f"Ad format : {fields['ad_format']}")
    print(f"Avatar    : {fields['avatar']}")
    print(f"Creator   : {fields['creator'] or '(none)'}")
    print(f"Awareness : {fields['awareness']}")
    print(f"Product   : {fields['product']}")
    print(f"FFmpeg    : {ffmpeg}\n")

    # Persist the undo log INCREMENTALLY — after every rename/crop — not just at
    # the end. The GUI's Stop hard-kills this process (SIGKILL), which skips any
    # finally/atexit, so an end-only save would lose the record of files we
    # already renamed and undo would find nothing. Flushing per action means a
    # kill still leaves an accurate, replayable log.
    actions: list = []
    log = _load_log(folder)
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "fields": fields,
        "actions": actions,
    }
    state = {"added": False}
    log_lock = threading.Lock()

    def flush():
        if dry_run:
            return
        with log_lock:
            snapshot = list(actions)   # stable copy (workers may be appending)
            if not snapshot:
                return
            entry["actions"] = snapshot
            if not state["added"]:
                log.setdefault("runs", []).append(entry)
                state["added"] = True
            _save_log(folder, log)

    try:
        run(folder, fields, ffmpeg, workers=workers,
            dry_run=dry_run, actions=actions, on_action=flush)
        print("\n✓ All done!" if not dry_run else "\n✓ Preview done — no files changed.")
    finally:
        flush()
        if not dry_run and actions:
            print(f"  (saved {len(actions)} action(s) to {LOG_FILENAME} for undo)")


def main():
    args = list(sys.argv[1:])

    workers = DEFAULT_WORKERS
    if "--workers" in args:
        idx = args.index("--workers")
        try:
            workers = max(1, int(args[idx + 1]))
        except (IndexError, ValueError):
            print("--workers needs an integer (e.g. --workers 3)")
            sys.exit(2)
        del args[idx:idx + 2]

    dry_run = False
    if "--dry-run" in args:
        args.remove("--dry-run")
        dry_run = True

    # --undo FOLDER — reverse the last logged run for that campaign folder.
    if args and args[0] == "--undo":
        if len(args) < 2:
            print("Usage: crop.py --undo FOLDER")
            sys.exit(2)
        undo_last(Path(args[1]).expanduser().resolve())
        return

    if args and args[0] == "--creative":
        if len(args) < 8:
            print("Usage: crop.py --creative FOLDER ID "
                  "AD_FORMAT AVATAR CREATOR AWARENESS PRODUCT")
            sys.exit(2)
        fields = {
            "creative_id": args[2].strip(),
            "ad_format": args[3].strip(),
            "avatar": args[4].strip(),
            "creator": normalize_creator(args[5]),
            "awareness": args[6].strip(),
            "product": args[7].strip() or DEFAULT_PRODUCT,
        }
        run_with(Path(args[1]).expanduser().resolve(), fields,
                 workers=workers, dry_run=dry_run)
        return

    if args:
        print(__doc__)
        sys.exit(2)

    interactive(workers=workers)


if __name__ == "__main__":
    main()
