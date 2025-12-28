# build_all.py
# -*- coding: utf-8 -*-
"""
LavrGPT05 — централізований запуск компіляції UI та ресурсів.
Працює незалежно від директорії запуску.
Видалено активацію середовища — більше не потрібна.
"""

import re
import subprocess
import sys
from pathlib import Path


def run_bat(bat_path: Path, work_dir: Path) -> tuple[int, str]:
    """Запускає .bat без активації venv."""
    if not bat_path.exists():
        return 1, f"❌ Не знайдено файл: {bat_path}"

    print(f"\n▶ Виконується: {bat_path.name}")

    # ВАЖЛИВО: запускаємо .bat напряму — без activate.bat
    cmd = f'cmd.exe /c "cd /d {work_dir} && {bat_path.name}"'

    process = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=60,
    )

    output = process.stdout.strip()
    print(output)
    return process.returncode, output


def check_output_for_errors(output: str) -> list[str]:
    """Шукає ключові помилки у виводі."""
    problems = []
    for line in output.splitlines():
        if re.search(r"(Cannot find file|error|No resources)", line, re.IGNORECASE):
            problems.append(line.strip())
    return problems


def main():
    root_dir = Path(__file__).resolve().parent.parent
    dev_tools = root_dir / "dev_tools"

    res_bat = dev_tools / "compile_resources.bat"
    ui_bat = dev_tools / "compile_ui.bat"

    all_ok = True

    # ---- QRC ----
    code_res, out_res = run_bat(res_bat, dev_tools)
    errs_res = check_output_for_errors(out_res)
    if errs_res:
        all_ok = False
        print("\n❌ Помилки у compile_resources:")
        for e in errs_res:
            print("   ", e)
    else:
        print("✅ Ресурси успішно зібрані.")

    # ---- UI ----
    code_ui, out_ui = run_bat(ui_bat, dev_tools)
    errs_ui = check_output_for_errors(out_ui)
    if errs_ui:
        all_ok = False
        print("\n❌ Помилки у compile_ui:")
        for e in errs_ui:
            print("   ", e)
    else:
        print("✅ UI-файли успішно згенеровані.")

    # ---- Summary ----
    print("\n" + "=" * 60)
    if all_ok:
        print("🎯 Усі файли успішно зібрані без помилок.")
    else:
        print("⚠️ Завершено з попередженнями. Перевір журнал вище.")
    print("=" * 60)


if __name__ == "__main__":
    sys.exit(main())
