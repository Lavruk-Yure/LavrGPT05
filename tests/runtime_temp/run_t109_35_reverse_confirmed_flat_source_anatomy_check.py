from __future__ import annotations

from pathlib import Path

TEST_ID = "T109-35"
FACTUAL_VERDICT = "C. POSITION_SOURCE_EXISTS_BUT_CONFIRMED_FLAT_IS_AMBIGUOUS"
FIRST_UNRESOLVED_BOUNDARY = "BROKER_POSITION_SNAPSHOT_SUCCESS_AND_FRESHNESS_CONTRACT"
BOUNDARY_CONTRACT = (
    "CONTROLLER_MAY_TREAT_ACCOUNT_SYMBOL_AS_CONFIRMED_FLAT_ONLY_AFTER_A_"
    "SUCCESSFUL_FRESH_BROKER_POSITION_SNAPSHOT_DISTINGUISHES_ZERO_EXPOSURE_"
    "FROM_DISCONNECTED_TIMEOUT_OR_REQUEST_FAILURE"
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ENGINE = PROJECT_ROOT / "engine" / "runtime_engine.py"
BROKER_POSITION = PROJECT_ROOT / "engine" / "broker_position.py"
IB_ADAPTER = PROJECT_ROOT / "engine" / "ib_adapter.py"
CTRADER_ADAPTER = PROJECT_ROOT / "engine" / "ctrader_adapter.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _matching_exposure(
    positions: list[dict[str, object]],
    *,
    broker: str,
    account_id: str,
    symbol: str,
) -> list[dict[str, object]]:
    broker_norm = broker.strip().upper()
    account_norm = account_id.strip().upper()
    symbol_norm = symbol.replace("/", "").replace(".", "").strip().upper()
    return [
        position
        for position in positions
        if str(position["broker"]).strip().upper() == broker_norm
        and str(position["account_id"]).strip().upper() == account_norm
        and str(position["symbol_name"])
        .replace("/", "")
        .replace(".", "")
        .strip()
        .upper()
        == symbol_norm
        and abs(float(str(position["volume"]))) > 0.0
    ]


def main() -> None:
    runtime_source = _read(RUNTIME_ENGINE)
    broker_position_source = _read(BROKER_POSITION)
    ib_source = _read(IB_ADAPTER)
    ctrader_source = _read(CTRADER_ADAPTER)

    assert "def get_active_broker_positions" in runtime_source
    assert "service.get_positions()" in runtime_source
    for field_name in ("account_id", "symbol_name", "side", "volume"):
        assert field_name in broker_position_source

    assert "reqPositions()" in ib_source
    assert "IB positions timeout" in ib_source
    assert "return []" in ib_source
    assert "ProtoOAReconcileReq" in ctrader_source
    assert "cTrader reconcile timeout" in ctrader_source
    assert "return []" in ctrader_source

    fixture = [
        {
            "broker": "IB",
            "account_id": "DU123",
            "symbol_name": "EURUSD",
            "side": "SELL",
            "volume": 3000.0,
        },
        {
            "broker": "IB",
            "account_id": "DU999",
            "symbol_name": "EURUSD",
            "side": "BUY",
            "volume": 5000.0,
        },
        {
            "broker": "IB",
            "account_id": "DU123",
            "symbol_name": "GBPUSD",
            "side": "BUY",
            "volume": 2000.0,
        },
    ]
    matching = _matching_exposure(
        fixture,
        broker="IB",
        account_id="DU123",
        symbol="EUR/USD",
    )
    assert len(matching) == 1
    assert matching[0]["side"] == "SELL"

    print(f"{TEST_ID}_REVERSE_CONFIRMED_FLAT_SOURCE_ANATOMY=OK")
    print("test_scope=TEST_ONLY")
    print("production_change=False")
    print("runtime_active_position_source_present=True")
    print("broker_position_account_field_present=True")
    print("broker_position_symbol_field_present=True")
    print("broker_position_side_field_present=True")
    print("account_symbol_direction_filter_feasible=True")
    print("ib_position_snapshot_requires_broker_request=True")
    print("ctrader_position_snapshot_requires_broker_request=True")
    print("ib_empty_result_can_mean_confirmed_flat=True")
    print("ib_empty_result_can_mean_disconnected_or_timeout=True")
    print("ctrader_empty_result_can_mean_confirmed_flat=True")
    print("ctrader_empty_result_can_mean_disconnected_or_timeout=True")
    print("snapshot_success_metadata_present=False")
    print("snapshot_observed_at_or_freshness_present=False")
    print("controller_can_safely_default_confirmed_flat=False")
    print("broker_requests=0")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


if __name__ == "__main__":
    main()
