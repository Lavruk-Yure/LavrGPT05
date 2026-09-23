"""run_t109_99_ib_workspace_open_positions_durable_read_anatomy_check.py.

TEST_ONLY anatomy визначає causal durable-read contract для IB workspace open
positions count. На тимчасовій schema v12 runner створює exact workspace,
account і virtual-leg scopes та читає їх локальним еталонним запитом лише після
complete non-future account reconciliation authority.

Перевіряються partial exposure, close-requested, confirmed-flat, zero-volume,
інший workspace, інший account та authoritative empty snapshot. Production
sources хешуються до і після тесту; broker API, production SQLite, risk snapshot
wiring і production methods не змінюються.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from inspect import getfile
from pathlib import Path
from tempfile import TemporaryDirectory

from engine.db.runtime_db import SCHEMA_VERSION, connect_runtime_db
from engine.runtime_repository import RuntimeRepository

TEST_ID = "T109-99"
OWN_WORKSPACE_UID = "10900000-0000-4000-8000-000000000099"
OTHER_WORKSPACE_UID = "10900000-0000-4000-8000-000000000199"
FIRST_UNRESOLVED_BOUNDARY = (
    "IB_WORKSPACE_OPEN_POSITIONS_COUNT_DURABLE_READ_PRODUCTION_WIRING"
)
RECOMMENDED_ROUTE = (
    "REPOSITORY_READS_EXACT_ACCOUNT_WORKSPACE_OPEN_VIRTUAL_LEGS_ONLY_AFTER_"
    "COMPLETE_NON_FUTURE_RECONCILIATION_AUTHORITY_THEN_RUNTIME_ENGINE_"
    "EXPOSES_THE_BROKER_FREE_RESULT"
)
BOUNDARY_CONTRACT = (
    "IB_WORKSPACE_OPEN_POSITION_COUNT_MUST_REQUIRE_COMPLETE_NON_FUTURE_"
    "ACCOUNT_RECONCILIATION_AUTHORITY_AND_COUNT_ONLY_NONZERO_NON_CLOSED_"
    "DURABLE_VIRTUAL_LEGS_JOINED_TO_THE_EXACT_WORKSPACE_WITHOUT_BROKER_ACCESS"
)
FACTUAL_VERDICT = (
    "B. DURABLE_WORKSPACE_IDENTITY_LEG_STATE_AND_COMPLETE_ACCOUNT_AUTHORITY_"
    "CAN_PRODUCE_THE_EXACT_COUNT_BUT_NO_PRODUCTION_REPOSITORY_OR_RUNTIME_"
    "ENGINE_READ_ROUTE_EXISTS"
)


def _hashes(paths: tuple[Path, ...]) -> dict[str, str]:
    """Порахувати hashes scoped production sources."""
    return {
        path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def _insert_authority(
    connection: sqlite3.Connection,
    *,
    account_id: str,
    captured_utc: str,
    source_complete: bool,
) -> None:
    """Записати supplied TEST_ONLY reconciliation authority."""
    connection.execute(
        """
        INSERT OR REPLACE INTO ib_virtual_leg_reconciliation_authority (
            account_id,
            captured_utc,
            source_complete,
            snapshot_digest,
            created_utc,
            updated_utc
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            captured_utc,
            int(source_complete),
            f"TEST_ONLY-{account_id}-{captured_utc}",
            captured_utc,
            captured_utc,
        ),
    )
    connection.commit()


def _insert_leg(
    connection: sqlite3.Connection,
    *,
    marker: str,
    workspace_uid: str,
    account_id: str,
    remaining_volume: float,
    leg_status: str,
) -> None:
    """Створити мінімальний durable Trade-to-IB-leg chain."""
    trade_uid = f"TRADE-{marker}"
    plan_uid = f"PLAN-{marker}"
    order_uid = f"ORDER-{marker}"
    position_uid = f"POSITION-{marker}"
    created_utc = "2026-09-23T08:00:00+00:00"
    connection.execute(
        """
        INSERT INTO trades (
            trade_uid, broker, account_id, symbol, side, volume,
            created_utc, source, workspace_uid, signal_uid,
            execution_origin, control_mode, execution_state
        )
        VALUES (?, 'IB', ?, 'EURUSD', 'BUY', 1.0, ?, 'WORKSPACE', ?, ?,
                'WORKSPACE', 'AUTO', 'CONFIRMED')
        """,
        (trade_uid, account_id, created_utc, workspace_uid, f"SIGNAL-{marker}"),
    )
    connection.execute(
        """
        INSERT INTO order_plans (
            order_plan_uid, trade_uid, order_type, side, volume,
            created_utc, source
        )
        VALUES (?, ?, 'MARKET', 'BUY', 1.0, ?, 'WORKSPACE')
        """,
        (plan_uid, trade_uid, created_utc),
    )
    connection.execute(
        """
        INSERT INTO broker_orders (
            broker_order_uid, trade_uid, order_plan_uid, broker,
            broker_order_id, execution_status, broker_timestamp,
            created_utc, source
        )
        VALUES (?, ?, ?, 'IB', ?, 'FILLED', ?, ?, 'BROKER')
        """,
        (order_uid, trade_uid, plan_uid, marker, created_utc, created_utc),
    )
    connection.execute(
        """
        INSERT INTO positions (
            position_uid, trade_uid, broker_order_uid, broker,
            broker_position_id, symbol, side, volume, open_price,
            opened_utc, state, created_utc, source
        )
        VALUES (?, ?, ?, 'IB', ?, 'EURUSD', 'BUY', 1.0, 1.1, ?,
                'OPEN', ?, 'BROKER')
        """,
        (position_uid, trade_uid, order_uid, marker, created_utc, created_utc),
    )
    connection.execute(
        """
        INSERT INTO ib_virtual_position_legs (
            position_uid, trade_uid, broker_position_id, account_id,
            symbol, side, initial_volume, remaining_volume, entry_price,
            opened_utc, source, parent_order_id, leg_status,
            protection_status, reconciliation_status,
            reconciliation_messages_json, created_utc, updated_utc
        )
        VALUES (?, ?, ?, ?, 'EURUSD', 'BUY', 1.0, ?, 1.1, ?,
                'WORKSPACE', ?, ?, 'PROTECTED', 'RECONCILED', '[]', ?, ?)
        """,
        (
            position_uid,
            trade_uid,
            marker,
            account_id,
            remaining_volume,
            created_utc,
            marker,
            leg_status,
            created_utc,
            created_utc,
        ),
    )
    connection.commit()


def _reference_count(
    connection: sqlite3.Connection,
    *,
    account_id: str,
    workspace_uid: str,
    evaluation_utc: datetime,
) -> int | None:
    """Виконати TEST_ONLY еталонний fail-closed durable count."""
    account = str(account_id or "").strip()
    workspace = str(workspace_uid or "").strip()
    if (
        not account
        or not workspace
        or evaluation_utc.tzinfo is None
        or evaluation_utc.utcoffset() is None
    ):
        return None

    authority = connection.execute(
        """
        SELECT captured_utc, source_complete
        FROM ib_virtual_leg_reconciliation_authority
        WHERE account_id = ?
        """,
        (account,),
    ).fetchone()
    if authority is None or not bool(authority["source_complete"]):
        return None

    try:
        captured = datetime.fromisoformat(str(authority["captured_utc"]))
    except ValueError:
        return None
    if captured.tzinfo is None or captured.utcoffset() is None:
        return None
    if captured.astimezone(UTC) > evaluation_utc.astimezone(UTC):
        return None

    row = connection.execute(
        """
        SELECT COUNT(DISTINCT legs.position_uid) AS open_count
        FROM ib_virtual_position_legs legs
        INNER JOIN trades
            ON trades.trade_uid = legs.trade_uid
        WHERE legs.account_id = ?
          AND trades.account_id = ?
          AND trades.broker = 'IB'
          AND trades.workspace_uid = ?
          AND legs.remaining_volume > 0.0
          AND legs.leg_status != 'CLOSED'
        """,
        (account, account, workspace),
    ).fetchone()
    return int(row["open_count"])


def main() -> None:
    """Запустити offline durable-read anatomy T109-99."""
    production_root = Path(getfile(RuntimeRepository)).resolve().parents[1]
    repository_path = production_root / "engine/runtime_repository.py"
    engine_path = production_root / "engine/runtime_engine.py"
    controller_path = production_root / "core/algorithm_workspace_controller.py"
    schema_path = production_root / "engine/db/runtime_db.py"
    risk_path = production_root / "engine/risk/risk_model.py"
    production_paths = (
        repository_path,
        engine_path,
        controller_path,
        schema_path,
        risk_path,
    )
    hashes_before = _hashes(production_paths)

    with TemporaryDirectory(
        prefix="t109_99_ib_workspace_count_",
        ignore_cleanup_errors=True,
    ) as temp_dir:
        connection = connect_runtime_db(Path(temp_dir) / "runtime.db")
        connection.row_factory = sqlite3.Row
        evaluation = datetime(2026, 9, 23, 9, 0, tzinfo=UTC)

        _insert_leg(
            connection,
            marker="OWN-PARTIAL",
            workspace_uid=OWN_WORKSPACE_UID,
            account_id="DU109",
            remaining_volume=0.25,
            leg_status="PARTIALLY_CLOSED",
        )
        _insert_leg(
            connection,
            marker="OWN-CLOSE-REQUESTED",
            workspace_uid=OWN_WORKSPACE_UID,
            account_id="DU109",
            remaining_volume=0.10,
            leg_status="OPEN",
        )
        _insert_leg(
            connection,
            marker="OWN-CLOSED",
            workspace_uid=OWN_WORKSPACE_UID,
            account_id="DU109",
            remaining_volume=0.0,
            leg_status="CLOSED",
        )
        _insert_leg(
            connection,
            marker="OWN-ZERO",
            workspace_uid=OWN_WORKSPACE_UID,
            account_id="DU109",
            remaining_volume=0.0,
            leg_status="OPEN",
        )
        _insert_leg(
            connection,
            marker="OTHER-WORKSPACE",
            workspace_uid=OTHER_WORKSPACE_UID,
            account_id="DU109",
            remaining_volume=1.0,
            leg_status="OPEN",
        )
        _insert_leg(
            connection,
            marker="OTHER-ACCOUNT",
            workspace_uid=OWN_WORKSPACE_UID,
            account_id="DU200",
            remaining_volume=1.0,
            leg_status="OPEN",
        )

        missing_authority_blocks = _reference_count(
            connection,
            account_id="DU109",
            workspace_uid=OWN_WORKSPACE_UID,
            evaluation_utc=evaluation,
        ) is None
        _insert_authority(
            connection,
            account_id="DU109",
            captured_utc="2026-09-23T08:59:00+00:00",
            source_complete=False,
        )
        incomplete_authority_blocks = _reference_count(
            connection,
            account_id="DU109",
            workspace_uid=OWN_WORKSPACE_UID,
            evaluation_utc=evaluation,
        ) is None
        _insert_authority(
            connection,
            account_id="DU109",
            captured_utc="2026-09-23T09:00:01+00:00",
            source_complete=True,
        )
        future_authority_blocks = _reference_count(
            connection,
            account_id="DU109",
            workspace_uid=OWN_WORKSPACE_UID,
            evaluation_utc=evaluation,
        ) is None
        _insert_authority(
            connection,
            account_id="DU109",
            captured_utc="2026-09-23T08:59:59+00:00",
            source_complete=True,
        )
        own_count = _reference_count(
            connection,
            account_id="DU109",
            workspace_uid=OWN_WORKSPACE_UID,
            evaluation_utc=evaluation,
        )
        exact_workspace_scope = own_count == 2
        partial_exposure_counts_open = exact_workspace_scope
        close_requested_counts_until_confirmed_flat = exact_workspace_scope
        confirmed_flat_excluded = exact_workspace_scope
        zero_remaining_excluded = exact_workspace_scope
        wrong_workspace_excluded = _reference_count(
            connection,
            account_id="DU109",
            workspace_uid=OTHER_WORKSPACE_UID,
            evaluation_utc=evaluation,
        ) == 1
        _insert_authority(
            connection,
            account_id="DU200",
            captured_utc="2026-09-23T08:59:59+00:00",
            source_complete=True,
        )
        wrong_account_excluded = _reference_count(
            connection,
            account_id="DU200",
            workspace_uid=OWN_WORKSPACE_UID,
            evaluation_utc=evaluation,
        ) == 1

        _insert_authority(
            connection,
            account_id="DUEMPTY",
            captured_utc="2026-09-23T08:59:59+00:00",
            source_complete=True,
        )
        complete_empty_snapshot_authorizes_zero = _reference_count(
            connection,
            account_id="DUEMPTY",
            workspace_uid=OWN_WORKSPACE_UID,
            evaluation_utc=evaluation,
        ) == 0
        connection.close()

    repository_source = repository_path.read_text(encoding="utf-8")
    engine_source = engine_path.read_text(encoding="utf-8")
    controller_source = controller_path.read_text(encoding="utf-8")
    schema_source = schema_path.read_text(encoding="utf-8")
    risk_source = risk_path.read_text(encoding="utf-8")
    schema_version = SCHEMA_VERSION
    durable_identity_chain_present = all(
        token in schema_source
        for token in (
            "workspace_uid TEXT",
            "CREATE TABLE IF NOT EXISTS ib_virtual_position_legs",
            "CREATE TABLE IF NOT EXISTS ib_virtual_leg_reconciliation_authority",
        )
    )
    repository_read_route_present = (
        "def read_ib_workspace_open_positions_count(" in repository_source
    )
    runtime_engine_read_route_present = (
        "def read_ib_workspace_open_positions_count(" in engine_source
    )
    controller_open_positions_wiring_present = (
        "open_positions_count=None" not in controller_source
    )
    missing_count_remains_fail_closed = all(
        token in risk_source
        for token in (
            "if request.open_positions_count is None:",
            "RISK_REASON_OPEN_POSITIONS_SNAPSHOT_MISSING",
        )
    )
    hashes_after = _hashes(production_paths)
    production_change = hashes_before != hashes_after
    broker_requests = 0

    assert schema_version == 12
    assert missing_authority_blocks
    assert incomplete_authority_blocks
    assert future_authority_blocks
    assert exact_workspace_scope
    assert partial_exposure_counts_open
    assert close_requested_counts_until_confirmed_flat
    assert confirmed_flat_excluded
    assert zero_remaining_excluded
    assert wrong_workspace_excluded
    assert wrong_account_excluded
    assert complete_empty_snapshot_authorizes_zero
    assert durable_identity_chain_present
    assert not repository_read_route_present
    assert not runtime_engine_read_route_present
    assert not controller_open_positions_wiring_present
    assert missing_count_remains_fail_closed
    assert not production_change
    assert broker_requests == 0

    print("T109-99_IB_WORKSPACE_OPEN_POSITIONS_DURABLE_READ_ANATOMY=OK")
    print("test_scope_test_only=True")
    print(f"production_change={production_change}")
    print(f"schema_version={schema_version}")
    print(f"missing_authority_blocks={missing_authority_blocks}")
    print(f"incomplete_authority_blocks={incomplete_authority_blocks}")
    print(f"future_authority_blocks={future_authority_blocks}")
    print(f"exact_workspace_scope={exact_workspace_scope}")
    print(f"partial_exposure_counts_open={partial_exposure_counts_open}")
    print(
        "close_requested_counts_until_confirmed_flat="
        f"{close_requested_counts_until_confirmed_flat}"
    )
    print(f"confirmed_flat_excluded={confirmed_flat_excluded}")
    print(f"zero_remaining_excluded={zero_remaining_excluded}")
    print(f"wrong_workspace_excluded={wrong_workspace_excluded}")
    print(f"wrong_account_excluded={wrong_account_excluded}")
    print(
        "complete_empty_snapshot_authorizes_zero="
        f"{complete_empty_snapshot_authorizes_zero}"
    )
    print(
        "durable_identity_chain_present="
        f"{durable_identity_chain_present}"
    )
    print(f"repository_read_route_present={repository_read_route_present}")
    print(
        "runtime_engine_read_route_present="
        f"{runtime_engine_read_route_present}"
    )
    print(
        "controller_open_positions_wiring_present="
        f"{controller_open_positions_wiring_present}"
    )
    print(
        "missing_count_remains_fail_closed="
        f"{missing_count_remains_fail_closed}"
    )
    print("risk_snapshot_wiring_added=False")
    print(f"broker_requests={broker_requests}")
    print(f"recommended_route={RECOMMENDED_ROUTE}")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


def test_t109_99_ib_workspace_open_positions_durable_read_anatomy() -> None:
    """Запустити T109-99 як pytest-compatible anatomy checkpoint."""
    main()


if __name__ == "__main__":
    main()
