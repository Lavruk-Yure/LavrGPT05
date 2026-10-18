# -*- coding: utf-8 -*-
"""
T111-36 v2 — Final Frozen Cryptography Guard — TEST_ONLY.

Виправлення v2:
- pyi-archive-viewer може друкувати внутрішні Windows-шляхи з подвійним '\\\\';
- нормалізуємо текст архіву перед перевіркою _rust.pyd;
- production не змінюється;
- broker requests = 0.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "Конфігурація auto py to exe.json"
EXE_PATH = Path(r"D:\LGE\LGE.exe")
ARCHIVE_VIEWER = Path(sys.executable).resolve().parent / "pyi-archive_viewer.exe"

TEST_ONLY = True
BROKER_REQUESTS = 0
BROKER_EXECUTION_ATTEMPTED = False
PRODUCTION_LOGIC_CHANGED = False

COLLECT_BINARIES = "--collect-binaries=cryptography"
HIDDEN_IMPORT = "--hidden-import=cryptography.hazmat.bindings._rust"


def _find_key_values(node: Any, key: str) -> list[str]:
    values: list[str] = []

    if isinstance(node, dict):
        for current_key, value in node.items():
            if current_key == key:
                values.append(str(value))
            values.extend(_find_key_values(value, key))
    elif isinstance(node, list):
        for value in node:
            values.extend(_find_key_values(value, key))

    return values


def _require(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(f"missing evidence: {label}")


def main() -> int:
    _require(CONFIG_PATH.is_file(), f"config exists: {CONFIG_PATH}")
    _require(EXE_PATH.is_file(), f"exe exists: {EXE_PATH}")
    _require(ARCHIVE_VIEWER.is_file(), f"archive viewer exists: {ARCHIVE_VIEWER}")

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    manual_arguments_values = _find_key_values(config, "manualArguments")

    config_has_collect_binaries = any(
        COLLECT_BINARIES in value for value in manual_arguments_values
    )
    config_has_hidden_import = any(
        HIDDEN_IMPORT in value for value in manual_arguments_values
    )

    result = subprocess.run(
        [str(ARCHIVE_VIEWER), "-l", "-r", str(EXE_PATH)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )

    archive_text_raw = result.stdout + "\n" + result.stderr
    archive_text = archive_text_raw.replace("\\\\", "\\").replace("/", "\\")

    rust_archive_path = r"cryptography\hazmat\bindings\_rust.pyd"
    archive_contains_rust_pyd = rust_archive_path in archive_text
    archive_contains_rust_name = "_rust" in archive_text

    _require(result.returncode == 0, "pyi-archive-viewer completed")
    _require(
        config_has_collect_binaries,
        "config contains --collect-binaries=cryptography",
    )
    _require(
        config_has_hidden_import,
        "config keeps _rust hidden-import",
    )
    _require(
        archive_contains_rust_pyd,
        "built LGE.exe contains normalized _rust.pyd path",
    )

    print("T111-36 TEST_ONLY")
    print("verdict=FINAL_FROZEN_CRYPTOGRAPHY_PACKAGING_GUARDED")
    print(f"config_has_collect_binaries={config_has_collect_binaries}")
    print(f"config_has_hidden_import={config_has_hidden_import}")
    print(f"archive_viewer_returncode={result.returncode}")
    print(f"archive_contains_rust_name={archive_contains_rust_name}")
    print(f"archive_contains_rust_pyd={archive_contains_rust_pyd}")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"broker_execution_attempted={BROKER_EXECUTION_ATTEMPTED}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
