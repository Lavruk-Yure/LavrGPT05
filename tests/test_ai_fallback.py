# tests/unit/test_ai_fallback.py
import json
from pathlib import Path  # noqa

from core.lang_manager import LangManager


def test_ai_fallback_caches_from_uk(tmp_path, monkeypatch):
    # Підготовка ізоляції: копія conf у temp
    conf = tmp_path / "LGE05.conf"
    conf.write_text(
        json.dumps(
            {
                "language": "de Deutsch",
                "multi_language": False,
                "translator": {"provider": "mock"},
            }
        ),
        encoding="utf-8",
    )

    # Створюємо lang структуру
    lang_dir = tmp_path / "lang"
    (lang_dir / "cache").mkdir(parents=True, exist_ok=True)
    (lang_dir / "strings.json").write_text(
        json.dumps(
            {"only_uk_key": {"uk": "Тільки український текст"}}, ensure_ascii=False
        ),
        encoding="utf-8",
    )

    # Підмінимо шлях LangManager на наш tmp (хитрий трюк: копіюємо файл)
    # Простий спосіб: тимчасово запускаємо з робочої директорії tmp_path
    import os

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        lm = LangManager()
        # Перший виклик — нема de у strings,
        # має створитись кеш із 'mock' перекладом (ідентичний)
        out = lm.t("only_uk_key")
        assert out == "Тільки український текст"

        # Перевіряємо кеш
        de_cache = json.loads(
            (tmp_path / "lang" / "cache" / "de.json").read_text(encoding="utf-8")
        )
        assert de_cache.get("only_uk_key") == "Тільки український текст"
    finally:
        os.chdir(cwd)
