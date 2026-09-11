"""T109-23 — TEST_ONLY trade Workspace identity schema feasibility.

Перевіряє фактичний SQLite/runtime repository контракт без production-змін:
- поточна ``trades`` ще не зберігає Workspace causal identity;
- чинний migration механізм підтримує additive nullable columns;
- partial/nullable semantics SQLite не ламають manual rows;
- UNIQUE(workspace_uid, signal_uid) може забезпечити idempotency для Workspace;
- старі рядки переживають additive migration без зміни значень;
- RuntimeRepository.create_trade() поки не приймає Workspace identity.

Runner не відкриває runtime DB проєкту, не виконує broker request і не змінює
production schema. Feasibility migration моделюється лише в ``:memory:`` SQLite.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ID = "T109-23"
FACTUAL_VERDICT = "A. ADDITIVE_TRADE_IDENTITY_SCHEMA_FEASIBLE"
FIRST_UNRESOLVED_BOUNDARY = "PRODUCTION_TRADE_SCHEMA_AND_REPOSITORY_WIRING"
BOUNDARY_CONTRACT = (
    "RISK_ALLOW_MUST_ATOMICALLY_CREATE_OR_REUSE_ONE_WORKSPACE_OWNED_TRADE_"
    "BY_WORKSPACE_UID_SIGNAL_UID_BEFORE_ANY_BROKER_SUBMISSION"
)

RUNTIME_DB_PATH = PROJECT_ROOT / "engine" / "db" / "runtime_db.py"
REPOSITORY_PATH = PROJECT_ROOT / "engine" / "runtime_repository.py"
PRODUCTION_FILES = (RUNTIME_DB_PATH, REPOSITORY_PATH)

EXPECTED_IDENTITY_COLUMNS = (
    "workspace_uid",
    "signal_uid",
    "execution_origin",
    "control_mode",
    "execution_state",
)


def _hashes() -> dict[str, str]:
    """Повернути hashes scoped production files для TEST_ONLY invariant."""
    return {
        path.relative_to(PROJECT_ROOT)
        .as_posix(): hashlib.sha256(path.read_bytes())
        .hexdigest()
        for path in PRODUCTION_FILES
    }


def _source(path: Path) -> str:
    """Прочитати UTF-8 production source."""
    return path.read_text(encoding="utf-8")


def _table_sql(source: str, table_name: str) -> str:
    """Витягти CREATE TABLE body для одного runtime table."""
    match = re.search(
        rf"CREATE TABLE IF NOT EXISTS {re.escape(table_name)} \((.*?)\n\);",
        source,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"table schema missing: {table_name}")
    return match.group(0)


def _create_trade_section(source: str) -> str:
    """Витягти фактичний RuntimeRepository.create_trade method."""
    start = source.index("    def create_trade(")
    end = source.index("    def create_order_plan(", start)
    return source[start:end]


def _simulate_additive_migration() -> dict[str, object]:
    """Довести migration/idempotency лише на isolated in-memory SQLite."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_uid TEXT NOT NULL UNIQUE,
            broker TEXT NOT NULL,
            account_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            volume REAL NOT NULL,
            created_utc TEXT NOT NULL,
            source TEXT NOT NULL,
            comment TEXT NOT NULL DEFAULT ''
        )
        """
    )
    legacy_values = (
        "legacy-trade",
        "IB",
        "DU123",
        "EURUSD",
        "BUY",
        1000.0,
        "2026-09-11T08:00:00+00:00",
        "MANUAL",
        "legacy",
    )
    connection.execute(
        """
        INSERT INTO trades (
            trade_uid, broker, account_id, symbol, side, volume,
            created_utc, source, comment
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        legacy_values,
    )

    for column in EXPECTED_IDENTITY_COLUMNS:
        connection.execute(f"ALTER TABLE trades ADD COLUMN {column} TEXT")

    connection.execute(
        """
        CREATE UNIQUE INDEX idx_trades_workspace_signal_unique
        ON trades (workspace_uid, signal_uid)
        """
    )

    legacy = connection.execute(
        "SELECT * FROM trades WHERE trade_uid = ?",
        ("legacy-trade",),
    ).fetchone()
    if legacy is None:
        raise AssertionError("legacy trade disappeared after additive migration")

    legacy_identity_null = all(
        legacy[column] is None for column in EXPECTED_IDENTITY_COLUMNS
    )
    legacy_payload_preserved = (
        tuple(
            legacy[name]
            for name in (
                "trade_uid",
                "broker",
                "account_id",
                "symbol",
                "side",
                "volume",
                "created_utc",
                "source",
                "comment",
            )
        )
        == legacy_values
    )

    manual_insert_sql = """
        INSERT INTO trades (
            trade_uid, broker, account_id, symbol, side, volume,
            created_utc, source, comment
        ) VALUES (?, 'IB', 'DU123', 'EURUSD', 'BUY', 1000,
                  '2026-09-11T08:01:00+00:00', 'MANUAL', '')
    """
    connection.execute(manual_insert_sql, ("manual-2",))
    connection.execute(manual_insert_sql, ("manual-3",))
    manual_null_duplicates_allowed = True

    workspace_insert_sql = """
        INSERT INTO trades (
            trade_uid, broker, account_id, symbol, side, volume,
            created_utc, source, comment,
            workspace_uid, signal_uid, execution_origin,
            control_mode, execution_state
        ) VALUES (?, 'IB', 'DU123', 'EURUSD', 'BUY', 1000,
                  '2026-09-11T08:02:00+00:00', 'WORKSPACE', '',
                  ?, ?, 'WORKSPACE', 'AUTO', 'READY_FOR_SUBMISSION')
    """
    connection.execute(workspace_insert_sql, ("w-trade-1", "wsp-1", "sig-1"))
    connection.execute(workspace_insert_sql, ("w-trade-2", "wsp-1", "sig-2"))

    duplicate_workspace_signal_rejected = False
    try:
        connection.execute(
            workspace_insert_sql,
            ("w-trade-duplicate", "wsp-1", "sig-1"),
        )
    except sqlite3.IntegrityError:
        duplicate_workspace_signal_rejected = True

    same_signal_other_workspace_allowed = True
    connection.execute(
        workspace_insert_sql,
        ("w-trade-3", "wsp-2", "sig-1"),
    )

    columns = tuple(
        str(row[1]) for row in connection.execute("PRAGMA table_info(trades)")
    )
    indexes = tuple(
        str(row[1]) for row in connection.execute("PRAGMA index_list(trades)")
    )
    connection.close()

    return {
        "columns": columns,
        "indexes": indexes,
        "legacy_identity_null": legacy_identity_null,
        "legacy_payload_preserved": legacy_payload_preserved,
        "manual_null_duplicates_allowed": manual_null_duplicates_allowed,
        "duplicate_workspace_signal_rejected": duplicate_workspace_signal_rejected,
        "same_signal_other_workspace_allowed": same_signal_other_workspace_allowed,
    }


def main() -> None:
    """Перевірити factual feasibility без production migration."""
    hashes_before = _hashes()
    runtime_db = _source(RUNTIME_DB_PATH)
    repository = _source(REPOSITORY_PATH)
    trades_schema = _table_sql(runtime_db, "trades")
    create_trade = _create_trade_section(repository)

    current_identity_columns = tuple(
        column
        for column in EXPECTED_IDENTITY_COLUMNS
        if re.search(rf"\b{re.escape(column)}\b", trades_schema)
    )
    current_unique_workspace_signal = bool(
        re.search(
            r"UNIQUE\s*\(\s*workspace_uid\s*,\s*signal_uid\s*\)",
            trades_schema,
            re.IGNORECASE,
        )
        or re.search(
            r"CREATE\s+UNIQUE\s+INDEX.*workspace_uid.*signal_uid",
            runtime_db,
            re.IGNORECASE | re.DOTALL,
        )
    )
    additive_migration_mechanism_present = all(
        token in runtime_db
        for token in (
            "def _ensure_runtime_column(",
            "ALTER TABLE",
            "def migrate_runtime_schema(",
        )
    )
    repository_identity_parameters_present = all(
        re.search(rf"\b{re.escape(column)}\b", create_trade)
        for column in EXPECTED_IDENTITY_COLUMNS
    )

    simulation = _simulate_additive_migration()

    assert current_identity_columns == ()
    assert not current_unique_workspace_signal
    assert additive_migration_mechanism_present
    assert not repository_identity_parameters_present
    assert all(column in simulation["columns"] for column in EXPECTED_IDENTITY_COLUMNS)
    assert "idx_trades_workspace_signal_unique" in simulation["indexes"]
    assert simulation["legacy_identity_null"] is True
    assert simulation["legacy_payload_preserved"] is True
    assert simulation["manual_null_duplicates_allowed"] is True
    assert simulation["duplicate_workspace_signal_rejected"] is True
    assert simulation["same_signal_other_workspace_allowed"] is True

    hashes_after = _hashes()
    assert hashes_after == hashes_before

    print(f"{TEST_ID}_TRADE_WORKSPACE_IDENTITY_SCHEMA_FEASIBILITY=OK")
    print("test_scope=TEST_ONLY")
    print(f"current_schema_version_marker_present={'SCHEMA_VERSION = 8' in runtime_db}")
    print(
        f"current_trade_identity_columns={','.join(current_identity_columns) or 'NONE'}"
    )
    print(
        f"current_workspace_signal_unique_constraint={current_unique_workspace_signal}"
    )
    print(
        f"additive_migration_mechanism_present={additive_migration_mechanism_present}"
    )
    print(
        f"repository_create_trade_identity_parameters_present="
        f"{repository_identity_parameters_present}"
    )
    print(f"simulated_columns_added={','.join(EXPECTED_IDENTITY_COLUMNS)}")
    print(f"legacy_payload_preserved={simulation['legacy_payload_preserved']}")
    print(f"legacy_identity_null={simulation['legacy_identity_null']}")
    print(
        f"manual_null_duplicates_allowed={simulation['manual_null_duplicates_allowed']}"
    )
    print(
        f"duplicate_workspace_signal_rejected="
        f"{simulation['duplicate_workspace_signal_rejected']}"
    )
    print(
        f"same_signal_other_workspace_allowed="
        f"{simulation['same_signal_other_workspace_allowed']}"
    )
    print("broker_requests=0")
    print("production_schema_changed=False")
    print("production_repository_changed=False")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


if __name__ == "__main__":
    main()
