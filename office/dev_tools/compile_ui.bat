@echo off
chcp 65001 >nul
setlocal

REM ============================================
REM LGEOffice — compile_ui.bat
REM Запуск з терміналу:
REM   .\office\dev_tools\compile_ui.bat
REM ============================================

REM Перейти в корінь office (на 1 рівень вище dev_tools)
cd /d "%~dp0.."

echo.
echo 🔧 Генерація UI (*.ui) → ui_*.py ...
echo.

for %%F in ("ui\*.ui") do (
  echo.
  echo ▶ %%~nxF
  pyside6-uic "%%F" -o "ui\ui_%%~nF.py"
  if errorlevel 1 (
    echo.
    echo ❌ Помилка генерації UI для: %%~nxF
    exit /b 1
  )
)

echo.
echo ✅ UI-файли успішно згенеровані:
echo    %CD%\ui
exit /b 0
