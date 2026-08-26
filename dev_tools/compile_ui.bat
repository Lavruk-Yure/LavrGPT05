@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ------------------------------------------------------------
REM LavrGPT05 — компіляція .ui файлів через PySide6
REM ------------------------------------------------------------

set PYUIC=D:\LavrGPT\venv313\Scripts\pyside6-uic.exe
set SRC_DIR=D:\LavrGPT\LavrGPT05\ui
set DST_DIR=D:\LavrGPT\LavrGPT05\ui

if not exist "%PYUIC%" (
    echo ❌ Не знайдено pyside6-uic.exe
    pause
    exit /b 1
)

echo.
echo 🔧 Компіляція .ui через PySide6...
echo.

for %%F in (%SRC_DIR%\*.ui) do (
    set NAME=%%~nF
    echo ▶ %%~nxF → ui_!NAME!.py
    "%PYUIC%" "%%F" -o "%DST_DIR%\ui_!NAME!.py"
)

echo.
echo ✅ Компіляцію .ui завершено.
echo.

endlocal
