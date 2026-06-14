# CLAUDE.md — codebase map for AI sessions

Mariposa Studio is a **native desktop app built with PySide6 (Qt for Python)** —
NOT a web/Electron app. It's a small "OS for creators": a launcher desktop where
each bundled tool opens as its own full-canvas app. It shells out to per-tool
scripts via `QProcess`.

Read this first so you can orient without re-exploring the whole tree.

## Where things live

```
Mariposa Studio/
├── src/                  ← ALL Python app code (run as flat scripts, no package)
├── tools/                ← the 4 bundled tools (their own scripts + installers)
│   ├── flow-cropper/     crop.py        (ffmpeg-based 9:16→4:5 batch crop)
│   ├── captions-de/      caption.py     (WhisperX + Gemini → .srt; .env lives here)
│   ├── extract-frame/    extract_last_frame.py  (OpenCV; cross-platform)
│   └── camera-prompts/   prompts.json + images/*.webp
├── brand/                ← brand assets (logos, shots) used by design.py
├── docs/                 ← BRAND.md, DESIGN.md
├── exports/              ← runtime output (gitignored); animator_log.json lives here
├── scripts/smoketest.py  ← headless boot test (see "Verifying" below)
├── requirements.txt      ← single dep manifest (PySide6-Essentials, opencv, numpy)
├── Mariposa Studio.command / .app   ← macOS launchers
├── Mariposa Studio.bat              ← Windows launcher (uses pythonw)
├── install-mac.command / install-windows.bat
└── venv/                 ← local virtualenv (gitignored)
```

## The Python modules (`src/`)

The app was split out of a former 3837-line `studio.py` monolith. **Keep the
split** — don't merge modules back together. Dependency graph is acyclic:

```
core  ←  widgets  ←  {tool_pages, camera_page, animator_page, launcher}  ←  studio
       design.py is imported by all (the design system / single source of truth)
```

| Module | ~lines | Contains |
|---|---|---|
| `core.py` | 150 | Paths (`APP_DIR`, `TOOLS_DIR`, `VENV_PY`, `WHISPERX_PY`, `ENV_PATH`), `.env` read/write, platform/icon helpers, the `IS_MAC/IS_WINDOWS/IS_LINUX` flags. Has `__all__`. |
| `widgets.py` | 430 | Reusable widgets: `Card`, `FormRow`, `DropZone`, `Segmented`, `Field`, `ChipGroup`, `Switch`, `ConsoleView`, `AppBar`, plus `_panel`/`_video_thumb_and_meta`. Has `__all__`. |
| `tool_pages.py` | 745 | `ToolPage` base ("job runner": input → `build_command()` → live QProcess output) + `FlowCropperPage`, `CaptionsPage`, `ExtractFramePage`. Also `whisperx_arch_ok()`. |
| `camera_page.py` | 937 | `CameraPromptsPage` — searchable shot/angle gallery (loads `.webp`) that composes a Gemini prompt. `GeminiWorker`. |
| `animator_page.py` | 1109 | `AnimatorPage` + floating segment panel + `GeminiSegmenterWorker`/`GeminiRefineWorker`. |
| `launcher.py` | 507 | `SettingsPage`, the launcher desktop (`LauncherPage`, `AppIcon`), `SpotlightOverlay`. |
| `studio.py` | 165 | Thin entrypoint: `MainWindow` (the OS shell + nav) and `main()`. Tools are registered in the `specs` list in `MainWindow.__init__`. Hosts the `UpdateBanner`; `main()` kicks off the background update check. |
| `updater.py` | 290 | In-app auto-update (stdlib only). Pure logic (version compare, GitHub `releases/latest` fetch, zip extract/overlay preserving `venv`/`exports`/`.env`) + Qt glue (`UpdateBanner`, check/apply threads). **Repo coords live in `REPO_OWNER`/`REPO_NAME` — edit when wiring the GitHub repo.** See `docs/SHIP.md`. |
| `design.py` | 665 | The **"Studio Instrument"** design system: tokens, `svg_icon()` (Lucide), `build_stylesheet()` → QSS keyed by objectName. `BRAND_DIR` points to `../brand`. |
| `make_icon.py` | 113 | Build script: renders `AppIcon.icns` via macOS `iconutil`. **macOS-only**; not run by the Windows installer. |

Imports between modules are **explicit** (`from core import (...)`, not `*`) —
keep them that way so the code stays greppable/analyzable.

## Running & launching

- **macOS:** double-click `Mariposa Studio.app` / `Mariposa Studio.command`, or
  `./venv/bin/python src/studio.py`.
- **Windows:** double-click `Mariposa Studio.bat`, or
  `venv\Scripts\pythonw.exe src\studio.py`.
- Launchers `cd` to the repo root first, so `APP_DIR = Path(__file__).parent.parent`
  (modules live in `src/`) resolves `tools/`, `exports/`, `venv/`, `brand/`
  against the root. If you move modules, fix these `.parent.parent` paths.

## Verifying a change (do this after edits)

```
QT_QPA_PLATFORM=offscreen ./venv/bin/python scripts/smoketest.py
```

This constructs and shows `MainWindow` (and every page) offscreen, then quits —
catching import errors, missing names, and construction crashes without a
display. It must print `BOOT OK`. Tool *logic* (QProcess, Gemini, .env) is
unchanged by refactors and should stay that way unless explicitly asked.

## Conventions that emerged in the June 2026 refactor

- **Keep the module split** (above). `studio.py` stays a thin entrypoint.
- **Qt footprint:** depends on **PySide6-Essentials**, NOT the full `PySide6`
  meta (which pulls Addons: QtWebEngine ~588 MB, QtMultimedia, Qt3D, Charts,
  Pdf…). The app only uses **QtCore, QtGui, QtWidgets, QtSvg**. Don't add imports
  from heavy Addons modules — it would re-bloat the venv (~500 MB → 1.3 GB).
- **Cross-platform:** branch on `core.IS_MAC/IS_WINDOWS/IS_LINUX`, never assume
  macOS. All `open`/Homebrew/`file` calls are already inside `IS_MAC` branches;
  venv python paths go through `core._venv_python` (Scripts/ vs bin/).
- **To verify on real Windows** (written/tested on Mac, field-confirm pending):
  - The Windows launcher (`Mariposa Studio.bat`) and `install-windows.bat`.
  - Flow Cropper's `ffmpeg -preset faster` H.264 encode runs as well as on Mac
    (libx264 is portable, so this is expected — just unconfirmed on Windows).
- **Intentionally-kept "dead" code (do NOT remove):** the unused design-token
  palette in `design.py` (`CARD`, `BORDER`, `SHADOW_*`, `DUR_*`, etc.) and
  `ToolPage.add_row()` — kept as design-system / API vocabulary.
- **Secrets:** `tools/captions-de/.env` is gitignored (the live key was once
  committed; treat history as compromised). `.env.example` is the tracked template.
- **`.bat` files are CRLF** (enforced via `.gitattributes`); `.command` are LF.

## Adding a new tool

Subclass `ToolPage` in `src/tool_pages.py` (or a bespoke `QWidget` starting with
an `AppBar`), register it in `specs` in `MainWindow.__init__` (`src/studio.py`),
and add its hue/icon/tagline in `src/design.py`. See README "Adding a new tool".

## Not done yet

P3 — a shared pattern/manifest across the 4 tools (they still have divergent
structures and separate installers) — is deferred to a future session.
