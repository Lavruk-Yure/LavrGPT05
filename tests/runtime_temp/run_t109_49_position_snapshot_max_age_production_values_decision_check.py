"""T109-49 — рішення щодо freshness production position snapshot. TEST_ONLY."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENGINE_DIR = PROJECT_ROOT / "engine"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> None:
    ib_text = _read(ENGINE_DIR / "ib_adapter.py")
    ctrader_text = _read(ENGINE_DIR / "ctrader_adapter.py")
    position_text = _read(ENGINE_DIR / "broker_position.py")
    runtime_text = _read(ENGINE_DIR / "runtime_engine.py")
    policy_text = _read(ENGINE_DIR / "runtime_execution_safety_policy.py")
    constants_text = _read(ENGINE_DIR / "runtime_constants.py")

    ib_snapshot_is_synchronous = (
        "def get_positions_snapshot" in ib_text
        and "self._client.reqPositions()" in ib_text
        and "position_event.wait" in ib_text
        and "BrokerPositionSnapshot.success_result" in ib_text
    )
    ctrader_snapshot_is_synchronous = (
        "def get_positions_snapshot" in ctrader_text
        and "positions = self.get_positions()" in ctrader_text
        and "BrokerPositionSnapshot.success_result" in ctrader_text
    )
    terminal_outcome_stamps_observed_at = (
        "observed_at_utc=datetime.now(UTC)" in position_text
    )
    named_route_returns_direct_snapshot = (
        "def get_workspace_broker_positions_snapshot" in runtime_text
        and "snapshot = service.get_positions_snapshot()" in runtime_text
    )
    request_timeouts_present = (
        "IB_POSITIONS_TIMEOUT_SECONDS" in constants_text
        and "CTRADER_POSITIONS_TIMEOUT_SECONDS" in constants_text
    )
    request_timeout_is_not_snapshot_age = (
        request_timeouts_present and terminal_outcome_stamps_observed_at
    )
    policy_source_present = (
        "class RuntimeExecutionSafetyPolicy" in policy_text
        and "position_snapshot_max_age_by_broker" in policy_text
    )
    production_policy_values_configured = (
        '"IB": timedelta(' in runtime_text
        or '"CTRADER": timedelta(' in runtime_text
        or "'IB': timedelta(" in runtime_text
        or "'CTRADER': timedelta(" in runtime_text
    )
    broker_specific_empirical_ttl_source_present = any(
        marker in (ib_text + ctrader_text + runtime_text + policy_text)
        for marker in (
            "position_snapshot_latency_p95",
            "position_snapshot_latency_p99",
            "measured_position_snapshot_max_age",
        )
    )

    same_call_contract_supported = all(
        (
            ib_snapshot_is_synchronous,
            ctrader_snapshot_is_synchronous,
            terminal_outcome_stamps_observed_at,
            named_route_returns_direct_snapshot,
        )
    )
    numeric_ttl_factually_justified = (
        production_policy_values_configured
        or broker_specific_empirical_ttl_source_present
    )

    assert policy_source_present
    assert same_call_contract_supported
    assert request_timeout_is_not_snapshot_age
    assert not numeric_ttl_factually_justified

    print("T109-49_POSITION_SNAPSHOT_MAX_AGE_PRODUCTION_VALUES_DECISION=OK")
    print("test_scope=TEST_ONLY")
    print("production_change=False")
    print(f"ib_snapshot_is_synchronous={ib_snapshot_is_synchronous}")
    print(f"ctrader_snapshot_is_synchronous={ctrader_snapshot_is_synchronous}")
    print(
        "terminal_outcome_stamps_observed_at="
        f"{terminal_outcome_stamps_observed_at}"
    )
    print(f"named_route_returns_direct_snapshot={named_route_returns_direct_snapshot}")
    print(f"request_timeouts_present={request_timeouts_present}")
    print(
        "request_timeout_is_position_snapshot_freshness_policy="
        f"{not request_timeout_is_not_snapshot_age}"
    )
    print(f"policy_source_present={policy_source_present}")
    print(
        "production_policy_values_configured="
        f"{production_policy_values_configured}"
    )
    print(
        "broker_specific_empirical_ttl_source_present="
        f"{broker_specific_empirical_ttl_source_present}"
    )
    print(f"numeric_ttl_factually_justified={numeric_ttl_factually_justified}")
    print(f"same_call_freshness_contract_supported={same_call_contract_supported}")
    print("recommended_freshness_contract=SAME_CALL_TERMINAL_SNAPSHOT_ONLY")
    print("snapshot_reuse_across_submission_attempts=False")
    print("broker_specific_numeric_ttl_required=False")
    print("missing_same_call_snapshot_behavior=BLOCK")
    print("workspace_controller_submission_wiring=False")
    print("broker_requests=0")
    print(
        "first_unresolved_boundary="
        "WORKSPACE_SAME_CALL_FRESHNESS_PRODUCTION_CONTRACT_WIRING"
    )
    print(
        "boundary_contract=CONTROLLER_MUST_ACQUIRE_A_NEW_TERMINAL_POSITION_"
        "SNAPSHOT_IN_THE_SAME_AUTO_SUBMISSION_GATE_CALL_AND_MUST_NOT_REUSE_"
        "CACHED_SNAPSHOT_ACROSS_SUBMISSION_ATTEMPTS"
    )
    print(
        "factual_verdict=A. SAME_CALL_FRESHNESS_CONTRACT_PREFERRED_OVER_"
        "UNGROUNDED_NUMERIC_TTL"
    )


if __name__ == "__main__":
    main()
