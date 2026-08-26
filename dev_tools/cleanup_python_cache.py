"""Safely remove Python bytecode caches from the LavrGPT05 tree."""

from __future__ import annotations

import argparse
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIRECTORY_NAME = "__pycache__"
COMPILED_SUFFIXES = {".pyc", ".pyo"}
SKIP_DIRECTORY_NAMES = {
    ".git",
    ".venv",
    "venv",
    "venv313",
}


@dataclass(frozen=True, slots=True)
class PythonCacheCleanupResult:
    """Summary of one Python cache cleanup pass."""

    root: Path
    cache_directories_found: int
    compiled_files_found: int
    cache_directories_removed: int
    compiled_files_removed: int
    python_source_files_deleted: int
    dry_run: bool


def _resolve_root(root: Path) -> Path:
    """Return a validated cleanup root."""
    resolved_root = root.expanduser().resolve()
    if not resolved_root.exists():
        raise FileNotFoundError(f"Cleanup root does not exist: {resolved_root}")
    if not resolved_root.is_dir():
        raise NotADirectoryError(f"Cleanup root is not a directory: {resolved_root}")
    if resolved_root == resolved_root.parent:
        raise ValueError("Filesystem root cannot be used as cleanup root")
    return resolved_root


def _is_within_root(path: Path, root: Path) -> bool:
    """Return True only when path belongs to root."""
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _collect_targets(root: Path) -> tuple[list[Path], list[Path]]:
    """Collect cache directories and standalone compiled files."""
    cache_directories: list[Path] = []
    compiled_files: list[Path] = []

    for current_root, directory_names, file_names in os.walk(
        root,
        topdown=True,
        followlinks=False,
    ):
        current_path = Path(current_root)
        directory_names[:] = [
            directory_name
            for directory_name in directory_names
            if directory_name not in SKIP_DIRECTORY_NAMES
            and not (current_path / directory_name).is_symlink()
        ]

        for directory_name in list(directory_names):
            if directory_name != CACHE_DIRECTORY_NAME:
                continue
            cache_path = current_path / directory_name
            cache_directories.append(cache_path)
            directory_names.remove(directory_name)

        for file_name in file_names:
            file_path = current_path / file_name
            if file_path.is_symlink():
                continue
            if file_path.suffix.lower() in COMPILED_SUFFIXES:
                compiled_files.append(file_path)

    for cache_directory in cache_directories:
        for compiled_path in cache_directory.rglob("*"):
            if not compiled_path.is_file() or compiled_path.is_symlink():
                continue
            if compiled_path.suffix.lower() in COMPILED_SUFFIXES:
                compiled_files.append(compiled_path)

    unique_directories = sorted(set(cache_directories))
    unique_files = sorted(set(compiled_files))
    return unique_directories, unique_files


def cleanup_python_cache(
    root: Path = PROJECT_ROOT,
    *,
    dry_run: bool = False,
) -> PythonCacheCleanupResult:
    """Remove only __pycache__, .pyc and .pyo under root."""
    resolved_root = _resolve_root(root)
    cache_directories, compiled_files = _collect_targets(resolved_root)

    for target in [*cache_directories, *compiled_files]:
        resolved_target = target.resolve(strict=False)
        if not _is_within_root(resolved_target, resolved_root):
            raise RuntimeError(f"Cleanup target escaped root: {target}")

    cache_directories_removed = 0
    compiled_files_removed = 0

    if not dry_run:
        for cache_directory in cache_directories:
            if cache_directory.exists():
                shutil.rmtree(cache_directory)

        for compiled_file in compiled_files:
            if compiled_file.exists():
                compiled_file.unlink()

        cache_directories_removed = sum(
            not cache_directory.exists()
            for cache_directory in cache_directories
        )
        compiled_files_removed = sum(
            not compiled_file.exists()
            for compiled_file in compiled_files
        )

    return PythonCacheCleanupResult(
        root=resolved_root,
        cache_directories_found=len(cache_directories),
        compiled_files_found=len(compiled_files),
        cache_directories_removed=cache_directories_removed,
        compiled_files_removed=compiled_files_removed,
        python_source_files_deleted=0,
        dry_run=dry_run,
    )


def _build_parser() -> argparse.ArgumentParser:
    """Build command-line parser."""
    parser = argparse.ArgumentParser(
        description="Remove Python bytecode caches from LavrGPT05 safely."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Project root to clean. Defaults to the current LavrGPT05 tree.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report targets without deleting them.",
    )
    return parser


def main() -> int:
    """Run Python cache cleanup from the command line."""
    args = _build_parser().parse_args()
    result = cleanup_python_cache(args.project_root, dry_run=args.dry_run)

    print("Python cache cleanup result")
    print(f"  root={result.root}")
    print(f"  dry_run={result.dry_run}")
    print(f"  cache_directories_found={result.cache_directories_found}")
    print(f"  compiled_python_files_found={result.compiled_files_found}")
    print(f"  python_cache_directories_removed={result.cache_directories_removed}")
    print(f"  compiled_python_files_removed={result.compiled_files_removed}")
    print(f"  python_source_files_deleted={result.python_source_files_deleted}")
    print("PYTHON_CACHE_CLEANUP=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
