# build_all.py
# -*- coding: utf-8 -*-
"""
LavrGPT05 — централізований запуск компіляції UI та ресурсів.
Працює незалежно від директорії запуску.
Без activate.bat — запускаємо .bat напряму в dev_tools.

Додано:
- Валідація критичних JSON (strings.json, strings_fallback.json) перед збіркою.
- Друк і stdout, і stderr.
- Пошук типових помилок (у т.ч. JSON).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


def validate_json(path: Path) -> list[str]:
    """Повертає список проблем (порожній, якщо JSON валідний)."""
    try:
        json.loads(path.read_text(encoding="utf-8"))
        return []
    except Exception as exc:  # noqa
        return [f"{path}: {exc}"]


def run_bat(bat_path: Path, work_dir: Path) -> tuple[int, str]:
    """Запускає .bat без активації venv і повертає (returncode, combined_output)."""
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
        r"JSONDecodeError",
        r"Expecting property name",
        r"Extra data",
        r"Trailing comma",
        r"invalid json",
    ]

    for line in output.splitlines():
        for pat in patterns:
            if re.search(pat, line, re.IGNORECASE):
                problems.append(line.strip())
                break

    return problems


def main() -> int:
    root_dir = Path(__file__).resolve().parent.parent
    dev_tools = root_dir / "dev_tools"

    # --- Критичні JSON, які ламають переклад/ресурси ---
    strings = root_dir / "lang" / "strings.json"
    fallback = root_dir / "lang" / "strings_fallback.json"

    bad: list[str] = []
    if strings.exists():
        bad += validate_json(strings)
    else:
        bad.append(f"{strings}: файл не знайдено")

    if fallback.exists():
        bad += validate_json(fallback)
    else:
        bad.append(f"{fallback}: файл не знайдено")

    if bad:
        print("\n❌ Некоректний JSON (збірку зупинено):")
        for x in bad:
            print("   ", x)
        return 1

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
        print("🎯 Усі файли успішно зібрані без помилок.")
        print("=" * 60)
        return 0

    print("⚠️ Завершено з попередженнями/помилками. Дивись журнал вище.")
    print("=" * 60)
    return 2


if __name__ == "__main__":
    sys.exit(main())
