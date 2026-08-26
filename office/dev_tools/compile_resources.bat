@echo off
chcp 65001 >nul
setlocal

REM ============================================
REM LGEOffice — compile_resources.bat
REM Запуск з терміналу:
REM   .\office\dev_tools\compile_resources.bat
REM ============================================

REM Перейти в корінь office (на 1 рівень вище dev_tools)
cd /d "%~dp0.."

echo.
echo 🔧 Компіляція resources.qrc → resources_rc.py ...
echo.

pyside6-rcc "resources.qrc" -o "resources_rc.py"
if errorlevel 1 (
  echo.
  echo ❌ Помилка компіляції resources.qrc
  exit /b 1
)

echo.
echo ✅ Ресурс успішно згенеровано:
echo    %CD%\resources_rc.py
exit /b 0
