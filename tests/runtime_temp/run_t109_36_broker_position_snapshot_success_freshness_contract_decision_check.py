from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

TEST_ID = "T109-36"
FACTUAL_VERDICT = "A. BROKER_POSITION_SNAPSHOT_SUCCESS_FRESHNESS_CONTRACT_IDENTIFIED"
FIRST_UNRESOLVED_BOUNDARY = "BROKER_POSITION_SNAPSHOT_RESULT_TYPE_AND_ADAPTER_MAPPING"
BOUNDARY_CONTRACT = (
    "CONFIRMED_FLAT_REQUIRES_SUCCESSFUL_FRESH_EXACT_ACCOUNT_SNAPSHOT_WITH_ZERO_"
    "MATCHING_EXPOSURE_WHILE_FAILURE_TIMEOUT_DISCONNECT_STALE_OR_SCOPE_MISMATCH_BLOCKS"
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ENGINE = PROJECT_ROOT / "engine" / "runtime_engine.py"
IB_ADAPTER = PROJECT_ROOT / "engine" / "ib_adapter.py"
CTRADER_ADAPTER = PROJECT_ROOT / "engine" / "ctrader_adapter.py"


@dataclass(frozen=True, slots=True)
class _Snapshot:
    broker: str
    account_id: str
    success: bool
    observed_at_utc: datetime | None
    positions: tuple[dict[str, object], ...]
    failure_reason: str | None = None


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalize_symbol(value: str) -> str:
    return value.replace("/", "").replace(".", "").strip().upper()


def _matching_exposure(
    snapshot: _Snapshot,
    *,
    broker: str,
    account_id: str,
    symbol: str,
) -> list[dict[str, object]]:
    broker_norm = broker.strip().upper()
    account_norm = account_id.strip().upper()
    symbol_norm = _normalize_symbol(symbol)
    return [
        position
        for position in snapshot.positions
        if str(position["broker"]).strip().upper() == broker_norm
        and str(position["account_id"]).strip().upper() == account_norm
        and _normalize_symbol(str(position["symbol_name"])) == symbol_norm
        and abs(float(str(position["volume"]))) > 0.0
    ]


def _confirmed_flat(
    snapshot: _Snapshot,
    *,
    broker: str,
    account_id: str,
    symbol: str,
    now_utc: datetime,
    max_age: timedelta,
) -> bool:
    if not snapshot.success:
        return False
    if snapshot.observed_at_utc is None:
        return False
    if snapshot.observed_at_utc.tzinfo is None:
        return False
    if snapshot.broker.strip().upper() != broker.strip().upper():
        return False
    if snapshot.account_id.strip().upper() != account_id.strip().upper():
        return False
    age = now_utc - snapshot.observed_at_utc.astimezone(UTC)
    if age < timedelta(0) or age > max_age:
        return False
    return not _matching_exposure(
        snapshot,
        broker=broker,
        account_id=account_id,
        symbol=symbol,
    )


def main() -> None:
    runtime_source = _read(RUNTIME_ENGINE)
    ib_source = _read(IB_ADAPTER)
    ctrader_source = _read(CTRADER_ADAPTER)

    assert "def get_active_broker_positions" in runtime_source
    assert "return service.get_positions()" in runtime_source
    assert "positions = service.get_positions()" in runtime_source

    assert "if not self._connected:" in ib_source
    assert "return []" in ib_source
    assert "IB positions timeout." in ib_source

    assert "if not self.is_connected():" in ctrader_source
    assert "return []" in ctrader_source
    assert "cTrader reconcile timeout." in ctrader_source

    now = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
    test_max_age = timedelta(seconds=5)

    fresh_empty = _Snapshot(
        broker="IB",
        account_id="DU123",
        success=True,
        observed_at_utc=now - timedelta(seconds=1),
        positions=(),
    )
    failed_empty = _Snapshot(
        broker="IB",
        account_id="DU123",
        success=False,
        observed_at_utc=None,
        positions=(),
        failure_reason="TIMEOUT",
    )
    stale_empty = _Snapshot(
        broker="IB",
        account_id="DU123",
        success=True,
        observed_at_utc=now - timedelta(seconds=10),
        positions=(),
    )
    fresh_opposite = _Snapshot(
        broker="IB",
        account_id="DU123",
        success=True,
        observed_at_utc=now - timedelta(seconds=1),
        positions=(
            {
                "broker": "IB",
                "account_id": "DU123",
                "symbol_name": "EURUSD",
                "side": "SELL",
                "volume": 3000.0,
            },
        ),
    )

    assert _confirmed_flat(
        fresh_empty,
        broker="IB",
        account_id="DU123",
        symbol="EUR/USD",
        now_utc=now,
        max_age=test_max_age,
    )
    assert not _confirmed_flat(
        failed_empty,
        broker="IB",
        account_id="DU123",
        symbol="EUR/USD",
        now_utc=now,
        max_age=test_max_age,
    )
    assert not _confirmed_flat(
        stale_empty,
        broker="IB",
        account_id="DU123",
        symbol="EUR/USD",
        now_utc=now,
        max_age=test_max_age,
    )
    assert not _confirmed_flat(
        fresh_opposite,
        broker="IB",
        account_id="DU123",
        symbol="EUR/USD",
        now_utc=now,
        max_age=test_max_age,
    )
    assert not _confirmed_flat(
        fresh_empty,
        broker="IB",
        account_id="DU999",
        symbol="EUR/USD",
        now_utc=now,
        max_age=test_max_age,
    )

    print(f"{TEST_ID}_BROKER_POSITION_SNAPSHOT_SUCCESS_FRESHNESS_CONTRACT_DECISION=OK")
    print("test_scope=TEST_ONLY")
    print("production_change=False")
    print("current_runtime_position_api_returns_bare_list=True")
    print("current_snapshot_success_metadata_present=False")
    print("current_snapshot_observed_at_metadata_present=False")
    print("current_failure_reason_metadata_present=False")
    recommended_fields = ",".join(
        [
            "broker",
            "account_id",
            "success",
            "observed_at_utc",
            "positions",
            "failure_reason",
        ]
    )
    print(f"recommended_snapshot_fields={recommended_fields}")
    print("freshness_policy_required=True")
    print("production_freshness_ttl_value_decided=False")
    print("exact_broker_account_binding_required=True")
    print("fresh_successful_zero_exposure_means_confirmed_flat=True")
    print("failed_empty_snapshot_blocks=True")
    print("stale_empty_snapshot_blocks=True")
    print("scope_mismatch_blocks=True")
    print("matching_open_exposure_blocks_confirmed_flat=True")
    print("timeout_disconnect_request_failure_blocks=True")
    print("broker_requests=0")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


if __name__ == "__main__":
    main()
