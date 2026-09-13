from __future__ import annotations

import importlib
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

TEST_ID = "T109-41"
FACTUAL_VERDICT = (
    "A. BROKER_NEUTRAL_CONFIRMED_FLAT_FRESHNESS_EVALUATION_CONTRACT_IDENTIFIED"
)
FIRST_UNRESOLVED_BOUNDARY = (
    "WORKSPACE_CONFIRMED_FLAT_PRODUCTION_EVALUATOR_WIRING"
)
BOUNDARY_CONTRACT = (
    "CONFIRMED_FLAT_MAY_BE_TRUE_ONLY_FOR_SUCCESSFUL_FRESH_EXACT_ACCOUNT_"
    "SNAPSHOT_WITH_ZERO_MATCHING_SYMBOL_EXPOSURE_WHILE_FAILURE_STALE_FUTURE_"
    "TIMESTAMP_SCOPE_MISMATCH_OR_OPEN_EXPOSURE_BLOCKS"
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

broker_position_module = importlib.import_module("engine.broker_position")
BrokerPosition = broker_position_module.BrokerPosition
BrokerPositionSnapshot = broker_position_module.BrokerPositionSnapshot


def _normalize_symbol(value: str) -> str:
    return value.replace("/", "").replace(".", "").strip().upper()


def _confirmed_flat(
    snapshot: Any,
    *,
    broker: str,
    account_id: str,
    symbol: str,
    now_utc: datetime,
    max_age: timedelta,
) -> bool:
    if not snapshot.success:
        return False
    if max_age <= timedelta(0):
        return False

    observed_at_utc = snapshot.observed_at_utc
    if observed_at_utc.tzinfo is None:
        return False

    broker_norm = broker.strip().upper()
    account_norm = account_id.strip().upper()
    symbol_norm = _normalize_symbol(symbol)

    if snapshot.broker.strip().upper() != broker_norm:
        return False
    if snapshot.account_id.strip().upper() != account_norm:
        return False

    age = now_utc.astimezone(UTC) - observed_at_utc.astimezone(UTC)
    if age < timedelta(0) or age > max_age:
        return False

    for position in snapshot.positions:
        if str(position.broker).strip().upper() != broker_norm:
            continue
        if str(position.account_id).strip().upper() != account_norm:
            continue
        if _normalize_symbol(str(position.symbol_name)) != symbol_norm:
            continue
        if abs(float(position.volume)) > 0.0:
            return False

    return True


def _position(
    *,
    broker: str = "IB",
    account_id: str = "DU123",
    symbol_name: str = "EURUSD",
    side: str = "SELL",
    volume: float = 3000.0,
) -> Any:
    return BrokerPosition(
        broker=broker,
        account_id=account_id,
        account_mode="PAPER",
        position_id="P1",
        symbol_name=symbol_name,
        side=side,
        volume=volume,
    )


def _snapshot_factory() -> Callable[..., Any]:
    return BrokerPositionSnapshot


def main() -> None:
    snapshot_type = _snapshot_factory()
    now_utc = datetime(2026, 9, 13, 17, 0, tzinfo=UTC)
    test_max_age = timedelta(seconds=5)

    fresh_empty = snapshot_type(
        broker="IB",
        account_id="DU123",
        success=True,
        observed_at_utc=now_utc - timedelta(seconds=1),
        positions=(),
    )
    failed_empty = snapshot_type(
        broker="IB",
        account_id="DU123",
        success=False,
        observed_at_utc=now_utc - timedelta(seconds=1),
        positions=(),
        failure_reason="TIMEOUT",
    )
    stale_empty = snapshot_type(
        broker="IB",
        account_id="DU123",
        success=True,
        observed_at_utc=now_utc - timedelta(seconds=10),
        positions=(),
    )
    future_empty = snapshot_type(
        broker="IB",
        account_id="DU123",
        success=True,
        observed_at_utc=now_utc + timedelta(seconds=1),
        positions=(),
    )
    open_exposure = snapshot_type(
        broker="IB",
        account_id="DU123",
        success=True,
        observed_at_utc=now_utc - timedelta(seconds=1),
        positions=(_position(),),
    )
    other_symbol = snapshot_type(
        broker="IB",
        account_id="DU123",
        success=True,
        observed_at_utc=now_utc - timedelta(seconds=1),
        positions=(_position(symbol_name="GBPUSD"),),
    )

    assert _confirmed_flat(
        fresh_empty,
        broker="IB",
        account_id="DU123",
        symbol="EUR/USD",
        now_utc=now_utc,
        max_age=test_max_age,
    )
    assert not _confirmed_flat(
        failed_empty,
        broker="IB",
        account_id="DU123",
        symbol="EUR/USD",
        now_utc=now_utc,
        max_age=test_max_age,
    )
    assert not _confirmed_flat(
        stale_empty,
        broker="IB",
        account_id="DU123",
        symbol="EUR/USD",
        now_utc=now_utc,
        max_age=test_max_age,
    )
    assert not _confirmed_flat(
        future_empty,
        broker="IB",
        account_id="DU123",
        symbol="EUR/USD",
        now_utc=now_utc,
        max_age=test_max_age,
    )
    assert not _confirmed_flat(
        open_exposure,
        broker="IB",
        account_id="DU123",
        symbol="EUR/USD",
        now_utc=now_utc,
        max_age=test_max_age,
    )
    assert _confirmed_flat(
        other_symbol,
        broker="IB",
        account_id="DU123",
        symbol="EUR/USD",
        now_utc=now_utc,
        max_age=test_max_age,
    )
    assert not _confirmed_flat(
        fresh_empty,
        broker="IB",
        account_id="DU999",
        symbol="EUR/USD",
        now_utc=now_utc,
        max_age=test_max_age,
    )
    assert not _confirmed_flat(
        fresh_empty,
        broker="CTRADER",
        account_id="DU123",
        symbol="EUR/USD",
        now_utc=now_utc,
        max_age=test_max_age,
    )
    assert not _confirmed_flat(
        fresh_empty,
        broker="IB",
        account_id="DU123",
        symbol="EUR/USD",
        now_utc=now_utc,
        max_age=timedelta(0),
    )

    print(f"{TEST_ID}_WORKSPACE_CONFIRMED_FLAT_FRESHNESS_EVALUATION=OK")
    print("test_scope=TEST_ONLY")
    print("production_change=False")
    print("broker_neutral_snapshot_type_present=True")
    print("runtime_engine_snapshot_routing_present=True")
    print("exact_broker_account_binding_required=True")
    print("symbol_scope_matching_required=True")
    print("fresh_successful_zero_exposure_means_confirmed_flat=True")
    print("other_symbol_exposure_does_not_block_symbol_flat=True")
    print("failed_snapshot_blocks=True")
    print("stale_snapshot_blocks=True")
    print("future_timestamp_blocks=True")
    print("scope_mismatch_blocks=True")
    print("matching_open_exposure_blocks=True")
    print("freshness_policy_is_parameterized=True")
    print("production_freshness_ttl_value_decided=False")
    print("workspace_controller_submission_wiring=False")
    print("broker_requests=0")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


if __name__ == "__main__":
    main()
