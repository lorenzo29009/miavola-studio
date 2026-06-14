@echo off
setlocal
cd /d "%~dp0"

cls
echo ====================================================
echo  Flow Cropper - Installer for Windows
echo ====================================================
echo.
echo This will install:
echo   - ffmpeg (video crop engine)
echo.
echo Python 3.10+ must already be installed.
echo If not, get it from https://python.org (check "Add Python to PATH").
echo.
pause

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo X Python is not on PATH.
    echo   Install Python 3.10+ from https://python.org
    echo   IMPORTANT: tick "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo.
    echo Installing ffmpeg via winget...
    winget install --silent --source winget --accept-package-agreements --accept-source-agreements Gyan.FFmpeg
    if errorlevel 1 (
        echo.
        echo X Could not install ffmpeg automatically.
        echo   Download manually from https://www.gyan.dev/ffmpeg/builds/
        echo   and add the bin/ folder to your PATH.
        pause
        exit /b 1
    )
    echo.
    echo NOTE: you may need to restart this window or your computer
    echo       for ffmpeg to be picked up on PATH.
) else (
    echo.
    echo ffmpeg is already installed.
)

echo.
echo ====================================================
echo  Done!
echo ====================================================
echo.
echo To crop a campaign:
echo   Double-click 'crop.bat'
echo.
pause
endlocal
