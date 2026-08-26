"""Regression check for the safe Python bytecode-cache cleanup tool."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dev_tools.cleanup_python_cache import cleanup_python_cache  # noqa: E402


def _write_bytes(path: Path, payload: bytes = b"cache") -> None:
    """Create one binary fixture file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def main() -> int:
    """Verify dry-run, cleanup scope and idempotence."""
    with tempfile.TemporaryDirectory(prefix="lge_python_cache_cleanup_") as tmp:
        root = Path(tmp)
        package = root / "package"
        nested = package / "nested"
        source_files = [
            package / "module.py",
            nested / "worker.py",
        ]
        retained_file = root / "notes.txt"

        for source_file in source_files:
            source_file.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_text("VALUE = 1\n", encoding="utf-8")
        retained_file.write_text("keep\n", encoding="utf-8")

        cache_files = [
            package / "__pycache__" / "module.cpython-313.pyc",
            nested / "__pycache__" / "worker.cpython-313.pyo",
            root / ".idea" / "__pycache__" / "settings.cpython-313.pyc",
            root / "orphan.pyc",
        ]
        for cache_file in cache_files:
            _write_bytes(cache_file)

        dry_run = cleanup_python_cache(root, dry_run=True)
        assert dry_run.cache_directories_found == 3
        assert dry_run.compiled_files_found == 4
        assert dry_run.cache_directories_removed == 0
        assert dry_run.compiled_files_removed == 0
        assert all(cache_file.exists() for cache_file in cache_files)

        cleaned = cleanup_python_cache(root)
        assert cleaned.cache_directories_found == 3
        assert cleaned.compiled_files_found == 4
        assert cleaned.cache_directories_removed == 3
        assert cleaned.compiled_files_removed == 4
        assert cleaned.python_source_files_deleted == 0
        assert not any(cache_file.exists() for cache_file in cache_files)
        assert all(source_file.exists() for source_file in source_files)
        assert retained_file.exists()

        repeated = cleanup_python_cache(root)
        assert repeated.cache_directories_found == 0
        assert repeated.compiled_files_found == 0
        assert repeated.cache_directories_removed == 0
        assert repeated.compiled_files_removed == 0
        assert repeated.python_source_files_deleted == 0

    print("Python Cache Cleanup result")
    print("  dry_run_detects_targets=True")
    print("  cache_directories_removed=3")
    print("  compiled_python_files_removed=4")
    print("  pyc_and_pyo_supported=True")
    print("  python_source_files_preserved=True")
    print("  unrelated_files_preserved=True")
    print("  repeat_run_idempotent=True")
    print("PYTHON_CACHE_CLEANUP_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
