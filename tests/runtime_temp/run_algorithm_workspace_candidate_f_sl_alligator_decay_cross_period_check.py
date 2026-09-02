# -*- coding: utf-8 -*-
"""RoadMap103 / 7F: causal Alligator-decay anatomy для production SL.

Diagnostic-only runner повторює production Candidate F після 6K для frozen
2025 та трьох відомих вікон 2026. Для кожної фактично відкритої угоди він
бере лише Alligator evidence, уже доступний на завершеному M15 signal bar:
normalized opening/slope для t-2, t-1, t, їх зміни та monotonic deterioration.

Мета — перевірити, чи помірне згасання Alligator перед входом є спільною
ознакою STOP_LOSS у 2025 і 2026, не вводячи нового gate та не змінюючи SL/TP,
Candidate F profile або 6K exit recovery. Future price як feature не
використовується; PnL потрібен тільки для post-trade групування результатів.
"""

from __future__ import annotations

import math
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, TEST_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_indicator_profile import (  # noqa: E402
    ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F,
    WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY,
    WorkspaceIndicatorProfileBinding,
    built_in_workspace_indicator_profile,
    new_workspace_indicator_profile_bindings,
)
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WORKSPACE_REPLAY_SOURCE_CSV,
)
from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)

HISTORY_2026 = (
    PROJECT_ROOT
    / "data"
    / "history"
    / "IB"
    / "EURUSD"
    / "M1"
    / "2026-01-02_2026-08-11_IB_EURUSD_M1.csv"
)

WINDOWS_2026 = (
    (
        "DEVELOPMENT",
        "2026-01-02T00:00:00+00:00",
        "2026-02-28T00:00:00+00:00",
    ),
    (
        "VALIDATION",
        "2026-03-01T00:00:00+00:00",
        "2026-05-31T23:59:00+00:00",
    ),
    (
        "HOLDOUT",
        "2026-06-01T00:00:00+00:00",
        "2026-08-11T08:24:00+00:00",
    ),
)

EXPECTED_BASELINES = {
    "2025": (59, 40, 18, 1, 9, -4.05, 0.7808, 5.80),
    "DEVELOPMENT": (7, 6, 1, 0, 0, 1.11, 10.2500, 0.12),
    "VALIDATION": (16, 12, 4, 0, 2, -0.78, 0.8579, 3.69),
    "HOLDOUT": (7, 6, 1, 0, 0, 0.46, 7.5714, 0.07),
}

OUTCOME_STOP_LOSS = "STOP_LOSS"
OUTCOME_OTHER_LOSS = "OTHER_LOSS"
OUTCOME_WIN = "WIN"
OUTCOME_BREAK_EVEN = "BREAK_EVEN"
OUTCOMES = (
    OUTCOME_STOP_LOSS,
    OUTCOME_OTHER_LOSS,
    OUTCOME_WIN,
    OUTCOME_BREAK_EVEN,
)
EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class AlligatorDecayEvidence:
    """Causal t-2/t-1/t Alligator evidence однієї фактичної угоди."""

    window: str
    signal_timestamp: datetime
    direction: str
    outcome: str
    final_profit: float
    active_age: int
    opening_t2: float
    opening_t1: float
    opening_t: float
    opening_delta_2: float
    opening_delta_1: float
    slope_t2: float
    slope_t1: float
    slope_t: float
    slope_delta_2: float
    slope_delta_1: float
    opening_monotonic_down: bool
    slope_monotonic_down: bool
    both_monotonic_down: bool


class FullSignalHistoryRuntime(WorkspaceRuntime):
    """Production Runtime з public immutable full signal history для тесту."""

    @property
    def historical_signal_records(self) -> tuple[WorkspaceSignalRecord, ...]:
        """Повернути повну історію signal records deterministic Replay."""
        return tuple(self._historical_signal_records)


def _candidate_bindings() -> dict[str, dict[str, object]]:
    bindings = new_workspace_indicator_profile_bindings()
    candidate = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
    )
    bindings[WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY] = (
        WorkspaceIndicatorProfileBinding.from_profile(candidate).to_storage_dict()
    )
    return bindings


def _workspace_2026(start_utc: str, end_utc: str) -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id=None,
        account_mode=None,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        display_name="RM103 7F SL Alligator Decay Cross-Period",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "EXTENDED",
            "alligator_filter_enabled": True,
            "alligator_confirmation": WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
            "spread_limit": 0.00020,
            "warmup_bars": 3,
            "macd_extremum_min_prominence": 0.000015,
            "macd_extremum_to_cross_min_distance": 0.000050,
            "macd_cross_min_angle": 45.0,
            "macd_cross_angle_model": "ABC_REALTIME_SCALED",
            "macd_cross_min_abc_angle": 2.25,
        },
        risk_settings={
            "risk_percent": 0.5,
            "maximum_position_volume": 1000.0,
            "maximum_open_positions": 2,
            "max_daily_loss_percent": 2.0,
            "require_stop_loss": True,
        },
        profit_protection={
            "enabled": True,
            "activation_mode": "AFTER_SPREAD",
            "max_profit_drawdown_percent": 30.0,
            "minimum_profit": 0.0,
        },
        replay_settings={
            "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
            "file_path": str(HISTORY_2026),
            "start_utc": start_utc,
            "end_utc": end_utc,
            "source_timezone": "UTC",
            "delimiter": "AUTO",
            "decimal_separator": ".",
            "spread": 0.00012,
            "source": "2026-01-02_2026-08-11_IB_EURUSD_M1",
            "source_timeframe": "M1",
            "risk_equity": 1000.0,
            "speed": -1,
        },
        indicator_profile_bindings=_candidate_bindings(),
    )


def _outcome(close_reason: str, final_profit: float) -> str:
    if close_reason == "STOP_LOSS":
        return OUTCOME_STOP_LOSS
    if final_profit > EPSILON:
        return OUTCOME_WIN
    if final_profit < -EPSILON:
        return OUTCOME_OTHER_LOSS
    return OUTCOME_BREAK_EVEN


def _evidence(
    window: str,
    trade,
    record: WorkspaceSignalRecord,
) -> AlligatorDecayEvidence:
    context = record.filter_context
    assert context is not None
    assert context.active_age is not None
    observations = context.diagnostic_observations
    assert len(observations) >= 3
    t2, t1, current = observations[-3:]
    assert t2.timestamp < t1.timestamp < current.timestamp
    assert current.available_at <= record.timestamp
    assert t2.normalized_opening is not None
    assert t1.normalized_opening is not None
    assert current.normalized_opening is not None
    assert t2.normalized_slope is not None
    assert t1.normalized_slope is not None
    assert current.normalized_slope is not None

    opening_t2 = float(t2.normalized_opening)
    opening_t1 = float(t1.normalized_opening)
    opening_t = float(current.normalized_opening)
    slope_t2 = float(t2.normalized_slope)
    slope_t1 = float(t1.normalized_slope)
    slope_t = float(current.normalized_slope)
    opening_monotonic_down = opening_t2 > opening_t1 > opening_t
    slope_monotonic_down = slope_t2 > slope_t1 > slope_t

    return AlligatorDecayEvidence(
        window=window,
        signal_timestamp=trade.signal_timestamp,
        direction=trade.direction,
        outcome=_outcome(trade.close_reason, trade.final_profit),
        final_profit=trade.final_profit,
        active_age=int(context.active_age),
        opening_t2=opening_t2,
        opening_t1=opening_t1,
        opening_t=opening_t,
        opening_delta_2=opening_t - opening_t2,
        opening_delta_1=opening_t - opening_t1,
        slope_t2=slope_t2,
        slope_t1=slope_t1,
        slope_t=slope_t,
        slope_delta_2=slope_t - slope_t2,
        slope_delta_1=slope_t - slope_t1,
        opening_monotonic_down=opening_monotonic_down,
        slope_monotonic_down=slope_monotonic_down,
        both_monotonic_down=opening_monotonic_down and slope_monotonic_down,
    )


def _run(
    window: str,
    workspace: AlgorithmWorkspace,
) -> tuple[AlligatorDecayEvidence, ...]:
    runtime = FullSignalHistoryRuntime(
        workspace,
        algorithm_factory=create_registered_workspace_algorithm,
    )
    assert isinstance(
        runtime.profit_drawdown_guard,
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    summary = runtime.historical_summary
    execution = runtime.replay_execution
    assert summary is not None
    assert execution is not None
    expected = EXPECTED_BASELINES[window]
    assert summary.opened_trades == expected[0]
    assert summary.winning_trades == expected[1]
    assert summary.losing_trades == expected[2]
    assert summary.break_even_trades == expected[3]
    assert summary.close_reason_count("STOP_LOSS") == expected[4]
    assert math.isclose(summary.net_profit, expected[5], abs_tol=0.005)
    assert summary.profit_factor is not None
    assert math.isclose(summary.profit_factor, expected[6], abs_tol=0.00005)
    assert math.isclose(summary.maximum_drawdown, expected[7], abs_tol=0.005)

    records = {
        record.signal_uid: record for record in runtime.historical_signal_records
    }
    evidence: list[AlligatorDecayEvidence] = []
    for trade in execution.trade_diagnostics():
        record = records.get(trade.signal_uid)
        assert record is not None, trade.signal_uid
        evidence.append(_evidence(window, trade, record))

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted
    return tuple(evidence)


def _median(items: tuple[AlligatorDecayEvidence, ...], attribute: str) -> float:
    values = tuple(float(getattr(item, attribute)) for item in items)
    assert values
    return float(statistics.median(values))


def _group_line(name: str, items: tuple[AlligatorDecayEvidence, ...]) -> str:
    return (
        f"    {name}=n:{len(items)},"
        f"opening:{_median(items, 'opening_t'):.3f},"
        f"open_d2:{_median(items, 'opening_delta_2'):+.3f},"
        f"open_d1:{_median(items, 'opening_delta_1'):+.3f},"
        f"slope:{_median(items, 'slope_t'):.3f},"
        f"slope_d2:{_median(items, 'slope_delta_2'):+.3f},"
        f"slope_d1:{_median(items, 'slope_delta_1'):+.3f},"
        f"open_monotonic_down:{sum(item.opening_monotonic_down for item in items)},"
        f"slope_monotonic_down:{sum(item.slope_monotonic_down for item in items)},"
        f"both_monotonic_down:{sum(item.both_monotonic_down for item in items)}"
    )


def _rule_matrix(
    evidence: tuple[AlligatorDecayEvidence, ...],
) -> tuple[str, ...]:
    rules = (
        ("opening_delta_2<0", lambda item: item.opening_delta_2 < 0.0),
        ("opening_delta_2<=-0.05", lambda item: item.opening_delta_2 <= -0.05),
        ("opening_delta_2<=-0.10", lambda item: item.opening_delta_2 <= -0.10),
        ("opening_delta_2<=-0.20", lambda item: item.opening_delta_2 <= -0.20),
        ("opening_monotonic_down", lambda item: item.opening_monotonic_down),
        ("slope_monotonic_down", lambda item: item.slope_monotonic_down),
        ("both_monotonic_down", lambda item: item.both_monotonic_down),
    )
    rows: list[str] = []
    for name, predicate in rules:
        matched = tuple(item for item in evidence if predicate(item))
        counts = Counter(item.outcome for item in matched)
        by_window = Counter(item.window for item in matched)
        pnl = sum(item.final_profit for item in matched)
        rows.append(
            "    "
            f"{name}: SL:{counts[OUTCOME_STOP_LOSS]},"
            f"OTHER_LOSS:{counts[OUTCOME_OTHER_LOSS]},"
            f"WIN:{counts[OUTCOME_WIN]},BE:{counts[OUTCOME_BREAK_EVEN]},"
            f"pnl:{pnl:+.2f},"
            f"windows:2025={by_window['2025']},DEV={by_window['DEVELOPMENT']},"
            f"VAL={by_window['VALIDATION']},HOLD={by_window['HOLDOUT']}"
        )
    return tuple(rows)


def main() -> None:
    """Запустити cross-period causal Alligator decay diagnostic."""
    assert_frozen_oos_snapshot()
    assert HISTORY_2026.is_file(), HISTORY_2026

    all_evidence: list[AlligatorDecayEvidence] = []
    all_evidence.extend(_run("2025", frozen_oos_workspace()))
    for window, start_utc, end_utc in WINDOWS_2026:
        all_evidence.extend(_run(window, _workspace_2026(start_utc, end_utc)))
    evidence = tuple(all_evidence)

    groups = {
        outcome: tuple(item for item in evidence if item.outcome == outcome)
        for outcome in OUTCOMES
    }
    assert len(evidence) == 89
    assert len(groups[OUTCOME_STOP_LOSS]) == 11
    assert len(groups[OUTCOME_OTHER_LOSS]) == 13
    assert len(groups[OUTCOME_WIN]) == 64
    assert len(groups[OUTCOME_BREAK_EVEN]) == 1

    stop_windows = Counter(item.window for item in groups[OUTCOME_STOP_LOSS])
    assert stop_windows == Counter({"2025": 9, "VALIDATION": 2})

    print("Algorithm Workspace Candidate F SL Alligator Decay Cross-Period result")
    print("  mode=PRODUCTION_6K_CAUSAL_ALLIGATOR_DECAY_DIAGNOSTIC_ONLY")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  signal_filter_applied=False")
    print("  alternative_stop_applied=False")
    print("  exit_recovery_policy=PRODUCTION_6K_PRESERVED")
    print("  future_price_used_as_feature=False")
    print("  periods=2025_frozen_plus_2026_development_validation_holdout")
    print("  2026_is_not_blind_oos=True")
    print(
        "  groups="
        f"stop_loss:{len(groups[OUTCOME_STOP_LOSS])},"
        f"other_loss:{len(groups[OUTCOME_OTHER_LOSS])},"
        f"win:{len(groups[OUTCOME_WIN])},"
        f"break_even:{len(groups[OUTCOME_BREAK_EVEN])}"
    )
    print("  group_medians_and_monotonic_counts:")
    for outcome in OUTCOMES:
        items = groups[outcome]
        if items:
            print(_group_line(outcome, items))
    print("  fixed_diagnostic_rule_matrix:")
    for row in _rule_matrix(evidence):
        print(row)
    print("  chronological_stop_loss_alligator_decay:")
    for index, item in enumerate(groups[OUTCOME_STOP_LOSS], start=1):
        print(
            "    "
            f"{index:02d}. {item.window} {item.signal_timestamp.isoformat()} "
            f"{item.direction} pnl:{item.final_profit:+.2f} "
            f"active_age:{item.active_age} "
            f"opening:{item.opening_t2:.3f}->{item.opening_t1:.3f}->"
            f"{item.opening_t:.3f} "
            f"open_d2:{item.opening_delta_2:+.3f} "
            f"open_d1:{item.opening_delta_1:+.3f} "
            f"slope:{item.slope_t2:.3f}->{item.slope_t1:.3f}->"
            f"{item.slope_t:.3f} "
            f"slope_d2:{item.slope_delta_2:+.3f} "
            f"slope_d1:{item.slope_delta_1:+.3f} "
            f"open_down:{item.opening_monotonic_down} "
            f"slope_down:{item.slope_monotonic_down}"
        )
    print("  completed_bars_only=True")
    print("  causal_t2_t1_t_signal_evidence_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_SL_ALLIGATOR_DECAY_CROSS_PERIOD_CHECK=OK")


if __name__ == "__main__":
    main()
