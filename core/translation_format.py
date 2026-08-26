# core/translation_format.py
# -*- coding: utf-8 -*-
"""
Utilities for safe translated Python format strings.

Machine placeholders such as ``{error}``, ``{details}`` and ``{count}``
must never be translated.  A translated placeholder would break later
``str.format(...)`` calls with ``KeyError``.
"""

from __future__ import annotations

import re

_FORMAT_PLACEHOLDER_RE = re.compile(r"(?<![{])[{][^{}]+[}](?![}])")


def extract_format_placeholders(text: str) -> list[str]:
    """Return non-escaped ``str.format`` placeholders in source order."""
    return _FORMAT_PLACEHOLDER_RE.findall(text or "")


def restore_format_placeholders(source: str, translated: str) -> str:
    """
    Restore source placeholders inside translated text.

    If the translator removed or added placeholders, return the source text.
    Falling back to English is safer than returning a string that can raise
    ``KeyError`` or format the wrong value at runtime.
    """
    source_text = source or ""
    translated_text = translated or ""

    source_placeholders = extract_format_placeholders(source_text)
    if not source_placeholders:
        return translated_text

    translated_placeholders = extract_format_placeholders(translated_text)
    if len(translated_placeholders) != len(source_placeholders):
        return source_text

    source_iter = iter(source_placeholders)
    restored = _FORMAT_PLACEHOLDER_RE.sub(
        lambda _match: next(source_iter),
        translated_text,
    )

    if extract_format_placeholders(restored) != source_placeholders:
        return source_text

    return restored
