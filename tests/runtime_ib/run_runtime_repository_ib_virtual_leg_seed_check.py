# run_runtime_repository_ib_virtual_leg_seed_check.py
"""
Synthetic RuntimeRepository IB virtual-leg seed check.

RoadMap90:
- SQLite in-memory;
- без TWS;
- без schema migration;
- logical Trade fields мають перемогти IB net snapshot у positions.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.db.runtime_db import connect_runtime_db  # noqa: E402
from engine.ib_virtual_position_leg import (  # noqa: E402
    build_ib_virtual_position_legs_from_repository_seeds,
)
from engine.runtime_repository import RuntimeRepository  # noqa: E402


def _create_open_ib_position(
    repository: RuntimeRepository,
    *,
    account_id: str,
    symbol_name: str,
    logical_side: str,
    logical_volume: float,
    parent_order_id: int,
    broker_snapshot_side: str,
    broker_snapshot_volume: float,
    broker_snapshot_open_price: float,
) -> str:
    trade_uid = repository.create_trade(
        broker="IB",
        account_id=account_id,
        symbol=symbol_name,
        side=logical_side,
        volume=logical_volume,
        source="MANUAL",
    )
    order_plan_uid = repository.create_order_plan(
        trade_uid=trade_uid,
        order_type="MARKET",
        side=logical_side,
        volume=logical_volume,
        source="MANUAL",
    )
    broker_order_uid = repository.create_broker_order(
        trade_uid=trade_uid,
        order_plan_uid=order_plan_uid,
        broker="IB",
        broker_order_id=str(parent_order_id),
        execution_status="FILLED",
        source="MANUAL",
    )
    return repository.create_position(
        trade_uid=trade_uid,
        broker_order_uid=broker_order_uid,
        broker="IB",
        broker_position_id=(
            f"IB:{account_id}:{symbol_name}"
        ),
        symbol=symbol_name,
        side=broker_snapshot_side,
        volume=broker_snapshot_volume,
        open_price=broker_snapshot_open_price,
        opened_utc="2026-07-16T12:00:00+00:00",
        source="BROKER",
    )


def main() -> int:
    connection = connect_runtime_db(":memory:")
    repository = RuntimeRepository(connection)
    account_id = "DUM513747"

    expected_position_uids = [
        _create_open_ib_position(
            repository,
            account_id=account_id,
            symbol_name="EURUSD",
            logical_side="BUY",
            logical_volume=1000.0,
            parent_order_id=111,
            broker_snapshot_side="BUY",
            broker_snapshot_volume=1000.0,
            broker_snapshot_open_price=1.14885,
        ),
        _create_open_ib_position(
            repository,
            account_id=account_id,
            symbol_name="EURUSD",
            logical_side="BUY",
            logical_volume=2000.0,
            parent_order_id=114,
            broker_snapshot_side="BUY",
            broker_snapshot_volume=3000.0,
            broker_snapshot_open_price=1.1473833333,
        ),
        _create_open_ib_position(
            repository,
            account_id=account_id,
            symbol_name="GBPUSD",
            logical_side="BUY",
            logical_volume=3000.0,
            parent_order_id=117,
            broker_snapshot_side="BUY",
            broker_snapshot_volume=3000.0,
            broker_snapshot_open_price=1.35225,
        ),
        _create_open_ib_position(
            repository,
            account_id=account_id,
            symbol_name="GBPUSD",
            logical_side="SELL",
            logical_volume=2000.0,
            parent_order_id=120,
            broker_snapshot_side="BUY",
            broker_snapshot_volume=1000.0,
            broker_snapshot_open_price=1.3529166667,
        ),
    ]

    seeds = repository.get_open_ib_virtual_position_leg_seeds(
        account_id=account_id,
    )
    legs = build_ib_virtual_position_legs_from_repository_seeds(seeds)

    if len(seeds) != 4:
        raise AssertionError(f"Expected 4 seeds, got {len(seeds)}")

    if [leg.position_uid for leg in legs] != expected_position_uids:
        raise AssertionError("position_uid order mismatch")

    if [leg.parent_order_id for leg in legs] != [111, 114, 117, 120]:
        raise AssertionError("parent order ids mismatch")

    logical_pairs = [
        (leg.symbol_name, leg.side, leg.volume)
        for leg in legs
    ]
    expected_pairs = [
        ("EURUSD", "BUY", 1000.0),
        ("EURUSD", "BUY", 2000.0),
        ("GBPUSD", "BUY", 3000.0),
        ("GBPUSD", "SELL", 2000.0),
    ]

    if logical_pairs != expected_pairs:
        raise AssertionError(f"Logical leg fields mismatch: {logical_pairs}")

    if any(leg.entry_price is not None for leg in legs):
        raise AssertionError("Unsafe broker net price leaked into leg seed")

    if any(leg.opened_utc for leg in legs):
        raise AssertionError("Unsafe broker net opened time leaked into leg seed")

    if seeds[1]["broker_snapshot_volume"] != 3000.0:
        raise AssertionError("EURUSD net snapshot fixture mismatch")

    if seeds[3]["broker_snapshot_side"] != "BUY":
        raise AssertionError("GBPUSD reverse net snapshot fixture mismatch")

    if legs[3].side != "SELL" or legs[3].volume != 2000.0:
        raise AssertionError("Trade logical SELL leg was not preserved")

    eurusd_signed = sum(
        leg.signed_volume
        for leg in legs
        if leg.symbol_name == "EURUSD"
    )
    gbpusd_signed = sum(
        leg.signed_volume
        for leg in legs
        if leg.symbol_name == "GBPUSD"
    )

    print("RuntimeRepository IB virtual-leg seed result")
    print(f"  seeds={len(seeds)}")
    print(f"  parent_order_ids={[leg.parent_order_id for leg in legs]}")
    print(f"  eurusd_signed={eurusd_signed}")
    print(f"  gbpusd_signed={gbpusd_signed}")
    print("  entry_prices_are_unreconciled=True")
    print("RUNTIME_REPOSITORY_IB_VIRTUAL_LEG_SEED_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
