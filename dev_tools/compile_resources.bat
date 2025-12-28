@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ------------------------------------------------------------
REM LavrGPT05 — компіляція resources.qrc (який лежить у корені)
REM через PySide6 (pyside6-rcc)
REM Вивід resources_rc.py → у корінь проєкту
REM ------------------------------------------------------------

set RCC=D:\LavrGPT\venv313\Scripts\pyside6-rcc.exe
set ROOT_DIR=D:\LavrGPT\LavrGPT05

set QRC_FILE=%ROOT_DIR%\resources.qrc
set OUTPUT_FILE=%ROOT_DIR%\resources_rc.py

if not exist "%RCC%" (
    echo ❌ Не знайдено pyside6-rcc.exe
    pause
    exit /b 1
)

if not exist "%QRC_FILE%" (
    echo ❌ Не знайдено resources.qrc у корені проекту
    pause
    exit /b 1
)

echo.
echo 🔧 Компіляція resources.qrc → resources_rc.py ...
echo.

"%RCC%" "%QRC_FILE%" -o "%OUTPUT_FILE%"

if %ERRORLEVEL% NEQ 0 (
    echo ❌ Помилка компіляції ресурсу.
    pause
    exit /b 1
)

echo.
echo ✅ Ресурс успішно згенерованo:
echo    %OUTPUT_FILE%
echo.

endlocal
