# RoadMap99_04B — M15 MACD + lower-timeframe Alligator diagnostic
# -*- coding: utf-8 -*-
"""Діагностика Alligator M15/M5/M1 для незмінного MACD Quality.

RoadMap99_04B перевіряє lower-timeframe Alligator без зміни production
logic або WSP UI. MACD завжди обчислюється тільки на завершених M15 bars.
EXTENDED quality pipeline незмінний: prominence=0.000005,
distance=0.000050 і angle=45°. Для кожного прийнятого MACD Quality
кандидата незалежно оцінюється той самий профіль
``LGE Classic Smoothed`` на M15, M5 та M1.

M1 history є єдиним джерелом. M5 і M15 складаються причинно через
``WorkspaceTimeframeAggregator``. У момент завершення M15 signal bar
нижчий Alligator бачить лише останній повністю завершений M5 або M1 bar.
Майбутні дані заборонені. M15 варіант має відтворити ручний long-Replay
checkpoint 17 ALLOW / 97 REJECT. Після цього M5/M1 є diagnostic evidence.

Тест не додає LOWER timeframe до production enum і не змінює алгоритм,
WSP parameters, risk, execution або broker integration. Результат потрібен,
щоб вирішити, чи варто реалізовувати lower-timeframe Alligator як окремий
entry-timing confirmation. Broker execution лишається вимкненим.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_alligator import (  # noqa: E402
    WorkspaceAlligatorFilter,
    WorkspaceAlligatorRuntimeProfile,
)
from core.workspace_history import WorkspaceCsvHistoryLoader  # noqa: E402
from core.workspace_macd import (  # noqa: E402
    WorkspaceMacdRuntimeProfile,
    WorkspaceMacdSignalSource,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_signal import (  # noqa: E402
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WorkspaceSignalProposal,
)
from core.workspace_timeframe_aggregation import (  # noqa: E402
    WorkspaceTimeframeAggregator,
)

M1_FILE = (
    PROJECT_ROOT
    / "data"
    / "history"
    / "IB"
    / "EURUSD"
    / "M1"
    / "2026-01-02_2026-08-11_IB_EURUSD_M1.csv"
)
START_UTC = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
END_UTC = datetime(2026, 8, 11, 8, 24, tzinfo=UTC)
PROMINENCE = 0.000005
FIXED_DISTANCE = 0.000050
FIXED_ANGLE = 45.0
DIRECTIONAL_HORIZON_BARS = 8
DIRECTIONAL_MINIMUM_MOVE = 0.00020


@dataclass(frozen=True, slots=True)
class DiagnosticDecision:
    """Рішення Alligator для прийнятого MACD Quality."""

    signal_timestamp: datetime
    signal_available_at: datetime
    direction: str
    alligator_timeframe: str
    observation_timestamp: datetime
    observation_available_at: datetime
    allowed: bool


@dataclass(frozen=True, slots=True)
class TimeframeDiagnostic:
    """Підсумок одного timeframe Alligator."""

    timeframe: str
    allow: int
    reject: int
    allow_directional_hits: int
    reject_directional_hits: int

    @property
    def allow_percent(self) -> float:
        total = self.allow + self.reject
        if total <= 0:
            return 0.0
        return self.allow / total * 100.0

    @property
    def allow_hit_percent(self) -> float:
        if self.allow <= 0:
            return 0.0
        return self.allow_directional_hits / self.allow * 100.0

    @property
    def reject_hit_percent(self) -> float:
        if self.reject <= 0:
            return 0.0
        return self.reject_directional_hits / self.reject * 100.0


def load_m1_events() -> tuple[WorkspaceMarketEvent, ...]:
    """Завантажити long M1 dataset для causal diagnostics."""
    data_set = WorkspaceCsvHistoryLoader().load(
        file_path=M1_FILE,
        broker="IB",
        symbol="EURUSD",
        timeframe="M1",
        start_utc=START_UTC,
        end_utc=END_UTC,
        source_timezone="UTC",
        delimiter="AUTO",
        decimal_separator=".",
        default_spread=0.00012,
        source_name="IB_EURUSD_M1_RM99_LOWER_ALLIGATOR_DIAGNOSTIC",
    )
    return data_set.events


def build_macd_source() -> WorkspaceMacdSignalSource:
    """Побудувати M15 EXTENDED MACD Quality із фіксованим профілем."""
    return WorkspaceMacdSignalSource(
        enabled=True,
        mode="EXTENDED",
        runtime_profile=WorkspaceMacdRuntimeProfile.lge_default(),
        extremum_min_prominence=PROMINENCE,
        extremum_to_cross_min_distance=FIXED_DISTANCE,
        cross_min_angle_degrees=FIXED_ANGLE,
    )


def build_alligator_filters() -> dict[str, WorkspaceAlligatorFilter]:
    """Побудувати однаковий Alligator profile для M15, M5 та M1."""
    runtime_profile = WorkspaceAlligatorRuntimeProfile.lge_default()
    return {
        timeframe: WorkspaceAlligatorFilter(
            enabled=True,
            confirmation_mode="SAME_TIMEFRAME",
            runtime_profile=runtime_profile,
            timeframe=timeframe,
        )
        for timeframe in ("M15", "M5", "M1")
    }


def build_diagnostic_decisions(
    m1_events: tuple[WorkspaceMarketEvent, ...],
) -> tuple[
    tuple[DiagnosticDecision, ...],
    tuple[WorkspaceMarketEvent, ...],
    int,
    int,
]:
    """Обчислити M15 MACD і causal M15/M5/M1 Alligator decisions."""
    macd_source = build_macd_source()
    filters = build_alligator_filters()
    m5_aggregator = WorkspaceTimeframeAggregator(
        source_timeframe="M1",
        target_timeframe="M5",
    )
    m15_aggregator = WorkspaceTimeframeAggregator(
        source_timeframe="M1",
        target_timeframe="M15",
    )
    decisions: list[DiagnosticDecision] = []
    m15_events: list[WorkspaceMarketEvent] = []
    previous_m1: WorkspaceMarketEvent | None = None
    classic_crosses = 0
    quality_accept = 0

    for event in m1_events:
        if previous_m1 is not None:
            filters["M1"].on_market_event(
                previous_m1,
                available_at=previous_m1.timestamp + timedelta(minutes=1),
            )

        completed_m5 = m5_aggregator.on_market_event(event)
        if completed_m5 is not None:
            filters["M5"].on_market_event(
                completed_m5.event,
                available_at=completed_m5.completed_at,
            )

        completed_m15 = m15_aggregator.on_market_event(event)
        if completed_m15 is not None:
            m15_event = completed_m15.event
            m15_events.append(m15_event)
            filters["M15"].on_market_event(
                m15_event,
                available_at=completed_m15.completed_at,
            )
            proposal = macd_source.on_market_event(m15_event)
            if proposal is not None:
                classic_crosses += 1
                if proposal.filter_decision == WORKSPACE_SIGNAL_FILTER_ALLOW:
                    quality_accept += 1
                    append_alligator_decisions(
                        decisions,
                        filters,
                        proposal,
                        signal_timestamp=m15_event.timestamp,
                        signal_available_at=completed_m15.completed_at,
                    )
        previous_m1 = event

    assert m15_aggregator.completed_bars == 14941
    assert classic_crosses == 1154
    assert quality_accept == 114
    assert len(decisions) == quality_accept * 3
    return (
        tuple(decisions),
        tuple(m15_events),
        classic_crosses,
        quality_accept,
    )


def append_alligator_decisions(
    decisions: list[DiagnosticDecision],
    filters: dict[str, WorkspaceAlligatorFilter],
    proposal: WorkspaceSignalProposal,
    *,
    signal_timestamp: datetime,
    signal_available_at: datetime,
) -> None:
    """Додати три causal decisions для одного M15 MACD candidate."""
    for timeframe in ("M15", "M5", "M1"):
        signal_filter = filters[timeframe]
        observation = signal_filter.latest_observation
        assert observation is not None
        decision = signal_filter.evaluate(
            proposal,
            observation,
            proposal_timestamp=signal_available_at,
        )
        assert observation.timeframe == timeframe
        assert observation.available_at <= signal_available_at
        decisions.append(
            DiagnosticDecision(
                signal_timestamp=signal_timestamp,
                signal_available_at=signal_available_at,
                direction=proposal.direction,
                alligator_timeframe=timeframe,
                observation_timestamp=observation.timestamp,
                observation_available_at=observation.available_at,
                allowed=decision.allowed,
            )
        )


def directional_hit(
    decision: DiagnosticDecision,
    event_index: dict[datetime, int],
    m15_events: tuple[WorkspaceMarketEvent, ...],
) -> bool:
    """Перевірити directional move через 8 M15 bars."""
    index = event_index[decision.signal_timestamp]
    future_index = index + DIRECTIONAL_HORIZON_BARS
    if future_index >= len(m15_events):
        return False
    start_close = float(m15_events[index].close)
    future_close = float(m15_events[future_index].close)
    if decision.direction == "BUY":
        move = future_close - start_close
    elif decision.direction == "SELL":
        move = start_close - future_close
    else:
        raise AssertionError(f"unsupported direction: {decision.direction}")
    return move >= DIRECTIONAL_MINIMUM_MOVE


def summarize_timeframes(
    decisions: tuple[DiagnosticDecision, ...],
    m15_events: tuple[WorkspaceMarketEvent, ...],
) -> tuple[TimeframeDiagnostic, ...]:
    """Підсумувати allow/reject і directional-hit rate по timeframe."""
    event_index = {event.timestamp: index for index, event in enumerate(m15_events)}
    assert len(event_index) == len(m15_events)
    reports: list[TimeframeDiagnostic] = []
    for timeframe in ("M15", "M5", "M1"):
        subset = tuple(
            item for item in decisions if item.alligator_timeframe == timeframe
        )
        allow = sum(item.allowed for item in subset)
        reject = len(subset) - allow
        allow_hits = sum(
            directional_hit(item, event_index, m15_events)
            for item in subset
            if item.allowed
        )
        reject_hits = sum(
            directional_hit(item, event_index, m15_events)
            for item in subset
            if not item.allowed
        )
        reports.append(
            TimeframeDiagnostic(
                timeframe=timeframe,
                allow=allow,
                reject=reject,
                allow_directional_hits=allow_hits,
                reject_directional_hits=reject_hits,
            )
        )
    return tuple(reports)


def main() -> None:
    """Запустити RoadMap99_04B lower-timeframe diagnostic."""
    print(
        "Algorithm Workspace M15 MACD + Lower-Timeframe Alligator Diagnostic "
        "Check — RoadMap99_04B",
        flush=True,
    )
    print(
        "  MACD=M15 EXTENDED prominence=0.000005; Alligator profile fixed. "
        "Only confirmation timeframe varies: M15 -> M5 -> M1.",
        flush=True,
    )
    print(
        "  Diagnostic only: production enum/UI/execution stay unchanged; "
        "broker execution remains disabled.",
        flush=True,
    )
    if not M1_FILE.is_file():
        raise FileNotFoundError("Real EURUSD M1 history is required: " + str(M1_FILE))

    print("Lower-Timeframe Alligator: loading M1 and calculating ...", flush=True)
    m1_events = load_m1_events()
    decisions, m15_events, classic_crosses, quality_accept = build_diagnostic_decisions(
        m1_events
    )
    reports = summarize_timeframes(decisions, m15_events)

    by_timeframe = {report.timeframe: report for report in reports}
    assert (by_timeframe["M15"].allow, by_timeframe["M15"].reject) == (17, 97)
    for report in reports:
        assert report.allow + report.reject == quality_accept

    print("Algorithm Workspace Lower-Timeframe Alligator Diagnostic result")
    print("  symbol=EURUSD")
    print("  period=2026-01-02..2026-08-11")
    print("  source_timeframe=M1")
    print("  strategy_timeframe=M15")
    print("  historical_m15_bars=14941")
    print(f"  classic_macd_crosses={classic_crosses}")
    print(f"  macd_quality_candidates={quality_accept}")
    print("  macd_profile=LGE Classic EMA 12/26/9 Close")
    print("  macd_quality_prominence=0.000005")
    print("  macd_quality_distance=0.000050")
    print("  macd_quality_angle=45.00")
    print("  alligator_profile=LGE Classic Smoothed")
    for report in reports:
        print(
            f"  Alligator {report.timeframe}: "
            f"allow/reject={report.allow}/{report.reject}, "
            f"allow_rate={report.allow_percent:.2f}%, "
            f"allow_hits_8bar={report.allow_directional_hits}/"
            f"{report.allow} ({report.allow_hit_percent:.2f}%), "
            f"reject_hits_8bar={report.reject_directional_hits}/"
            f"{report.reject} ({report.reject_hit_percent:.2f}%)"
        )
    print("  m15_manual_checkpoint_17_97_reproduced=True")
    print("  lower_timeframe_lookahead=False")
    print("  production_alligator_modes_changed=False")
    print("  production_signal_logic_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_MACD_LOWER_TIMEFRAME_ALLIGATOR_" "DIAGNOSTIC_CHECK=OK")


if __name__ == "__main__":
    main()
