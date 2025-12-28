@echo off
chcp 65001 >nul
setlocal ENABLEDELAYEDEXPANSION

:: Шлях до проєкту (можеш змінити за потреби)
set PROJECT_PATH=D:\LavrGPT\LavrGPT05

cd /d %PROJECT_PATH%
echo ========================================
echo 🕐 Початок CI-перевірки: %date% %time%
echo ========================================

:: 1. ISORT
echo.
echo ---------- [1/4] ISORT ----------
set t1=%time%
isort . --profile black
set t2=%time%
echo Завершено isort: від %t1% до %t2%
echo ----------------------------------------

:: 2. BLACK
echo.
echo ---------- [2/4] BLACK ----------
set t1=%time%
black . --check
set t2=%time%
echo Завершено black: від %t1% до %t2%
echo ----------------------------------------

:: 3. FLAKE8
echo.
echo ---------- [3/4] FLAKE8 ----------
set t1=%time%
flake8 . --statistics
set t2=%time%
echo Завершено flake8: від %t1% до %t2%
echo ----------------------------------------

:: 4. PYTEST
echo.
echo ---------- [4/4] PYTEST ----------
set t1=%time%
pytest -v --tb=short
set t2=%time%
echo Завершено pytest: від %t1% до %t2%
echo ----------------------------------------

echo ========================================
echo ✅ CI-перевірка завершена о %time%
echo ========================================

pause
endlocal
