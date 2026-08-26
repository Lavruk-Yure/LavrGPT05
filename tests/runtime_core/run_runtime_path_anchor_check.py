"""Regression guard for project-root runtime data and language paths."""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.app_paths import LANG_DIR, STRINGS_JSON  # noqa: E402
from engine.db.runtime_db import get_runtime_database_path  # noqa: E402


def main() -> int:
    """Verify that runtime paths never depend on the process working directory."""
    expected_lang_dir = PROJECT_ROOT / "lang"
    expected_strings_json = expected_lang_dir / "strings.json"
    expected_demo_db = PROJECT_ROOT / "data" / "demo.db"

    if LANG_DIR != expected_lang_dir:
        raise AssertionError(f"LANG_DIR differs: {LANG_DIR}")

    if STRINGS_JSON != expected_strings_json:
        raise AssertionError(f"STRINGS_JSON differs: {STRINGS_JSON}")

    demo_db = get_runtime_database_path("DEMO")
    if demo_db != expected_demo_db:
        raise AssertionError(f"DEMO DB path differs: {demo_db}")

    lang_manager_source = (PROJECT_ROOT / "core" / "lang_manager.py").read_text(
        encoding="utf-8"
    )
    forbidden_lang_tokens = (
        'Path("lang")',
        "Path('lang')",
        'Path("lang/strings.json")',
        "Path('lang/strings.json')",
    )
    present_lang_tokens = [
        token for token in forbidden_lang_tokens if token in lang_manager_source
    ]
    if present_lang_tokens:
        raise AssertionError(
            f"CWD-relative LangManager paths remain: {present_lang_tokens}"
        )

    runtime_dir = PROJECT_ROOT / "tests" / "runtime"
    relative_db_pattern = re.compile(
        r"(?:RuntimeEngine\(db_path=|Path\()[\"']data[\\/](?:demo|live|test)\.db"
    )
    relative_db_hits: list[str] = []

    for source_path in runtime_dir.glob("*.py"):
        source = source_path.read_text(encoding="utf-8")
        if relative_db_pattern.search(source):
            relative_db_hits.append(source_path.name)

    if relative_db_hits:
        raise AssertionError(
            f"CWD-relative runtime DB paths remain: {relative_db_hits}"
        )

    with tempfile.TemporaryDirectory(prefix="lge_path_anchor_") as tmp:
        previous_cwd = Path.cwd()
        try:
            os.chdir(tmp)
            _ = get_runtime_database_path("DEMO")
        finally:
            os.chdir(previous_cwd)

        temp_root = Path(tmp)
        cwd_artifacts = [
            path.name
            for path in (temp_root / "data", temp_root / "lang")
            if path.exists()
        ]

    if cwd_artifacts:
        raise AssertionError(f"Unexpected CWD artifacts: {cwd_artifacts}")

    print("Runtime path anchor result")
    print(f"  project_root={PROJECT_ROOT}")
    print(f"  lang_dir={LANG_DIR}")
    print(f"  strings_json={STRINGS_JSON}")
    print(f"  demo_db={demo_db}")
    print("  relative_lang_paths=0")
    print("  relative_runtime_db_paths=0")
    print("  cwd_artifacts_created=False")
    print("RUNTIME_PATH_ANCHOR_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
