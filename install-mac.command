#!/bin/bash
set -e
cd "$(dirname "$0")"

clear
cat <<'BANNER'
====================================================
 Mariposa Studio — Installer for macOS
====================================================

This single installer sets up EVERYTHING needed to run
the app and all 4 bundled tools:

  • Homebrew (if missing)
  • Python 3.12 (only if no 3.10–3.13 is found)
  • ffmpeg               (Flow Cropper + Captions)
  • A local virtualenv in ./venv (PySide6-Essentials,
    opencv) for the app + Extract Frame
  • WhisperX in ~/whisperx (~3 GB; German Captions)
  • Your Gemini API key   (Camera Prompts + Animator
    + Captions polishing)

When it finishes, just double-click "Mariposa Studio.app".

Press Enter to continue, or Ctrl+C to cancel.
BANNER
read

# ---- Locate Homebrew (Apple Silicon vs Intel) ----------------------------
if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
elif [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
fi

if ! command -v brew >/dev/null 2>&1; then
    echo ""
    echo ">> Installing Homebrew. You may be asked for your Mac password."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    if [ -x /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [ -x /usr/local/bin/brew ]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi
fi

# A usable interpreter must actually load its core C-extension stdlib. A broken
# Homebrew python@3.12 revision shipped a `pyexpat` linked against the OLD system
# libexpat, so `import xml.parsers.expat` crashes with
#   "Symbol not found: _XML_SetAllocTrackerActivationThreshold"
# which then takes down pip/get-pip (it imports xmlrpc -> expat). Reject such an
# interpreter instead of building a doomed venv on top of it.
py_core_ok() {  # $1 = interpreter
    "$1" -c 'import xml.parsers.expat, ssl, ctypes' >/dev/null 2>&1
}

# ---- Pick a Python that PySide6 supports (3.10 – 3.13) AND actually works ----
PYBIN=""
SAW_BROKEN_PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 \
                 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 \
                 /opt/homebrew/bin/python3.11 /opt/homebrew/bin/python3.10 \
                 /usr/local/bin/python3.13 /usr/local/bin/python3.12 \
                 /usr/local/bin/python3.11 /usr/local/bin/python3.10 \
                 "$HOME/.local/bin/python3.13" "$HOME/.local/bin/python3.12" \
                 "$HOME/.local/bin/python3.11" "$HOME/.local/bin/python3.10"; do
    if command -v "$candidate" >/dev/null 2>&1 || [ -x "$candidate" ]; then
        ver=$("$candidate" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo "")
        case "$ver" in
            3.10|3.11|3.12|3.13)
                if py_core_ok "$candidate"; then
                    PYBIN="$candidate"; break
                else
                    echo ">> Skipping $candidate — its core stdlib (xml/expat) won't load (broken install)."
                    SAW_BROKEN_PY="$candidate"
                fi ;;
        esac
    fi
done

if [ -z "$PYBIN" ]; then
    echo ""
    if [ -n "$SAW_BROKEN_PY" ]; then
        # A Python is installed but broken — almost always Homebrew's python@3.12
        # mis-linked against expat. Relink/rebuild expat + python, then retry.
        echo ">> Found a broken Python ($SAW_BROKEN_PY). Repairing via Homebrew (expat + python)..."
        brew update || true
        brew reinstall expat 2>/dev/null || true
        brew reinstall python@3.12 2>/dev/null || brew install python@3.12 || true
    else
        echo ">> No usable Python found. Installing python@3.12 via Homebrew..."
        brew install python@3.12
    fi
    PYBIN="$(brew --prefix)/bin/python3.12"
fi

if ! py_core_ok "$PYBIN"; then
    echo ""
    echo "!! The Python at $PYBIN is still broken (its xml/expat module won't load)."
    echo "   This is usually a Homebrew linking problem. Fix it manually with:"
    echo "       brew update && brew reinstall expat python@3.12"
    echo "   then re-run this installer."
    exit 1
fi

echo ""
echo ">> Using Python: $PYBIN  ($("$PYBIN" --version))"

# ---- ffmpeg (Flow Cropper + Captions need the binary on PATH) ------------
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo ""
    echo ">> Installing ffmpeg..."
    brew install ffmpeg
else
    echo ">> ffmpeg already installed."
fi

# ---- Recreate the app venv -----------------------------------------------
if [ -d ./venv ]; then
    echo ">> Removing previous venv..."
    rm -rf ./venv
fi

echo ">> Creating ./venv..."
# Some Python builds (notably Homebrew's, which `brew install ffmpeg` may have
# just pulled in) ship a broken `ensurepip`, so a plain `python -m venv` dies
# with "ensurepip ... returned non-zero exit status 1". If that happens, build
# the venv WITHOUT pip and bootstrap pip ourselves below — works regardless of
# why ensurepip failed.
if ! "$PYBIN" -m venv venv; then
    echo ">> venv pip-bootstrap (ensurepip) failed — retrying without pip..."
    rm -rf ./venv
    "$PYBIN" -m venv --without-pip venv
fi

# Make sure pip is actually present (it won't be after --without-pip, and a
# half-broken ensurepip can leave it missing even on the normal path).
if ! ./venv/bin/python -m pip --version >/dev/null 2>&1; then
    echo ">> Bootstrapping pip via get-pip.py..."
    curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/mariposa-get-pip.py
    ./venv/bin/python /tmp/mariposa-get-pip.py
    rm -f /tmp/mariposa-get-pip.py
fi

echo ">> Upgrading pip..."
./venv/bin/python -m pip install --upgrade pip wheel setuptools

# --no-compile sidesteps a pip bug that bytecompiles Jinja .tmpl.py files
# inside the PySide6 wheel and explodes on older Pythons.
echo ">> Installing Python dependencies from requirements.txt..."
./venv/bin/pip install --no-compile -r requirements.txt

echo ">> Rendering app icon..."
./venv/bin/python src/make_icon.py || echo "(icon generation failed — non-fatal)"

# ---- WhisperX (German Captions, ~3 GB) -----------------------------------
# Force a native-arch Python: a venv built under Rosetta (x86_64) on an arm64
# Mac makes torch dlopen crash. Wipe a mismatched ~/whisperx, then build with
# Homebrew's native python3 via the cross-platform tools/captions-de/install.py.
echo ""
echo "===================================================="
echo " WhisperX — German speech-to-text (~3 GB, required)"
echo "===================================================="
echo ""
echo "WhisperX powers German Captions. It pulls PyTorch + speech models"
echo "(~3 GB) and the first caption run downloads ~3 GB more, so this step"
echo "can take 10–15 minutes."

# WhisperX needs real room: ~3 GB venv + ~3 GB models on the home volume.
# Bail out CLEARLY if there isn't enough, instead of dying mid-download with a
# cryptic "No space left on device".
FREE_KB="$(df -Pk "$HOME" 2>/dev/null | awk 'NR==2{print $4}')"
NEED_KB=7000000
if [ -n "$FREE_KB" ] && [ "$FREE_KB" -lt "$NEED_KB" ]; then
    FREE_GB=$(( FREE_KB / 1024 / 1024 ))
    echo ""
    echo "!! Not enough free disk space for WhisperX."
    echo "   Need ~7 GB free on your home volume; you have about ${FREE_GB} GB."
    echo "   Free up space and re-run this installer to enable Captions."
    echo "   (The other four tools are already set up and work now.)"
else
    SYS_ARCH="$(uname -m)"
    if [ -x "$HOME/whisperx/bin/python" ]; then
        VENV_ARCH="$(file "$HOME/whisperx/bin/python" 2>/dev/null \
            | grep -oE 'arm64|x86_64' | head -n1)"
        if [ -n "$VENV_ARCH" ] && [ "$VENV_ARCH" != "$SYS_ARCH" ]; then
            echo ">> Existing ~/whisperx is $VENV_ARCH but this Mac is $SYS_ARCH —"
            echo "   removing it so it can be rebuilt for the right architecture..."
            rm -rf "$HOME/whisperx"
        fi
    fi

    # WhisperX supports Python 3.10–3.12 ONLY (its pinned ctranslate2/torch have
    # no wheels for 3.13/3.14). A bare `python3` is now often 3.14 on Homebrew,
    # so pin the range explicitly instead of taking the first python3 found.
    WX_PY=""
    for candidate in python3.12 python3.11 python3.10 \
                     /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 /opt/homebrew/bin/python3.10 \
                     /usr/local/bin/python3.12 /usr/local/bin/python3.11 /usr/local/bin/python3.10; do
        if command -v "$candidate" >/dev/null 2>&1 || [ -x "$candidate" ]; then
            v=$("$candidate" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo "")
            case "$v" in 3.10|3.11|3.12)
                if py_core_ok "$candidate"; then WX_PY="$candidate"; break; fi ;;
            esac
        fi
    done
    if [ -z "$WX_PY" ] && py_core_ok "$PYBIN"; then
        # The app interpreter we already validated above is 3.10–3.13; reuse it
        # for WhisperX too if it's in range (3.10–3.12).
        pv=$("$PYBIN" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo "")
        case "$pv" in 3.10|3.11|3.12) WX_PY="$PYBIN" ;; esac
    fi
    if [ -z "$WX_PY" ]; then
        echo ">> No working Python 3.10–3.12 found; installing python@3.12 for WhisperX..."
        brew reinstall python@3.12 2>/dev/null || brew install python@3.12
        WX_PY="$(brew --prefix)/bin/python3.12"
    fi
    echo ">> Setting up WhisperX with $WX_PY  ($("$WX_PY" --version 2>&1))"
    ( cd tools/captions-de && "$WX_PY" install.py ) \
        || echo "(WhisperX setup failed — Captions won't run until this succeeds.)"
fi

# ---- Gemini API key (Camera Prompts + Animator + Captions polishing) -----
echo ""
echo "===================================================="
echo " Gemini API key (free) — used by 3 tools"
echo "===================================================="
echo ""
echo "Open this link in your browser:"
echo "  https://aistudio.google.com/apikey"
echo ""
echo "Sign in with a Google account, click 'Create API key',"
echo "and copy the key."
echo ""
ENV_FILE="tools/captions-de/.env"
# Seed from the template so the optional CAPTION_BRAND/CAPTION_TERMS lines and
# their comments are preserved when we set the key below.
[ ! -f "$ENV_FILE" ] && cp tools/captions-de/.env.example "$ENV_FILE"
EXISTING_KEY="$(grep -E '^GEMINI_API_KEY=.+' "$ENV_FILE" 2>/dev/null | head -n1 | cut -d= -f2-)"
if [ -n "$EXISTING_KEY" ]; then
    echo "A key is already saved in $ENV_FILE — press Enter to keep it."
fi
read -p "Paste your key here (or press Enter to keep/skip): " key

if [ -n "$key" ]; then
    # Shared helper upserts the key (same code path as the Windows installer).
    ./venv/bin/python scripts/upsert_env.py GEMINI_API_KEY "$key"
elif [ -n "$EXISTING_KEY" ]; then
    echo "✓ Keeping existing key."
else
    echo "Skipped. Camera Prompts / Animator / Captions polishing stay off"
    echo "until you add a key (Settings inside the app, or edit $ENV_FILE)."
fi

# ---- Make tool launchers executable --------------------------------------
chmod +x ./tools/captions-de/*.command ./tools/flow-cropper/*.command 2>/dev/null || true

# ---- Clear the download quarantine on the whole folder -------------------
# An unzipped, unsigned .app that's still quarantined gets "App Translocation":
# macOS runs it from a random read-only copy, so it can't find ./venv next to
# it and reports "not installed yet". Stripping the quarantine flag lets the
# .app run in place. (This is why "Mariposa Studio.command" worked but the .app
# didn't.) Also removes the right-click→Open dance on first launch.
xattr -dr com.apple.quarantine . 2>/dev/null || true

cat <<'DONE'

====================================================
 ✓ Mariposa Studio is fully installed!
====================================================

Opening the app now. Next time:
  • Double-click  "Mariposa Studio.app"   (works in place)
  • Or double-click  "Mariposa Studio.command"

DONE

# Launch the app straight away so install flows into a running app.
open "./Mariposa Studio.app" 2>/dev/null || ./venv/bin/python src/studio.py &
sleep 1
