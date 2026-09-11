"""T109-24 — production trade Workspace identity schema/repository wiring check.

Перевіряє мінімальну production-зміну після GREEN T109-23:
- schema v9 додає nullable Workspace causal identity до ``trades``;
- legacy/manual rows зберігаються без зміни семантики;
- ``RuntimeRepository.create_trade()`` приймає Workspace identity;
- ``workspace_uid + signal_uid`` атомарно створює або повторно використовує один trade;
- конфлікт causal key з іншими immutable execution fields fail-closed;
- broker execution і Workspace post-risk orchestration не підключаються цим кроком.

Runner використовує лише тимчасову SQLite DB і не звертається до broker API.
"""

from __future__ import annotations

import importlib
import sqlite3
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

runtime_db = importlib.import_module("engine.db.runtime_db")
SCHEMA_VERSION = runtime_db.SCHEMA_VERSION
connect_runtime_db = runtime_db.connect_runtime_db
RuntimeRepository = importlib.import_module(
    "engine.runtime_repository"
).RuntimeRepository

TEST_ID = "T109-24"
FACTUAL_VERDICT = "A. PRODUCTION_TRADE_IDENTITY_SCHEMA_REPOSITORY_WIRING_GREEN"
FIRST_UNRESOLVED_BOUNDARY = "POST_RISK_ALLOW_TO_WORKSPACE_TRADE_PERSISTENCE"
BOUNDARY_CONTRACT = (
    "RISK_ALLOW_MUST_CREATE_OR_REUSE_WORKSPACE_TRADE_BEFORE_ANY_BROKER_SUBMISSION"
)
EXPECTED_COLUMNS = (
    "workspace_uid",
    "signal_uid",
    "execution_origin",
    "control_mode",
    "execution_state",
)


def _create_legacy_v8_database(db_path: Path) -> None:
    """Створити мінімальну legacy trades schema v8 для migration check."""
    connection = sqlite3.connect(db_path)
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
    connection.execute(
        """
        INSERT INTO trades (
            trade_uid, broker, account_id, symbol, side, volume,
            created_utc, source, comment
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "legacy-manual-trade",
            "IB",
            "DU123",
            "EURUSD",
            "BUY",
            1000.0,
            "2026-09-11T08:00:00+00:00",
            "MANUAL",
            "legacy",
        ),
    )
    connection.execute("PRAGMA user_version=8")
    connection.commit()
    connection.close()


def main() -> None:
    """Перевірити production schema/repository wiring на isolated SQLite."""
    assert SCHEMA_VERSION == 9

    with tempfile.TemporaryDirectory(prefix="t109_24_") as tmp_dir:
        db_path = Path(tmp_dir) / "runtime.db"
        _create_legacy_v8_database(db_path)

        connection = connect_runtime_db(db_path)
        connection.row_factory = sqlite3.Row
        repository = RuntimeRepository(connection)

        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(trades)").fetchall()
        }
        indexes = {
            str(row[1])
            for row in connection.execute("PRAGMA index_list(trades)").fetchall()
        }
        legacy = connection.execute(
            "SELECT * FROM trades WHERE trade_uid = ?",
            ("legacy-manual-trade",),
        ).fetchone()

        assert version == 9
        assert all(column in columns for column in EXPECTED_COLUMNS)
        assert "idx_trades_workspace_signal_unique" in indexes
        assert legacy is not None
        assert legacy["comment"] == "legacy"
        assert all(legacy[column] is None for column in EXPECTED_COLUMNS)

        manual_one = repository.create_trade(
            broker="IB",
            account_id="DU123",
            symbol="EURUSD",
            side="BUY",
            volume=1000.0,
        )
        manual_two = repository.create_trade(
            broker="IB",
            account_id="DU123",
            symbol="EURUSD",
            side="BUY",
            volume=1000.0,
        )
        assert manual_one != manual_two

        workspace_kwargs = {
            "broker": "IB",
            "account_id": "DU123",
            "symbol": "EURUSD",
            "side": "BUY",
            "volume": 3000.0,
            "source": "WORKSPACE",
            "workspace_uid": "workspace-109",
            "signal_uid": "signal-109-24",
            "execution_origin": "WORKSPACE",
            "control_mode": "AUTO",
            "execution_state": "READY_FOR_SUBMISSION",
        }
        workspace_trade_one = repository.create_trade(**workspace_kwargs)
        workspace_trade_two = repository.create_trade(**workspace_kwargs)
        assert workspace_trade_two == workspace_trade_one

        workspace_rows = connection.execute(
            """
            SELECT * FROM trades
            WHERE workspace_uid = ? AND signal_uid = ?
            """,
            ("workspace-109", "signal-109-24"),
        ).fetchall()
        assert len(workspace_rows) == 1
        workspace_row = workspace_rows[0]
        assert workspace_row["trade_uid"] == workspace_trade_one
        assert workspace_row["execution_origin"] == "WORKSPACE"
        assert workspace_row["control_mode"] == "AUTO"
        assert workspace_row["execution_state"] == "READY_FOR_SUBMISSION"

        other_workspace_trade = repository.create_trade(
            **{
                **workspace_kwargs,
                "workspace_uid": "workspace-other",
            }
        )
        assert other_workspace_trade != workspace_trade_one

        conflict_rejected = False
        try:
            repository.create_trade(
                **{
                    **workspace_kwargs,
                    "side": "SELL",
                }
            )
        except ValueError:
            conflict_rejected = True
        assert conflict_rejected

        partial_identity_rejected = False
        try:
            repository.create_trade(
                broker="IB",
                account_id="DU123",
                symbol="EURUSD",
                side="BUY",
                volume=1000.0,
                workspace_uid="workspace-only",
            )
        except ValueError:
            partial_identity_rejected = True
        assert partial_identity_rejected

        connection.close()

    print(f"{TEST_ID}_TRADE_WORKSPACE_IDENTITY_SCHEMA_REPOSITORY_WIRING=OK")
    print("production_change=True")
    print(f"schema_version={SCHEMA_VERSION}")
    print(f"workspace_identity_columns={','.join(EXPECTED_COLUMNS)}")
    print("workspace_signal_unique_index=True")
    print("legacy_v8_migration_preserved=True")
    print("legacy_identity_null=True")
    print("manual_create_trade_backward_compatible=True")
    print("workspace_create_or_reuse_idempotent=True")
    print("same_signal_other_workspace_allowed=True")
    print("conflicting_workspace_causal_key_rejected=True")
    print("partial_workspace_identity_rejected=True")
    print("workspace_post_risk_wiring=False")
    print("broker_submission_wiring=False")
    print("broker_requests=0")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


if __name__ == "__main__":
    main()
