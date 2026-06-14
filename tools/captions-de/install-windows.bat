@echo off
setlocal
cd /d "%~dp0"

cls
echo ====================================================
echo  Captions DE - Installer for Windows
echo ====================================================
echo.
echo This will install:
echo   - ffmpeg (via winget)
echo   - WhisperX (German speech-to-text, ~3 GB)
echo.
echo Python 3.10+ must already be installed.
echo If not, install from https://python.org (check "Add to PATH").
echo.
pause

REM 1. Check Python
where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo X Python is not on PATH.
    echo   Install Python 3.10+ from https://python.org
    echo   IMPORTANT: check the "Add Python to PATH" box during install.
    echo.
    pause
    exit /b 1
)

REM 2. Install ffmpeg via winget
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo.
    echo Installing ffmpeg...
    winget install --silent --source winget --accept-package-agreements --accept-source-agreements Gyan.FFmpeg
    echo.
    echo NOTE: You may need to restart your terminal or computer
    echo       for ffmpeg to be on PATH.
)

REM 3. Set up venv + whisperx
echo.
echo Setting up Python environment for WhisperX...
python install.py
if errorlevel 1 (
    echo.
    echo X Setup failed. See messages above.
    pause
    exit /b 1
)

REM 4. Gemini API key
echo.
echo ====================================================
echo  Gemini API key (free)
echo ====================================================
echo.
echo Open in your browser:
echo   https://aistudio.google.com/apikey
echo.
echo Sign in with a Google account, click "Create API key",
echo and copy the key.
echo.
set /p key="Paste your key here (or press Enter to skip): "

if not "%key%"=="" (
    > .env echo GEMINI_API_KEY=%key%
    echo Key saved to .env
) else (
    if not exist .env copy .env.example .env >nul
    echo Skipped. Edit .env later to add the key.
)

echo.
echo ====================================================
echo  Done!
echo ====================================================
echo.
echo To create captions for a video:
echo   Drag any .mp4 file onto 'caption.bat'
echo.
echo The .srt file appears next to your video.
echo.
pause
endlocal
