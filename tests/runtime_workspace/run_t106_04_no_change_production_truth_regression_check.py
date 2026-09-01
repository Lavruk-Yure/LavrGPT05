"""run_t106_04_no_change_production_truth_regression_check.py — T106-04.

Фінальний TEST_ONLY checkpoint RoadMap106 повторно запускає registered
current-production Candidate F runtime на канонічних періодах 2025 і 2026.
Runner використовує готові production regression assertions T105-18 для
Candidate F, Alligator, Stochastic 14/1/3 CURRENT_BAR reject, factual metrics,
SL/TP geometry, PD 35%, negative-PD recovery, completed M15 events і broker
safety; production алгоритм або його правила тут не дублюються.

Додатковий wiring audit підтверджує відсутність Donchian production gate і
Supertrend execution wiring. Hashes усіх Python production files у core/engine
та strings.json порівнюються до і після Replay. Вихід фіксує фінальне рішення
RoadMap106 VARIANT_C_NO_CHANGE, але не створює candidate, threshold, entry/exit
rule, не змінює MD7 і не торкається production logic.
"""

from __future__ import annotations

import inspect

from run_t105_15_stochastic_entry_anatomy_check import _production_hashes
from run_t105_18_stochastic_current_bar_production_regression_check import (
    BASELINE_POPULATION,
    EXPECTED_REJECTS,
    PERIODS,
    _run_period,
    _summary_line,
)

import core.workspace_replay_execution as replay_execution
from core.workspace_alligator import WorkspaceMacdAlligatorReplayAlgorithm
from core.workspace_replay_execution import (
    REPLAY_CLOSE_PROFIT_DRAWDOWN,
    REPLAY_CLOSE_REASONS,
    REPLAY_CLOSE_SESSION_END,
    REPLAY_CLOSE_STOP_LOSS,
    REPLAY_CLOSE_TAKE_PROFIT,
    WorkspaceReplayExecutionEngine,
)
from core.workspace_runtime import WorkspaceRuntime

TEST_ID = "T106-04"
MODE = "RM106_T106_04_NO_CHANGE_PRODUCTION_TRUTH_REGRESSION_TEST_ONLY"


def _assert_absent_optional_production_wiring() -> None:
    """Підтвердити відсутність Donchian gate і Supertrend execution wiring."""

    algorithm_source = inspect.getsource(WorkspaceMacdAlligatorReplayAlgorithm).upper()
    assert "DONCHIAN" not in algorithm_source

    expected_close_reasons = (
        REPLAY_CLOSE_STOP_LOSS,
        REPLAY_CLOSE_TAKE_PROFIT,
        REPLAY_CLOSE_PROFIT_DRAWDOWN,
        REPLAY_CLOSE_SESSION_END,
    )
    assert REPLAY_CLOSE_REASONS == expected_close_reasons
    removed_execution_symbols = (
        "REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH",
        "SELL_SUPERTREND_TIMEFRAME",
        "SELL_SUPERTREND_ATR_LENGTH",
        "SELL_SUPERTREND_FACTOR",
        "SELL_SUPERTREND_SOURCE",
        "SELL_SUPERTREND_ATR_SMOOTHING",
        "WorkspaceSupertrendObservation",
        "WorkspaceCanonicalSupertrend",
    )
    assert all(
        not hasattr(replay_execution, symbol) for symbol in removed_execution_symbols
    )
    assert not hasattr(WorkspaceReplayExecutionEngine, "on_completed_m15_bar")
    assert not hasattr(WorkspaceRuntime, "_apply_replay_sell_supertrend_exit")
    execution_source = inspect.getsource(WorkspaceReplayExecutionEngine).upper()
    runtime_source = inspect.getsource(WorkspaceRuntime).upper()
    assert "SUPERTREND" not in execution_source
    assert "SUPERTREND" not in runtime_source


def main() -> None:
    """Запустити no-change production truth regression RoadMap106."""

    production_before = _production_hashes()
    _assert_absent_optional_production_wiring()

    print("T106-04 No-Change Production Truth Regression")
    print(f"  test_id={TEST_ID}")
    print(f"  mode={MODE}")
    print("  path=REGISTERED_CURRENT_PRODUCTION_CANDIDATE_F_RUNTIME")
    print("  production_algorithm=Candidate_F")
    print("  production_alligator_logic=current_registered_production")
    for spec in PERIODS:
        runtime, rejects, broker_requests = _run_period(spec)
        assert rejects == EXPECTED_REJECTS[spec.code]
        print(f"  period={spec.code}")
        print(f"    production={_summary_line(runtime)}")
        print(
            f"    stochastic_current_bar_rejects={rejects},"
            f"factual_population={BASELINE_POPULATION[spec.code]}"
        )
        print(f"    broker_requests={broker_requests}")

    _assert_absent_optional_production_wiring()
    assert _production_hashes() == production_before
    print("  roadmap106_decision=VARIANT_C_NO_CHANGE")
    print("  entry_problem_anatomy_confirmed=True")
    print("  stable_causal_entry_discriminator_found=False")
    print("  exit_problem_supported=False")
    print("  new_candidate_rule_created=False")
    print("  production_change_required=False")
    print("  production_stochastic_current_bar_reject_active=True")
    print("  production_stochastic_profile=14/1/3")
    print("  production_profit_drawdown_threshold=35.0")
    print("  production_sl_geometry=max(signal_bar_range,spread*10)")
    print("  production_tp_geometry=2R")
    print("  negative_pd_recovery_production_state_machine=True")
    print("  donchian_production_gate=False")
    print("  supertrend_production_wiring=False")
    print("  completed_market_events_only=True")
    print("  no_look_ahead=True")
    print("  deterministic_replay=True")
    print("  production_logic_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T106_04_NO_CHANGE_PRODUCTION_TRUTH_REGRESSION=OK")


if __name__ == "__main__":
    main()
