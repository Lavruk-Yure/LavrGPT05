# -*- coding: utf-8 -*-
"""RoadMap103 / 7H: cross-period Alligator regime-age anatomy для SL.

Diagnostic-only runner повторює production Candidate F після 6K для
frozen 2025 та трьох відомих вікон 2026. Для кожної фактично
відкритої угоди він бере causal Alligator context, уже доступний на
завершеному M15 signal bar, і аналізує active_age — кількість
послідовних ACTIVE bars того самого напрямку до моменту сигналу.

Мета — перевірити, чи STOP_LOSS концентруються на ранніх або пізніх
ділянках Alligator trend. Нового gate немає; SL/TP, Candidate F
profile і 6K exit recovery не змінюються. Future price не
використовується як feature; PnL потрібен тільки для post-trade
групування результатів.
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

AGE_BUCKETS = (
    ("1-2", 1, 2),
    ("3-5", 3, 5),
    ("6-10", 6, 10),
    ("11-20", 11, 20),
    ("21-40", 21, 40),
    ("41+", 41, None),
)


@dataclass(frozen=True, slots=True)
class RegimeAgeEvidence:
    """Causal Alligator regime-age evidence фактичної угоди."""

    window: str
    signal_timestamp: datetime
    direction: str
    outcome: str
    final_profit: float
    active_age: int
    regime: str
    regime_phase: str
    normalized_opening: float
    normalized_slope: float


class FullSignalHistoryRuntime(WorkspaceRuntime):
    """Production Runtime з public immutable full signal history для тесту."""

    @property
    def historical_signal_records(self) -> tuple[WorkspaceSignalRecord, ...]:
        """Повернути повну історію signal records Replay."""
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
        display_name="RM103 7H SL Regime Age Cross-Period",
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
) -> RegimeAgeEvidence:
    context = record.filter_context
    assert context is not None
    assert context.active_age is not None
    assert context.regime is not None
    assert context.regime_phase is not None
    assert context.normalized_opening is not None
    assert context.normalized_slope is not None
    assert context.available_at is not None
    assert context.available_at <= record.timestamp
    assert context.active_age >= 1

    return RegimeAgeEvidence(
        window=window,
        signal_timestamp=trade.signal_timestamp,
        direction=trade.direction,
        outcome=_outcome(trade.close_reason, trade.final_profit),
        final_profit=trade.final_profit,
        active_age=int(context.active_age),
        regime=context.regime,
        regime_phase=context.regime_phase,
        normalized_opening=float(context.normalized_opening),
        normalized_slope=float(context.normalized_slope),
    )


def _run(
    window: str,
    workspace: AlgorithmWorkspace,
) -> tuple[RegimeAgeEvidence, ...]:
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
    evidence: list[RegimeAgeEvidence] = []
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


def _percentile_nearest(values: tuple[int, ...], fraction: float) -> int:
    assert values
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


def _group_line(name: str, items: tuple[RegimeAgeEvidence, ...]) -> str:
    ages = tuple(item.active_age for item in items)
    return (
        f"    {name}=n:{len(items)},"
        f"age:min:{min(ages)},p25:{_percentile_nearest(ages, 0.25)},"
        f"median:{statistics.median(ages):.1f},"
        f"p75:{_percentile_nearest(ages, 0.75)},max:{max(ages)},"
        f"opening_median:"
        f"{statistics.median(item.normalized_opening for item in items):.3f},"
        f"slope_median:"
        f"{statistics.median(item.normalized_slope for item in items):.3f}"
    )


def _in_bucket(age: int, start: int, end: int | None) -> bool:
    if end is None:
        return age >= start
    return start <= age <= end


def _bucket_matrix(evidence: tuple[RegimeAgeEvidence, ...]) -> tuple[str, ...]:
    rows: list[str] = []
    for name, start, end in AGE_BUCKETS:
        matched = tuple(
            item for item in evidence if _in_bucket(item.active_age, start, end)
        )
        counts = Counter(item.outcome for item in matched)
        by_window = Counter(item.window for item in matched)
        pnl = sum(item.final_profit for item in matched)
        sl_rate = (
            counts[OUTCOME_STOP_LOSS] / len(matched) * 100.0 if matched else 0.0
        )
        rows.append(
            "    "
            f"age={name}: n:{len(matched)},SL:{counts[OUTCOME_STOP_LOSS]},"
            f"OTHER_LOSS:{counts[OUTCOME_OTHER_LOSS]},"
            f"WIN:{counts[OUTCOME_WIN]},BE:{counts[OUTCOME_BREAK_EVEN]},"
            f"SL_rate:{sl_rate:.1f}%,pnl:{pnl:+.2f},"
            f"windows:2025={by_window['2025']},DEV={by_window['DEVELOPMENT']},"
            f"VAL={by_window['VALIDATION']},HOLD={by_window['HOLDOUT']}"
        )
    return tuple(rows)


def _fixed_rule_matrix(
    evidence: tuple[RegimeAgeEvidence, ...],
) -> tuple[str, ...]:
    rules = (
        ("active_age<=2", lambda item: item.active_age <= 2),
        ("active_age<=5", lambda item: item.active_age <= 5),
        ("active_age>=10", lambda item: item.active_age >= 10),
        ("active_age>=20", lambda item: item.active_age >= 20),
        ("active_age>=40", lambda item: item.active_age >= 40),
    )
    rows: list[str] = []
    for name, rule_predicate in rules:
        matched = tuple(item for item in evidence if rule_predicate(item))
        rule_counts = Counter(item.outcome for item in matched)
        by_window = Counter(item.window for item in matched)
        rule_pnl = sum(item.final_profit for item in matched)
        rows.append(
            "    "
            f"{name}: SL:{rule_counts[OUTCOME_STOP_LOSS]},"
            f"OTHER_LOSS:{rule_counts[OUTCOME_OTHER_LOSS]},"
            f"WIN:{rule_counts[OUTCOME_WIN]},BE:{rule_counts[OUTCOME_BREAK_EVEN]},"
            f"pnl:{rule_pnl:+.2f},"
            f"windows:2025={by_window['2025']},DEV={by_window['DEVELOPMENT']},"
            f"VAL={by_window['VALIDATION']},HOLD={by_window['HOLDOUT']}"
        )
    return tuple(rows)


def main() -> None:
    """Запустити cross-period causal Alligator regime-age diagnostic."""
    assert_frozen_oos_snapshot()
    assert HISTORY_2026.is_file(), HISTORY_2026

    all_evidence: list[RegimeAgeEvidence] = []
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

    print("Algorithm Workspace Candidate F SL Regime Age Cross-Period result")
    print("  mode=PRODUCTION_6K_CAUSAL_ALLIGATOR_REGIME_AGE_DIAGNOSTIC_ONLY")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  signal_filter_applied=False")
    print("  alternative_stop_applied=False")
    print("  exit_recovery_policy=PRODUCTION_6K_PRESERVED")
    print("  future_price_used_as_feature=False")
    print("  periods=2025_frozen_plus_2026_development_validation_holdout")
    print("  2026_is_not_blind_oos=True")
    print("  active_age_definition=consecutive_same_direction_ACTIVE_M15_bars")
    print(
        "  groups="
        f"stop_loss:{len(groups[OUTCOME_STOP_LOSS])},"
        f"other_loss:{len(groups[OUTCOME_OTHER_LOSS])},"
        f"win:{len(groups[OUTCOME_WIN])},"
        f"break_even:{len(groups[OUTCOME_BREAK_EVEN])}"
    )
    print("  group_age_distribution:")
    for outcome in OUTCOMES:
        items = groups[outcome]
        if items:
            print(_group_line(outcome, items))
    print("  age_bucket_matrix:")
    for row in _bucket_matrix(evidence):
        print(row)
    print("  fixed_diagnostic_rule_matrix:")
    for row in _fixed_rule_matrix(evidence):
        print(row)
    print("  chronological_stop_loss_regime_age:")
    for index, item in enumerate(groups[OUTCOME_STOP_LOSS], start=1):
        print(
            "    "
            f"{index:02d}. {item.window} {item.signal_timestamp.isoformat()} "
            f"{item.direction} pnl:{item.final_profit:+.2f} "
            f"active_age:{item.active_age} regime:{item.regime} "
            f"phase:{item.regime_phase} opening:{item.normalized_opening:.3f} "
            f"slope:{item.normalized_slope:.3f}"
        )
    print("  completed_bars_only=True")
    print("  causal_signal_alligator_context_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_SL_REGIME_AGE_CROSS_PERIOD_CHECK=OK")


if __name__ == "__main__":
    main()
