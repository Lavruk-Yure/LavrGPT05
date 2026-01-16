# lang_autofill.py
"""
dev_tools/lang_autofill.py

Patch 6a+6b:
- Автозаповнення перекладів для нової мови у lang/strings.json
  на основі lang/strings_fallback.json для ВСЬОГО UI.
- Підтримка DeepL з двома незалежними ключами (primary/backup) і ретраєм.
- Виправлення імпорту пакетів проєкту при запуску з dev_tools (sys.path fix).

Режими:
- copy (default): target_lang = source_lang (наприклад pl = en)
- translate: target_lang = DeepL(source_lang) через core.ai_translator.AITranslator

Запуск:
  python dev_tools/lang_autofill.py --lang pl --dry-run
  python dev_tools/lang_autofill.py --lang pl

  python dev_tools/lang_autofill.py --lang pl --translate --deepl-key "KEY1" --dry-run
  python dev_tools/lang_autofill.py --lang pl --translate
  --deepl-key "KEY1" --deepl-key2 "KEY2"

Опції:
  --source en          (default: en)
  --force              перезаписувати навіть непорожні target_lang
  --limit N            ліміт ключів за один запуск (для тестів)

Логи:
  lang/lang_autofill.log
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# --- sys.path fix (dev_tools -> project root) ---
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEBUG_LANG_AUTOFILL = False


def log_cp(log_path: Path, name: str, **kw: Any) -> None:
    """Лог у stdout (за DEBUG) + файл. Секрети не передавати сюди."""
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"[LANG_AUTOFILL:{name}] " + ", ".join(f"{k}={v!r}" for k, v in kw.items())
    line = f"[{ts}] {msg}"

    if DEBUG_LANG_AUTOFILL:
        print(line)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def pick_source_text(entry: Dict[str, Any], source_lang: str) -> Tuple[str, str]:
    """
    Повертає (text, used_lang):
    1) source_lang якщо є і не пустий
    2) перший непорожній з інших мов
    3) "" якщо нічого нема
    """
    val = entry.get(source_lang)
    if isinstance(val, str) and val.strip():
        return val, source_lang

    for k, v in entry.items():
        if isinstance(v, str) and v.strip():
            return v, str(k)

    return "", ""


def is_deepl_retryable_error(err: Exception) -> bool:
    """
    Груба, але практична перевірка “чи є сенс пробувати інший ключ”.
    Орієнтуємось на типові коди/ознаки:
      - 429 (rate limit)
      - 456 (quota exceeded у DeepL трапляється)
      - 5xx
      - timeout / connection
    """
    msg = str(err).lower()
    retry_markers = (
        "http 429",
        "http 456",
        "http 500",
        "http 502",
        "http 503",
        "http 504",
        "timeout",
        "timed out",
        "connectionerror",
        "temporarily unavailable",
        "too many requests",
        "quota",
        "limit",
    )
    return any(m in msg for m in retry_markers)


def make_deepl_translator(lang_dir: Path, deepl_key: str) -> Optional[Any]:
    """Створює AITranslator(provider=deepl). Повертає None, якщо імпорт/ключ не ок."""
    if not deepl_key.strip():
        return None

    try:
        from core.ai_translator import AITranslator  # type: ignore
    except Exception as e:  # noqa: BLE001
        # Не ховаємо помилку імпорту: це головне місце, де все ламається.
        print("IMPORT_FAIL:", repr(e))
        return None

    conf: Dict[str, Any] = {
        "translator": {
            "provider": "deepl",
            "deepl_api_key": deepl_key.strip(),
        }
    }
    tr = AITranslator(conf=conf, lang_dir=lang_dir)

    if getattr(tr, "provider", "") != "deepl":
        return None

    return tr


def translate_with_two_keys(
    lang_dir: Path,
    text: str,
    target_lang: str,
    key1: str,
    key2: str,
    log_path: Path,
) -> str:
    """
    Переклад через DeepL з двома ключами.
    1) пробує key1
    2) якщо помилка “retryable” і є key2 -> пробує key2
    На будь-якій фатальній помилці повертає source text (не ламаємо пайплайн).
    """
    tr1 = make_deepl_translator(lang_dir=lang_dir, deepl_key=key1)
    if tr1 is None:
        log_cp(log_path, "deepl.init_fail", which="primary")
        return text

    try:
        return tr1.translate(text, target_lang)
    except Exception as e:  # noqa: BLE001
        log_cp(
            log_path,
            "deepl.fail",
            which="primary",
            retryable=is_deepl_retryable_error(e),
        )
        if not key2.strip() or not is_deepl_retryable_error(e):
            return text

    tr2 = make_deepl_translator(lang_dir=lang_dir, deepl_key=key2)
    if tr2 is None:
        log_cp(log_path, "deepl.init_fail", which="backup")
        return text

    try:
        return tr2.translate(text, target_lang)
    except Exception as e:  # noqa: BLE001
        log_cp(
            log_path,
            "deepl.fail",
            which="backup",
            retryable=is_deepl_retryable_error(e),
        )
        return text


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Autofill strings.json from strings_fallback.json."
    )
    parser.add_argument("--lang", required=True, help="Target language code, e.g. pl")
    parser.add_argument(
        "--source", default="en", help="Source language in fallback (default: en)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write files")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing non-empty values for target lang",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of processed keys (0 = no limit)",
    )

    parser.add_argument(
        "--translate", action="store_true", help="Use DeepL via AITranslator"
    )
    parser.add_argument("--deepl-key", default="", help="DeepL API key (primary)")
    parser.add_argument("--deepl-key2", default="", help="DeepL API key (backup)")

    args = parser.parse_args()

    project_root = PROJECT_ROOT
    lang_dir = project_root / "lang"
    log_path = lang_dir / "lang_autofill.log"

    fallback_path = lang_dir / "strings_fallback.json"
    strings_path = lang_dir / "strings.json"

    fallback = load_json(fallback_path)
    strings = load_json(strings_path)

    target_lang = args.lang.strip().lower()
    source_lang = args.source.strip().lower()

    use_translate = bool(args.translate)
    key1 = (args.deepl_key or "").strip()
    key2 = (args.deepl_key2 or "").strip()

    if use_translate and not key1:
        log_cp(log_path, "error", reason="--translate requires --deepl-key")
        return 2

    log_cp(
        log_path,
        "start",
        target=target_lang,
        source=source_lang,
        translate=use_translate,
        has_key1=bool(key1),
        has_key2=bool(key2),
        dry_run=args.dry_run,
        force=args.force,
        limit=args.limit,
    )

    total = 0
    added = 0
    overwritten = 0
    skipped = 0

    processed = 0

    for key, entry in fallback.items():
        if not isinstance(key, str) or key == "lang_active":
            continue
        if not isinstance(entry, dict):
            continue

        total += 1

        if key not in strings or not isinstance(strings.get(key), dict):
            strings[key] = {}

        cur_map: Dict[str, Any] = strings[key]  # type: ignore[assignment]
        existing = cur_map.get(target_lang)
        has_existing = isinstance(existing, str) and existing.strip()

        if has_existing and not args.force:
            skipped += 1
            continue

        src_text, used_lang = pick_source_text(entry, source_lang)

        if not src_text.strip():
            new_text = ""
        else:
            if use_translate:
                new_text = translate_with_two_keys(
                    lang_dir=lang_dir,
                    text=src_text,
                    target_lang=target_lang,
                    key1=key1,
                    key2=key2,
                    log_path=log_path,
                )
            else:
                new_text = src_text

        if has_existing and args.force:
            overwritten += 1
        else:
            added += 1

        cur_map[target_lang] = new_text

        log_cp(
            log_path,
            "set",
            key=key,
            target=target_lang,
            source=used_lang or source_lang,
            mode=("translate" if use_translate else "copy"),
            empty=(new_text.strip() == ""),
        )

        processed += 1
        if processed >= args.limit > 0:
            break

    log_cp(
        log_path,
        "summary",
        total=total,
        processed=processed,
        added=added,
        overwritten=overwritten,
        skipped=skipped,
        dry_run=args.dry_run,
        target=target_lang,
        translate=use_translate,
    )

    if not args.dry_run:
        save_json(strings_path, strings)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
