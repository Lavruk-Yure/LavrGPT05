"""T109-37: broker position snapshot result type / adapter mapping anatomy."""

from __future__ import annotations

from pathlib import Path

TEST_ID = "T109-37"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

BROKER_POSITION = PROJECT_ROOT / "engine" / "broker_position.py"
RUNTIME_ENGINE = PROJECT_ROOT / "engine" / "runtime_engine.py"
IB_ADAPTER = PROJECT_ROOT / "engine" / "ib_adapter.py"
CTRADER_ADAPTER = PROJECT_ROOT / "engine" / "ctrader_adapter.py"
IB_SERVICE = PROJECT_ROOT / "engine" / "services" / "ib_runtime_service.py"
CTRADER_SERVICE = PROJECT_ROOT / "engine" / "services" / "ctrader_runtime_service.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> None:
    broker_position_source = _read(BROKER_POSITION)
    runtime_source = _read(RUNTIME_ENGINE)
    ib_source = _read(IB_ADAPTER)
    ctrader_source = _read(CTRADER_ADAPTER)
    ib_service_source = _read(IB_SERVICE)
    ctrader_service_source = _read(CTRADER_SERVICE)

    snapshot_type_present = "BrokerPositionSnapshot" in broker_position_source
    runtime_returns_bare_list = (
        "def get_active_broker_positions(self) -> list:" in runtime_source
        and "return service.get_positions()" in runtime_source
    )
    services_return_bare_list = (
        "def get_positions(self) -> list:" in ib_service_source
        and "return adapter.get_positions()" in ib_service_source
        and "def get_positions(self):" in ctrader_service_source
        and "return adapter.get_positions()" in ctrader_service_source
    )

    ib_disconnected_collapses_to_empty = (
        "IB get_positions called while disconnected." in ib_source
        and "return []" in ib_source
    )
    ib_timeout_collapses_to_empty = (
        "IB positions timeout." in ib_source
        and "if not finished:" in ib_source
    )
    ib_success_end_marker_present = (
        "def positionEnd(self)" in ib_source
        and "self.position_event.set()" in ib_source
    )

    ctrader_disconnected_collapses_to_empty = (
        "cTrader get_positions called while disconnected." in ctrader_source
        and "return []" in ctrader_source
    )
    ctrader_timeout_collapses_to_empty = (
        "cTrader reconcile timeout." in ctrader_source
        and "if not finished:" in ctrader_source
    )
    ctrader_success_end_marker_present = (
        "def _on_reconcile_res" in ctrader_source
        and "self._positions_event.set()" in ctrader_source
    )
    ctrader_error_sets_same_event = (
        "def _on_positions_deferred_error" in ctrader_source
        and "self._positions_event.set()" in ctrader_source
    )
    ctrader_error_state_flag_present = any(
        marker in ctrader_source
        for marker in (
            "_positions_error =",
            "_positions_failure =",
            "_positions_request_error =",
        )
    )

    assert not snapshot_type_present
    assert runtime_returns_bare_list
    assert services_return_bare_list
    assert ib_disconnected_collapses_to_empty
    assert ib_timeout_collapses_to_empty
    assert ib_success_end_marker_present
    assert ctrader_disconnected_collapses_to_empty
    assert ctrader_timeout_collapses_to_empty
    assert ctrader_success_end_marker_present
    assert ctrader_error_sets_same_event
    assert not ctrader_error_state_flag_present

    print(f"{TEST_ID}_BROKER_POSITION_SNAPSHOT_RESULT_TYPE_ADAPTER_MAPPING_ANATOMY=OK")
    print("test_scope=TEST_ONLY")
    print("production_change=False")
    print(f"broker_position_snapshot_type_present={snapshot_type_present}")
    print(f"runtime_position_api_returns_bare_list={runtime_returns_bare_list}")
    print(f"runtime_services_return_bare_list={services_return_bare_list}")
    print("recommended_result_type_owner=engine.broker_position")
    print("recommended_mapping_owner=broker_adapter_get_positions_snapshot")
    print("ib_success_mapping_feasible=True")
    print("ib_success_marker=positionEnd")
    print("ib_disconnected_mapping_feasible=True")
    print("ib_timeout_mapping_feasible=True")
    print("ctrader_success_mapping_feasible=True")
    print("ctrader_success_marker=ProtoOAReconcileRes")
    print("ctrader_disconnected_mapping_feasible=True")
    print("ctrader_timeout_mapping_feasible=True")
    print("ctrader_request_error_mapping_unambiguous=False")
    print("ctrader_error_sets_same_completion_event=True")
    print("ctrader_request_error_state_flag_present=False")
    print("observed_at_can_be_captured_at_terminal_outcome=True")
    print("freshness_ttl_value_decided=False")
    print("broker_requests=0")
    print("first_unresolved_boundary=CTRADER_POSITION_REQUEST_OUTCOME_STATE")
    print(
        "boundary_contract=CTRADER_POSITION_RECONCILE_MUST_DISTINGUISH_SUCCESS_"
        "FROM_DEFERRED_ERROR_BEFORE_BROKER_NEUTRAL_SNAPSHOT_CAN_MARK_EMPTY_AS_SUCCESS"
    )
    print(
        "factual_verdict=B. RESULT_TYPE_FEASIBLE_BUT_CTRADER_ERROR_OUTCOME_IS_CONFLATED"
    )


if __name__ == "__main__":
    main()
