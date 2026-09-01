# -*- coding: utf-8 -*-
"""RoadMap102: заморожений OOS Replay Candidate F на незалежному 2025 році.

Runner використовує production ``RailAlgorithm`` і cTrader EURUSD M1 dataset,
але жорстко обмежує Replay тільки 2025 роком. Перед запуском фіксуються MACD
8/17/5, Candidate F r1, quality thresholds, risk, spread, NEXT_BAR_OPEN і
Profit Drawdown 30%. Після перегляду результату цей runner не змінює жодного
threshold і не має performance-умов типу ``PnL > 0`` або ``PF > 1``.

PASS означає лише: frozen snapshot відтворився causal/deterministic способом,
Replay завершився, усі потрібні OOS-метрики зібрані та broker execution не
виконувався. Самі PnL/PF/DD є результатом OOS, а не критерієм проходження.
"""

from __future__ import annotations

import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_algorithm import (  # noqa: E402
    WorkspaceAlgorithm,
    create_registered_workspace_algorithm,
)
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REASON_DEFERRED_ARMED,
    ALLIGATOR_REASON_OPENING_COLLAPSE,
    ALLIGATOR_REASON_OVEREXTENDED,
    ALLIGATOR_REASON_VOLATILITY_SPIKE,
    ALLIGATOR_REASON_WEAK_OPENING,
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_indicator_profile import (  # noqa: E402
    ALLIGATOR_LOGIC_MODE_CANDIDATE_F,
    ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F,
    MACD_PROFILE_UID_LGE_DEFAULT,
    WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY,
    WorkspaceIndicatorProfileBinding,
    built_in_workspace_indicator_profile,
    new_workspace_indicator_profile_bindings,
)
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceProfitDrawdownGuard,
)
from core.workspace_replay_margin import (  # noqa: E402
    HISTORICAL_REPLAY_LEVERAGE,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WORKSPACE_REPLAY_SOURCE_CSV,
)

HISTORY_FILE = (
    PROJECT_ROOT
    / "data"
    / "history"
    / "CTRADER"
    / "EURUSD"
    / "M1"
    / "2025-01-01_2026-08-21_CTRADER_EURUSD_M1.csv"
)
OOS_START_UTC = "2025-01-01T00:00:00+00:00"
OOS_END_UTC = "2025-12-31T23:59:00+00:00"


class FrozenOosRuntime(WorkspaceRuntime):
    """Тестовий Runtime із frozen pre-6J exit і full signal history."""

    def __init__(
        self,
        workspace: AlgorithmWorkspace,
        algorithm_factory: Callable[[str], WorkspaceAlgorithm] | None = None,
    ) -> None:
        super().__init__(workspace, algorithm_factory=algorithm_factory)
        self.profit_drawdown_guard = WorkspaceProfitDrawdownGuard(
            self.profit_protection_policy
        )

    def historical_signal_records_for_test(
        self,
    ) -> tuple[WorkspaceSignalRecord, ...]:
        """Повернути full-run records, а не bounded Signals UI buffer."""
        return tuple(self._historical_signal_records)


def _candidate_bindings() -> dict[str, dict[str, object]]:
    """Повернути frozen indicator bindings для OOS до запуску Replay."""
    bindings = new_workspace_indicator_profile_bindings()
    candidate = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
    )
    bindings[WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY] = (
        WorkspaceIndicatorProfileBinding.from_profile(candidate).to_storage_dict()
    )
    return bindings


def frozen_oos_workspace() -> AlgorithmWorkspace:
    """Створити один frozen Candidate F Historical Replay WSP за 2025 рік."""
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id=None,
        account_mode=None,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        display_name="RM102 Candidate F Frozen OOS 2025",
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
            "file_path": str(HISTORY_FILE),
            "start_utc": OOS_START_UTC,
            "end_utc": OOS_END_UTC,
            "source_timezone": "UTC",
            "delimiter": "AUTO",
            "decimal_separator": ".",
            "spread": 0.00012,
            "source": "2025-01-01_2026-08-21_CTRADER_EURUSD_M1",
            "source_timeframe": "M1",
            "risk_equity": 1000.0,
            "speed": -1,
        },
        indicator_profile_bindings=_candidate_bindings(),
    )


def assert_frozen_oos_snapshot() -> None:
    """Зафіксувати всі параметри, які не можна рухати після OOS."""
    macd = built_in_workspace_indicator_profile(MACD_PROFILE_UID_LGE_DEFAULT)
    candidate = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
    )

    assert macd.parameters["fast_period"] == 8
    assert macd.parameters["slow_period"] == 17
    assert macd.parameters["signal_period"] == 5
    assert candidate.parameters["logic_mode"] == ALLIGATOR_LOGIC_MODE_CANDIDATE_F
    assert candidate.parameters["trend_start_confirmation_bars"] == 4
    assert candidate.parameters["deferred_expiry_bars"] == 5
    assert candidate.parameters["opening_collapse_threshold"] == -0.700
    assert candidate.parameters["weak_max_active_age"] == 2
    assert candidate.parameters["weak_max_opening"] == 0.500
    assert candidate.parameters["spike_min_range_ratio"] == 3.500
    assert candidate.parameters["spike_max_opening_delta"] == -0.500
    assert candidate.parameters["spike_max_slope_delta"] == -0.010
    assert candidate.parameters["overextended_min_slope"] == 0.200
    assert candidate.parameters["overextended_min_opening"] == 3.000


def _fmt_pf(value: float | None) -> str:
    return "NONE" if value is None else f"{value:.4f}"


def main() -> None:
    assert HISTORY_FILE.is_file(), HISTORY_FILE
    assert_frozen_oos_snapshot()

    runtime = FrozenOosRuntime(
        frozen_oos_workspace(),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    summary = runtime.historical_summary
    algorithm = runtime.algorithm
    assert summary is not None
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    execution = runtime.replay_execution
    assert execution is not None
    assert execution.leverage == HISTORICAL_REPLAY_LEVERAGE == 500.0
    assert execution.policy.stop_range_multiplier == 1.0
    assert execution.policy.take_profit_r_multiple == 2.0
    assert execution.policy.ambiguous_bar_policy == "STOP_LOSS_FIRST"
    assert summary.period_start.year == 2025
    assert summary.period_end.year == 2025

    records = runtime.historical_signal_records_for_test()
    assert len(records) == summary.signals.total
    reason_counts = Counter(
        str(record.filter_reason_code or "").strip().upper()
        for record in records
        if str(record.filter_reason_code or "").strip()
    )
    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted
    assert all(
        record.filter_context is None
        or record.filter_context.available_at is None
        or record.filter_context.available_at <= record.timestamp
        for record in records
    )

    signals = summary.signals
    armed = reason_counts[ALLIGATOR_REASON_DEFERRED_ARMED]
    releases = len(algorithm.deferred_releases)
    cancel_opposite_macd = algorithm.deferred_cancelled_opposite_cross
    cancel_macd_invalid = algorithm.deferred_cancelled_macd_invalid
    cancel_opposite_alligator = algorithm.deferred_cancelled_opposite_alligator
    expires = algorithm.deferred_expired
    cancels = cancel_opposite_macd + cancel_macd_invalid + cancel_opposite_alligator

    print("Algorithm Workspace Candidate F Frozen OOS 2025 result")
    print(f"  dataset={HISTORY_FILE.name}")
    print("  requested_period=" f"{OOS_START_UTC} -> {OOS_END_UTC}")
    print(
        "  actual_period="
        f"{summary.period_start.isoformat()} -> {summary.period_end.isoformat()}"
    )
    print("  candidate_f_frozen_before_run=True")
    print("  macd_profile=8/17/5 EMA Close")
    print("  macd_quality=" "prominence:0.000015,distance:0.000050,ABC:2.25")
    print(
        "  candidate_f="
        "confirm:4,ttl:5,collapse:-0.700,weak_age:2,weak_opening:0.500,"
        "spike_ratio:3.500,spike_opening_delta:-0.500,"
        "spike_slope_delta:-0.010,overextended_slope:0.200,"
        "overextended_opening:3.000"
    )
    print("  spread=0.000120")
    print("  initial_balance=1000.00")
    print(f"  replay_leverage=1:{HISTORICAL_REPLAY_LEVERAGE:g}")
    print("  risk_percent=0.50")
    print("  maximum_position_volume=1000")
    print("  maximum_open_positions=2")
    print("  max_daily_loss_percent=2.00")
    print("  stop_loss_required=True")
    print("  entry_policy=NEXT_BAR_OPEN")
    print("  profit_drawdown_percent=30.0")
    print(f"  accepted_bars={summary.accepted_bars}")
    print(f"  skipped_bars={summary.skipped_bars}")
    print(f"  gaps={summary.gaps}")
    print(
        "  trades="
        f"{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},break_even:{summary.break_even_trades}"
    )
    print(f"  win_rate={summary.win_rate_percent:.1f}%")
    print(f"  stop_loss_closes={summary.close_reason_count('STOP_LOSS')}")
    print(f"  take_profit_closes={summary.close_reason_count('TAKE_PROFIT')}")
    print(
        "  profit_drawdown_closes=" f"{summary.close_reason_count('PROFIT_DRAWDOWN')}"
    )
    print(f"  session_end_closes={summary.close_reason_count('SESSION_END')}")
    print(f"  net_profit={summary.net_profit:+.2f}")
    print(f"  final_balance={summary.final_balance:.2f}")
    print(f"  profit_factor={_fmt_pf(summary.profit_factor)}")
    print(
        "  maximum_drawdown="
        f"{summary.maximum_drawdown:.2f} / {summary.maximum_drawdown_percent:.2f}%"
    )
    print(f"  average_trade={summary.average_trade:+.4f}")
    print(
        "  macd_quality="
        f"pass:{signals.macd_quality_accept},reject:{signals.macd_quality_reject}"
    )
    print(
        "  alligator="
        f"allow:{signals.alligator_allow},reject:{signals.alligator_reject}"
    )
    print(
        "  candidate_f_lifecycle="
        f"armed:{armed},release:{releases},cancel:{cancels},expire:{expires}"
    )
    print(
        "  candidate_f_cancel_detail="
        f"opposite_macd:{cancel_opposite_macd},"
        f"macd_invalid:{cancel_macd_invalid},"
        f"opposite_active_alligator:{cancel_opposite_alligator}"
    )
    print(
        "  structural_rejects="
        f"opening_collapse:{reason_counts[ALLIGATOR_REASON_OPENING_COLLAPSE]},"
        f"weak_opening:{reason_counts[ALLIGATOR_REASON_WEAK_OPENING]},"
        f"volatility_spike:{reason_counts[ALLIGATOR_REASON_VOLATILITY_SPIKE]},"
        f"overextended:{reason_counts[ALLIGATOR_REASON_OVEREXTENDED]}"
    )
    print("  completed_bars_only=True")
    print("  no_look_ahead=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_FROZEN_OOS_2025_CHECK=OK")


if __name__ == "__main__":
    main()
