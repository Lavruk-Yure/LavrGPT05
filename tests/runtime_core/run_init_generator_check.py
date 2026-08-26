# -*- coding: utf-8 -*-
"""Перевірка генерації підпакетних __init__.py."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dev_tools.init_generator import generate_init_content  # noqa: E402


def main() -> None:
    minimal = generate_init_content(Path("tests"), [])
    regular = generate_init_content(Path("sample_package"), ["alpha", "beta"])

    compile(minimal, "tests/__init__.py", "exec")
    compile(regular, "sample_package/__init__.py", "exec")
    assert '"""Пакет tests."""' in minimal
    regular_docstring = (
        '"""Ініціалізаційний модуль пакету '
        'sample_package."""'
    )
    assert regular_docstring in regular
    assert 'from .alpha import *  # noqa' in regular
    assert 'from .beta import *  # noqa' in regular

    print("Init Generator result")
    print("  minimal_docstring_closed=True")
    print("  regular_docstring_closed=True")
    print("  generated_content_compiles=True")
    print("INIT_GENERATOR_CHECK=OK")


if __name__ == "__main__":
    main()
