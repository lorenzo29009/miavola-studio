@echo off
setlocal
cd /d "%~dp0"

if "%~1"=="" (
    echo.
    echo ====================================================
    echo  Drag a video file onto this script.
    echo ====================================================
    echo.
    pause
    exit /b 1
)

set "VIDEO=%~1"
set "NAME=%~nx1"

cls
echo ====================================================
echo  Captions DE
echo ====================================================
echo.
echo Processing:  %NAME%
echo.
echo (First run on a new machine downloads ~3 GB of models;
echo  this only happens once.)
echo.

set "PYEXE=%USERPROFILE%\whisperx\Scripts\python.exe"
if not exist "%PYEXE%" (
    echo X WhisperX is not installed yet.
    echo   Run install-windows.bat first.
    echo.
    pause
    exit /b 1
)

"%PYEXE%" caption.py "%VIDEO%"

echo.
echo ====================================================
echo  Done!
echo ====================================================
echo.
echo Your .srt file is next to the video:
echo   %~dp1
echo.
echo Tip: drop another video onto this script to do another.
echo.
pause
endlocal
