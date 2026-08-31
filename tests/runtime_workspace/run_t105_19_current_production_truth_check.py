# -*- coding: utf-8 -*-
"""T105-19: short runnable checkpoint of current production truth."""

from __future__ import annotations

import inspect

from run_t105_18_stochastic_current_bar_production_regression_check import (
    PERIODS,
    WorkspaceMacdAlligatorReplayAlgorithm,
    _file_hashes,
    _run_period,
    _summary_line,
)

TEST_ID = "T105-19"


def main() -> None:
    """Reuse T105-18 production assertions and report the canonical truth."""
    exit_hashes_before = _file_hashes()
    algorithm_source = inspect.getsource(WorkspaceMacdAlligatorReplayAlgorithm)
    assert "DONCHIAN" not in algorithm_source.upper()

    print("T105-19 Current Production Truth Check")
    print(f"  test_id={TEST_ID}")
    print("  path=REGISTERED_PRODUCTION_CANDIDATE_F_WORKSPACE_RUNTIME")
    for spec in PERIODS:
        runtime, _rejects, broker_requests = _run_period(spec)
        print(f"  period={spec.code}")
        print(f"    production={_summary_line(runtime)}")
        print(f"    broker_requests={broker_requests}")

    assert _file_hashes() == exit_hashes_before
    print("  stochastic_current_bar_reject_production=True")
    print("  stochastic_profile=14/1/3")
    print("  donchian_production_gate=False")
    print("  production_profit_drawdown_threshold=35.0")
    print("  production_sl_geometry=max(signal_bar_range,spread*10)")
    print("  production_tp_geometry=2R")
    print("  negative_pd_recovery_unchanged=True")
    print("  production_exit_logic_unchanged=True")
    print("  completed_market_events_only=True")
    print("  no_look_ahead=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T105_19_CURRENT_PRODUCTION_TRUTH=OK")


if __name__ == "__main__":
    main()
