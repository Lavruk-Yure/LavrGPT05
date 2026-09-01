"""Synthetic check for active-language English fallback registration."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import PySide6  # noqa: F401
except ModuleNotFoundError:
    import types

    class _FakeOpenModeFlag:
        ReadOnly = 1

    class _FakeQIODevice:
        OpenModeFlag = _FakeOpenModeFlag

    class _FakeQFile:
        def __init__(self, path: str) -> None:
            self._path = path

        def open(self, _mode: object) -> bool:
            _ = self._path
            return False

        @staticmethod
        def exists(_path: str) -> bool:
            return False

    class _FakeQIcon:
        def __init__(self, _path: str = "") -> None:
            pass

    qt_core = types.ModuleType("PySide6.QtCore")
    qt_core.QFile = _FakeQFile
    qt_core.QIODevice = _FakeQIODevice
    qt_gui = types.ModuleType("PySide6.QtGui")
    qt_gui.QIcon = _FakeQIcon
    pyside6 = types.ModuleType("PySide6")
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtCore"] = qt_core
    sys.modules["PySide6.QtGui"] = qt_gui

from core.lang_manager import LangManager  # noqa: E402
from dev_tools.rebuild_fallback import complete_translation_map  # noqa: E402


def create_in_memory_lang_manager() -> LangManager:
    """Create LangManager state without filesystem access or DeepL."""
    manager = object.__new__(LangManager)
    setattr(manager, "_strings", {"lang_active": {"code": "uk"}})
    setattr(manager, "_fallback", {})
    setattr(manager, "_languages", {"en": "English", "uk": "Українська"})
    setattr(manager, "_current_lang", "uk")
    setattr(manager, "save_strings_file", lambda: None)
    setattr(
        manager,
        "_auto_translate",
        lambda _target_lang, _text, **_kwargs: "",
    )
    return manager


def registered_translation(
    manager: LangManager,
    key: str,
) -> dict[str, str]:
    """Return one runtime-registered translation without protected access."""
    strings = getattr(manager, "_strings", None)
    if not isinstance(strings, dict):
        raise AssertionError("LangManager did not expose an in-memory strings map")

    value = strings.get(key)
    if not isinstance(value, dict):
        raise AssertionError(f"Translation was not registered: {key}")

    return {str(language): str(text) for language, text in value.items()}


def main() -> None:
    """Run fallback map and runtime registration checks."""
    translations = {
        "en": "Account balance",
        "uk": "",
        "pl": "Saldo rachunku",
    }
    filled = complete_translation_map(translations, "uk")

    assert filled == ["uk"]
    assert translations["uk"] == "Account balance"
    assert "de" not in translations
    assert translations["pl"] == "Saldo rachunku"

    blank_placeholder = {"en": "", "uk": ""}
    assert complete_translation_map(blank_placeholder, "uk") == []

    existing_translation = {
        "en": "Close position",
        "uk": "Закрити позицію",
        "pl": "Zamknij pozycję",
    }
    assert complete_translation_map(existing_translation, "uk") == []
    assert existing_translation == {
        "en": "Close position",
        "uk": "Закрити позицію",
        "pl": "Zamknij pozycję",
    }

    manager = create_in_memory_lang_manager()
    resolved = manager.tr("Test.accountBalance", "Account balance")
    registered = registered_translation(manager, "Test.accountBalance")

    assert resolved == "Account balance"
    assert registered == {
        "en": "Account balance",
        "uk": "Account balance",
    }

    contextual_manager = create_in_memory_lang_manager()
    contextual_strings = getattr(contextual_manager, "_strings")
    contextual_key = "AlgorithmWorkspaceParametersDialog.alligatorDisabled"
    contextual_strings[contextual_key] = {
        "en": "Disabled",
        "uk": "З інвалідністю",
    }
    contextual_resolved = contextual_manager.tr(
        contextual_key,
        "Disabled",
    )
    contextual_registered = registered_translation(
        contextual_manager,
        contextual_key,
    )

    assert contextual_resolved == "Вимкнено"
    assert contextual_registered == {
        "en": "Disabled",
        "uk": "Вимкнено",
        "pl": "Wyłączone",
    }

    print("Rebuild fallback active-language fill result")
    print(f"  filled_languages={filled}")
    print(f"  preserved_polish={translations['pl']}")
    print(f"  runtime_registered={registered}")
    print(f"  contextual_override={contextual_registered}")
    print("REBUILD_FALLBACK_ENGLISH_FILL_CHECK=OK")


if __name__ == "__main__":
    main()
