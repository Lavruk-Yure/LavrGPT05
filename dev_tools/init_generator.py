# init_generator.py
"""
Генератор __init__.py для підпакетів проєкту LavrGPT05.

Принципи:
- Працює лише з підпапками проєкту.
- Кореневий __init__.py не читається, не створюється
  і не змінюється.
- Може створювати або оновлювати __init__.py тільки
  в підпакетах.
- Для tests/ та experiments генерує мінімальний __init__.
- Для інших пакетів формує __all__ за локальними
  *.py модулями.
- Існуючі __init__.py без --force не перезаписуються.

Увага:
- Цей інструмент не є джерелом метаданих
  застосунку.
- Версія, назва продукту, trial/policy та інші
  константи
  беруться з core/app_meta.py.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import List

LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SPECIAL_FOLDERS = {"core", "brokers", "ui", "monitoring", "strategies"}
SKIP_DIR_NAMES = {
    ".git",
    ".idea",
    ".vs",
    ".pytest_cache",
    ".mypy_cache",
    "__pycache__",
    "venv",
    "venv313",
}
SKIP_NAME_PREFIXES = (".", "_")
MAX_LINE_LENGTH = 88


def setup_logging() -> None:
    """Налаштувати базовий debug-logging."""
    if logging.getLogger().handlers:
        return

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def is_skipped_dir(path_dir: Path) -> bool:
    """Перевірити, чи папку треба пропустити."""
    if not path_dir.is_dir():
        return True

    if path_dir.name in SKIP_DIR_NAMES:
        return True

    if path_dir.name.startswith(SKIP_NAME_PREFIXES):
        return True

    if any(part in SKIP_DIR_NAMES for part in path_dir.parts):
        return True

    return False


def list_all_python_folders(root: Path) -> List[Path]:
    """Повернути можливі Python-підпакети."""
    folders: List[Path] = []

    for path_item in root.rglob("*"):
        if not path_item.is_dir():
            continue

        if is_skipped_dir(path_item):
            LOGGER.debug("Skip dir: %s", path_item)
            continue

        if path_item.resolve() == root.resolve():
            LOGGER.debug("Skip project root: %s", path_item)
            continue

        folders.append(path_item)

    folders_sorted = sorted(folders)
    LOGGER.debug("Found candidate folders: %d", len(folders_sorted))
    return folders_sorted


def list_python_modules(folder: Path) -> List[str]:
    """Повернути *.py модулі у папці без __init__.py."""
    modules = sorted(
        file_item.stem
        for file_item in folder.glob("*.py")
        if file_item.is_file() and file_item.name != "__init__.py"
    )
    LOGGER.debug("Folder %s modules: %s", folder, modules)
    return modules


def _format_multiline_all(modules: List[str]) -> str:
    """Сформатувати багаторядковий список __all__."""
    if not modules:
        return "[]"

    parts = [f'"{module_name}"' for module_name in modules]
    lines: List[str] = []
    current = "    "

    for part in parts:
        if len(current) + len(part) + 2 > MAX_LINE_LENGTH:
            lines.append(current.rstrip())
            current = f"    {part}, "
        else:
            current += f"{part}, "

    lines.append(current.rstrip(", "))
    return "[\n" + "\n".join(lines) + "\n]"


def generate_init_content(folder: Path, modules: List[str]) -> str:
    """Згенерувати вміст __init__.py для папки."""
    package_name = folder.name

    if "test" in package_name.lower() or package_name == "experiments":
        LOGGER.debug("Generate minimal __init__ for package: %s", package_name)
        return (
            "# __init__.py\n"
            f'"""Пакет {package_name}."""\n\n'
            "from __future__ import annotations\n\n"
            "__all__ = []\n"
        )

    header = (
        "# __init__.py\n"
        f'"""Ініціалізаційний модуль пакету '
        f'{package_name}."""\n\n'
        "from __future__ import annotations\n\n"
    )

    if not modules:
        LOGGER.debug("Generate empty __all__ for package: %s", package_name)
        return header + "__all__ = []\n"

    import_lines = "\n".join(
        f"    from .{module_name} import *  # noqa" for module_name in modules
    )
    imports_block = (
        "# Імпортуємо модулі без падіння; частина файлів може "
        "бути в розробці.\n"
        "try:\n"
        f"{import_lines}\n"
        "except ImportError:\n"
        "    pass\n\n"
    )

    all_block = "__all__ = " + _format_multiline_all(modules) + "\n"

    LOGGER.debug(
        "Generate package __init__ for %s with %d modules",
        package_name,
        len(modules),
    )
    return header + imports_block + all_block


def create_or_update_init(path_init: Path, content: str, force: bool = False) -> str:
    """
    Створити або оновити __init__.py.

    Повертає:
    - created
    - updated
    - skipped
    """
    project_root_init = PROJECT_ROOT / "__init__.py"

    if path_init.resolve() == project_root_init.resolve():
        LOGGER.debug("Skip root __init__.py: %s", path_init)
        return "skipped"

    if path_init.exists():
        if not force:
            LOGGER.debug("Skip existing __init__.py without --force: %s", path_init)
            return "skipped"

        old_content = path_init.read_text(encoding="utf-8")
        if old_content == content:
            LOGGER.debug("Skip unchanged __init__.py: %s", path_init)
            return "skipped"

        path_init.write_text(content, encoding="utf-8")
        LOGGER.debug("Updated __init__.py: %s", path_init)
        return "updated"

    path_init.parent.mkdir(parents=True, exist_ok=True)
    path_init.write_text(content, encoding="utf-8")
    LOGGER.debug("Created __init__.py: %s", path_init)
    return "created"


def main() -> int:
    """Точка входу."""
    setup_logging()

    parser = argparse.ArgumentParser(
        description=(
            "Генератор __init__.py для підпакетів LavrGPT05"
        )
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Перезаписати __init__.py у підпакетах",
    )
    args = parser.parse_args()

    print(
        "🔧 Генерація __init__.py у підпакетах проєкту: "
        f"{PROJECT_ROOT}"
    )
    print(
        "⚙️  Кореневий __init__.py не читається "
        "і не змінюється."
    )

    created = 0
    updated = 0
    skipped = 0

    folders = list_all_python_folders(PROJECT_ROOT)
    print(
        f"📁 Знайдено {len(folders)} папок для перевірки.\n"
    )

    for folder in folders:
        modules = list_python_modules(folder)
        content = generate_init_content(folder, modules)
        status = create_or_update_init(folder / "__init__.py", content, args.force)

        if status == "created":
            created += 1
            print(f"✅ Створено: {folder / '__init__.py'}")
        elif status == "updated":
            updated += 1
            print(f"🔄 Оновлено: {folder / '__init__.py'}")
        else:
            skipped += 1

    print("\nПідсумок:")
    print(f"  створено: {created}")
    print(f"  оновлено: {updated}")
    print(f"  пропущено: {skipped}")
    print("Готово ✅")

    LOGGER.debug(
        "Done: created=%d updated=%d skipped=%d",
        created,
        updated,
        skipped,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
