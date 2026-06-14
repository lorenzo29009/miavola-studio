@echo off
REM Mariposa Studio - Windows installer entry point.
REM The real work is in scripts\install-windows.ps1 (PowerShell is far more
REM reliable for Python/ffmpeg detection, downloads, PATH and shortcuts).
REM This wrapper just launches it with the execution policy bypassed for THIS
REM run only (no machine policy change).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-windows.ps1"
echo.
pause
