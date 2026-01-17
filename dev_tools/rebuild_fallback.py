# rebuild_fallback.py
"""
Перезбирання fallback-перекладів із lang/strings.json у lang/strings_fallback.json.

Правила:
1) Усі переклади зі strings.json (крім lang_active) зливаються у strings_fallback.json
2) translated_languages зберігається ВСЕРЕДИНІ strings_fallback.json
3) Для кожного ключа перекладу забезпечується наявність усіх мов із translated_languages
   (відсутні — додаються копією з en або з першої доступної мови)
4) На кожне додавання пропуску — ПОПЕРЕДЖЕННЯ у консоль + показ перекладів
5) strings.json після виконання містить ТІЛЬКИ: {"lang_active": {"code": "<active>"}}
6) Якщо не задано --no-rcc, компілюється resources.qrc (якщо існує)

Контроль якості:
- Якщо у fallback є ключ перекладу, якого не знайдено у коді/UI (py + ui) —
    ПОПЕРЕДЖЕННЯ у консоль
  + друк перекладів для цього ключа.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

# ВАЖЛИВО:
# - fallback не має “роздуватися” копіями en у всі мови.
# - старі «автозаповнені» значення (lang -> те саме, що en) чистимо.
# - ключі, яких нема у проекті (py + ui), видаляємо ЗАВЖДИ.
DELETE_UNUSED = True


META_KEYS = {"languages", "translated_languages", "lang_active"}


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"ПОМИЛКА: файл не знайдено: {path}")
        sys.exit(2)
    except json.JSONDecodeError as exc:
        print(f"ПОМИЛКА: некоректний JSON: {path} ({exc})")
        sys.exit(2)


def write_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def backup_json(path: Path, backup_name: str) -> None:
    """
    Робить простий backup поруч із файлом.
    Приклад:
      strings.json -> strings.bak.json
      strings_fallback.json -> strings_fallback.bak.json
    """
    try:
        if not path.exists():
            return
        backup_path = path.with_name(backup_name)
        backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:  # noqa
        # Backup не має валити rebuild.
        return


def detect_root() -> Path:
    """
    Детермінований корінь:
    <ROOT>/dev_tools/rebuild_fallback.py => ROOT = батько dev_tools
    """
    here = Path(__file__).resolve()
    root = here.parent.parent

    strings_path = root / "lang" / "strings.json"
    fallback_path = root / "lang" / "strings_fallback.json"

    if not strings_path.exists():
        print("ПОМИЛКА: очікував lang/strings.json тут:")
        print(f"  {strings_path}")
        sys.exit(2)

    if not fallback_path.exists():
        print("ПОМИЛКА: очікував lang/strings_fallback.json тут:")
        print(f"  {fallback_path}")
        sys.exit(2)

    return root


def is_translation_map(value: object) -> bool:
    """
    Мапа перекладів: dict, де всі значення — рядки.
    """
    if not isinstance(value, dict):
        return False
    for v in value.values():
        if not isinstance(v, str):
            return False
    return True


def clean_translation_map(trans: dict[str, str]) -> int:
    """
    Чистить «старий стиль» fallback:
    - прибирає порожні значення
    - прибирає значення, які дорівнюють en (типовий автокопіпаст)

    Повертає кількість видалених елементів.

    Правило просте й чесне:
    - en та uk залишаємо завжди (навіть якщо вони збігаються)
    - інші мови лишаємо тільки якщо рядок не порожній і не дорівнює en
    """
    removed = 0

    en_text = trans.get("en") if isinstance(trans.get("en"), str) else None

    # 1) прибрати порожні
    for lang in list(trans.keys()):
        v = trans.get(lang)
        if not isinstance(v, str):
            trans.pop(lang, None)
            removed += 1
            continue
        if lang not in ("en", "uk") and not v.strip():
            trans.pop(lang, None)
            removed += 1

    # 2) прибрати «копію з en» (крім en/uk)
    if en_text is not None:
        for lang in list(trans.keys()):
            if lang in ("en", "uk"):
                continue
            if trans.get(lang) == en_text:
                trans.pop(lang, None)
                removed += 1

    return removed


def format_translations(trans: dict, langs: Iterable[str] | None = None) -> str:
    """
    Форматує переклади в один рядок для консолі.
    Якщо langs задано — виводить тільки ці мови (у цьому порядку).
    """
    if not isinstance(trans, dict):
        return "<не dict>"

    items: list[tuple[str, str]] = []
    if langs is None:
        for k in sorted(trans.keys()):
            v = trans.get(k)
            if isinstance(v, str):
                items.append((k, v))
    else:
        for k in langs:
            v = trans.get(k)
            if isinstance(v, str):
                items.append((k, v))

    if not items:
        return "<порожньо>"

    parts = [f"{k}={repr(v)}" for k, v in items]
    return "; ".join(parts)


def normalize_key(s: str) -> str:
    s = s.strip()
    if s.startswith("[") and s.endswith("]") and len(s) > 2:
        s = s[1:-1].strip()
    return s


def collect_used_keys(root: Path) -> set[str]:
    """
    Збір ключів, які реально згадуються у коді/UI.

    Підтримує:
    - "[Key]" (як у Qt translate placeholder)
    - lang.t("Key") / lang.t('Key')
    - прямі "Key" у .ui (пошук як підрядок, але з фільтром на крапку в ключі)
    """
    used: set[str] = set()

    # ---- 1) Python: "[Key]" і lang.t("Key")
    for path in root.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa
            continue

        marker = "LANG.resolve("
        if marker in text:
            for q in ('"', "'"):
                parts = text.split(marker)
                for part in parts[1:]:
                    if part.startswith(q):
                        end = part.find(q, 1)
                        if end > 1:
                            key = part[1:end].strip()
                            if "." in key:
                                used.add(normalize_key(key))

        for marker in (".resolve(", "_t(", "self._t("):
            if marker not in text:
                continue
            for q in ('"', "'"):
                parts = text.split(marker)
                for part in parts[1:]:
                    if part.startswith(q):
                        end = part.find(q, 1)
                        if end > 1:
                            key = part[1:end].strip()
                            if "." in key:
                                used.add(normalize_key(key))

        parts = text.split("[")
        for part in parts[1:]:
            if "]" not in part:
                continue
            key = part.split("]", 1)[0].strip()
            if "." in key:
                used.add(normalize_key(key))

        marker = "lang.t("
        pos = 0
        while True:
            pos = text.find(marker, pos)
            if pos == -1:
                break
            start = pos + len(marker)
            if start >= len(text):
                break
            q = text[start : start + 1]  # noqa
            if q not in ("'", '"'):
                pos = start
                continue
            end = text.find(q, start + 1)
            if end == -1:
                break
            key = text[start + 1 : end].strip()  # noqa
            if "." in key:
                used.add(normalize_key(key))
            pos = end + 1

        for q in ('"', "'"):
            segs = text.split(q)
            for i in range(1, len(segs), 2):
                s = segs[i].strip()
                if (
                    "." in s
                    and "://" not in s
                    and not s.endswith((".json", ".py", ".ui", ".qrc"))
                ):
                    if 3 <= len(s) <= 200 and s[0].isalpha():
                        used.add(normalize_key(s))

    # ---- 2) UI: *.ui
    for path in root.rglob("*.ui"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa
            continue

        parts = text.split("[")
        for part in parts[1:]:
            if "]" not in part:
                continue
            key = part.split("]", 1)[0].strip()
            if "." in key:
                used.add(normalize_key(key))

        for q in ('"', "'"):
            segs = text.split(q)
            for i in range(1, len(segs), 2):
                s = segs[i].strip()
                if (
                    "." in s
                    and "://" not in s
                    and not s.endswith((".json", ".py", ".ui", ".qrc"))
                ):
                    if 3 <= len(s) <= 200 and s[0].isalpha():
                        used.add(normalize_key(s))

    return used


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-rcc", action="store_true", help="Не компілювати resources.qrc"
    )
    args = parser.parse_args()

    root = detect_root()
    lang_dir = root / "lang"
    strings_path = lang_dir / "strings.json"
    fallback_path = lang_dir / "strings_fallback.json"
    delete_log_path = root / "lang" / "delete_fallback.log"

    qrc_path = root / "resources.qrc"

    print(f"[ШЛЯХ] ROOT     = {root}")
    print(f"[ШЛЯХ] STRINGS  = {strings_path}")
    print(f"[ШЛЯХ] FALLBACK = {fallback_path}")
    print(f"[ШЛЯХ] DELETE_LOG = {delete_log_path}")

    # ------------------------------------------------------------------
    # 1/6 Читання strings.json
    # ------------------------------------------------------------------
    strings = read_json(strings_path)
    active_lang = (
        strings.get("lang_active", {}).get("code")
        if isinstance(strings.get("lang_active"), dict)
        else None
    )
    if not active_lang:
        print("ПОМИЛКА: lang_active.code не знайдено у strings.json")
        sys.exit(2)

    source_keys: dict[str, dict[str, str]] = {}
    source_languages: set[str] = set()

    for key, value in strings.items():
        if key in META_KEYS:
            continue
        if is_translation_map(value):
            source_keys[key] = value  # type: ignore[assignment]
            source_languages.update(value.keys())

    print(
        f"[1/6] Прочитано strings.json — ключів: {len(source_keys)}, мови: "
        f"{', '.join(sorted(source_languages))}"
    )

    # ------------------------------------------------------------------
    # 2/6 Злиття strings -> fallback
    # ------------------------------------------------------------------
    fallback = read_json(fallback_path)

    merged_count = 0
    for key, translations in source_keys.items():
        fb_entry = fallback.get(key)
        if not isinstance(fb_entry, dict):
            fallback[key] = fb_entry = {}

        for lang, text in translations.items():
            prev = fb_entry.get(lang)
            fb_entry[lang] = text
            if prev != text:
                merged_count += 1

    print(f"[2/6] Злиття strings → fallback (оновлень: {merged_count})")

    # ------------------------------------------------------------------
    # 3/6 Побудова translated_languages (з languages, а не з ключів)
    # ------------------------------------------------------------------
    translated_languages: set[str] = set()
    languages_meta = fallback.get("languages")
    if isinstance(languages_meta, dict):
        for code in languages_meta.keys():
            if isinstance(code, str) and code:
                translated_languages.add(code)

    fallback["translated_languages"] = sorted(translated_languages)
    print(f"[3/6] translated_languages: {len(translated_languages)} мов")

    # ------------------------------------------------------------------
    # 3.5/6 Чистка «старого стилю» fallback (копії en у всі мови)
    # ------------------------------------------------------------------
    cleaned = 0
    for key, value in fallback.items():
        if key in META_KEYS:
            continue
        if not is_translation_map(value):
            continue
        trans: dict[str, str] = value  # type: ignore[assignment]
        cleaned += clean_translation_map(trans)

    if cleaned:
        print(f"[3.5/6] Чистка fallback (видалено записів: {cleaned})")

    # ------------------------------------------------------------------
    # 4/6 Нормалізація fallback (НЕ роздуваємо ключі порожніми мовами)
    # ------------------------------------------------------------------
    added_minimal = 0

    for key, value in fallback.items():
        if key in META_KEYS:
            continue
        if not is_translation_map(value):
            continue

        trans: dict[str, str] = value  # type: ignore[assignment]
        if not trans:
            continue

        if "uk" not in trans:
            trans["uk"] = ""
            added_minimal += 1
            print(
                f"ПОПЕРЕДЖЕННЯ: додано мінімальну мову [uk] для ключа {key} "
                f"(порожньо) | {format_translations(trans)}"
            )

        if "en" not in trans:
            trans["en"] = ""
            added_minimal += 1
            print(
                f"ПОПЕРЕДЖЕННЯ: додано мінімальну мову [en] для ключа {key} "
                f"(порожньо) | {format_translations(trans)}"
            )

    print(f"[4/6] Fallback нормалізовано мінімально (додано: {added_minimal})")

    # ------------------------------------------------------------------
    # 5/6 Очищення strings.json (тільки lang_active)
    # ------------------------------------------------------------------
    backup_json(strings_path, "strings.bak.json")
    write_json(strings_path, {"lang_active": {"code": active_lang}})
    print("[5/6] strings.json очищено (залишено тільки lang_active)")

    # ------------------------------------------------------------------
    # 5.5 Контроль якості + автовидалення: ключі у fallback, яких нема у проекті
    # ------------------------------------------------------------------
    used_keys = collect_used_keys(root)

    to_delete: list[tuple[str, dict[str, str]]] = []

    for key, value in fallback.items():
        if key in META_KEYS:
            continue
        if not is_translation_map(value):
            continue
        if key not in used_keys:
            trans: dict[str, str] = value  # type: ignore[assignment]
            to_delete.append((key, trans))

    print(f"[QC] Кандидатів на видалення (нема у проекті): {len(to_delete)}")
    if to_delete:
        for k, tr in to_delete:
            print(f"[QC?] {k} | {format_translations(tr)}")

    if DELETE_UNUSED and to_delete:
        backup_json(fallback_path, "strings_fallback.bak.json")

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines_out: list[str] = []
        for k, tr in to_delete:
            langs = ",".join(sorted(tr.keys()))
            lines_out.append(
                f"{ts} | DELETE | {k} | langs={langs} | "
                f"reason=not_found_in_project_scan"
            )
            fallback.pop(k, None)

        try:
            delete_log_path.parent.mkdir(parents=True, exist_ok=True)
            old = ""
            if delete_log_path.exists():
                old = delete_log_path.read_text(encoding="utf-8", errors="ignore")
                if old and not old.endswith("\n"):
                    old += "\n"
            delete_log_path.write_text(
                old + "\n".join(lines_out) + "\n", encoding="utf-8"
            )
        except Exception:  # noqa
            pass

        print(f"[QC] Видалено ключів із fallback (нема у проекті): {len(to_delete)}")
    else:
        print("[QC] Нічого видаляти")

    # ------------------------------------------------------------------
    # 6/6 Запис fallback + компіляція ресурсу (опційно)
    # ------------------------------------------------------------------
    write_json(fallback_path, fallback)

    if args.no_rcc:
        print("[6/6] Компіляцію ресурсів пропущено (--no-rcc)")
        return

    if not qrc_path.exists():
        print("[6/6] resources.qrc не знайдено — пропущено")
        return

    subprocess.run(
        ["pyside6-rcc", str(qrc_path), "-o", "resources_rc.py"],
        cwd=root,
        check=False,
    )
    print("[6/6] resources скомпільовано")


if __name__ == "__main__":
    main()
