# build_all.py
# -*- coding: utf-8 -*-
"""
LGEOffice — централізований запуск компіляції UI та ресурсів (office/dev_tools).

Особливості:
- Працює незалежно від директорії запуску.
- НЕ перевіряє lang/strings*.json (у LGEOffice перекладів поки немає).
- Викликає compile_resources.bat та compile_ui.bat (як у LGE), бо вони у тебе працюють.
- Друк і stdout, і stderr.
- Пошук типових помилок у виводі.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def run_bat(bat_path: Path, work_dir: Path) -> tuple[int, str]:
    """Запускає .bat напряму і повертає (returncode, combined_output)."""
    if not bat_path.exists():
        return 1, f"❌ Не знайдено файл: {bat_path}"

    print(f"\n▶ Виконується: {bat_path.name}")

    cmd = f'cmd.exe /c "cd /d {work_dir} && {bat_path.name}"'

    process = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=120,
    )

    stdout = (process.stdout or "").strip()
    stderr = (process.stderr or "").strip()
    combined = "\n".join([s for s in (stdout, stderr) if s])

    if combined:
        print(combined)

    return process.returncode, combined


def check_output_for_errors(output: str) -> list[str]:
    """Шукає ключові помилки у виводі (stdout+stderr)."""
    problems: list[str] = []

    patterns = [
        r"Cannot find file",
        r"No resources",
        r"\berror\b",
        r"Traceback",
        r"JSONDecodeError",
        r"ModuleNotFoundError",
    ]

    for line in output.splitlines():
        for pat in patterns:
            if re.search(pat, line, re.IGNORECASE):
                problems.append(line.strip())
                break

    return problems


def main() -> int:
    dev_tools = Path(__file__).resolve().parent

    res_bat = dev_tools / "compile_resources.bat"
    ui_bat = dev_tools / "compile_ui.bat"

    all_ok = True

    # ---- QRC ----
    code_res, out_res = run_bat(res_bat, dev_tools)
    errs_res = check_output_for_errors(out_res)
    if code_res != 0 or errs_res:
        all_ok = False
        print("\n❌ Помилки у compile_resources:")
        if code_res != 0:
            print(f"   Return code: {code_res}")
        for e in errs_res:
            print("   ", e)
    else:
        print("✅ Ресурси успішно зібрані.")

    # ---- UI ----
    code_ui, out_ui = run_bat(ui_bat, dev_tools)
    errs_ui = check_output_for_errors(out_ui)
    if code_ui != 0 or errs_ui:
        all_ok = False
        print("\n❌ Помилки у compile_ui:")
        if code_ui != 0:
            print(f"   Return code: {code_ui}")
        for e in errs_ui:
            print("   ", e)
    else:
        print("✅ UI-файли успішно згенеровані.")

    # ---- Summary ----
    print("\n" + "=" * 60)
    if all_ok:
        print("🎯 LGEOffice: збірка завершена без помилок.")
        print("=" * 60)
        return 0

    print("⚠️ LGEOffice: завершено з попередженнями/помилками. Дивись журнал вище.")
    print("=" * 60)
    return 2


if __name__ == "__main__":
    sys.exit(main())
