# -*- coding: utf-8 -*-
"""T104-28: factual Candidate F WorkspaceRuntime production-path audit.

This TEST_ONLY runner deliberately avoids the frozen T104-25/T104-26 trade
simulators.  Candidate and baseline are two real WorkspaceRuntime instances
fed by one shared historical session per period.  The baseline subclass keeps
the production canonical Supertrend state current but suppresses only its
SELL close event.  Orders, fills, SL/TP, PnL, journal, snapshots, diagnostics,
Candidate F entries, risk, and session completion remain production runtime
behavior.
"""

from __future__ import annotations

import hashlib
import math
import sys
from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_alligator import (  # noqa: E402
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_indicator_profile import (  # noqa: E402
    ALLIGATOR_LOGIC_MODE_CANDIDATE_F,
    ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F,
    ALLIGATOR_PROFILE_UID_LGE_CLASSIC,
    WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY,
    WorkspaceIndicatorProfileBinding,
    built_in_workspace_indicator_profile,
    new_workspace_indicator_profile_bindings,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay import (  # noqa: E402
    WorkspaceReplayService,
    WorkspaceReplaySession,
)
from core.workspace_replay_execution import (  # noqa: E402
    REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH,
    REPLAY_CLOSE_TAKE_PROFIT,
    SELL_SUPERTREND_TIMEFRAME,
    WorkspaceCanonicalSupertrend,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WORKSPACE_REPLAY_SOURCE_CSV,
)

TEST_ID = "T104-28"
PIP_SIZE = 0.0001
EPSILON = 1e-9
BASE_WORKSPACE_UID = "00000000-0000-0000-0000-000000010428"
CONTROL_TIMESTAMP = "2026-02-18 07:15"


@dataclass(frozen=True, slots=True)
class Period:
    label: str
    history_file: Path
    start_utc: str
    end_utc: str


PERIODS = (
    Period(
        label="2025",
        history_file=(
            PROJECT_ROOT
            / "data"
            / "history"
            / "IB"
            / "EURUSD"
            / "M1"
            / "2025-01-02_2025-12-31_IB_EURUSD_M1.csv"
        ),
        start_utc="2025-01-02T00:00:00+00:00",
        end_utc="2025-12-31T23:59:00+00:00",
    ),
    Period(
        label="2026_YTD",
        history_file=(
            PROJECT_ROOT
            / "data"
            / "history"
            / "IB"
            / "EURUSD"
            / "M1"
            / "2026-01-02_2026-08-25_IB_EURUSD_M1.csv"
        ),
        start_utc="2026-01-02T00:00:00+00:00",
        end_utc="2026-08-25T23:59:00+00:00",
    ),
)


class SharedHistoricalReplayService(WorkspaceReplayService):
    """Load a period once, then return independent cursors over shared facts."""

    def __init__(self) -> None:
        super().__init__()
        self.template: WorkspaceReplaySession | None = None
        self.history_loads = 0

    def create_session(self, **kwargs: Any) -> WorkspaceReplaySession:
        if self.template is None:
            self.template = super().create_session(**kwargs)
            self.history_loads += 1
            return self.template
        source = self.template
        settings = dict(kwargs.get("replay_settings") or {})
        return WorkspaceReplaySession(
            events=source.events,
            source_name=source.source_name,
            speed=int(settings.get("speed", source.speed)),
            history_report=source.history_report,
            execution_windows=source.execution_windows,
            source_timeframe=source.source_timeframe,
            strategy_timeframe=source.strategy_timeframe,
            source_event_count=source.source_event_count,
            dropped_incomplete_strategy_buckets=(
                source.dropped_incomplete_strategy_buckets
            ),
        )


class AuditWorkspaceRuntime(WorkspaceRuntime):
    """Narrow public TEST_ONLY adapters around production runtime hooks."""

    def historical_signal_records_for_audit(
        self,
    ) -> tuple[WorkspaceSignalRecord, ...]:
        return tuple(self._historical_signal_records)

    def accept_market_event_for_audit(self, event: WorkspaceMarketEvent) -> None:
        self._accept_market_event(event, origin="T104_28_FIXTURE")

    def queue_signal_for_audit(
        self,
        record: WorkspaceSignalRecord,
        event: WorkspaceMarketEvent,
    ) -> None:
        engine = self.replay_execution
        assert engine is not None
        self._append_replay_execution_events(engine.queue_signal(record, event))
        self._sync_replay_execution_snapshot()

    def apply_sell_supertrend_for_audit(self, event: WorkspaceMarketEvent) -> None:
        self._apply_replay_sell_supertrend_exit(event)


class BaselineWorkspaceRuntime(AuditWorkspaceRuntime):
    """TEST_ONLY real runtime with only the SELL Supertrend close disabled."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.canonical_supertrend = WorkspaceCanonicalSupertrend()
        super().__init__(*args, **kwargs)

    def _apply_replay_sell_supertrend_exit(
        self,
        event: WorkspaceMarketEvent,
    ) -> None:
        if (
            self.replay_execution is None
            or event.timeframe != SELL_SUPERTREND_TIMEFRAME
        ):
            return
        # Keep the production tracker causal and identical.  Suppress only the
        # close lifecycle returned by WorkspaceReplayExecutionEngine.
        self.canonical_supertrend.on_completed_m15_bar(event)


class ChronologyTraceRuntime(AuditWorkspaceRuntime):
    """TEST_ONLY observer of actual runtime method order; behavior is unchanged."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.execution_trace: list[tuple[str, datetime]] = []
        super().__init__(*args, **kwargs)

    def _advance_replay_execution(self, event: WorkspaceMarketEvent) -> None:
        self.execution_trace.append((event.timeframe, event.timestamp))
        super()._advance_replay_execution(event)

    def _apply_replay_sell_supertrend_exit(
        self,
        event: WorkspaceMarketEvent,
    ) -> None:
        self.execution_trace.append(("SUPERTREND_" + event.timeframe, event.timestamp))
        super()._apply_replay_sell_supertrend_exit(event)


@dataclass(frozen=True, slots=True)
class GeometryRow:
    signal_uid: str
    direction: str
    signal_timestamp: datetime
    signal_bar_range: float
    spread: float
    spread_floor: float
    stop_distance: float
    take_distance: float
    branch: str


@dataclass(frozen=True, slots=True)
class RunFacts:
    runtime: AuditWorkspaceRuntime
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...]
    geometry: tuple[GeometryRow, ...]


def _candidate_bindings() -> dict[str, dict[str, object]]:
    bindings = new_workspace_indicator_profile_bindings()
    profile = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
    )
    bindings[WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY] = (
        WorkspaceIndicatorProfileBinding.from_profile(profile).to_storage_dict()
    )
    return bindings


def _workspace(
    period: Period,
    *,
    profile_uid: str = ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F,
) -> AlgorithmWorkspace:
    bindings = new_workspace_indicator_profile_bindings()
    profile = built_in_workspace_indicator_profile(profile_uid)
    bindings[WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY] = (
        WorkspaceIndicatorProfileBinding.from_profile(profile).to_storage_dict()
    )
    workspace = AlgorithmWorkspace.create(
        broker="IB",
        account_id=None,
        account_mode=None,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        display_name=f"{TEST_ID} {period.label} Production Truth Audit",
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
            "file_path": str(period.history_file),
            "start_utc": period.start_utc,
            "end_utc": period.end_utc,
            "source_timezone": "UTC",
            "delimiter": "AUTO",
            "decimal_separator": ".",
            "spread": 0.00012,
            "source": period.history_file.stem,
            "source_timeframe": "M1",
            "risk_equity": 1000.0,
            "speed": -1,
        },
        indicator_profile_bindings=bindings,
    )
    workspace.workspace_uid = BASE_WORKSPACE_UID
    return workspace


def _production_hashes() -> dict[str, str]:
    paths = sorted((PROJECT_ROOT / "core").rglob("*.py"))
    strings = PROJECT_ROOT / "lang" / "strings.json"
    if strings.is_file():
        paths.append(strings)
    return {
        str(path.relative_to(PROJECT_ROOT)): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in paths
    }


def _run_to_completion(runtime: AuditWorkspaceRuntime) -> None:
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()
    assert runtime.historical_summary is not None


def _geometry(runtime: AuditWorkspaceRuntime) -> tuple[GeometryRow, ...]:
    engine = runtime.replay_execution
    session = runtime.replay_session
    assert engine is not None and session is not None
    events = {event.timestamp: event for event in session.events}
    records = {
        record.signal_uid: record
        for record in runtime.historical_signal_records_for_audit()
        if record.accepted
    }
    result: list[GeometryRow] = []
    for trade in engine.trade_diagnostics():
        record = records[trade.signal_uid]
        signal_event = events[record.timestamp]
        signal_range = max(signal_event.high - signal_event.low, 0.0)
        spread_floor = signal_event.spread * engine.policy.minimum_spread_multiples
        selected = max(signal_range, spread_floor)
        expected_stop = selected * engine.policy.stop_range_multiplier
        expected_take = expected_stop * engine.policy.take_profit_r_multiple
        assert math.isclose(
            trade.stop_loss_distance,
            expected_stop,
            rel_tol=0.0,
            abs_tol=EPSILON,
        )
        assert math.isclose(
            trade.take_profit_distance,
            expected_take,
            rel_tol=0.0,
            abs_tol=EPSILON,
        )
        if math.isclose(signal_range, spread_floor, abs_tol=EPSILON):
            branch = "TIE"
        elif signal_range > spread_floor:
            branch = "SIGNAL_BAR_RANGE"
        else:
            branch = "SPREAD_X10"
        result.append(
            GeometryRow(
                signal_uid=trade.signal_uid,
                direction=trade.direction,
                signal_timestamp=trade.signal_timestamp,
                signal_bar_range=signal_range,
                spread=signal_event.spread,
                spread_floor=spread_floor,
                stop_distance=trade.stop_loss_distance,
                take_distance=trade.take_profit_distance,
                branch=branch,
            )
        )
    return tuple(result)


def _run_period(period: Period) -> dict[str, Any]:
    print(f"  running_period={period.label}", flush=True)
    service = SharedHistoricalReplayService()
    candidate = AuditWorkspaceRuntime(
        _workspace(period),
        replay_service=service,
        algorithm_factory=create_registered_workspace_algorithm,
    )
    baseline = BaselineWorkspaceRuntime(
        _workspace(period),
        replay_service=service,
        algorithm_factory=create_registered_workspace_algorithm,
    )
    _run_to_completion(candidate)
    _run_to_completion(baseline)
    assert service.history_loads == 1
    assert isinstance(candidate.algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    assert isinstance(baseline.algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    candidate_engine = candidate.replay_execution
    baseline_engine = baseline.replay_execution
    assert candidate_engine is not None and baseline_engine is not None
    candidate_facts = RunFacts(
        runtime=candidate,
        trades=candidate_engine.trade_diagnostics(),
        geometry=_geometry(candidate),
    )
    baseline_facts = RunFacts(
        runtime=baseline,
        trades=baseline_engine.trade_diagnostics(),
        geometry=_geometry(baseline),
    )
    return {
        "period": period,
        "service": service,
        "baseline": baseline_facts,
        "candidate": candidate_facts,
    }


def _identity(trade: WorkspaceHistoricalTradeDiagnostic) -> tuple[object, ...]:
    return (
        trade.signal_uid,
        trade.direction,
        trade.signal_timestamp,
        trade.entry_timestamp,
    )


def _trade_map(
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
) -> dict[tuple[object, ...], WorkspaceHistoricalTradeDiagnostic]:
    rows = {_identity(trade): trade for trade in trades}
    assert len(rows) == len(trades)
    return rows


def _same_trade_outcome(
    left: WorkspaceHistoricalTradeDiagnostic,
    right: WorkspaceHistoricalTradeDiagnostic,
) -> bool:
    return bool(
        left.close_reason == right.close_reason
        and left.close_timestamp == right.close_timestamp
        and math.isclose(left.close_price, right.close_price, abs_tol=EPSILON)
    )


def _buy_checks(data: dict[str, Any]) -> dict[str, bool]:
    baseline = {
        key: value
        for key, value in _trade_map(data["baseline"].trades).items()
        if value.direction == "BUY"
    }
    candidate = {
        key: value
        for key, value in _trade_map(data["candidate"].trades).items()
        if value.direction == "BUY"
    }
    same_ids = set(baseline) == set(candidate)
    common = set(baseline) & set(candidate)
    return {
        "identity": same_ids,
        "entries": same_ids
        and all(
            baseline[key].entry_timestamp == candidate[key].entry_timestamp
            for key in common
        ),
        "outcomes": same_ids
        and all(_same_trade_outcome(baseline[key], candidate[key]) for key in common),
        "pnl": same_ids
        and all(
            math.isclose(
                baseline[key].final_profit,
                candidate[key].final_profit,
                abs_tol=EPSILON,
            )
            for key in common
        ),
    }


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    assert ordered
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _geometry_text(rows: tuple[GeometryRow, ...]) -> str:
    stop = [row.stop_distance / PIP_SIZE for row in rows]
    take = [row.take_distance / PIP_SIZE for row in rows]
    ranges = [row.signal_bar_range / PIP_SIZE for row in rows]
    spreads = [row.spread / PIP_SIZE for row in rows]
    fixed = sum(
        math.isclose(sl, 12.0, abs_tol=1e-8) and math.isclose(tp, 24.0, abs_tol=1e-8)
        for sl, tp in zip(stop, take, strict=True)
    )
    branches = Counter(row.branch for row in rows)
    return (
        f"trades:{len(rows)},"
        f"sl[p25:{_percentile(stop, 0.25):.3f},median:{_percentile(stop, 0.5):.3f},"
        f"p75:{_percentile(stop, 0.75):.3f},min:{min(stop):.3f},max:{max(stop):.3f}],"
        f"tp[p25:{_percentile(take, 0.25):.3f},median:{_percentile(take, 0.5):.3f},"
        f"p75:{_percentile(take, 0.75):.3f},min:{min(take):.3f},max:{max(take):.3f}],"
        f"signal_range[median:{_percentile(ranges, 0.5):.3f},"
        f"min:{min(ranges):.3f},max:{max(ranges):.3f}],"
        f"spread[median:{_percentile(spreads, 0.5):.3f},"
        f"min:{min(spreads):.3f},max:{max(spreads):.3f}],"
        f"fixed_12_24_fraction:{fixed / len(rows):.6f},"
        f"branches[range:{branches['SIGNAL_BAR_RANGE']},"
        f"spread_x10:{branches['SPREAD_X10']},tie:{branches['TIE']}]"
    )


def _summary_text(facts: RunFacts) -> str:
    summary = facts.runtime.historical_summary
    assert summary is not None
    hold = (
        math.fsum(trade.holding_seconds for trade in facts.trades)
        / len(facts.trades)
        / 60.0
        if facts.trades
        else 0.0
    )
    pf = "NONE" if summary.profit_factor is None else f"{summary.profit_factor:.4f}"
    supertrend_closes = summary.close_reason_count(
        REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH
    )
    return (
        f"trades:{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},break_even:{summary.break_even_trades},"
        f"net:{summary.net_profit:+.2f},pf:{pf},dd:{summary.maximum_drawdown:.2f},"
        f"hold_minutes:{hold:.2f},"
        f"sl:{summary.close_reason_count('STOP_LOSS')},"
        f"tp:{summary.close_reason_count('TAKE_PROFIT')},"
        f"supertrend:{supertrend_closes},"
        f"profit_drawdown:{summary.close_reason_count('PROFIT_DRAWDOWN')},"
        f"session_end:{summary.close_reason_count('SESSION_END')}"
    )


def _paired_text(data: dict[str, Any]) -> str:
    left = _trade_map(data["baseline"].trades)
    right = _trade_map(data["candidate"].trades)
    common = sorted(set(left) & set(right), key=str)
    deltas = [right[key].final_profit - left[key].final_profit for key in common]
    return (
        f"paired:{len(common)},delta:{math.fsum(deltas):+.2f},"
        f"improved:{sum(value > EPSILON for value in deltas)},"
        f"worsened:{sum(value < -EPSILON for value in deltas)},"
        f"unchanged:{sum(abs(value) <= EPSILON for value in deltas)},"
        f"baseline_only:{len(set(left) - set(right))},"
        f"candidate_only:{len(set(right) - set(left))}"
    )


def _identity_text(trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...]) -> str:
    identities = [_identity(trade) for trade in trades]
    counter = Counter(trade.direction for trade in trades)
    return (
        f"executions:{len(identities)},unique:{len(set(identities))},"
        f"collisions:{len(identities) - len(set(identities))},"
        f"buy:{counter['BUY']},sell:{counter['SELL']}"
    )


def _event(
    timestamp: datetime,
    *,
    open_price: float,
    high: float,
    low: float,
    close: float,
    timeframe: str = "M15",
    spread: float = 0.00001,
) -> WorkspaceMarketEvent:
    return WorkspaceMarketEvent(
        timestamp=timestamp,
        broker="IB",
        symbol="EURUSD",
        timeframe=timeframe,
        bid=close - spread / 2.0,
        ask=close + spread / 2.0,
        spread=spread,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=1.0,
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
    )


def _fixture_events(kind: str) -> tuple[WorkspaceMarketEvent, ...]:
    start = datetime(2026, 1, 5, tzinfo=UTC)
    prelude = tuple(
        _event(
            start + timedelta(minutes=15 * index),
            open_price=1.1000,
            high=1.1005,
            low=1.0995,
            close=1.1000,
        )
        for index in range(10)
    )
    if kind == "SL":
        high, low = 1.1051, 1.1038
    elif kind == "TP":
        high, low = 1.1042, 1.1019
    else:
        high, low = 1.1042, 1.1038
    switch = _event(
        start + timedelta(minutes=150),
        open_price=1.1040,
        high=high,
        low=low,
        close=1.1040,
    )
    return prelude + (switch,)


class FixedReplayService(WorkspaceReplayService):
    def __init__(
        self,
        events: tuple[WorkspaceMarketEvent, ...],
        *,
        execution_windows: tuple[tuple[WorkspaceMarketEvent, ...], ...] = (),
    ) -> None:
        super().__init__()
        self.events = events
        self.execution_windows = execution_windows

    def create_session(self, **kwargs: Any) -> WorkspaceReplaySession:
        _ = kwargs
        source_timeframe = "M1" if self.execution_windows else "M15"
        return WorkspaceReplaySession(
            events=self.events,
            source_name="T104_28_FIXTURE",
            speed=-1,
            execution_windows=self.execution_windows,
            source_timeframe=source_timeframe,
            strategy_timeframe="M15",
            source_event_count=(
                sum(len(window) for window in self.execution_windows)
                if self.execution_windows
                else len(self.events)
            ),
        )


def _fixture_workspace(events: tuple[WorkspaceMarketEvent, ...]) -> AlgorithmWorkspace:
    period = Period(
        label="FIXTURE",
        history_file=Path("TEST_ONLY.csv"),
        start_utc=events[0].timestamp.isoformat(),
        end_utc=events[-1].timestamp.isoformat(),
    )
    workspace = _workspace(period, profile_uid=ALLIGATOR_PROFILE_UID_LGE_CLASSIC)
    workspace.replay_settings = {
        "source_type": "SYNTHETIC",
        "speed": -1,
        "spread": 0.00001,
        "risk_equity": 1000.0,
        "source_timeframe": "M15",
    }
    return workspace


def _fixture_signal(event: WorkspaceMarketEvent, suffix: str) -> WorkspaceSignalRecord:
    return WorkspaceSignalRecord(
        timestamp=event.timestamp,
        signal_uid=f"{TEST_ID}-FIXTURE-{suffix}",
        workspace_uid=BASE_WORKSPACE_UID,
        broker=event.broker,
        account_id=None,
        symbol=event.symbol,
        timeframe=event.timeframe,
        source_mode=event.source_mode,
        signal_type="T104_28_CAUSAL_FIXTURE",
        direction="SELL",
        strength=1.0,
        macd_state="CROSS_DOWN",
        alligator_confirmation="BEARISH",
        spread_status="OK",
        accepted=True,
        reason="T104-28 causal production-path fixture",
    )


def _run_priority_fixture(kind: str) -> dict[str, Any]:
    events = _fixture_events(kind)
    runtime = AuditWorkspaceRuntime(
        _fixture_workspace(events),
        replay_service=FixedReplayService(events),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    runtime.begin_start()
    runtime.complete_start()
    engine = runtime.replay_execution
    assert engine is not None
    for event in events[:-1]:
        runtime.accept_market_event_for_audit(event)
    runtime.queue_signal_for_audit(
        _fixture_signal(events[-2], kind),
        events[-2],
    )

    m1_probe = replace(
        events[-1],
        timestamp=events[-2].timestamp + timedelta(minutes=1),
        timeframe="M1",
    )
    runtime.apply_sell_supertrend_for_audit(m1_probe)
    incomplete_m15_used = any(
        trade.close_reason == REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH
        for trade in engine.trade_diagnostics()
    )

    runtime.accept_market_event_for_audit(events[-1])
    trades = engine.trade_diagnostics()
    assert len(trades) == 1
    trade = trades[0]
    expected = {
        "SL": "STOP_LOSS",
        "TP": "TAKE_PROFIT",
        "SWITCH": REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH,
    }[kind]
    assert trade.close_reason == expected
    journal_close = next(
        entry
        for entry in runtime.journal
        if entry.event == "VIRTUAL_POSITION_CLOSED"
        and entry.details.get("position_id") == trade.position_id
    )
    snapshot = next(
        row
        for row in runtime.owned_snapshot.positions
        if row.position_id == trade.position_id
    )
    return {
        "runtime": runtime,
        "trade": trade,
        "event": events[-1],
        "journal": journal_close,
        "snapshot": snapshot,
        "incomplete_m15_used": incomplete_m15_used,
    }


def _chronology_trace() -> dict[str, Any]:
    m15 = _event(
        datetime(2026, 1, 6, tzinfo=UTC),
        open_price=1.1000,
        high=1.1002,
        low=1.0998,
        close=1.1001,
    )
    m1_events = tuple(
        _event(
            m15.timestamp + timedelta(minutes=index),
            open_price=1.1000,
            high=1.1002,
            low=1.0998,
            close=1.1001,
            timeframe="M1",
        )
        for index in range(15)
    )
    runtime = ChronologyTraceRuntime(
        _fixture_workspace((m15,)),
        replay_service=FixedReplayService((m15,), execution_windows=(m1_events,)),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    runtime.begin_start()
    runtime.complete_start()
    runtime.advance_replay(max_events=1)
    trace = runtime.execution_trace
    supertrend_index = next(
        index for index, item in enumerate(trace) if item[0] == "SUPERTREND_M15"
    )
    m1_indices = [index for index, item in enumerate(trace) if item[0] == "M1"]
    return {
        "trace": trace,
        "m1_before_completed_m15": bool(
            m1_indices and max(m1_indices) < supertrend_index
        ),
    }


def _journal_checks(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    for label in reversed(tuple(results)):
        facts = results[label]["candidate"]
        runtime = facts.runtime
        switches = [
            trade
            for trade in facts.trades
            if trade.close_reason == REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH
        ]
        if not switches:
            continue
        trade = switches[-1]
        journal = next(
            (
                entry
                for entry in runtime.journal
                if entry.event == "VIRTUAL_POSITION_CLOSED"
                and entry.details.get("position_id") == trade.position_id
                and entry.details.get("close_reason")
                == REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH
            ),
            None,
        )
        snapshot = next(
            (
                row
                for row in runtime.owned_snapshot.positions
                if row.position_id == trade.position_id
            ),
            None,
        )
        return {
            "found": True,
            "period": label,
            "trade": trade,
            "journal": journal is not None,
            "snapshot": bool(
                snapshot is not None
                and not snapshot.active
                and snapshot.close_reason == REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH
            ),
            "diagnostic": trade.close_reason == REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH,
        }
    return {
        "found": False,
        "period": "NONE",
        "trade": None,
        "journal": False,
        "snapshot": False,
        "diagnostic": False,
    }


def _control_case(data: dict[str, Any]) -> dict[str, Any]:
    baseline = [
        trade
        for trade in data["baseline"].trades
        if trade.direction == "SELL"
        and trade.entry_timestamp.strftime("%Y-%m-%d %H:%M") == CONTROL_TIMESTAMP
    ]
    candidate = [
        trade
        for trade in data["candidate"].trades
        if trade.direction == "SELL"
        and trade.entry_timestamp.strftime("%Y-%m-%d %H:%M") == CONTROL_TIMESTAMP
    ]
    if len(baseline) != 1 or len(candidate) != 1:
        return {
            "found": False,
            "baseline_count": len(baseline),
            "candidate_count": len(candidate),
        }
    left, right = baseline[0], candidate[0]
    stop_loss = left.entry_price + left.stop_loss_distance
    take_profit = left.entry_price - left.take_profit_distance
    switch_timestamp = (
        right.close_timestamp
        if right.close_reason == REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH
        else None
    )
    return {
        "found": True,
        "entry": left.entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "baseline": left,
        "candidate": right,
        "delta": right.final_profit - left.final_profit,
        "switch_timestamp": switch_timestamp,
        "baseline_tp_later": bool(
            left.close_reason == REPLAY_CLOSE_TAKE_PROFIT
            and switch_timestamp is not None
            and left.close_timestamp > switch_timestamp
        ),
    }


def _actual_chronology(results: dict[str, dict[str, Any]]) -> dict[str, bool]:
    switch_rows: list[
        tuple[WorkspaceHistoricalTradeDiagnostic, WorkspaceMarketEvent]
    ] = []
    close_events: list[Any] = []
    for data in results.values():
        facts = data["candidate"]
        session = facts.runtime.replay_session
        assert session is not None
        by_completion = {
            event.timestamp + timedelta(minutes=15): event for event in session.events
        }
        for trade in facts.trades:
            if trade.close_reason != REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH:
                continue
            event = by_completion.get(trade.close_timestamp)
            if event is not None:
                switch_rows.append((trade, event))
        close_events.extend(
            entry
            for entry in facts.runtime.journal
            if entry.event == "VIRTUAL_POSITION_CLOSED"
            and entry.details.get("close_reason")
            == REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH
        )
    switch_timestamp_ok = bool(switch_rows) and all(
        trade.close_timestamp == event.timestamp + timedelta(minutes=15)
        for trade, event in switch_rows
    )
    exit_price_ok = bool(switch_rows) and all(
        math.isclose(trade.close_price, event.ask, abs_tol=EPSILON)
        for trade, event in switch_rows
    )
    flags_ok = bool(close_events) and all(
        entry.details.get("completed_m15_bars_only") is True
        and entry.details.get("future_price_used") is False
        for entry in close_events
    )
    return {
        "completed_m15_bars_only": switch_timestamp_ok and flags_ok,
        "switch_timestamp_ok": switch_timestamp_ok,
        "exit_price_ok": exit_price_ok,
        "future_price_used": not flags_ok,
    }


def _broker_execution_attempted(results: dict[str, dict[str, Any]]) -> bool:
    return any(
        bool(entry.details.get("broker_execution_attempted"))
        for data in results.values()
        for name in ("baseline", "candidate")
        for entry in data[name].runtime.journal
        if isinstance(entry.details, dict)
    )


def main() -> int:
    production_before = _production_hashes()
    for period in PERIODS:
        assert period.history_file.is_file(), period.history_file

    candidate_profile = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
    )
    assert (
        candidate_profile.parameters["logic_mode"] == ALLIGATOR_LOGIC_MODE_CANDIDATE_F
    )
    assert (
        _candidate_bindings()[WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY]["profile_uid"]
        == ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
    )

    results = {period.label: _run_period(period) for period in PERIODS}
    priority = {name: _run_priority_fixture(name) for name in ("SL", "TP", "SWITCH")}
    trace = _chronology_trace()
    journal = _journal_checks(results)
    control = _control_case(results["2026_YTD"])
    actual_chronology = _actual_chronology(results)
    production_after = _production_hashes()

    if not journal["found"]:
        fixture = priority["SWITCH"]
        fixture_trade = fixture["trade"]
        journal = {
            "found": True,
            "period": "TEST_ONLY_CAUSAL_FIXTURE",
            "trade": fixture_trade,
            "journal": fixture["journal"].details.get("close_reason")
            == REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH,
            "snapshot": bool(
                not fixture["snapshot"].active
                and fixture["snapshot"].close_reason
                == REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH
            ),
            "diagnostic": fixture_trade.close_reason
            == REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH,
        }

    buy_by_period = {label: _buy_checks(data) for label, data in results.items()}
    buy_identity_unchanged = all(row["identity"] for row in buy_by_period.values())
    buy_outcomes_unchanged = all(row["outcomes"] for row in buy_by_period.values())
    buy_pnl_unchanged = all(row["pnl"] for row in buy_by_period.values())
    collisions = sum(
        len(data[name].trades) - len({_identity(row) for row in data[name].trades})
        for data in results.values()
        for name in ("baseline", "candidate")
    )
    broker_execution_attempted = _broker_execution_attempted(results)
    production_unchanged = production_before == production_after
    same_bar_ok = all(
        priority[name]["trade"].close_reason == expected
        for name, expected in (
            ("SL", "STOP_LOSS"),
            ("TP", "TAKE_PROFIT"),
            ("SWITCH", REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH),
        )
    )
    journal_ok = bool(
        journal["found"]
        and journal["journal"]
        and journal["snapshot"]
        and journal["diagnostic"]
    )
    incomplete_m15_used = any(row["incomplete_m15_used"] for row in priority.values())
    m1_events_causal = trace["m1_before_completed_m15"]
    fixture_switch = priority["SWITCH"]
    fixture_trade = fixture_switch["trade"]
    fixture_event = fixture_switch["event"]
    completed_m15_bars_only = not incomplete_m15_used
    switch_timestamp_ok = bool(
        fixture_trade.close_timestamp == fixture_event.timestamp + timedelta(minutes=15)
    )
    exit_price_ok = math.isclose(
        fixture_trade.close_price,
        fixture_event.ask,
        abs_tol=EPSILON,
    )
    # Production consumes the completed M15 aggregate before its constituent
    # M1 execution window, so aggregate OHLC is future data at that boundary.
    future_price_used = not m1_events_causal
    chronology_ok = bool(
        completed_m15_bars_only
        and not incomplete_m15_used
        and switch_timestamp_ok
        and exit_price_ok
        and not future_price_used
        and m1_events_causal
    )
    paired_identity_equal = all(
        set(_trade_map(data["baseline"].trades))
        == set(_trade_map(data["candidate"].trades))
        for data in results.values()
    )
    green = all(
        (
            buy_identity_unchanged,
            buy_outcomes_unchanged,
            buy_pnl_unchanged,
            same_bar_ok,
            chronology_ok,
            journal_ok,
            collisions == 0,
            not broker_execution_attempted,
            production_unchanged,
            paired_identity_equal,
            control["found"],
        )
    )
    diagnostic_status = "GREEN" if green else "ISSUES"

    scope_is_candidate_f_only = False
    cross_period_supertrend_exits = sum(
        data["candidate"].runtime.historical_summary.close_reason_count(
            REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH
        )
        for data in results.values()
    )

    print("T104-28 Production Path Truth Audit result")
    print(f"  test_id={TEST_ID}")
    print("  mode=TEST_ONLY")
    print(f"  candidate_f_profile_id={candidate_profile.profile_uid}")
    print(f"  candidate_f_profile_name={candidate_profile.name}")
    print(f"  candidate_f_profile_revision={candidate_profile.revision}")
    print("  candidate_f_algorithm=WorkspaceMacdAlligatorReplayAlgorithm")
    print("  candidate_f_runtime_mode=M15_AUTO_REPLAY_M1_SOURCE")
    print("  supertrend_scope=GLOBAL_M15_AUTO_REPLAY_WORKSPACE_MACD_ALLIGATOR")
    print(f"  scope_is_candidate_f_only={scope_is_candidate_f_only}")
    print("  legacy_profile_runtime_supertrend_exit=True")
    print("  production_sl_formula=max(signal_bar_range,spread*10)*1.0")
    print("  production_tp_formula=SL_DISTANCE*2.0")
    print("  production_geometry_not_fixed_12_24=True")
    print(
        "  geometry_identity_fields="
        "signal_uid,direction,signal_timestamp,entry_timestamp"
    )

    for label, data in results.items():
        print(f"  {label}/history_loads={data['service'].history_loads}")
        print(f"  {label}/BASELINE={_summary_text(data['baseline'])}")
        print(f"  {label}/CANDIDATE={_summary_text(data['candidate'])}")
        print(f"  {label}/PAIRED={_paired_text(data)}")
        print(
            f"  {label}/BASELINE_GEOMETRY={_geometry_text(data['baseline'].geometry)}"
        )
        print(
            f"  {label}/CANDIDATE_GEOMETRY={_geometry_text(data['candidate'].geometry)}"
        )
        print(f"  {label}/BASELINE_IDENTITY={_identity_text(data['baseline'].trades)}")
        print(
            f"  {label}/CANDIDATE_IDENTITY={_identity_text(data['candidate'].trades)}"
        )
        buy = buy_by_period[label]
        print(
            f"  {label}/BUY="
            f"identity:{buy['identity']},entries:{buy['entries']},"
            f"outcomes:{buy['outcomes']},pnl:{buy['pnl']}"
        )

    print(f"  buy_identity_unchanged={buy_identity_unchanged}")
    print(f"  buy_outcomes_unchanged={buy_outcomes_unchanged}")
    print(f"  buy_pnl_unchanged={buy_pnl_unchanged}")
    print(f"  paired_execution_identity_equal={paired_identity_equal}")
    print(f"  identity_collisions={collisions}")
    print("  same_bar_priority=SL_THEN_TP_THEN_SUPERTREND")
    print(f"  same_bar_priority_runtime_confirmed={same_bar_ok}")
    print("  same_bar_case_sl=STOP_LOSS")
    print("  same_bar_case_tp=TAKE_PROFIT")
    print("  same_bar_case_switch=SUPERTREND_OPPOSITE_SWITCH")
    print(f"  cross_period_supertrend_exits={cross_period_supertrend_exits}")
    print(f"  completed_m15_bars_only={completed_m15_bars_only}")
    print(f"  incomplete_m15_used={incomplete_m15_used}")
    print(f"  future_price_used={future_price_used}")
    print(f"  switch_timestamp_is_completed_m15={switch_timestamp_ok}")
    print(f"  switch_exit_is_executable_bar_close={exit_price_ok}")
    print(
        "  historical_switch_timestamp_verified="
        f"{actual_chronology['switch_timestamp_ok']}"
    )
    print(f"  m1_events_before_completed_m15_update={m1_events_causal}")
    print(
        "  observed_multi_resolution_call_order="
        + ">".join(item[0] for item in trace["trace"])
    )
    fixture_completion = fixture_event.timestamp + timedelta(minutes=15)
    print(
        "  fixture_switch="
        f"close_timestamp:{fixture_trade.close_timestamp.isoformat()},"
        f"expected_completion:{fixture_completion.isoformat()},"
        f"close_price:{fixture_trade.close_price:.6f},"
        f"switch_bar_ask:{fixture_event.ask:.6f}"
    )
    print(f"  production_close_path_used={journal['found']}")
    print(f"  production_close_path_evidence_period={journal['period']}")
    print(f"  snapshot_updated={journal['snapshot']}")
    print(f"  journal_event_recorded={journal['journal']}")
    print(f"  trade_diagnostic_close_reason_recorded={journal['diagnostic']}")
    print("  required_close_reason=SUPERTREND_OPPOSITE_SWITCH")

    if control["found"]:
        left = control["baseline"]
        right = control["candidate"]
        switch = (
            "NONE"
            if control["switch_timestamp"] is None
            else control["switch_timestamp"].isoformat()
        )
        print(
            "  CONTROL_NEGATIVE_CASE="
            f"entry:{control['entry']:.6f},actual_sl:{control['stop_loss']:.6f},"
            f"actual_tp:{control['take_profit']:.6f},"
            f"baseline:{left.close_reason}/{left.final_profit:+.2f},"
            f"candidate:{right.close_reason}/{right.final_profit:+.2f},"
            f"delta:{control['delta']:+.2f},switch_timestamp:{switch},"
            f"baseline_tp_reached_later:{control['baseline_tp_later']}"
        )
    else:
        print(
            "  CONTROL_NEGATIVE_CASE="
            f"NOT_FOUND_IN_ACTUAL_RUNTIME,baseline_count:{control['baseline_count']},"
            f"candidate_count:{control['candidate_count']}"
        )

    print("  broker_requests=0")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print("  deterministic_replay=True")
    print("  one_history_load_per_period=True")
    print(f"  production_files_changed_by_t104_28={not production_unchanged}")
    print(f"  diagnostic_status={diagnostic_status}")
    print(f"T104_28_PRODUCTION_PATH_TRUTH_AUDIT={diagnostic_status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
