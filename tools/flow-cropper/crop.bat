@echo off
setlocal
cd /d "%~dp0"

cls
echo ====================================================
echo  Flow Cropper - 9:16 to 4:5
echo ====================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo X Python is not on PATH.
    echo   Install Python 3 from https://python.org
    echo   IMPORTANT: check "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

python crop.py

echo.
pause
endlocal
