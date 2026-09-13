from __future__ import annotations

import importlib
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

TEST_ID = "T109-42"
FACTUAL_VERDICT = "A. WORKSPACE_CONFIRMED_FLAT_PRODUCTION_EVALUATOR_GREEN"
FIRST_UNRESOLVED_BOUNDARY = (
    "WORKSPACE_CONTROLLER_CONFIRMED_FLAT_SOURCE_TO_AUTO_SUBMISSION_GATE"
)
BOUNDARY_CONTRACT = (
    "CONTROLLER_MAY_PASS_CONFIRMED_FLAT_TO_RUNTIME_SUBMIT_ONLY_FROM_"
    "PRODUCTION_EVALUATOR_USING_SUCCESSFUL_FRESH_EXACT_ACCOUNT_SYMBOL_"
    "SNAPSHOT_WITH_ZERO_MATCHING_EXPOSURE"
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

broker_position_module = importlib.import_module("engine.broker_position")
BrokerPosition = broker_position_module.BrokerPosition
BrokerPositionSnapshot = broker_position_module.BrokerPositionSnapshot
confirmed_flat = broker_position_module.broker_position_snapshot_confirms_flat


def _position(
    *,
    broker: str = "IB",
    account_id: str = "DU123",
    symbol_name: str = "EURUSD",
    volume: float = 3000.0,
) -> Any:
    return BrokerPosition(
        broker=broker,
        account_id=account_id,
        account_mode="PAPER",
        position_id="P1",
        symbol_name=symbol_name,
        side="SELL",
        volume=volume,
    )


def _snapshot_factory() -> Callable[..., Any]:
    return BrokerPositionSnapshot


def main() -> None:
    snapshot_type = _snapshot_factory()
    now_utc = datetime(2026, 9, 13, 18, 0, tzinfo=UTC)
    max_age = timedelta(seconds=5)

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
    naive_observed = snapshot_type(
        broker="IB",
        account_id="DU123",
        success=True,
        observed_at_utc=datetime(2026, 9, 13, 17, 59, 59),
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

    args = {
        "broker": "IB",
        "account_id": "DU123",
        "symbol": "EUR/USD",
        "now_utc": now_utc,
        "max_age": max_age,
    }
    assert confirmed_flat(fresh_empty, **args)
    assert not confirmed_flat(failed_empty, **args)
    assert not confirmed_flat(stale_empty, **args)
    assert not confirmed_flat(future_empty, **args)
    assert not confirmed_flat(naive_observed, **args)
    assert not confirmed_flat(open_exposure, **args)
    assert confirmed_flat(other_symbol, **args)
    assert not confirmed_flat(fresh_empty, **{**args, "account_id": "DU999"})
    assert not confirmed_flat(fresh_empty, **{**args, "broker": "CTRADER"})
    assert not confirmed_flat(
        fresh_empty,
        **{**args, "now_utc": datetime(2026, 9, 13, 18, 0)},
    )
    assert not confirmed_flat(
        fresh_empty,
        **{**args, "max_age": timedelta(0)},
    )

    print(f"{TEST_ID}_WORKSPACE_CONFIRMED_FLAT_PRODUCTION_EVALUATOR=OK")
    print("production_change=True")
    print("production_evaluator_present=True")
    print("exact_broker_account_binding_enforced=True")
    print("symbol_scope_matching_enforced=True")
    print("fresh_successful_zero_exposure_means_confirmed_flat=True")
    print("other_symbol_exposure_does_not_block_symbol_flat=True")
    print("failed_snapshot_blocks=True")
    print("stale_snapshot_blocks=True")
    print("future_timestamp_blocks=True")
    print("naive_timestamp_blocks=True")
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
