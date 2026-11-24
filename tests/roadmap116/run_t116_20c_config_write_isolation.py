"""T116-20C TEST_ONLY — файловий захист LGE.conf у діагностичній сесії.

Усі спроби запису виконуються тільки на тимчасових файлах pytest.
Не імпортує LGE, не відкриває брокерські з'єднання й не читає реальний LGE.conf.
"""

from __future__ import annotations

import ast
import builtins
import os
import runpy
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
TELEMETRY_FILE = (
    ROOT / "tests" / "roadmap116" / "run_t116_19_ctrader_raw_spot_telemetry.py"
)


def test_t116_20c_config_write_isolation(tmp_path: Path) -> None:
    """Довести, що читання дозволено, а запис і перенесення заблоковані."""
    tree = ast.parse(TELEMETRY_FILE.read_text(encoding="utf-8"))
    launcher = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "launch_live_diagnostics"
    )
    guarded_scopes = [
        item
        for item in ast.walk(launcher)
        if isinstance(item, ast.With)
        and any(
            isinstance(entry.context_expr, ast.Call)
            and isinstance(entry.context_expr.func, ast.Name)
            and entry.context_expr.func.id == "isolate_real_config_writes"
            for entry in item.items
        )
    ]
    lge_imports = [
        item
        for item in ast.walk(launcher)
        if isinstance(item, ast.Import)
        and any(alias.name == "LGE" for alias in item.names)
    ]
    assert len(guarded_scopes) == 1
    assert len(lge_imports) == 1
    assert lge_imports[0].lineno > guarded_scopes[0].lineno
    assert any(lge_imports[0] in ast.walk(scope) for scope in guarded_scopes)

    scope = runpy.run_path(str(TELEMETRY_FILE), run_name="t116_20c_offline")
    isolate = scope["isolate_real_config_writes"]
    config = tmp_path / "LGE.conf"
    backup = tmp_path / "LGE.conf.bad"
    scratch = tmp_path / "unrelated.json"
    config.write_bytes(b"TEST_ONLY_ENCRYPTED_CONFIG")
    backup.write_bytes(b"TEST_ONLY_EXISTING_BACKUP")
    scratch.write_text("before", encoding="utf-8")
    initial_config = config.read_bytes()
    initial_backup = backup.read_bytes()
    writes: list[str] = []

    class FakeConfigManager:
        """Лише контракт методу save, без AES і реальних налаштувань."""

        @staticmethod
        def save(_data: object, _password: str) -> None:
            writes.append("CONFIG_SAVE_REACHED")

    alias_dir = tmp_path / "alias_dir"
    alias_dir.mkdir()
    cases: list[tuple[str, Callable[[], object]]] = [
        ("CONFIG_MANAGER_SAVE", lambda: FakeConfigManager().save({}, "dummy")),
        ("PATH_WRITE_BYTES", lambda: config.write_bytes(b"changed")),
        ("PATH_WRITE_TEXT", lambda: config.write_text("changed", encoding="utf-8")),
        ("PATH_OPEN_WB", lambda: config.open("wb")),
        ("PATH_OPEN_APPEND", lambda: config.open("ab")),
        ("BUILTINS_OPEN", lambda: builtins.open(config, "wb")),
        ("OS_OPEN", lambda: os.open(config, os.O_WRONLY | os.O_TRUNC)),
        ("PATH_RENAME", lambda: config.rename(tmp_path / "lost.conf")),
        ("PATH_REPLACE", lambda: config.replace(tmp_path / "lost.conf")),
        ("PATH_UNLINK", lambda: config.unlink()),
        ("OS_RENAME", lambda: os.rename(config, tmp_path / "lost.conf")),
        ("OS_REPLACE", lambda: os.replace(config, tmp_path / "lost.conf")),
        ("OS_UNLINK", lambda: os.unlink(config)),
        ("OS_REMOVE", lambda: os.remove(config)),
        ("BACKUP_UNLINK", lambda: backup.unlink()),
        ("BACKUP_REPLACE", lambda: config.replace(backup)),
        (
            "ALIAS_WRITE",
            lambda: (alias_dir / ".." / config.name).write_bytes(b"changed"),
        ),
    ]

    with isolate(FakeConfigManager, config):
        assert config.read_bytes() == initial_config
        with config.open("rb") as reader:
            assert reader.read() == initial_config
        with builtins.open(config, "rb") as reader:
            assert reader.read() == initial_config
        for name, action in cases:
            try:
                action()
            except RuntimeError as error:
                assert "T116-20C TEST_ONLY" in str(error), name
            else:
                raise AssertionError(f"Не заблоковано: {name}")
            assert config.read_bytes() == initial_config, name
            assert backup.read_bytes() == initial_backup, name
        scratch.write_text("allowed", encoding="utf-8")
        assert scratch.read_text(encoding="utf-8") == "allowed"

    # Після завершення контексту всі підміни мають бути зняті.
    FakeConfigManager().save({}, "dummy")
    assert writes == ["CONFIG_SAVE_REACHED"]
    assert config.read_bytes() == initial_config
    assert backup.read_bytes() == initial_backup
    print("T116-20C TEST_ONLY | read-only real config during live diagnostics")
    print("config_guard_before_lge_import=YES")
    print("real_config_reads_allowed=YES")
    print(f"config_mutation_paths_blocked={len(cases)}/{len(cases)}")
    print("existing_config_backup_preserved=YES")
    print("unrelated_test_file_write_allowed=YES")
    print("guard_restored_after_exit=YES")
    print("real_config_disk_writes=0")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("T116-20C=GREEN_CONFIG_WRITE_ISOLATION")
