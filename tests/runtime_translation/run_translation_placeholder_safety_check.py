# tests/runtime/run_translation_placeholder_safety_check.py
"""
Synthetic translation placeholder safety check.

The test does not call DeepL. It verifies that translated Python format
placeholders are restored to the canonical English machine names.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.lang_manager import LangManager  # noqa: E402
from core.translation_format import restore_format_placeholders  # noqa: E402


class SyntheticLangManager(LangManager):
    """In-memory LangManager for placeholder normalization checks."""

    def __init__(self) -> None:
        super().__init__()
        self._current_lang = "pl"
        self._strings = {
            "Test.message": {
                "pl": "Nie udało się wykonać operacji: {błąd}",
            }
        }
        self._fallback = {
            "Test.message": {
                "en": "Operation failed: {error}",
            }
        }
        self._languages = {"en": "English", "pl": "Polski"}


def main() -> None:
    """Run synthetic placeholder checks."""
    restored_error = restore_format_placeholders(
        "Modify SL/TP failed: {error}",
        "Nie udało się zmienić SL/TP: {błąd}",
    )
    assert restored_error == "Nie udało się zmienić SL/TP: {error}"

    restored_details = restore_format_placeholders(
        "WARNING: {details}",
        "OSTRZEŻENIE: {szczegóły}",
    )
    assert restored_details == "OSTRZEŻENIE: {details}"

    missing_placeholder = restore_format_placeholders(
        "Created file: {path}",
        "Utworzono plik: ścieżka",
    )
    assert missing_placeholder == "Created file: {path}"

    manager = SyntheticLangManager()

    resolved = manager.resolve("Test.message")
    assert resolved == "Nie udało się wykonać operacji: {error}"
    assert resolved.format(error="synthetic") == (
        "Nie udało się wykonać operacji: synthetic"
    )

    print("Translation placeholder safety result")
    print(f"  error={restored_error}")
    print(f"  details={restored_details}")
    print(f"  resolved={resolved}")
    print("TRANSLATION_PLACEHOLDER_SAFETY_CHECK=OK")


if __name__ == "__main__":
    main()
