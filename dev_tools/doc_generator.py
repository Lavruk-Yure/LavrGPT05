# doc_generator.py
# noinspection TaskProblemsInspection
"""
doc_generator.py - генератор і оновлювач документації LavrGPT05 LGE.

Функції:
- створює базові документи у doc/
- перевіряє, чи реально існує файл перед логуванням
- додає запис у DevNotes_LGE.md
- оновлює README_DOCS.md
"""
# Використання:
#   python dev_tools/doc_generator.py
#   → у консолі введи: core\encryption_manager.py

from datetime import date
from pathlib import Path

BASE_PATH = Path(__file__).resolve().parent.parent
DOC_PATH = BASE_PATH / "doc"


def ensure_doc_base():
    """Гарантує, що базові документи існують."""
    DOC_PATH.mkdir(exist_ok=True)

    readme_path = DOC_PATH / "README_DOCS.md"
    devnotes_path = DOC_PATH / "DevNotes_LGE.md"

    if not readme_path.exists():
        # noinspection TaskProblemsInspection
        readme_path.write_text(
            f"""# LavrGPT05 — Документація проєкт
> **Гілка:** LGE
> **Дата початку:** {date.today()}
> **Призначення:** централізована документація по модулях LavrGPT05.

---

## 🔹 Основні файли

| Файл | Призначення |
|------|--------------|
| `DevNotes_LGE.md` | Щоденник розробника. |
| `README_DOCS.md` | Індекс документів `doc/`. |

---

*Оновлено:* {date.today()}
*Автор:* Lavruk Y.V. / Еон
""",
            encoding="utf-8",
        )
        print(f"✅ Створено: {readme_path}")
    else:
        print(f"⏩ Пропущено (вже існує): {readme_path}")

    if not devnotes_path.exists():
        # noinspection TaskProblemsInspection
        devnotes_path.write_text(
            f"# DevNotes — LavrGPT05 / LGE \n"
            f"            > **Дата створення:** {date.today()} \n"
            f"            > **Призначення:** короткий щоденник змін у"
            f" проєкті LavrGPT05.\n"
            f"            --- \n"
            f"            ### 🗓 {date.today()} \n"
            f"            - Створено документаційну базу LGE. \n"
            f"            --- \n"
            f"            *Автор:* Lavruk Y.V. \n"
            f"            *Редактор:* Еон",
            encoding="utf-8",
        )
        print(f"✅ Створено: {devnotes_path}")
    else:
        print(f"⏩ Пропущено (вже існує): {devnotes_path}")


def append_devnote_and_readme(module_path: str):
    """Додає запис про новий модуль у DevNotes і README_DOCS.md,
    якщо файл реально існує."""
    module_path = module_path.strip().replace("/", "\\")
    if not module_path.endswith(".py"):
        print("⚠️ Вкажи коректний шлях до .py файлу, напр.: core\\token_manager.py")
        return False

    abs_path = BASE_PATH / module_path
    if not abs_path.exists():
        print(
            f"❌ Помилка: файл '{abs_path}' не знайдено. Запис у документацію скасовано."
        )
        return False

    notes_path = DOC_PATH / "DevNotes_LGE.md"
    readme_path = DOC_PATH / "README_DOCS.md"

    # --- DevNotes ---
    entry = (
        f"\n\n### 🗓 {date.today()}\n"
        f"- Додано `{module_path}` у структуру LavrGPT05.\n"
        f"- Перевірити відповідність flake8/black/isort."
    )
    with notes_path.open("a", encoding="utf-8") as f:
        f.write(entry)
    # noinspection TaskProblemsInspection
    print("📝 Додано запис у DevNotes_LGE.md.")

    # --- README_DOCS ---
    with readme_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    table_start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("| Файл"):
            table_start = i + 2
            break

    if table_start:
        new_row = f"| `{module_path}` | Новий модуль, додано {date.today()}. |\n"
        lines.insert(table_start, new_row)
        readme_path.write_text("".join(lines), encoding="utf-8")
        print(f"📗 Оновлено README_DOCS.md — додано {module_path}.")
    else:
        print("⚠️ Не знайдено таблицю для вставки у README_DOCS.md.")

    return True


if __name__ == "__main__":
    ensure_doc_base()
    try:
        user_input = input(
            "Вкажи шлях до нового модуля (папка\\скрипт.py) або"
            " натисни Enter, щоб пропустити: "
        )
    except EOFError:
        user_input = ""

    if user_input.strip():
        append_devnote_and_readme(user_input)
    else:
        print("⏭️ Логування нового модуля пропущено.")
