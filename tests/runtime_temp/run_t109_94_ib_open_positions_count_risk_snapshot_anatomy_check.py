"""run_t109_94_ib_open_positions_count_risk_snapshot_anatomy_check.py.

TEST_ONLY anatomy визначає фактичну межу перед production wiring
``WorkspaceRiskAccountSnapshot.open_positions_count`` для IB. Runner перевіряє
прийняту workspace-only semantics на supplied rows, простежує durable identity
від virtual leg до Trade та відокремлює persisted OPEN state від свіжого
повного broker reconciliation.

Тест не викликає broker API і не змінює production. Він доводить, що чинний
seed reader не повертає ``workspace_uid`` і не має workspace filter, а повний
reconciliation route потребує broker evidence та не має production caller.
Тому stale durable rows не можуть авторизувати risk count; за відсутності
авторитетного count значення лишається ``None`` і risk evaluation fail-closed.
"""

from __future__ import annotations

import hashlib
from dataclasses import fields
from inspect import getfile
from pathlib import Path

from core.workspace_ownership import (
    WorkspaceBinding,
    WorkspaceOwnershipFilter,
)
from engine.broker_position import BrokerPosition
from engine.runtime_repository import RuntimeRepository

TEST_ID = "T109-94"
OWN_WORKSPACE_UID = "10900000-0000-4000-8000-000000000094"
OTHER_WORKSPACE_UID = "10900000-0000-4000-8000-000000000095"
FIRST_UNRESOLVED_BOUNDARY = (
    "IB_VIRTUAL_LEG_RECONCILIATION_PRODUCTION_CALLER"
)
BOUNDARY_CONTRACT = (
    "IB_OPEN_POSITION_COUNT_REQUIRES_A_FRESH_COMPLETE_RECONCILED_VIRTUAL_"
    "LEG_SNAPSHOT_BEFORE_AN_EXACT_WORKSPACE_SCOPED_DURABLE_READ_CAN_WIRE_"
    "THE_RISK_SNAPSHOT_WITHOUT_A_NEW_BROKER_REQUEST"
)
FACTUAL_VERDICT = (
    "B. IB_WORKSPACE_IDENTITY_REACHES_THE_DURABLE_VIRTUAL_LEG_CHAIN_BUT_"
    "THE_READ_ROUTE_OMITS_WORKSPACE_SCOPE_AND_NO_PRODUCTION_CALLER_"
    "PERSISTS_A_FRESH_COMPLETE_RECONCILIATION_SNAPSHOT"
)


def _read(path: Path) -> str:
    """Прочитати production source як UTF-8 для static assertions."""
    return path.read_text(encoding="utf-8")


def _section(source: str, start: str, end: str) -> str:
    """Виділити точну секцію між двома production declarations."""
    start_index = source.index(start)
    end_index = source.index(end, start_index + len(start))
    return source[start_index:end_index]


def _hashes(paths: tuple[Path, ...]) -> dict[str, str]:
    """Порахувати hashes лише для scoped production sources."""
    return {
        path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def _position(
    *,
    workspace_uid: str,
    symbol: str,
    position_id: str,
    volume: float,
    status: str,
) -> dict[str, object]:
    """Побудувати supplied position row для ownership/lifecycle перевірки."""
    return {
        "workspace_uid": workspace_uid,
        "broker": "IB",
        "account_id": "DU109",
        "symbol": symbol,
        "position_id": position_id,
        "broker_position_id": position_id,
        "side": "BUY",
        "volume": volume,
        "entry_price": 1.10,
        "current_price": 1.11,
        "current_profit": 1.0,
        "peak_profit": 1.5,
        "stop_loss": 1.09,
        "take_profit": 1.12,
        "opened_at": "2026-09-22T06:00:00+00:00",
        "reconciliation_status": status,
    }


def _pending_order() -> dict[str, object]:
    """Побудувати active pending order, який не є open position."""
    return {
        "workspace_uid": OWN_WORKSPACE_UID,
        "broker": "IB",
        "account_id": "DU109",
        "symbol": "EURUSD",
        "order_id": "ORDER-PENDING",
        "broker_order_id": "901",
        "side": "BUY",
        "order_type": "LMT",
        "volume": 1.0,
        "price": 1.09,
        "stop_loss": 1.08,
        "take_profit": 1.12,
        "status": "SUBMITTED",
        "created_at": "2026-09-22T06:00:00+00:00",
        "profit": 0.0,
        "active": True,
    }


def main() -> None:
    """Запустити offline anatomy assertions T109-94."""
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

    repository_source = _read(repository_path)
    engine_source = _read(engine_path)
    controller_source = _read(controller_path)
    schema_source = _read(schema_path)
    risk_source = _read(risk_path)
    seed_section = _section(
        repository_source,
        "    def get_open_ib_virtual_position_leg_seeds(",
        "    def upsert_ib_virtual_position_leg(",
    )
    sync_section = _section(
        engine_source,
        "    def sync_reconciled_ib_virtual_position_legs(",
        "    def _build_open_runtime_position_leg_snapshot(",
    )
    broker_snapshot_section = _section(
        engine_source,
        "    def get_workspace_broker_positions_snapshot(",
        "    def _enrich_ib_positions_from_runtime_repository(",
    )

    binding = WorkspaceBinding(
        workspace_uid=OWN_WORKSPACE_UID,
        broker="IB",
        account_id="DU109",
        symbol="EURUSD",
    )
    selection = WorkspaceOwnershipFilter(binding).select(
        [_pending_order()],
        [
            _position(
                workspace_uid=OWN_WORKSPACE_UID,
                symbol="EURUSD",
                position_id="PARTIAL-FILL",
                volume=0.25,
                status="RECONCILED",
            ),
            _position(
                workspace_uid=OWN_WORKSPACE_UID,
                symbol="EURUSD",
                position_id="CLOSE-REQUESTED",
                volume=0.10,
                status="CLOSE_REQUESTED",
            ),
            _position(
                workspace_uid=OWN_WORKSPACE_UID,
                symbol="EURUSD",
                position_id="CONFIRMED-FLAT",
                volume=0.0,
                status="CLOSED",
            ),
            _position(
                workspace_uid=OTHER_WORKSPACE_UID,
                symbol="EURUSD",
                position_id="FOREIGN-WORKSPACE",
                volume=1.0,
                status="RECONCILED",
            ),
            _position(
                workspace_uid=OWN_WORKSPACE_UID,
                symbol="GBPUSD",
                position_id="WRONG-SYMBOL",
                volume=1.0,
                status="RECONCILED",
            ),
        ],
    )

    accepted_scope_workspace_only = selection.rejected_positions == 2
    pending_orders_excluded = (
        len(selection.active_orders) == 1
        and len(selection.active_positions) == 2
    )
    partial_exposure_counts_open = any(
        position.position_id == "PARTIAL-FILL"
        for position in selection.active_positions
    )
    close_requested_counts_until_confirmed_flat = any(
        position.position_id == "CLOSE-REQUESTED"
        for position in selection.active_positions
    )
    confirmed_flat_excluded = all(
        position.position_id != "CONFIRMED-FLAT"
        for position in selection.active_positions
    )

    trade_workspace_identity_persisted = all(
        token in schema_source
        for token in (
            "workspace_uid TEXT",
            "signal_uid TEXT",
            "ON trades (workspace_uid, signal_uid)",
        )
    )
    virtual_leg_join_reaches_trade_identity = all(
        token in seed_section
        for token in (
            "INNER JOIN trades",
            "ON trades.trade_uid = positions.trade_uid",
        )
    )
    virtual_leg_seed_selects_workspace_identity = (
        "trades.workspace_uid" in seed_section
    )
    virtual_leg_seed_filters_workspace_identity = (
        "workspace_uid: str" in seed_section
        or "AND trades.workspace_uid" in seed_section
    )
    broker_fields = {field.name for field in fields(BrokerPosition)}
    fresh_broker_snapshot_lacks_workspace_identity = (
        "workspace_uid" not in broker_fields
        and "signal_uid" not in broker_fields
    )
    fresh_broker_snapshot_requires_request = (
        "service.get_positions_snapshot()" in broker_snapshot_section
    )
    durable_open_leg_read_api_present = (
        "def get_open_ib_virtual_position_leg_seeds(" in repository_source
    )
    durable_open_leg_state_is_not_freshness_authority = all(
        token not in seed_section
        for token in (
            "snapshot_complete",
            "coverage_complete",
            "captured_utc",
        )
    )
    complete_reconciliation_persistence_route_present = all(
        token in sync_section
        for token in (
            "get_ib_virtual_position_leg_evidence_snapshot()",
            "sync_reconciled_ib_virtual_position_leg_snapshot(",
        )
    )
    reconciliation_production_caller_present = (
        engine_source.count("sync_reconciled_ib_virtual_position_legs(") > 1
        or "sync_reconciled_ib_virtual_position_legs(" in controller_source
    )
    cached_complete_reconciliation_snapshot_available = any(
        token in schema_source
        for token in (
            "ib_virtual_position_leg_snapshots",
            "snapshot_complete INTEGER",
            "reconciliation_coverage",
        )
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

    assert accepted_scope_workspace_only
    assert pending_orders_excluded
    assert partial_exposure_counts_open
    assert close_requested_counts_until_confirmed_flat
    assert confirmed_flat_excluded
    assert trade_workspace_identity_persisted
    assert virtual_leg_join_reaches_trade_identity
    assert not virtual_leg_seed_selects_workspace_identity
    assert not virtual_leg_seed_filters_workspace_identity
    assert fresh_broker_snapshot_lacks_workspace_identity
    assert fresh_broker_snapshot_requires_request
    assert durable_open_leg_read_api_present
    assert durable_open_leg_state_is_not_freshness_authority
    assert complete_reconciliation_persistence_route_present
    assert not reconciliation_production_caller_present
    assert not cached_complete_reconciliation_snapshot_available
    assert not controller_open_positions_wiring_present
    assert missing_count_remains_fail_closed

    hashes_after = _hashes(production_paths)
    production_change = hashes_before != hashes_after
    assert not production_change

    print("T109-94_IB_OPEN_POSITIONS_COUNT_RISK_SNAPSHOT_ANATOMY=OK")
    print("test_scope_test_only=True")
    print(f"production_change={production_change}")
    print(f"accepted_scope_workspace_only={accepted_scope_workspace_only}")
    print(f"pending_orders_excluded={pending_orders_excluded}")
    print(f"partial_exposure_counts_open={partial_exposure_counts_open}")
    print(
        "close_requested_counts_until_confirmed_flat="
        f"{close_requested_counts_until_confirmed_flat}"
    )
    print(f"confirmed_flat_excluded={confirmed_flat_excluded}")
    print(
        "trade_workspace_identity_persisted="
        f"{trade_workspace_identity_persisted}"
    )
    print(
        "virtual_leg_join_reaches_trade_identity="
        f"{virtual_leg_join_reaches_trade_identity}"
    )
    print(
        "virtual_leg_seed_selects_workspace_identity="
        f"{virtual_leg_seed_selects_workspace_identity}"
    )
    print(
        "virtual_leg_seed_filters_workspace_identity="
        f"{virtual_leg_seed_filters_workspace_identity}"
    )
    print(
        "fresh_broker_snapshot_requires_request="
        f"{fresh_broker_snapshot_requires_request}"
    )
    print(
        "fresh_broker_snapshot_lacks_workspace_identity="
        f"{fresh_broker_snapshot_lacks_workspace_identity}"
    )
    print(
        "durable_open_leg_read_api_present="
        f"{durable_open_leg_read_api_present}"
    )
    print(
        "durable_open_leg_state_is_not_freshness_authority="
        f"{durable_open_leg_state_is_not_freshness_authority}"
    )
    print(
        "complete_reconciliation_persistence_route_present="
        f"{complete_reconciliation_persistence_route_present}"
    )
    print(
        "reconciliation_production_caller_present="
        f"{reconciliation_production_caller_present}"
    )
    print(
        "cached_complete_reconciliation_snapshot_available="
        f"{cached_complete_reconciliation_snapshot_available}"
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
    print("broker_requests=0")
    print(
        "recommended_sequence=PRODUCTION_CALLER_PERSISTS_FRESH_COMPLETE_"
        "RECONCILIATION_THEN_EXACT_WORKSPACE_DURABLE_READ_WIRES_RISK_SNAPSHOT"
    )
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


def test_t109_94_ib_open_positions_count_risk_snapshot_anatomy() -> None:
    """Запустити T109-94 як pytest-compatible checkpoint."""
    main()


if __name__ == "__main__":
    main()
