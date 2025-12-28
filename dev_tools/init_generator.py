# dev_tools/init_generator.py
"""Генератор __init__.py для проєкту LavrGPT05.

Особливості:
- Проходить усі вкладені папки (включно з tests/).
- Спеціальні пакети: core, brokers, ui, monitoring, strategies —
  отримують "розумні" __init__.
- experiments — завжди отримує мінімальний __init__.
- Кореневий __init__.py створюється лише один раз і не перезаписується.
- __all__ формується у багаторядковий блок (рядки ≤ 88 символів).
- Підсумок: створено / оновлено / пропущено.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPECIAL_FOLDERS = {"core", "brokers", "ui", "monitoring", "strategies"}
SKIP_PREFIXES = (".", "_")
MAX_LINE_LENGTH = 88


def list_all_python_folders(root: Path) -> List[Path]:
    """Повертає всі папки проєкту, які можуть містити Python-код."""
    folders: List[Path] = []
    for p in root.rglob("*"):
        if p.is_dir() and not p.name.startswith(SKIP_PREFIXES):
            # виключаємо приховані або системні (venv, .git)
            if any(x in p.parts for x in (".git", "venv", "__pycache__")):
                continue
            folders.append(p)
    return sorted(folders)


def list_python_modules(folder: Path) -> List[str]:
    """Повертає список Python-модулів (без __init__.py)."""
    return sorted(
        [f.stem for f in folder.glob("*.py") if f.is_file() and f.name != "__init__.py"]
    )


def _format_multiline_all(modules: List[str]) -> str:
    """Форматує __all__ як багаторядковий список."""
    if not modules:
        return "[]"

    parts = [f'"{m}"' for m in modules]
    lines: List[str] = []
    current = "    "
    for part in parts:
        if len(current) + len(part) + 2 > MAX_LINE_LENGTH:
            lines.append(current.rstrip())
            current = "    " + part + ", "
        else:
            current += part + ", "
    lines.append(current.rstrip(", "))
    return "[\n" + "\n".join(lines) + "\n]"


def generate_init_content(folder: Path, modules: List[str]) -> str:
    """Генерує вміст __init__.py відповідно до правил."""
    name = folder.name

    # Для tests/ або experiments — мінімальний варіант
    if "test" in name.lower() or name == "experiments":
        return f'"""Пакет {name}."""\n\n__all__ = []\n'

    header = (
        f'"""Ініціалізаційний модуль пакету {name}."""\n\n'
        "from __future__ import annotations\n\n"
    )

    if not modules:
        return header + "__all__ = []\n"

    # import_lines = "\n".join([f"    from .{m} import *" for m in modules])
    # imports_block = (
    #     "# Імпортуємо класи без падіння (модулі можуть бути в розробці)\n"
    #     "try:\n"
    #     f"{import_lines}\n"
    #     "except ImportError:\n"
    #     "    pass\n\n"
    # )
    import_lines = "\n".join([f"    from .{m} import *  # noqa" for m in modules])
    imports_block = (
        "# Імпортуємо класи без падіння (модулі можуть бути в розробці)\n"
        "try:\n"
        f"{import_lines}\n"
        "except ImportError:\n"
        "    pass\n\n"
    )

    all_block = "__all__ = " + _format_multiline_all(modules) + "\n"
    return header + imports_block + all_block


def create_or_update_init(path: Path, content: str, force: bool = False) -> str:
    """Створює або оновлює __init__.py; повертає статус."""
    root_init = PROJECT_ROOT / "__init__.py"

    if path.exists():
        if path.resolve() == root_init.resolve():
            return "skipped"
        if not force:
            return "skipped"
        old = path.read_text(encoding="utf-8")
        if old == content:
            return "skipped"
        path.write_text(content, encoding="utf-8")
        return "updated"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return "created"


def main() -> None:
    parser = argparse.ArgumentParser(description="Генератор __init__.py для LavrGPT05")
    parser.add_argument(
        "--force", action="store_true", help="Перезаписати існуючі файли"
    )
    args = parser.parse_args()

    print(f"🔧 Генерація __init__.py у проєкті: {PROJECT_ROOT}")

    root_init = PROJECT_ROOT / "__init__.py"
    if not root_init.exists():
        root_init.write_text(
            '__version__ = "1.0.0"\n__author__ = "LavrGPT Team"\n', encoding="utf-8"
        )
        print(f"✅ Створено: {root_init}")
    else:
        print("⚙️  Кореневий __init__.py існує і не змінюється.")
    created = updated = skipped = 0
    folders = list_all_python_folders(PROJECT_ROOT)
    print(f"📁 Знайдено {len(folders)} папок для перевірки.\n")

    for folder in folders:
        modules = list_python_modules(folder)
        content = generate_init_content(folder, modules)
        status = create_or_update_init(folder / "__init__.py", content, args.force)

        match status:
            case "created":
                created += 1
                print(f"✅ Створено: {folder / '__init__.py'}")
            case "updated":
                updated += 1
                print(f"🔄 Оновлено: {folder / '__init__.py'}")
            case _:
                skipped += 1

    print("\nПідсумок:")
    print(f"  створено: {created}, оновлено: {updated}, пропущено: {skipped}")
    print("Готово ✅")


if __name__ == "__main__":
    main()
