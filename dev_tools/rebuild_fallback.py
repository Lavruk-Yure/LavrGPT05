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
from pathlib import Path
from typing import Iterable

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

    # Не робимо “гарного” форматування — просто чесно показуємо.
    parts = [f"{k}={repr(v)}" for k, v in items]
    return "; ".join(parts)


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

        # [Key]
        parts = text.split("[")
        for part in parts[1:]:
            if "]" not in part:
                continue
            key = part.split("]", 1)[0].strip()
            if "." in key:
                used.add(key)

        # lang.t("Key") / lang.t('Key')
        # простий парсер без regex (щоб не тягнути зайве)
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
                used.add(key)
            pos = end + 1

    # ---- 2) UI: *.ui (XML). Шукаємо ключі як "[Key]" та як "Key" у лапках.
    for path in root.rglob("*.ui"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa
            continue

        # [Key] у .ui
        parts = text.split("[")
        for part in parts[1:]:
            if "]" not in part:
                continue
            key = part.split("]", 1)[0].strip()
            if "." in key:
                used.add(key)

        # Витягнути всі "...." та '....' і фільтрувати по крапці
        # (просто щоб не ловити купу сміття)
        for q in ('"', "'"):
            segs = text.split(q)
            # парні сегменти між лапками: 1,3,5...
            for i in range(1, len(segs), 2):
                s = segs[i].strip()
                if "." in s and 3 <= len(s) <= 200:
                    used.add(s)

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
    qrc_path = root / "resources.qrc"

    print(f"[ШЛЯХ] ROOT     = {root}")
    print(f"[ШЛЯХ] STRINGS  = {strings_path}")
    print(f"[ШЛЯХ] FALLBACK = {fallback_path}")

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
    # 3/6 Побудова translated_languages (тільки з перекладних ключів)
    # ------------------------------------------------------------------
    translated_languages: set[str] = set()

    for key, value in fallback.items():
        if key in META_KEYS:
            continue
        if is_translation_map(value):
            translated_languages.update(value.keys())

    fallback["translated_languages"] = sorted(translated_languages)

    print(f"[3/6] translated_languages: {len(translated_languages)} мов")

    # ------------------------------------------------------------------
    # 4/6 Нормалізація fallback (заповнення пропусків)
    # ------------------------------------------------------------------
    added_missing = 0

    for key, value in fallback.items():
        if key in META_KEYS:
            continue
        if not is_translation_map(value):
            continue

        trans: dict[str, str] = value  # type: ignore[assignment]
        if not trans:
            continue

        for lang in translated_languages:
            if lang in trans:
                continue

            if "en" in trans:
                trans[lang] = trans["en"]
                src = "en"
            else:
                src = next(iter(trans.keys()))
                trans[lang] = trans[src]

            added_missing += 1
            print(
                f"ПОПЕРЕДЖЕННЯ: додано відсутню мову [{lang}] для ключа {key} "
                f"(скопійовано з {src}) | {format_translations(trans)}"
            )

    print(f"[4/6] Fallback нормалізовано (додано: {added_missing})")

    # ------------------------------------------------------------------
    # 5/6 Очищення strings.json (тільки lang_active)
    # ------------------------------------------------------------------
    write_json(strings_path, {"lang_active": {"code": active_lang}})
    print("[5/6] strings.json очищено (залишено тільки lang_active)")

    # ------------------------------------------------------------------
    # 5.5 Контроль якості: ключі у fallback, яких нема у коді/UI
    # ------------------------------------------------------------------
    used_keys = collect_used_keys(root)

    unused = 0
    for key, value in fallback.items():
        if key in META_KEYS:
            continue
        if not is_translation_map(value):
            continue
        if key not in used_keys:
            unused += 1
            trans: dict[str, str] = value  # type: ignore[assignment]
            print(
                f"ПОПЕРЕДЖЕННЯ: ключ у fallback не знайдено у коді/UI → {key} | "
                f"{format_translations(trans)}"
            )

    print(f"[QC] Ключів у fallback, яких нема у коді/UI: {unused}")

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
