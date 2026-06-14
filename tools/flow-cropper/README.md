# Flow Cropper — 9:16 → 4:5 batch crop

Renames and center-crops a campaign folder of videos from 9:16 to 4:5 in one click.

Works on **macOS** and **Windows**. No coding required.

---

## What it does

For every `.mp4` in the `9x16/` subfolder of the campaign:

1. Renames it to a clean convention.
2. Center-crops 9:16 → 4:5 with FFmpeg and writes a parallel `4x5/` folder using the same naming.

Two folder structures are auto-detected:

```
simple:
  <campaign>/9x16/*.mp4        →  <campaign>/4x5/*.mp4

CTA:
  <campaign>/CTA1/9x16/*.mp4   →  <campaign>/CTA1/4x5/*.mp4
  <campaign>/CTA2/9x16/*.mp4   →  <campaign>/CTA2/4x5/*.mp4
```

Two creative types with different naming conventions:

```
AI :   9x16 - AI{n}-{i} - {name}.mp4
       9x16 - AI{n}-{CTA}-{i} - {name}.mp4

UGC:   {format} - {concept} - 9x16_{creator}_C{n}-{i} - {awareness} - {product}.mp4
       {format} - {concept} - 9x16_{creator}_C{n}-{CTA}-{i} - {awareness} - {product}.mp4
```

If the folder name starts with **AI{n}** the tool auto-picks AI mode and the number.
If it starts with **C{n}** the tool still asks (because some AI campaigns also start with C).
Otherwise the tool asks for the type explicitly.

The tool is **idempotent** — already-cropped files are skipped on re-run.

---

## How to install (one time, ~2 minutes)

### macOS

1. Unzip this folder somewhere stable (e.g. `~/Documents/flow-cropper`).
2. **Right-click** `install-mac.command` → **Open**. (Right-click the first time so macOS lets you run it.)
3. The installer takes care of Homebrew and ffmpeg.

### Windows

1. Unzip this folder somewhere stable.
2. If you don't have Python yet, install it from <https://python.org> — **tick "Add Python to PATH"** during install.
3. **Double-click** `install-windows.bat`. It installs ffmpeg via winget.

---

## How to use

### macOS — double-click `crop.command`

1. Pick the campaign folder.
2. If the folder name is `AI{n}` (e.g. `AI63`), the AI number is filled in automatically.
3. Otherwise pick the type (**AI** or **UGC**) when asked.
4. Fill the remaining fields:
   - **AI**: AI number, Creative name.
   - **UGC**: C number, Concept, Creator, Format, Awareness stage, Product.
5. The script runs. Cancel any dialog to exit cleanly.

### Windows — double-click `crop.bat`

Same flow.

---

## Speed

By default the tool runs **2 ffmpeg crops in parallel** to use multiple CPU cores. You can change this with the CLI:

```
python crop.py --workers 3        # 3 parallel crops
python crop.py --workers 1        # strictly sequential (safer on slow disks)
```

On modern Macs/PCs, 2–3 workers is sweet spot. Higher numbers usually don't help (FFmpeg already uses multiple threads inside each instance).

---

## CLI (no dialogs)

```
# AI one-shot
python crop.py /path/to/campaign 63 Pharmacist

# UGC one-shot
python crop.py --ugc /path/to/campaign 807 K41 Sandra_Lung "Product Aware"

# tune worker count for either
python crop.py --workers 4 /path/to/campaign 63 Pharmacist
```

---

## Troubleshooting

**"App can't be opened because it is from an unidentified developer" (macOS)**
Right-click the `.command` file → **Open** → confirm. macOS remembers your choice.

**"FFmpeg not found"**
Run `install-mac.command` or `install-windows.bat` first. Restart the terminal afterwards on Windows.

**Output filenames are wrong**
Re-run with the correct AI/C number and creative name. The first pass renames in place — existing files in `4x5/` are not overwritten, so you may want to delete them before re-running.
