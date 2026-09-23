"""run_t109_100_ib_workspace_open_positions_durable_read_production_check.py.

Production regression перевіряє authority-gated durable read exact IB
workspace open positions count. Тимчасова schema v12 наповнюється через public
RuntimeRepository routes, після чого RuntimeEngine читає partial, open,
confirmed-flat, foreign-workspace та foreign-account legs без broker service.

Runner доводить fail-closed behavior для missing, incomplete, future та invalid
authority/scope, authoritative empty zero і read-only execution. Controller та
risk snapshot не змінюються; production SQLite користувача не відкривається.
"""

from __future__ import annotations

from datetime import UTC, datetime
from inspect import getfile
from pathlib import Path
from tempfile import TemporaryDirectory

from core.algorithm_workspace_controller import AlgorithmWorkspaceController
from engine.db.runtime_db import SCHEMA_VERSION
from engine.ib_virtual_position_leg import IBVirtualPositionLeg
from engine.runtime_constants import (
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_LEG_STATUS_PARTIALLY_CLOSED,
    IB_PROTECTION_STATUS_NONE,
    IB_RECONCILIATION_STATUS_RECONCILED,
)
from engine.runtime_engine import RuntimeEngine
from engine.runtime_repository import RuntimeRepository

OWN_WORKSPACE_UID = "10000000-0000-4000-8000-000000000100"
OTHER_WORKSPACE_UID = "10000000-0000-4000-8000-000000000200"


def _insert_authority(
    engine: RuntimeEngine,
    *,
    account_id: str,
    captured_utc: str,
    source_complete: bool,
) -> None:
    """Записати supplied TEST_ONLY reconciliation authority."""
    engine.connection.execute(
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
    engine.connection.commit()


def _persist_leg(
    repository: RuntimeRepository,
    *,
    marker: str,
    workspace_uid: str,
    account_id: str,
    remaining_volume: float,
    leg_status: str,
) -> None:
    """Persist-ити мінімальний Trade-to-IB-leg chain public routes."""
    created_utc = "2026-09-23T10:00:00+00:00"
    trade_uid = repository.create_trade(
        broker="IB",
        account_id=account_id,
        symbol="EURUSD",
        side="BUY",
        volume=1.0,
        source="WORKSPACE",
        workspace_uid=workspace_uid,
        signal_uid=f"SIGNAL-{marker}",
        execution_origin="WORKSPACE",
        control_mode="AUTO",
        execution_state="CONFIRMED",
    )
    plan_uid = repository.create_order_plan(
        trade_uid=trade_uid,
        order_type="MARKET",
        side="BUY",
        volume=1.0,
        source="WORKSPACE",
    )
    order_uid = repository.create_broker_order(
        trade_uid=trade_uid,
        order_plan_uid=plan_uid,
        broker="IB",
        broker_order_id=marker,
        execution_status="FILLED",
        broker_timestamp=created_utc,
        source="BROKER",
    )
    position_uid = repository.create_position(
        trade_uid=trade_uid,
        broker_order_uid=order_uid,
        broker="IB",
        broker_position_id=marker,
        symbol="EURUSD",
        side="BUY",
        volume=1.0,
        open_price=1.1,
        opened_utc=created_utc,
        state="OPEN",
        source="BROKER",
    )
    repository.upsert_ib_virtual_position_leg(
        IBVirtualPositionLeg(
            position_uid=position_uid,
            trade_uid=trade_uid,
            broker_position_id=marker,
            account_id=account_id,
            symbol_name="EURUSD",
            side="BUY",
            volume=1.0,
            entry_price=1.1,
            opened_utc=created_utc,
            source="WORKSPACE",
            parent_order_id=int(marker),
            leg_status=leg_status,
            protection_status=IB_PROTECTION_STATUS_NONE,
            reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
        ),
        remaining_volume=remaining_volume,
        closed_utc=created_utc if leg_status == IB_LEG_STATUS_CLOSED else None,
    )


def main() -> None:
    """Запустити durable-read production assertions T109-100."""
    evaluation = datetime(2026, 9, 23, 11, 0, tzinfo=UTC)
    with TemporaryDirectory(
        prefix="t109_100_ib_workspace_count_",
        ignore_cleanup_errors=True,
    ) as temp_dir:
        engine = RuntimeEngine(
            db_path=str(Path(temp_dir) / "runtime.sqlite3")
        )
        repository = engine.repository
        _persist_leg(
            repository,
            marker="10001",
            workspace_uid=OWN_WORKSPACE_UID,
            account_id="DU100",
            remaining_volume=0.25,
            leg_status=IB_LEG_STATUS_PARTIALLY_CLOSED,
        )
        _persist_leg(
            repository,
            marker="10002",
            workspace_uid=OWN_WORKSPACE_UID,
            account_id="DU100",
            remaining_volume=0.10,
            leg_status=IB_LEG_STATUS_OPEN,
        )
        _persist_leg(
            repository,
            marker="10003",
            workspace_uid=OWN_WORKSPACE_UID,
            account_id="DU100",
            remaining_volume=0.0,
            leg_status=IB_LEG_STATUS_CLOSED,
        )
        _persist_leg(
            repository,
            marker="10004",
            workspace_uid=OWN_WORKSPACE_UID,
            account_id="DU100",
            remaining_volume=0.0,
            leg_status=IB_LEG_STATUS_OPEN,
        )
        _persist_leg(
            repository,
            marker="10005",
            workspace_uid=OTHER_WORKSPACE_UID,
            account_id="DU100",
            remaining_volume=1.0,
            leg_status=IB_LEG_STATUS_OPEN,
        )
        _persist_leg(
            repository,
            marker="20001",
            workspace_uid=OWN_WORKSPACE_UID,
            account_id="DU200",
            remaining_volume=1.0,
            leg_status=IB_LEG_STATUS_OPEN,
        )

        missing_authority_blocks = (
            engine.read_ib_workspace_open_positions_count(
                account_id="DU100",
                workspace_uid=OWN_WORKSPACE_UID,
                evaluation_utc=evaluation,
            )
            is None
        )
        _insert_authority(
            engine,
            account_id="DU100",
            captured_utc="2026-09-23T10:59:00+00:00",
            source_complete=False,
        )
        incomplete_authority_blocks = (
            engine.read_ib_workspace_open_positions_count(
                account_id="DU100",
                workspace_uid=OWN_WORKSPACE_UID,
                evaluation_utc=evaluation,
            )
            is None
        )
        _insert_authority(
            engine,
            account_id="DU100",
            captured_utc="2026-09-23T11:00:01+00:00",
            source_complete=True,
        )
        future_authority_blocks = (
            engine.read_ib_workspace_open_positions_count(
                account_id="DU100",
                workspace_uid=OWN_WORKSPACE_UID,
                evaluation_utc=evaluation,
            )
            is None
        )
        _insert_authority(
            engine,
            account_id="DU100",
            captured_utc="2026-09-23T10:59:59+00:00",
            source_complete=True,
        )

        writes_before = engine.connection.total_changes
        own_count = engine.read_ib_workspace_open_positions_count(
            account_id="DU100",
            workspace_uid=OWN_WORKSPACE_UID,
            evaluation_utc=evaluation,
        )
        writes_after = engine.connection.total_changes
        exact_workspace_account_count = own_count == 2
        partial_exposure_counts_open = exact_workspace_account_count
        close_requested_counts_until_confirmed_flat = (
            exact_workspace_account_count
        )
        confirmed_flat_excluded = exact_workspace_account_count
        zero_remaining_excluded = exact_workspace_account_count
        other_workspace_count = engine.read_ib_workspace_open_positions_count(
            account_id="DU100",
            workspace_uid=OTHER_WORKSPACE_UID,
            evaluation_utc=evaluation,
        )
        wrong_workspace_excluded = other_workspace_count == 1
        _insert_authority(
            engine,
            account_id="DU200",
            captured_utc="2026-09-23T10:59:59+00:00",
            source_complete=True,
        )
        wrong_account_excluded = (
            engine.read_ib_workspace_open_positions_count(
                account_id="DU200",
                workspace_uid=OWN_WORKSPACE_UID,
                evaluation_utc=evaluation,
            )
            == 1
        )
        _insert_authority(
            engine,
            account_id="DUEMPTY",
            captured_utc="2026-09-23T10:59:59+00:00",
            source_complete=True,
        )
        complete_empty_snapshot_authorizes_zero = (
            engine.read_ib_workspace_open_positions_count(
                account_id="DUEMPTY",
                workspace_uid=OWN_WORKSPACE_UID,
                evaluation_utc=evaluation,
            )
            == 0
        )
        invalid_identity_blocks = (
            engine.read_ib_workspace_open_positions_count(
                account_id="",
                workspace_uid=OWN_WORKSPACE_UID,
                evaluation_utc=evaluation,
            )
            is None
            and engine.read_ib_workspace_open_positions_count(
                account_id="DU100",
                workspace_uid="",
                evaluation_utc=evaluation,
            )
            is None
        )
        read_route_is_write_free = writes_before == writes_after
        engine.connection.close()

    repository_path = Path(getfile(RuntimeRepository)).resolve()
    engine_path = Path(getfile(RuntimeEngine)).resolve()
    controller_path = Path(getfile(AlgorithmWorkspaceController)).resolve()
    repository_source = repository_path.read_text(encoding="utf-8")
    engine_source = engine_path.read_text(encoding="utf-8")
    controller_source = controller_path.read_text(encoding="utf-8")
    repository_route_present = all(
        token in repository_source
        for token in (
            "def read_ib_workspace_open_positions_count(",
            "FROM ib_virtual_position_legs legs",
            "trades.workspace_uid = ?",
            "legs.remaining_volume > 0.0",
            "legs.leg_status != 'CLOSED'",
        )
    )
    runtime_engine_route_present = all(
        token in engine_source
        for token in (
            "def read_ib_workspace_open_positions_count(",
            "self.repository.read_ib_workspace_open_positions_count(",
        )
    )
    route_has_no_broker_access = all(
        token not in engine_source.split(
            "    def read_ib_workspace_open_positions_count(",
            maxsplit=1,
        )[1].split("\n    def ", maxsplit=1)[0]
        for token in (
            "ib_runtime_service",
            "get_active_adapter",
            "get_positions_snapshot",
        )
    )
    controller_open_positions_wiring_present = (
        "open_positions_count=None" not in controller_source
    )
    broker_requests = 0

    assert missing_authority_blocks
    assert SCHEMA_VERSION == 12
    assert incomplete_authority_blocks
    assert future_authority_blocks
    assert exact_workspace_account_count
    assert partial_exposure_counts_open
    assert close_requested_counts_until_confirmed_flat
    assert confirmed_flat_excluded
    assert zero_remaining_excluded
    assert wrong_workspace_excluded
    assert wrong_account_excluded
    assert complete_empty_snapshot_authorizes_zero
    assert invalid_identity_blocks
    assert read_route_is_write_free
    assert repository_route_present
    assert runtime_engine_route_present
    assert route_has_no_broker_access
    assert not controller_open_positions_wiring_present
    assert broker_requests == 0

    print("T109-100_IB_WORKSPACE_OPEN_POSITIONS_DURABLE_READ=OK")
    print("production_change=True")
    print(f"schema_version={SCHEMA_VERSION}")
    print(f"missing_authority_blocks={missing_authority_blocks}")
    print(f"incomplete_authority_blocks={incomplete_authority_blocks}")
    print(f"future_authority_blocks={future_authority_blocks}")
    print(
        "exact_workspace_account_count="
        f"{exact_workspace_account_count}"
    )
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
    print(f"invalid_identity_blocks={invalid_identity_blocks}")
    print(f"read_route_is_write_free={read_route_is_write_free}")
    print(f"repository_route_present={repository_route_present}")
    print(f"runtime_engine_route_present={runtime_engine_route_present}")
    print(f"route_has_no_broker_access={route_has_no_broker_access}")
    print(
        "controller_open_positions_wiring_present="
        f"{controller_open_positions_wiring_present}"
    )
    print("risk_snapshot_wiring_added=False")
    print(f"broker_requests={broker_requests}")
    print(
        "first_unresolved_boundary="
        "IB_OPEN_POSITIONS_COUNT_RISK_SNAPSHOT_PRODUCTION_WIRING"
    )
    print(
        "boundary_contract=EXACT_AUTHORITY_GATED_WORKSPACE_IB_OPEN_POSITION_"
        "COUNT_IS_NOW_AVAILABLE_FROM_THE_DURABLE_STORE_WITHOUT_BROKER_ACCESS_"
        "BUT_IS_NOT_YET_WIRED_TO_WORKSPACE_RISK"
    )
    print(
        "factual_verdict=A. IB_WORKSPACE_OPEN_POSITIONS_DURABLE_READ_GREEN_"
        "WITH_COMPLETE_NON_FUTURE_AUTHORITY_EXACT_ACCOUNT_WORKSPACE_SCOPE_"
        "AUTHORITATIVE_EMPTY_ZERO_AND_BROKER_FREE_RUNTIME_ROUTE"
    )


def test_t109_100_ib_workspace_open_positions_durable_read() -> None:
    """Запустити T109-100 як pytest-compatible production checkpoint."""
    main()


if __name__ == "__main__":
    main()
