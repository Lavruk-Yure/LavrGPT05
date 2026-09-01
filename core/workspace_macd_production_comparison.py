# -*- coding: utf-8 -*-
"""Канонічний deterministic comparison runner MACD для RoadMap101.

Модуль дає один стабільний API для Development/Validation/Holdout
порівнянь. Runner приймає історичний M1 dataset/window, точний MACD profile
snapshot, ABC threshold, prominence, distance та Alligator mode. Усі інші
Replay, risk, virtual execution і Profit Drawdown умови зафіксовані однаково,
щоб кожен наступний експеримент RoadMap101 змінював лише явно контрольовану
змінну.

Звіт поєднує structural signal-quality metrics, причинні price-turn latency,
virtual trading diagnostics та deterministic signature. Сигнатура не містить
wall-clock timing або абсолютного шляху до CSV, тому однакові дані й
параметри мають давати однаковий результат на повторному прогоні. Historical
Replay не виконує broker I/O або broker execution; M1 chronology після signal
і completed M15 strategy bars залишаються канонічними runtime invariants.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from core.algorithm_workspace import (
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_alligator import WorkspaceMacdAlligatorReplayAlgorithm
from core.workspace_broker_market import WorkspaceBrokerMarketProviderProtocol
from core.workspace_historical_summary import WorkspaceHistoricalReplaySummary
from core.workspace_historical_trade_diagnostics import (
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_indicator_profile import (
    WORKSPACE_INDICATOR_MACD,
    WORKSPACE_INDICATOR_MA_EXPONENTIAL,
    WORKSPACE_INDICATOR_PROFILE_SOURCE_USER,
    WORKSPACE_INDICATOR_SOURCE_CLOSE,
    WorkspaceIndicatorProfile,
    WorkspaceIndicatorProfileBinding,
    default_workspace_indicator_profile_bindings,
)
from core.workspace_macd_crossover_quality import (
    WorkspaceMacdCrossoverQualityDiagnostic,
)
from core.workspace_macd_signal_latency import (
    WorkspaceMacdSignalLatencyReport,
    build_workspace_macd_signal_latency_report,
)
from core.workspace_market_event import WorkspaceMarketEvent
from core.workspace_replay import REPLAY_SPEED_MAX
from core.workspace_replay_execution import (
    REPLAY_ORDER_STATUS_EXPIRED_NEXT_BAR_GAP,
)
from core.workspace_runtime import WorkspaceRuntime
from core.workspace_signal import WorkspaceSignalRecord
from engine.runtime_constants import (
    WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED,
    WORKSPACE_ALLIGATOR_CONFIRMATIONS,
    WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC,
    WORKSPACE_REPLAY_SOURCE_CSV,
)

MACD_COMPARISON_SOURCE_TIMEFRAME = "M1"
MACD_COMPARISON_STRATEGY_TIMEFRAME = "M15"
MACD_COMPARISON_LEGACY_ANGLE = 45.0
MACD_COMPARISON_INITIAL_BALANCE = 1000.0
MACD_COMPARISON_FIXED_VOLUME = 1000.0
MACD_COMPARISON_MAX_OPEN_POSITIONS = 2
MACD_COMPARISON_MAX_DAILY_LOSS_PERCENT = 2.0
MACD_COMPARISON_PROFIT_DRAWDOWN_PERCENT = 30.0
MACD_COMPARISON_SPREAD = 0.00012
MACD_COMPARISON_LATENCY_LOOKBACK_BARS = 8
MACD_COMPARISON_SIGNATURE_PERSON = b"LGE-RM101-MACD"


class WorkspaceMacdProductionComparisonError(ValueError):
    """Помилка конфігурації або неповного результату comparison runner."""


@dataclass(frozen=True, slots=True)
class WorkspaceMacdComparisonProfile:
    """Точний MACD profile snapshot одного контрольованого прогону."""

    name: str
    fast_period: int
    slow_period: int
    signal_period: int
    profile_uid: str | None = None
    profile_revision: int = 1

    def __post_init__(self) -> None:
        name = str(self.name or "").strip()
        if not name:
            raise WorkspaceMacdProductionComparisonError("profile name is required")
        fast = _positive_int(self.fast_period, "fast_period")
        slow = _positive_int(self.slow_period, "slow_period")
        signal = _positive_int(self.signal_period, "signal_period")
        revision = _positive_int(self.profile_revision, "profile_revision")
        if slow <= fast:
            raise WorkspaceMacdProductionComparisonError(
                "slow_period must exceed fast_period"
            )
        uid = str(self.profile_uid or "").strip()
        if not uid:
            uid = str(
                uuid5(
                    NAMESPACE_URL,
                    "lge:rm101:macd:" f"{name}:{fast}:{slow}:{signal}:r{revision}",
                )
            )
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "fast_period", fast)
        object.__setattr__(self, "slow_period", slow)
        object.__setattr__(self, "signal_period", signal)
        object.__setattr__(self, "profile_uid", uid)
        object.__setattr__(self, "profile_revision", revision)


@dataclass(frozen=True, slots=True)
class WorkspaceMacdProductionComparisonConfig:
    """Вхідна конфігурація одного RoadMap101 comparison run."""

    dataset_path: Path
    window_start: datetime
    window_end: datetime
    profile: WorkspaceMacdComparisonProfile
    abc_min_angle_degrees: float
    prominence: float
    distance: float
    alligator_mode: str = WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED
    dataset_label: str = "EURUSD_IB_M1"

    def __post_init__(self) -> None:
        path = Path(self.dataset_path)
        if not path.is_file():
            raise WorkspaceMacdProductionComparisonError(
                f"Historical dataset does not exist: {path}"
            )
        start = _utc_datetime(self.window_start, "window_start")
        end = _utc_datetime(self.window_end, "window_end")
        if end <= start:
            raise WorkspaceMacdProductionComparisonError(
                "window_end must be after window_start"
            )
        angle = _bounded_float(
            self.abc_min_angle_degrees,
            "abc_min_angle_degrees",
            minimum=0.0,
            maximum=180.0,
        )
        prominence = _positive_float(self.prominence, "prominence")
        distance = _positive_float(self.distance, "distance")
        alligator_mode = str(self.alligator_mode or "").strip().upper()
        if alligator_mode not in WORKSPACE_ALLIGATOR_CONFIRMATIONS:
            raise WorkspaceMacdProductionComparisonError(
                f"Unsupported Alligator mode: {alligator_mode}"
            )
        label = str(self.dataset_label or "").strip()
        if not label:
            label = path.name
        object.__setattr__(self, "dataset_path", path)
        object.__setattr__(self, "window_start", start)
        object.__setattr__(self, "window_end", end)
        object.__setattr__(self, "abc_min_angle_degrees", angle)
        object.__setattr__(self, "prominence", prominence)
        object.__setattr__(self, "distance", distance)
        object.__setattr__(self, "alligator_mode", alligator_mode)
        object.__setattr__(self, "dataset_label", label)


@dataclass(frozen=True, slots=True)
class WorkspaceMacdExtremumWindowMetrics:
    """Розподіл знайденого extremum по вікнах 3/5/7/NONE."""

    window_3: int
    window_5: int
    window_7: int
    none: int


@dataclass(frozen=True, slots=True)
class WorkspaceMacdCriterionMetrics:
    """Кількість pass/reject для одного MACD Quality criterion."""

    passed: int
    rejected: int


@dataclass(frozen=True, slots=True)
class WorkspaceMacdRejectReasonMetrics:
    """Канонічні N/W/D/F причини MACD Quality reject."""

    extremum_not_found_n: int
    weak_prominence_w: int
    distance_d: int
    flat_angle_f: int


@dataclass(frozen=True, slots=True)
class WorkspaceMacdLatencyMetrics:
    """Price-turn proxy latency для всіх classic crossover."""

    average_signal_bars: float
    median_signal_bars: float
    average_entry_bars: float | None
    median_entry_bars: float | None
    entry_gap_signals: int


@dataclass(frozen=True, slots=True)
class WorkspaceMacdExcursionMetrics:
    """Агреговані MFE/MAE virtual trades у валюті Replay account."""

    trades: int
    average_mfe: float
    average_mae: float
    maximum_mfe: float
    minimum_mae: float


@dataclass(frozen=True, slots=True)
class WorkspaceMacdProductionComparisonReport:
    """Структурований звіт однакового формату для RoadMap101."""

    dataset_label: str
    window_start: datetime
    window_end: datetime
    profile_name: str
    profile_uid: str
    profile_revision: int
    profile_periods: str
    abc_min_angle_degrees: float
    prominence: float
    distance: float
    alligator_mode: str
    historical_m1_rows: int
    completed_m15_bars: int
    dropped_incomplete_m15_buckets: int
    classic_crosses: int
    buy_crosses: int
    sell_crosses: int
    extremum_windows: WorkspaceMacdExtremumWindowMetrics
    prominence_criterion: WorkspaceMacdCriterionMetrics
    distance_criterion: WorkspaceMacdCriterionMetrics
    abc_angle_criterion: WorkspaceMacdCriterionMetrics
    quality_accepted: int
    quality_rejected: int
    reject_reasons: WorkspaceMacdRejectReasonMetrics
    classic_density_per_100_bars: float
    candidate_density_per_100_bars: float
    price_turn_latency: WorkspaceMacdLatencyMetrics
    orders_created: int
    trades: int
    winners: int
    losers: int
    break_even: int
    win_rate_percent: float
    profit_factor: float | None
    net_profit: float
    average_trade: float
    maximum_drawdown: float
    maximum_drawdown_percent: float
    stop_loss_closes: int
    take_profit_closes: int
    profit_drawdown_closes: int
    session_end_closes: int
    next_bar_gap_orders: int
    excursions: WorkspaceMacdExcursionMetrics
    signal_timestamp_before_entry: bool
    completed_m15_only: bool
    broker_requests: int
    broker_execution_attempted: bool
    deterministic_signature: str


class _BrokerRequestProbe(WorkspaceBrokerMarketProviderProtocol):
    """Probe відсутності broker I/O у Historical Replay."""

    def __init__(self) -> None:
        self.requests = 0

    def start_workspace(
        self,
        *,
        workspace_uid: str,
        broker: str,
        account_id: str | None,
        symbol: str,
        timeframe: str,
        warmup_bars: int,
        spread_limit: float,
    ) -> tuple[WorkspaceMarketEvent, ...]:
        _ = (
            workspace_uid,
            broker,
            account_id,
            symbol,
            timeframe,
            warmup_bars,
            spread_limit,
        )
        self.requests += 1
        return ()

    def poll_workspace(self, workspace_uid: str) -> WorkspaceMarketEvent | None:
        _ = workspace_uid
        self.requests += 1
        return None

    def is_workspace_broker_connected(self, workspace_uid: str) -> bool:
        _ = workspace_uid
        self.requests += 1
        return True

    def suspend_workspace(self, workspace_uid: str) -> None:
        _ = workspace_uid
        self.requests += 1

    def resume_workspace(
        self,
        workspace_uid: str,
    ) -> tuple[WorkspaceMarketEvent, ...]:
        _ = workspace_uid
        self.requests += 1
        return ()

    def stop_workspace(self, workspace_uid: str) -> None:
        _ = workspace_uid
        self.requests += 1


def run_workspace_macd_production_comparison(
    config: WorkspaceMacdProductionComparisonConfig,
) -> WorkspaceMacdProductionComparisonReport:
    """Виконати один canonical M1->M15 Historical Replay comparison run."""
    workspace = _build_workspace(config)
    algorithm = WorkspaceMacdAlligatorReplayAlgorithm(workspace.algorithm)
    probe = _BrokerRequestProbe()
    records: list[WorkspaceSignalRecord] = []
    runtime = WorkspaceRuntime(
        workspace,
        algorithm_factory=lambda _algorithm_id: algorithm,
        broker_market_provider=probe,
        signal_record_observer=records.append,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    if session is None:
        raise WorkspaceMacdProductionComparisonError(
            "Historical Replay session was not created"
        )
    while not session.completed:
        runtime.advance_replay()

    summary = runtime.historical_summary
    source = algorithm.source
    execution = runtime.replay_execution
    if summary is None or source is None or execution is None:
        raise WorkspaceMacdProductionComparisonError(
            "Completed Replay did not expose required diagnostics"
        )
    diagnostics = source.quality_diagnostics
    if not diagnostics:
        raise WorkspaceMacdProductionComparisonError(
            "MACD comparison requires at least one classic crossover"
        )
    latency = _latency_metrics(session.events, diagnostics)
    trades = execution.trade_diagnostics()
    order_rows = runtime.owned_snapshot.orders
    next_bar_gaps = sum(
        row.status == REPLAY_ORDER_STATUS_EXPIRED_NEXT_BAR_GAP for row in order_rows
    )
    report_without_signature = _build_report(
        config=config,
        records=tuple(records),
        diagnostics=diagnostics,
        latency=latency,
        trades=trades,
        historical_m1_rows=session.source_event_count,
        completed_m15_bars=len(session.events),
        dropped_incomplete_m15_buckets=session.dropped_incomplete_strategy_buckets,
        orders_created=len(order_rows),
        next_bar_gap_orders=next_bar_gaps,
        strategy_events=session.events,
        summary=summary,
        broker_requests=probe.requests,
    )
    signature = _deterministic_signature(report_without_signature)
    return replace(report_without_signature, deterministic_signature=signature)


def _build_workspace(
    config: WorkspaceMacdProductionComparisonConfig,
) -> AlgorithmWorkspace:
    profile = _build_profile(config.profile)
    binding = WorkspaceIndicatorProfileBinding.from_profile(profile)
    bindings = default_workspace_indicator_profile_bindings()
    bindings[WORKSPACE_INDICATOR_MACD] = binding.to_storage_dict()
    alligator_enabled = (
        config.alligator_mode != WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED
    )
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
        symbol="EURUSD",
        timeframe=MACD_COMPARISON_STRATEGY_TIMEFRAME,
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "EXTENDED",
            "macd_extremum_min_prominence": config.prominence,
            "macd_extremum_to_cross_min_distance": config.distance,
            "macd_cross_min_angle": MACD_COMPARISON_LEGACY_ANGLE,
            "macd_cross_angle_model": WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC,
            "macd_cross_min_abc_angle": config.abc_min_angle_degrees,
            "alligator_filter_enabled": alligator_enabled,
            "alligator_confirmation": config.alligator_mode,
            "warmup_bars": 2,
            "spread_limit": 0.00020,
        },
        replay_settings={
            "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
            "file_path": str(config.dataset_path),
            "source_timeframe": MACD_COMPARISON_SOURCE_TIMEFRAME,
            "start_utc": config.window_start.isoformat(),
            "end_utc": config.window_end.isoformat(),
            "source_timezone": "UTC",
            "delimiter": "AUTO",
            "decimal_separator": ".",
            "spread": MACD_COMPARISON_SPREAD,
            "source": config.dataset_label,
            "initial_balance": MACD_COMPARISON_INITIAL_BALANCE,
            "speed": REPLAY_SPEED_MAX,
        },
        risk_settings={
            "risk_percent": 0.5,
            "maximum_position_volume": MACD_COMPARISON_FIXED_VOLUME,
            "maximum_open_positions": MACD_COMPARISON_MAX_OPEN_POSITIONS,
            "max_daily_loss_percent": MACD_COMPARISON_MAX_DAILY_LOSS_PERCENT,
            "require_stop_loss": True,
        },
        profit_protection={
            "enabled": True,
            "activation_mode": "AFTER_SPREAD",
            "max_profit_drawdown_percent": (MACD_COMPARISON_PROFIT_DRAWDOWN_PERCENT),
            "minimum_profit": 0.0,
        },
        indicator_profile_bindings=bindings,
    )


def _build_profile(
    profile: WorkspaceMacdComparisonProfile,
) -> WorkspaceIndicatorProfile:
    timestamp = "2026-08-17T00:00:00+00:00"
    return WorkspaceIndicatorProfile(
        profile_uid=str(profile.profile_uid),
        indicator_code=WORKSPACE_INDICATOR_MACD,
        name=profile.name,
        revision=profile.profile_revision,
        built_in=False,
        archived=False,
        complete=True,
        source_reference=WORKSPACE_INDICATOR_PROFILE_SOURCE_USER,
        parameters={
            "source": WORKSPACE_INDICATOR_SOURCE_CLOSE,
            "fast_period": profile.fast_period,
            "slow_period": profile.slow_period,
            "signal_period": profile.signal_period,
            "oscillator_ma_type": WORKSPACE_INDICATOR_MA_EXPONENTIAL,
            "signal_ma_type": WORKSPACE_INDICATOR_MA_EXPONENTIAL,
            "shift": 0,
        },
        created_utc=timestamp,
        updated_utc=timestamp,
    )


def _build_report(
    *,
    config: WorkspaceMacdProductionComparisonConfig,
    records: tuple[WorkspaceSignalRecord, ...],
    diagnostics: tuple[WorkspaceMacdCrossoverQualityDiagnostic, ...],
    latency: WorkspaceMacdLatencyMetrics,
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    historical_m1_rows: int,
    completed_m15_bars: int,
    dropped_incomplete_m15_buckets: int,
    orders_created: int,
    next_bar_gap_orders: int,
    strategy_events: tuple[WorkspaceMarketEvent, ...],
    summary: WorkspaceHistoricalReplaySummary,
    broker_requests: int,
) -> WorkspaceMacdProductionComparisonReport:
    _validate_diagnostics(diagnostics)
    windows = WorkspaceMacdExtremumWindowMetrics(
        window_3=sum(item.search_window == 3 for item in diagnostics),
        window_5=sum(item.search_window == 5 for item in diagnostics),
        window_7=sum(item.search_window == 7 for item in diagnostics),
        none=sum(item.search_window is None for item in diagnostics),
    )
    prominence = _criterion_metrics(
        diagnostics,
        "criterion_prominence_pass",
    )
    distance = _criterion_metrics(
        diagnostics,
        "criterion_distance_pass",
    )
    angle = _criterion_metrics(
        diagnostics,
        "criterion_angle_pass",
    )
    accepted = sum(item.final_quality_pass for item in diagnostics)
    rejected = len(diagnostics) - accepted
    reasons = WorkspaceMacdRejectReasonMetrics(
        extremum_not_found_n=summary.signals.macd_extremum_not_found,
        weak_prominence_w=summary.signals.macd_extremum_too_weak,
        distance_d=summary.signals.macd_distance_too_small,
        flat_angle_f=summary.signals.macd_cross_too_flat,
    )
    reason_total = (
        reasons.extremum_not_found_n
        + reasons.weak_prominence_w
        + reasons.distance_d
        + reasons.flat_angle_f
    )
    if reason_total != rejected:
        raise WorkspaceMacdProductionComparisonError(
            "N/W/D/F reject reasons do not cover all Quality rejects"
        )
    signal_before_entry = all(
        trade.signal_timestamp < trade.entry_timestamp for trade in trades
    )
    event_timestamps = {event.timestamp for event in strategy_events}
    completed_only = bool(strategy_events) and all(
        event.timeframe == MACD_COMPARISON_STRATEGY_TIMEFRAME
        for event in strategy_events
    )
    completed_only = completed_only and all(
        item.timestamp in event_timestamps for item in diagnostics
    )
    completed_only = completed_only and all(
        record.timestamp in event_timestamps for record in records
    )
    profile = config.profile
    excursions = _excursion_metrics(trades)
    return WorkspaceMacdProductionComparisonReport(
        dataset_label=config.dataset_label,
        window_start=config.window_start,
        window_end=config.window_end,
        profile_name=profile.name,
        profile_uid=str(profile.profile_uid),
        profile_revision=profile.profile_revision,
        profile_periods=(
            f"{profile.fast_period}/{profile.slow_period}/{profile.signal_period}"
        ),
        abc_min_angle_degrees=config.abc_min_angle_degrees,
        prominence=config.prominence,
        distance=config.distance,
        alligator_mode=config.alligator_mode,
        historical_m1_rows=historical_m1_rows,
        completed_m15_bars=completed_m15_bars,
        dropped_incomplete_m15_buckets=dropped_incomplete_m15_buckets,
        classic_crosses=len(diagnostics),
        buy_crosses=sum(item.direction == "BUY" for item in diagnostics),
        sell_crosses=sum(item.direction == "SELL" for item in diagnostics),
        extremum_windows=windows,
        prominence_criterion=prominence,
        distance_criterion=distance,
        abc_angle_criterion=angle,
        quality_accepted=accepted,
        quality_rejected=rejected,
        reject_reasons=reasons,
        classic_density_per_100_bars=(len(diagnostics) / completed_m15_bars * 100.0),
        candidate_density_per_100_bars=(accepted / completed_m15_bars * 100.0),
        price_turn_latency=latency,
        orders_created=orders_created,
        trades=summary.opened_trades,
        winners=summary.winning_trades,
        losers=summary.losing_trades,
        break_even=summary.break_even_trades,
        win_rate_percent=summary.win_rate_percent,
        profit_factor=summary.profit_factor,
        net_profit=summary.net_profit,
        average_trade=summary.average_trade,
        maximum_drawdown=summary.maximum_drawdown,
        maximum_drawdown_percent=summary.maximum_drawdown_percent,
        stop_loss_closes=summary.close_reason_count("STOP_LOSS"),
        take_profit_closes=summary.close_reason_count("TAKE_PROFIT"),
        profit_drawdown_closes=summary.close_reason_count("PROFIT_DRAWDOWN"),
        session_end_closes=summary.close_reason_count("SESSION_END"),
        next_bar_gap_orders=next_bar_gap_orders,
        excursions=excursions,
        signal_timestamp_before_entry=signal_before_entry,
        completed_m15_only=completed_only,
        broker_requests=broker_requests,
        broker_execution_attempted=False,
        deterministic_signature="",
    )


def _latency_metrics(
    events: tuple[WorkspaceMarketEvent, ...],
    diagnostics: tuple[WorkspaceMacdCrossoverQualityDiagnostic, ...],
) -> WorkspaceMacdLatencyMetrics:
    report: WorkspaceMacdSignalLatencyReport = (
        build_workspace_macd_signal_latency_report(
            events,
            diagnostics,
            lookback_bars=MACD_COMPARISON_LATENCY_LOOKBACK_BARS,
            strategy_bar_minutes=15,
            quality_only=False,
        )
    )
    return WorkspaceMacdLatencyMetrics(
        average_signal_bars=report.average_price_to_signal_bars,
        median_signal_bars=report.median_price_to_signal_bars,
        average_entry_bars=report.average_price_to_entry_bars,
        median_entry_bars=report.median_price_to_entry_bars,
        entry_gap_signals=report.entry_gap_signals,
    )


def _criterion_metrics(
    diagnostics: tuple[WorkspaceMacdCrossoverQualityDiagnostic, ...],
    attribute: str,
) -> WorkspaceMacdCriterionMetrics:
    passed = sum(bool(getattr(item, attribute)) for item in diagnostics)
    return WorkspaceMacdCriterionMetrics(
        passed=passed,
        rejected=len(diagnostics) - passed,
    )


def _excursion_metrics(
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
) -> WorkspaceMacdExcursionMetrics:
    if not trades:
        return WorkspaceMacdExcursionMetrics(
            trades=0,
            average_mfe=0.0,
            average_mae=0.0,
            maximum_mfe=0.0,
            minimum_mae=0.0,
        )
    mfe = tuple(item.maximum_favorable_excursion for item in trades)
    mae = tuple(item.maximum_adverse_excursion for item in trades)
    return WorkspaceMacdExcursionMetrics(
        trades=len(trades),
        average_mfe=math.fsum(mfe) / len(mfe),
        average_mae=math.fsum(mae) / len(mae),
        maximum_mfe=max(mfe),
        minimum_mae=min(mae),
    )


def _validate_diagnostics(
    diagnostics: tuple[WorkspaceMacdCrossoverQualityDiagnostic, ...],
) -> None:
    previous: datetime | None = None
    for item in diagnostics:
        if previous is not None and item.timestamp <= previous:
            raise WorkspaceMacdProductionComparisonError(
                "MACD diagnostics must be strictly ordered"
            )
        if item.search_window not in {None, 3, 5, 7}:
            raise WorkspaceMacdProductionComparisonError(
                f"Unsupported extremum search window: {item.search_window}"
            )
        previous = item.timestamp


def _deterministic_signature(
    report: WorkspaceMacdProductionComparisonReport,
) -> str:
    payload = asdict(report)
    payload["window_start"] = report.window_start.isoformat()
    payload["window_end"] = report.window_end.isoformat()
    payload["deterministic_signature"] = ""
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.blake2b(
        encoded,
        digest_size=16,
        person=MACD_COMPARISON_SIGNATURE_PERSON,
    ).hexdigest()


def _utc_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise WorkspaceMacdProductionComparisonError(f"{field_name} must be datetime")
    if value.tzinfo is None:
        raise WorkspaceMacdProductionComparisonError(
            f"{field_name} must be timezone-aware"
        )
    return value.astimezone(UTC)


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise WorkspaceMacdProductionComparisonError(
            f"{field_name} must be positive integer"
        )
    return value


def _positive_float(value: object, field_name: str) -> float:
    number = _bounded_float(value, field_name, minimum=0.0, maximum=math.inf)
    if number <= 0.0:
        raise WorkspaceMacdProductionComparisonError(f"{field_name} must be positive")
    return number


def _bounded_float(
    value: object,
    field_name: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorkspaceMacdProductionComparisonError(f"{field_name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise WorkspaceMacdProductionComparisonError(f"{field_name} must be finite")
    if number < minimum or number > maximum:
        raise WorkspaceMacdProductionComparisonError(
            f"{field_name} is outside supported range"
        )
    return number
