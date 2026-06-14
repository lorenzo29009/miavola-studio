# SHIP.md — distributing & updating Mariposa Studio

How to get Mariposa Studio onto a teammate's machine and how to ship updates.
The strategy is **"bootstrap from source"**: the app ships as a normal folder of
Python source; one installer per OS builds everything around it; the app updates
itself by overlaying new source. No frozen binary, no code-signing certificates.

---

## One-time setup (you, the maintainer)

The in-app updater talks to **one GitHub repository's public Releases**. Wire it
up once:

1. Create a public GitHub repo (the code holds no secrets — the live key lives
   only in `tools/captions-de/.env`, which is gitignored).
2. Edit the two constants at the top of [`src/updater.py`](../src/updater.py):
   ```python
   REPO_OWNER = "mariposa"          # your GitHub org/user
   REPO_NAME  = "mariposa-studio"   # the repo name
   ```
3. Push the code.

> Private repo instead? The GitHub API then needs a token, which would have to be
> embedded in the app — more friction and a secret to manage. Public is the clean
> path and was the chosen default.

---

## Cutting a release

1. Bump [`VERSION`](../VERSION) (e.g. `1.0.0` → `1.1.0`). This single file is the
   source of truth the updater compares against.
2. Commit and tag:
   ```bash
   git commit -am "release: v1.1.0"
   git tag v1.1.0 && git push --tags
   ```
3. Build the release zip:
   ```bash
   ./venv/bin/python scripts/make_release_zip.py
   # -> dist/Mariposa-Studio-v1.1.0.zip
   ```
   It uses `git archive`, so the zip is exactly the tracked files at top level —
   `venv/`, `exports/` and `.env` are excluded automatically.
4. On GitHub, create a **Release** for tag `v1.1.0` and **attach the zip** as an
   asset. Write the changelog in the release body — it shows up as the update
   notes.

Anyone running an older `VERSION` sees the **Update now** banner on next launch.

> Version compare is numeric per dotted segment (`1.10.0 > 1.9.0`). Keep tags and
> `VERSION` in sync; the tag name (`tag_name`) is what the app reads as the
> remote version.

---

## First install on a clean machine (your teammate)

1. Download the release zip and unzip somewhere stable
   (e.g. `~/Applications/Mariposa Studio` — **not** the Downloads folder, since the
   app updates in place).
2. Run the **one** installer for the OS:
   - macOS: right-click `install-mac.command` → **Open**.
   - Windows: double-click `install-windows.bat`.
   It installs Python (if missing), ffmpeg, the app venv, WhisperX (~3 GB), and
   prompts once for the Gemini key.
3. Launch `Mariposa Studio.app` / `.command` (macOS) or `Mariposa Studio.bat`
   (Windows).

### The unsigned-app warning (unavoidable without certificates)

The app isn't code-signed or notarized (that needs an Apple Developer ID,
~99 USD/yr, and a Windows signing cert). So the **first** launch warns:

- **macOS** — "unidentified developer". Right-click the `.app` → **Open** →
  **Open**. macOS remembers the choice. (If double-clicking is blocked, the
  right-click path always works.)
- **Windows** — SmartScreen "Windows protected your PC". Click **More info** →
  **Run anyway**.

This is honest friction we can't remove from a source-based, unsigned
distribution — it's a one-time click per machine, not per launch.

---

## How an update actually applies

`src/updater.py` on launch (background thread):

1. Reads local `VERSION`, fetches `releases/latest` from the GitHub API.
2. If the release is newer, shows the banner.
3. **Update now**: downloads the zip → extracts to a temp dir → overlays the
   source over the install, **skipping** `venv/`, `exports/`, `.env`, `.git`,
   `__pycache__` → reinstalls deps **only if `requirements.txt` changed** →
   relaunches via `os.execv`.

Notes & limits (honest):

- It's an **overlay**: changed/new files are written; a file *deleted* in the new
  version isn't removed from an old install (rare; harmless for this app). A
  clean reinstall is the fallback if that ever bites.
- A dependency change triggers `pip install` into the existing venv, so an update
  that adds a package needs network and ~a minute.
- If the install folder isn't writable (e.g. dropped in `/Applications` with
  restricted perms), the update fails gracefully and the app keeps running on the
  current version — install into a user-writable location.
