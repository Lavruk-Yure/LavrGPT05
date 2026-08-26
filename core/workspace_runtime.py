# core/workspace_runtime.py — per-WSP runtime, lifecycle та журнал подій
# -*- coding: utf-8 -*-
"""Канонічний per-WSP runtime: lifecycle, market events, Replay і журнал.

WorkspaceRuntime ізолює стан WSP, керує Replay/Live Read-only startup,
market guards, signals, chart history та virtual Replay execution. RoadMap100
додає контрольовану ручну зміну SL/TP лише для active virtual position у
призупиненому Historical Replay та окремий ``Тік`` для покрокової обробки
найдрібніших execution events у multi-resolution Replay. Strategy ``Крок``
може зупинитися на завершеному M15 bar до його M1 execution window, а ``Тік``
обробляє тільки вже staged execution event і ніколи сам не просуває strategy
bar. Так зберігається чітка M1 chronology без look-ahead. Зміна SL/TP застосовується
до наступного ще не обробленого execution event, не переоцінює поточний
M1/M15 bar і не викликає
broker API. Viewport navigation, risk та broker integration лишаються
окремими від цієї diagnostic interaction. RoadMap101 також фіксує exact
signal timestamp у structured Journal details для надійної навігації з Signals.
RoadMap102 прикріплює terminal Candidate F lifecycle до початкового ARMED
signal record без створення другого сигналу та без broker execution.
"""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, cast

from core.algorithm_workspace import (
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_BROKER,
    WORKSPACE_DATA_MODE_REPLAY,
    WORKSPACE_STATE_ERROR,
    WORKSPACE_STATE_RESTORED,
    WORKSPACE_STATE_RUNNING,
    WORKSPACE_STATE_STARTING,
    WORKSPACE_STATE_STOPPED,
    WORKSPACE_STATE_STOPPING,
    AlgorithmWorkspace,
)
from core.workspace_algorithm import (
    WorkspaceAlgorithm,
    WorkspaceAlgorithmError,
    create_workspace_algorithm,
    normalize_signal_output,
)
from core.workspace_broker_market import (
    WorkspaceBrokerMarketError,
    WorkspaceBrokerMarketProviderProtocol,
    WorkspaceExecutionSafetySnapshot,
)
from core.workspace_chart import (
    WorkspaceChartModel,
    WorkspaceChartSnapshot,
)
from core.workspace_close_guard import (
    WorkspaceCloseGuard,
    WorkspaceCloseGuardResult,
)
from core.workspace_historical_summary import (
    WorkspaceHistoricalReplaySummary,
    build_workspace_historical_replay_summary,
    build_workspace_historical_signal_metrics,
)
from core.workspace_indicator_profile import (
    ALLIGATOR_LOGIC_MODE_CANDIDATE_F,
    WORKSPACE_INDICATOR_ALLIGATOR,
    normalize_workspace_indicator_profile_bindings,
    workspace_indicator_profile_binding,
)
from core.workspace_market_event import WorkspaceMarketEvent
from core.workspace_ownership import (
    WorkspaceBinding,
    WorkspaceOrderSnapshot,
    WorkspaceOwnedSnapshot,
    WorkspaceOwnershipFilter,
    WorkspacePositionSnapshot,
)
from core.workspace_profit_guard import (
    CANDIDATE_F_NEGATIVE_PD_EARLY_ABORT_EVENT_INDEX,
    CANDIDATE_F_NEGATIVE_PD_RECOVERY_WINDOW_M1,
    WORKSPACE_PROFIT_ACTION_CLOSE,
    WorkspaceCandidateFNegativePdRecoveryGuard,
    WorkspaceProfitDrawdownGuard,
    WorkspaceProfitProtectionDecision,
    WorkspaceProfitProtectionPolicy,
)
from core.workspace_replay import (
    REPLAY_SPEEDS,
    REPLAY_STATE_COMPLETED,
    REPLAY_STATE_PAUSED,
    REPLAY_STATE_RUNNING,
    WorkspaceReplayError,
    WorkspaceReplayService,
    WorkspaceReplaySession,
    replay_speed_label,
)
from core.workspace_replay_execution import (
    WorkspaceReplayExecutionEngine,
    WorkspaceReplayExecutionEvent,
    WorkspaceReplayExecutionPolicy,
)
from core.workspace_replay_margin import HISTORICAL_REPLAY_LEVERAGE
from core.workspace_replay_settings import WorkspaceReplaySettings
from core.workspace_runtime_requirements import build_workspace_warmup_plan
from core.workspace_signal import (
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WORKSPACE_SIGNAL_SPREAD_BLOCKED,
    WORKSPACE_SIGNAL_SPREAD_OK,
    WORKSPACE_SIGNAL_SPREAD_UNKNOWN,
    WorkspaceSignalProposal,
    WorkspaceSignalRecord,
    WorkspaceTradeIntent,
)
from engine.risk.account_snapshot import WorkspaceRiskAccountSnapshot
from engine.risk.risk_model import (
    WorkspaceRiskDecision,
    WorkspaceRiskEvaluator,
    WorkspaceRiskPolicy,
    WorkspaceRiskRequest,
)
from engine.runtime_constants import (
    DEFAULT_WORKSPACE_ALLIGATOR_CONFIRMATION,
    DEFAULT_WORKSPACE_ALLIGATOR_FILTER_ENABLED,
    DEFAULT_WORKSPACE_SPREAD_LIMIT,
    DEFAULT_WORKSPACE_WARMUP_BARS,
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WORKSPACE_ALLIGATOR_FILTER_ENABLED_KEY,
)

WORKSPACE_STARTUP_PHASE_IDLE = "IDLE"
WORKSPACE_STARTUP_PHASE_LOAD_DATA = "LOAD_DATA"
WORKSPACE_STARTUP_PHASE_WARMUP = "WARMUP"
WORKSPACE_STARTUP_PHASE_WAIT_BROKER = "WAIT_BROKER"
WORKSPACE_STARTUP_PHASE_SAFETY_HOLD_EXTERNAL_EXPOSURE = "SAFETY_HOLD_EXTERNAL_EXPOSURE"
WORKSPACE_STARTUP_PHASE_WAIT_SPREAD = "WAIT_SPREAD"
WORKSPACE_STARTUP_PHASE_READY = "READY"
WORKSPACE_STARTUP_PHASE_RUNNING = "RUNNING"
WORKSPACE_STARTUP_PHASES = (
    WORKSPACE_STARTUP_PHASE_IDLE,
    WORKSPACE_STARTUP_PHASE_LOAD_DATA,
    WORKSPACE_STARTUP_PHASE_WARMUP,
    WORKSPACE_STARTUP_PHASE_WAIT_BROKER,
    WORKSPACE_STARTUP_PHASE_SAFETY_HOLD_EXTERNAL_EXPOSURE,
    WORKSPACE_STARTUP_PHASE_WAIT_SPREAD,
    WORKSPACE_STARTUP_PHASE_READY,
    WORKSPACE_STARTUP_PHASE_RUNNING,
)

MAX_WORKSPACE_SIGNAL_RECORDS = 1000
MAX_WORKSPACE_PROFIT_DECISIONS = 1000


def _candidate_f_negative_pd_recovery_enabled(
    workspace: AlgorithmWorkspace,
) -> bool:
    """Увімкнути fixed 6J exit лише для Candidate F M1->M15 Replay."""
    if workspace.data_mode != WORKSPACE_DATA_MODE_REPLAY:
        return False
    if str(workspace.timeframe or "").strip().upper() != "M15":
        return False
    replay_settings = WorkspaceReplaySettings.from_workspace(workspace)
    if replay_settings.source_timeframe != "M1":
        return False
    enabled = bool(
        workspace.parameters.get(
            WORKSPACE_ALLIGATOR_FILTER_ENABLED_KEY,
            DEFAULT_WORKSPACE_ALLIGATOR_FILTER_ENABLED,
        )
    )
    if not enabled:
        return False
    confirmation = str(
        workspace.parameters.get(
            "alligator_confirmation",
            DEFAULT_WORKSPACE_ALLIGATOR_CONFIRMATION,
        )
    ).strip().upper()
    if confirmation != WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME:
        return False
    binding = workspace_indicator_profile_binding(
        workspace,
        WORKSPACE_INDICATOR_ALLIGATOR,
    )
    return (
        str(binding.profile.parameters.get("logic_mode") or "").strip().upper()
        == ALLIGATOR_LOGIC_MODE_CANDIDATE_F
    )


class WorkspaceRuntimeError(RuntimeError):
    """Invalid workspace runtime operation or transition."""


@dataclass(frozen=True, slots=True)
class WorkspaceJournalEntry:
    """One immutable diagnostic record in a WSP-local event journal."""

    timestamp: datetime
    workspace_uid: str
    category: str
    event: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def format_line(self) -> str:
        timestamp_text = self.timestamp.astimezone(UTC).isoformat(
            timespec="milliseconds"
        )
        source_timestamp = self._source_timestamp_text()
        if source_timestamp:
            return (
                f"{timestamp_text} [{self.category}] {self.event} "
                f"@ {source_timestamp}: {self.message}"
            )
        return f"{timestamp_text} [{self.category}] {self.event}: {self.message}"

    def _source_timestamp_text(self) -> str | None:
        """Повернути видимий market/signal/replay timestamp зі structured details."""
        for key in (
            "signal_timestamp",
            "timestamp",
            "strategy_timestamp",
            "execution_timestamp",
        ):
            value = self.details.get(key)
            if value is None or value == "":
                continue
            if isinstance(value, datetime):
                normalized = value
                if normalized.tzinfo is None:
                    normalized = normalized.replace(tzinfo=UTC)
                return normalized.astimezone(UTC).isoformat(timespec="seconds")
            text = str(value).strip()
            if not text:
                continue
            if len(text) > 10 and text[10:11] == " ":
                text = text[:10] + "T" + text[11:]
            return text
        return None


@dataclass(slots=True)
class WorkspaceRuntimeContext:
    """Volatile runtime state for exactly one persisted WSP configuration."""

    workspace_uid: str
    broker: str
    account_id: str | None
    account_mode: str | None
    symbol: str
    timeframe: str
    algorithm_id: str
    data_mode: str
    control_mode: str
    indicator_profile_bindings: dict[str, dict[str, object]] = field(
        default_factory=dict
    )
    runtime_state: str = WORKSPACE_STATE_STOPPED
    restored_from_session: bool = False
    startup_phase: str = WORKSPACE_STARTUP_PHASE_IDLE
    warmup_bars_required: int = DEFAULT_WORKSPACE_WARMUP_BARS
    warmup_bars_processed: int = 0
    warmup_complete: bool = False
    warmup_required_by_timeframe: dict[str, int] = field(default_factory=dict)
    warmup_components_by_timeframe: dict[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    spread_limit: float = DEFAULT_WORKSPACE_SPREAD_LIMIT
    current_spread: float | None = None
    spread_ok: bool = False
    signal_allowed: bool = False
    signal_block_reason: str | None = "runtime is stopped"
    safety_hold_active: bool = False
    safety_hold_reason_code: str | None = None
    safety_hold_message: str | None = None
    safety_hold_signed_volume: float = 0.0
    safety_hold_evidence_status: str | None = None
    safety_hold_confirmation_required: bool = False
    safety_hold_checked_utc: str | None = None
    safety_hold_revision: int = 0
    active_orders_count: int = 0
    positions_count: int = 0
    risk_equity: float | None = None
    daily_realized_pnl: float | None = None
    replay_initial_balance: float | None = None
    replay_leverage: float | None = None
    used_margin: float | None = None
    free_margin: float | None = None
    current_profit: float = 0.0
    peak_profit: float = 0.0
    profit_drawdown: float = 0.0
    profit_protection_enabled: bool = True
    profit_drawdown_close_percent: float = 30.0
    profit_drawdown_minimum_profit: float = 0.0
    profit_decisions_count: int = 0
    pending_close_decisions_count: int = 0
    current_market_event: WorkspaceMarketEvent | None = None
    current_execution_event: WorkspaceMarketEvent | None = None
    market_event_count: int = 0
    event_processing: bool = False
    broker_operation_active: bool = False
    last_error: str | None = None
    signals_count: int = 0
    accepted_signals_count: int = 0
    rejected_signals_count: int = 0

    @classmethod
    def from_workspace(
        cls,
        workspace: AlgorithmWorkspace,
    ) -> WorkspaceRuntimeContext:
        """Copy the WSP binding into a new non-persisted runtime context."""
        warmup_bars = _non_negative_int_parameter(
            workspace.parameters.get("warmup_bars"),
            DEFAULT_WORKSPACE_WARMUP_BARS,
            "warmup_bars",
        )
        spread_limit = _positive_float_parameter(
            workspace.parameters.get("spread_limit"),
            DEFAULT_WORKSPACE_SPREAD_LIMIT,
            "spread_limit",
        )
        profit_protection = workspace.profit_protection
        replay_initial_balance = None
        replay_leverage = None
        used_margin = None
        free_margin = None
        if workspace.data_mode == WORKSPACE_DATA_MODE_REPLAY:
            replay_settings = WorkspaceReplaySettings.from_workspace(workspace)
            replay_initial_balance = replay_settings.initial_balance
            replay_leverage = HISTORICAL_REPLAY_LEVERAGE
            used_margin = 0.0
            free_margin = replay_initial_balance
        return cls(
            workspace_uid=workspace.workspace_uid,
            broker=workspace.broker,
            account_id=workspace.account_id,
            account_mode=workspace.account_mode,
            symbol=workspace.symbol,
            timeframe=workspace.timeframe,
            algorithm_id=workspace.algorithm,
            data_mode=workspace.data_mode,
            control_mode=workspace.control_mode,
            indicator_profile_bindings=(
                normalize_workspace_indicator_profile_bindings(
                    workspace.indicator_profile_bindings
                )
            ),
            runtime_state=workspace.runtime_state,
            restored_from_session=workspace.runtime_state == WORKSPACE_STATE_RESTORED,
            warmup_bars_required=warmup_bars,
            spread_limit=spread_limit,
            replay_initial_balance=replay_initial_balance,
            replay_leverage=replay_leverage,
            used_margin=used_margin,
            free_margin=free_margin,
            profit_protection_enabled=bool(profit_protection.get("enabled", True)),
            profit_drawdown_close_percent=float(
                profit_protection.get("max_profit_drawdown_percent", 30.0)
            ),
            profit_drawdown_minimum_profit=float(
                profit_protection.get("minimum_profit", 0.0)
            ),
        )

    def set_runtime_snapshot(
        self,
        *,
        active_orders_count: int = 0,
        positions_count: int = 0,
        current_profit: float = 0.0,
        peak_profit: float = 0.0,
    ) -> None:
        """Update broker/replay facts without persisting them to Session."""
        self.active_orders_count = max(0, int(active_orders_count))
        self.positions_count = max(0, int(positions_count))
        self.current_profit = float(current_profit)
        self.peak_profit = max(float(peak_profit), self.current_profit, 0.0)
        if self.peak_profit > 0.0:
            pullback = self.peak_profit - self.current_profit
            self.profit_drawdown = max(
                0.0,
                pullback / self.peak_profit * 100.0,
            )
        else:
            self.profit_drawdown = 0.0


class WorkspaceRuntime:
    """Stateful runtime façade used by AlgorithmWorkspaceController."""

    def __init__(
        self,
        workspace: AlgorithmWorkspace,
        replay_service: WorkspaceReplayService | None = None,
        algorithm_factory: Callable[[str], WorkspaceAlgorithm] | None = None,
        broker_market_provider: WorkspaceBrokerMarketProviderProtocol | None = None,
        signal_record_observer: Callable[[WorkspaceSignalRecord], None] | None = None,
    ) -> None:
        self.context = WorkspaceRuntimeContext.from_workspace(workspace)
        self.algorithm_parameters = dict(workspace.parameters)
        self.risk_settings = dict(workspace.risk_settings)
        self.risk_policy = WorkspaceRiskPolicy.from_workspace(workspace)
        self.risk_evaluator = WorkspaceRiskEvaluator(self.risk_policy)
        self.risk_account_snapshot: WorkspaceRiskAccountSnapshot | None = None
        self.profit_protection_policy = WorkspaceProfitProtectionPolicy(
            enabled=bool(workspace.profit_protection.get("enabled", True)),
            activation_mode=str(
                workspace.profit_protection.get(
                    "activation_mode",
                    "AFTER_SPREAD",
                )
            ),
            max_drawdown_percent=float(
                workspace.profit_protection.get(
                    "max_profit_drawdown_percent",
                    30.0,
                )
            ),
            minimum_profit=float(
                workspace.profit_protection.get("minimum_profit", 0.0)
            ),
        )
        if _candidate_f_negative_pd_recovery_enabled(workspace):
            self.profit_drawdown_guard = (
                WorkspaceCandidateFNegativePdRecoveryGuard(
                    self.profit_protection_policy
                )
            )
        else:
            self.profit_drawdown_guard = WorkspaceProfitDrawdownGuard(
                self.profit_protection_policy
            )
        self.chart_model = WorkspaceChartModel()
        self.replay_settings = dict(workspace.replay_settings)
        self.replay_service = replay_service or WorkspaceReplayService()
        self.algorithm_factory = algorithm_factory or create_workspace_algorithm
        self.broker_market_provider = broker_market_provider
        self.signal_record_observer = signal_record_observer
        self.algorithm: WorkspaceAlgorithm | None = None
        self._chart_algorithm: WorkspaceAlgorithm | None = None
        self.replay_session: WorkspaceReplaySession | None = None
        self.replay_execution: WorkspaceReplayExecutionEngine | None = None
        self._pending_replay_execution_window_index: int | None = None
        self._pending_replay_execution_offset = 0
        self._replay_initial_equity: float | None = None
        self.journal: list[WorkspaceJournalEntry] = []
        self.signals: list[WorkspaceSignalRecord] = []
        self._historical_signal_records: list[WorkspaceSignalRecord] = []
        self.historical_summary: WorkspaceHistoricalReplaySummary | None = None
        self._historical_csv_selection_elapsed_seconds: float | None = None
        self._historical_replay_started_monotonic: float | None = None
        self._historical_replay_elapsed_seconds: float | None = None
        self.profit_decisions: list[WorkspaceProfitProtectionDecision] = []
        self.owned_snapshot = WorkspaceOwnedSnapshot(orders=(), positions=())
        self._replay_completion_logged = False
        self._live_quote_received = False
        self._append_journal(
            "LIFECYCLE",
            "RUNTIME_CREATED",
            f"Runtime created in {self.context.runtime_state} state.",
        )
        if isinstance(
            self.profit_drawdown_guard,
            WorkspaceCandidateFNegativePdRecoveryGuard,
        ):
            self._append_journal(
                "RISK",
                "CANDIDATE_F_NEGATIVE_PD_RECOVERY_ACTIVE",
                (
                    "Candidate F negative-PD recovery policy active: "
                    "3 M1 with M2 two-step deterioration abort."
                ),
                recovery_window_m1=(
                    CANDIDATE_F_NEGATIVE_PD_RECOVERY_WINDOW_M1
                ),
                early_abort_event_index=(
                    CANDIDATE_F_NEGATIVE_PD_EARLY_ABORT_EVENT_INDEX
                ),
                broker_execution_attempted=False,
            )

    @property
    def workspace_uid(self) -> str:
        return self.context.workspace_uid

    def evaluate_risk_request(
        self,
        request: WorkspaceRiskRequest,
    ) -> WorkspaceRiskDecision:
        """Apply this WSP policy without sending any broker operation."""
        binding_matches = (
            request.workspace_uid == self.context.workspace_uid
            and request.broker == self.context.broker
            and request.account_id == self.context.account_id
            and request.symbol == self.context.symbol
            and request.source_mode == self.context.data_mode
        )
        effective_request = request
        if request.binding_verified and not binding_matches:
            effective_request = replace(request, binding_verified=False)
        return self.risk_evaluator.evaluate(effective_request)

    def set_risk_account_snapshot(
        self,
        snapshot: WorkspaceRiskAccountSnapshot | None = None,
        *,
        equity: float | None = None,
        daily_realized_pnl: float | None = None,
        open_positions_count: int | None = None,
        snapshot_utc: datetime | None = None,
    ) -> WorkspaceRiskAccountSnapshot:
        """Set volatile account facts used by signal risk evaluation."""
        if snapshot is not None:
            if any(
                value is not None
                for value in (
                    equity,
                    daily_realized_pnl,
                    open_positions_count,
                    snapshot_utc,
                )
            ):
                raise ValueError(
                    "snapshot cannot be combined with account keyword values"
                )
            effective_snapshot = snapshot
        else:
            effective_snapshot = WorkspaceRiskAccountSnapshot(
                snapshot_utc=snapshot_utc
                or (
                    self.context.current_market_event.timestamp
                    if self.context.current_market_event is not None
                    else None
                )
                or datetime.now(UTC),
                workspace_uid=self.context.workspace_uid,
                broker=self.context.broker,
                account_id=self.context.account_id,
                source_mode=self.context.data_mode,
                equity=equity,
                daily_realized_pnl=daily_realized_pnl,
                open_positions_count=(
                    self.context.positions_count
                    if open_positions_count is None
                    else open_positions_count
                ),
                binding_verified=True,
                synthetic=self.context.data_mode == WORKSPACE_DATA_MODE_REPLAY,
            )
        binding_verified = effective_snapshot.matches_binding(
            workspace_uid=self.context.workspace_uid,
            broker=self.context.broker,
            account_id=self.context.account_id,
            source_mode=self.context.data_mode,
        )
        if not binding_verified and effective_snapshot.binding_verified:
            effective_snapshot = replace(
                effective_snapshot,
                binding_verified=False,
            )
        self.risk_account_snapshot = effective_snapshot
        self.context.risk_equity = effective_snapshot.equity
        self.context.daily_realized_pnl = effective_snapshot.daily_realized_pnl
        self._append_journal(
            "RISK",
            "ACCOUNT_SNAPSHOT_UPDATED",
            "Risk account snapshot updated without broker execution.",
            snapshot_utc=effective_snapshot.snapshot_utc.isoformat(),
            source_mode=effective_snapshot.source_mode,
            equity=effective_snapshot.equity,
            daily_realized_pnl=effective_snapshot.daily_realized_pnl,
            open_positions_count=effective_snapshot.open_positions_count,
            binding_verified=effective_snapshot.binding_verified,
            synthetic=effective_snapshot.synthetic,
        )
        return effective_snapshot

    def clear_risk_account_snapshot(self, reason: str) -> None:
        """Discard volatile account facts that are no longer trustworthy."""
        if self.risk_account_snapshot is None:
            return
        self.risk_account_snapshot = None
        self.context.risk_equity = None
        self.context.daily_realized_pnl = None
        self._append_journal(
            "RISK",
            "ACCOUNT_SNAPSHOT_CLEARED",
            "Risk account snapshot cleared without broker execution.",
            reason=str(reason or "snapshot cleared"),
        )

    def complete_restore(self) -> None:
        """Finalize RESTORED -> STOPPED without starting Replay or algorithm."""
        if not self.context.restored_from_session:
            return
        if self.context.runtime_state == WORKSPACE_STATE_STOPPED:
            return
        self._require_state({WORKSPACE_STATE_RESTORED}, "complete restore")
        self.context.startup_phase = WORKSPACE_STARTUP_PHASE_IDLE
        self.context.signal_allowed = False
        self.context.signal_block_reason = "runtime is stopped"
        self.context.event_processing = False
        self.context.broker_operation_active = False
        self._clear_execution_safety_hold(reset_revision=True)
        self._append_journal(
            "SESSION",
            "SESSION_RESTORED",
            "Persisted WSP configuration restored without automatic start.",
            data_mode=self.context.data_mode,
            control_mode=self.context.control_mode,
            replay_speed=self.replay_settings.get("speed", 1),
            algorithm_id=self.context.algorithm_id,
        )
        self._transition(
            WORKSPACE_STATE_STOPPED,
            "Session restore completed; automatic start is disabled.",
        )

    def begin_start(self) -> None:
        """Enter STARTING and reject repeated or unsafe starts."""
        self._require_state(
            {WORKSPACE_STATE_STOPPED, WORKSPACE_STATE_RESTORED},
            "start",
        )
        self.context.last_error = None
        self.context.current_market_event = None
        self.context.current_execution_event = None
        self.context.market_event_count = 0
        self._clear_pending_replay_execution()
        self.context.event_processing = False
        self.context.warmup_bars_processed = 0
        self.context.warmup_complete = self.context.warmup_bars_required == 0
        self.context.warmup_required_by_timeframe = {}
        self.context.warmup_components_by_timeframe = {}
        self.context.current_spread = None
        self.context.spread_ok = False
        self.context.signal_allowed = False
        self.context.signal_block_reason = "market data is not loaded"
        self._clear_execution_safety_hold(reset_revision=True)
        self.context.signals_count = 0
        self.context.accepted_signals_count = 0
        self.context.rejected_signals_count = 0
        self.signals.clear()
        self._historical_signal_records.clear()
        self.historical_summary = None
        self._historical_csv_selection_elapsed_seconds = None
        self._historical_replay_started_monotonic = None
        self._historical_replay_elapsed_seconds = None
        self.risk_account_snapshot = None
        self.context.risk_equity = None
        self.context.daily_realized_pnl = None
        self.context.profit_decisions_count = 0
        self.context.pending_close_decisions_count = 0
        self.profit_decisions.clear()
        self.chart_model.clear()
        self.algorithm = None
        self._chart_algorithm = None
        self._replay_completion_logged = False
        self._live_quote_received = False
        self._transition(WORKSPACE_STATE_STARTING, "Start requested.")
        if self.context.data_mode == WORKSPACE_DATA_MODE_REPLAY:
            load_message = "Loading Replay market data."
        else:
            load_message = "Preparing broker market data."
        self._transition_startup_phase(
            WORKSPACE_STARTUP_PHASE_LOAD_DATA,
            load_message,
        )

    def set_broker_market_provider(
        self,
        provider: WorkspaceBrokerMarketProviderProtocol | None,
    ) -> None:
        """Attach or replace the volatile read-only broker feed provider."""
        if self.context.runtime_state in {
            WORKSPACE_STATE_STARTING,
            WORKSPACE_STATE_RUNNING,
            WORKSPACE_STATE_STOPPING,
        }:
            raise WorkspaceRuntimeError(
                "Cannot replace broker market provider while runtime is active"
            )
        self.broker_market_provider = provider

    def complete_start(self) -> None:
        """Prepare the selected data mode and wait for startup guards."""
        self._require_state({WORKSPACE_STATE_STARTING}, "complete start")
        try:
            if self.context.data_mode == WORKSPACE_DATA_MODE_REPLAY:
                self._complete_replay_start()
            elif self.context.data_mode == WORKSPACE_DATA_MODE_BROKER:
                self._complete_broker_start()
            else:
                raise WorkspaceRuntimeError(
                    f"Unsupported workspace data mode: {self.context.data_mode}"
                )
        except (
            ValueError,
            WorkspaceAlgorithmError,
            WorkspaceBrokerMarketError,
            WorkspaceReplayError,
            WorkspaceRuntimeError,
        ) as exc:
            self.fail(exc)
            raise

    def _complete_replay_start(self) -> None:
        """Prepare deterministic Replay and wait for guards."""
        selection_started = time.monotonic()
        replay_session = self.replay_service.create_session(
            broker=self.context.broker,
            symbol=self.context.symbol,
            timeframe=self.context.timeframe,
            replay_settings=self.replay_settings,
        )
        selection_elapsed = max(0.0, time.monotonic() - selection_started)
        self.chart_model.attach_full_history(replay_session.events)
        history_report = replay_session.history_report
        if history_report is not None:
            self._historical_csv_selection_elapsed_seconds = selection_elapsed
        if history_report is not None:
            self._append_journal(
                "HISTORY",
                "CSV_HISTORY_LOADED",
                f"Historical CSV loaded: "
                f"{history_report.accepted_rows} source rows, "
                f"{len(replay_session.events)} strategy bars, "
                f"{history_report.gap_count} gaps.",
                file_path=history_report.file_path,
                input_rows=history_report.input_rows,
                accepted_rows=history_report.accepted_rows,
                filtered_rows=history_report.filtered_rows,
                derived_quotes=history_report.derived_quotes,
                gap_count=history_report.gap_count,
                first_timestamp=history_report.first_timestamp.isoformat(),
                last_timestamp=history_report.last_timestamp.isoformat(),
                source_timeframe=replay_session.source_timeframe,
                strategy_timeframe=replay_session.strategy_timeframe,
                strategy_bars=len(replay_session.events),
                dropped_incomplete_strategy_buckets=(
                    replay_session.dropped_incomplete_strategy_buckets
                ),
                csv_selection_elapsed_seconds=selection_elapsed,
            )
        self._append_journal(
            "GUARD",
            "DATA_LOADED",
            f"Replay data loaded: {len(replay_session.events)} events.",
            event_count=len(replay_session.events),
        )
        self.set_risk_account_snapshot(
            WorkspaceRiskAccountSnapshot.from_replay_settings(
                snapshot_utc=replay_session.events[0].timestamp,
                workspace_uid=self.context.workspace_uid,
                broker=self.context.broker,
                account_id=self.context.account_id,
                source_mode=self.context.data_mode,
                replay_settings=self.replay_settings,
            )
        )
        self._start_algorithm()
        self._initialize_replay_execution()
        replay_session.start()
        self._historical_replay_started_monotonic = time.monotonic()
        self.replay_session = replay_session
        self._append_journal(
            "REPLAY",
            "SESSION_STARTED",
            f"Replay source {replay_session.source_name} started "
            f"with {len(replay_session.events)} events at "
            f"{replay_speed_label(replay_session.speed)}.",
            source=replay_session.source_name,
            event_count=len(replay_session.events),
            speed=replay_session.speed,
        )
        if self.context.warmup_complete:
            self.context.signal_block_reason = "waiting for acceptable spread"
            self._transition_startup_phase(
                WORKSPACE_STARTUP_PHASE_WAIT_SPREAD,
                "Warm-up is disabled; waiting for spread guard.",
            )
        else:
            self.context.signal_block_reason = "warmup incomplete"
            self._transition_startup_phase(
                WORKSPACE_STARTUP_PHASE_WARMUP,
                f"Warm-up requires {self.context.warmup_bars_required} bars.",
            )

    def _initialize_replay_execution(self) -> None:
        """Create a virtual engine only for AUTO Replay workspaces."""
        self.replay_execution = None
        self._replay_initial_equity = (
            self.risk_account_snapshot.equity
            if self.risk_account_snapshot is not None
            else self.context.replay_initial_balance
        )
        self.context.replay_initial_balance = self._replay_initial_equity
        self.owned_snapshot = WorkspaceOwnedSnapshot(orders=(), positions=())
        self.context.set_runtime_snapshot()
        from core.workspace_alligator import (
            WorkspaceMacdAlligatorReplayAlgorithm,
        )

        if not isinstance(
            self.algorithm,
            WorkspaceMacdAlligatorReplayAlgorithm,
        ):
            self._append_journal(
                "REPLAY",
                "VIRTUAL_EXECUTION_DISABLED",
                "The active algorithm does not provide Replay virtual " "execution.",
                algorithm_id=self.context.algorithm_id,
                broker_execution_attempted=False,
            )
            return
        if self.context.control_mode != WORKSPACE_CONTROL_MODE_AUTO:
            self._append_journal(
                "REPLAY",
                "VIRTUAL_EXECUTION_DISABLED",
                "Replay signals remain visible; virtual execution requires "
                "AUTO control mode.",
                control_mode=self.context.control_mode,
                broker_execution_attempted=False,
            )
            return
        if self._replay_initial_equity is None:
            raise WorkspaceRuntimeError(
                "Replay virtual execution requires initial equity"
            )
        self.replay_execution = WorkspaceReplayExecutionEngine(
            workspace_uid=self.context.workspace_uid,
            broker=self.context.broker,
            account_id=self.context.account_id,
            symbol=self.context.symbol,
            policy=WorkspaceReplayExecutionPolicy(
                fixed_volume=self.risk_policy.maximum_position_volume,
                maximum_open_positions=self.risk_policy.maximum_open_positions,
            ),
            initial_balance=self._replay_initial_equity,
            leverage=HISTORICAL_REPLAY_LEVERAGE,
        )
        self._sync_replay_execution_snapshot()
        self._append_journal(
            "REPLAY",
            "VIRTUAL_EXECUTION_READY",
            "Replay AUTO virtual execution is ready; broker execution remains "
            "disabled.",
            fixed_volume=self.risk_policy.maximum_position_volume,
            maximum_open_positions=self.risk_policy.maximum_open_positions,
            stop_policy="SIGNAL_BAR_RANGE_1R",
            take_profit_policy="SIGNAL_BAR_RANGE_2R",
            ambiguous_bar_policy="STOP_LOSS_FIRST",
            profit_drawdown_close_percent=self.context.profit_drawdown_close_percent,
            leverage=HISTORICAL_REPLAY_LEVERAGE,
            broker_execution_attempted=False,
        )

    def _sync_replay_execution_snapshot(
        self,
        *,
        snapshot_utc: datetime | None = None,
    ) -> None:
        """Expose virtual rows through the existing WSP ownership UI model."""
        engine = self.replay_execution
        if engine is None:
            return
        snapshot = engine.snapshot()
        self.owned_snapshot = snapshot
        realized_profit = engine.realized_profit
        unrealized_profit = snapshot.current_profit
        total_profit = realized_profit + unrealized_profit
        self.context.set_runtime_snapshot(
            active_orders_count=len(snapshot.active_orders),
            positions_count=len(snapshot.active_positions),
            current_profit=total_profit,
            peak_profit=max(self.context.peak_profit, total_profit, 0.0),
        )
        margin_snapshot = engine.margin_snapshot()
        self.context.replay_leverage = margin_snapshot.leverage
        self.context.used_margin = margin_snapshot.used_margin
        self.context.free_margin = margin_snapshot.free_margin
        risk_snapshot = self.risk_account_snapshot
        if risk_snapshot is None:
            return
        base_equity = self._replay_initial_equity
        if base_equity is None:
            equity = None
        else:
            equity = base_equity + total_profit
        self.risk_account_snapshot = replace(
            risk_snapshot,
            snapshot_utc=(
                snapshot_utc
                or (
                    self.context.current_market_event.timestamp
                    if self.context.current_market_event is not None
                    else risk_snapshot.snapshot_utc
                )
            ),
            equity=equity,
            daily_realized_pnl=realized_profit,
            open_positions_count=len(snapshot.active_positions),
        )
        self.context.risk_equity = equity
        self.context.daily_realized_pnl = realized_profit

    def _append_replay_execution_events(
        self,
        events: tuple[WorkspaceReplayExecutionEvent, ...],
    ) -> None:
        for lifecycle_event in events:
            self._append_journal(
                "REPLAY_EXECUTION",
                lifecycle_event.event,
                lifecycle_event.message,
                **lifecycle_event.details,
            )

    def _advance_replay_execution(
        self,
        event: WorkspaceMarketEvent,
    ) -> None:
        self.context.current_execution_event = event
        engine = self.replay_execution
        if engine is None:
            return
        self._append_replay_execution_events(engine.on_market_event(event))
        self._sync_replay_execution_snapshot(snapshot_utc=event.timestamp)

    def _apply_replay_profit_protection(
        self,
        event: WorkspaceMarketEvent,
    ) -> None:
        engine = self.replay_execution
        if engine is None:
            return
        decisions = self._evaluate_profit_protection_at(event.timestamp)
        lifecycle = engine.close_profit_drawdown(decisions, event)
        if not lifecycle:
            return
        self._append_replay_execution_events(lifecycle)
        self._sync_replay_execution_snapshot(snapshot_utc=event.timestamp)
        self._evaluate_profit_protection_at(event.timestamp)

    def _complete_replay_execution(self) -> None:
        engine = self.replay_execution
        session = self.replay_session
        event = (
            session.last_execution_event
            if session is not None and session.multi_resolution
            else self.context.current_market_event
        )
        if engine is None or event is None:
            return
        self._append_replay_execution_events(engine.complete(event))
        self._sync_replay_execution_snapshot(snapshot_utc=event.timestamp)
        self._evaluate_profit_protection_at(event.timestamp)

    def _complete_broker_start(self) -> None:
        """Load historical warm-up and activate Live Read-only quotes."""
        provider = self.broker_market_provider
        if provider is None:
            raise WorkspaceRuntimeError(
                "Live Read-only market provider is not attached"
            )
        self.replay_session = None
        self._start_algorithm()
        if self.context.warmup_complete:
            self.context.signal_block_reason = "waiting for acceptable spread"
            self._transition_startup_phase(
                WORKSPACE_STARTUP_PHASE_WAIT_SPREAD,
                "Warm-up is disabled; waiting for live spread.",
            )
        else:
            self.context.signal_block_reason = "warmup incomplete"
            self._transition_startup_phase(
                WORKSPACE_STARTUP_PHASE_WARMUP,
                f"Broker warm-up requires "
                f"{self.context.warmup_bars_required} bars.",
            )
        try:
            events = provider.start_workspace(
                workspace_uid=self.context.workspace_uid,
                broker=self.context.broker,
                account_id=self.context.account_id,
                symbol=self.context.symbol,
                timeframe=self.context.timeframe,
                warmup_bars=self.context.warmup_bars_required,
                spread_limit=self.context.spread_limit,
            )
        except WorkspaceBrokerMarketError as exc:
            if not provider.is_workspace_broker_connected(self.context.workspace_uid):
                self._enter_wait_broker(str(exc))
                return
            provider.stop_workspace(self.context.workspace_uid)
            raise
        self._append_journal(
            "BROKER",
            "LIVE_READ_ONLY_STARTED",
            f"{self.context.broker} Live Read-only feed started for "
            f"{self.context.symbol} {self.context.timeframe}.",
            broker=self.context.broker,
            account_id=self.context.account_id,
            symbol=self.context.symbol,
            timeframe=self.context.timeframe,
        )
        if events:
            self._append_journal(
                "HISTORY",
                "BROKER_WARMUP_LOADED",
                f"Broker warm-up loaded: {len(events)} bars.",
                event_count=len(events),
                first_timestamp=events[0].timestamp.isoformat(),
                last_timestamp=events[-1].timestamp.isoformat(),
            )
        for event in events:
            self._accept_market_event(
                event,
                origin="BROKER_WARMUP",
                warmup_only=True,
            )
        if self.context.warmup_bars_processed < self.context.warmup_bars_required:
            raise WorkspaceRuntimeError(
                "Broker warm-up did not provide enough market bars"
            )
        self.context.current_spread = None
        self.context.spread_ok = False
        self.context.signal_allowed = False
        self.context.signal_block_reason = "waiting for live spread"
        self._transition_startup_phase(
            WORKSPACE_STARTUP_PHASE_WAIT_SPREAD,
            "Broker warm-up completed; waiting for live spread.",
        )
        self._refresh_execution_safety(force=True)

    def advance_broker_market(self) -> WorkspaceMarketEvent | None:
        """Poll one changed broker quote and process it read-only."""
        if self.context.data_mode != WORKSPACE_DATA_MODE_BROKER:
            raise WorkspaceRuntimeError(
                "Broker market polling requires BROKER data mode"
            )
        self._require_state(
            {WORKSPACE_STATE_STARTING, WORKSPACE_STATE_RUNNING},
            "poll broker market",
        )
        if (
            self.context.runtime_state == WORKSPACE_STATE_STARTING
            and self.context.startup_phase
            not in {
                WORKSPACE_STARTUP_PHASE_WAIT_BROKER,
                WORKSPACE_STARTUP_PHASE_SAFETY_HOLD_EXTERNAL_EXPOSURE,
                WORKSPACE_STARTUP_PHASE_WAIT_SPREAD,
                WORKSPACE_STARTUP_PHASE_READY,
                WORKSPACE_STARTUP_PHASE_RUNNING,
            }
        ):
            return None
        provider = self.broker_market_provider
        if provider is None:
            raise WorkspaceRuntimeError(
                "Live Read-only market provider is not attached"
            )
        if not provider.is_workspace_broker_connected(self.context.workspace_uid):
            self._enter_wait_broker("Broker connection is unavailable")
            return None
        if self.context.startup_phase == WORKSPACE_STARTUP_PHASE_WAIT_BROKER:
            try:
                events = provider.resume_workspace(self.context.workspace_uid)
            except WorkspaceBrokerMarketError as exc:
                if not provider.is_workspace_broker_connected(
                    self.context.workspace_uid
                ):
                    return None
                self.fail(exc)
                raise WorkspaceRuntimeError(str(exc)) from exc
            self._resume_after_broker_reconnect(events)
            self._refresh_execution_safety(force=True)
        else:
            self._refresh_execution_safety(force=False)
        try:
            event = provider.poll_workspace(self.context.workspace_uid)
        except (ValueError, WorkspaceBrokerMarketError) as exc:
            if not provider.is_workspace_broker_connected(self.context.workspace_uid):
                self._enter_wait_broker(str(exc))
                return None
            self.fail(exc)
            raise WorkspaceRuntimeError(str(exc)) from exc
        if event is None:
            return None
        self._accept_market_event(event, origin="LIVE_READ_ONLY")
        return event

    def _workspace_execution_guard_mode(self) -> str:
        """Map the WSP account mode to the execution guard contract."""
        account_mode = str(self.context.account_mode or "").strip().upper()
        return "LIVE" if account_mode == "LIVE" else "PAPER"

    def _refresh_execution_safety(
        self,
        *,
        force: bool,
    ) -> WorkspaceExecutionSafetySnapshot:
        """Apply broker-neutral execution safety without stopping market data."""
        provider = self.broker_market_provider
        if provider is None:
            raise WorkspaceRuntimeError(
                "Live Read-only market provider is not attached"
            )
        snapshot = provider.get_workspace_execution_safety(
            self.context.workspace_uid,
            runtime_mode=self._workspace_execution_guard_mode(),
            force=force,
        )
        if snapshot.allowed:
            self._leave_execution_safety_hold(snapshot)
        else:
            self._enter_execution_safety_hold(snapshot)
        return snapshot

    def _enter_execution_safety_hold(
        self,
        snapshot: WorkspaceExecutionSafetySnapshot,
    ) -> None:
        """Block execution/signals while preserving read-only market flow."""
        previous_facts = (
            self.context.safety_hold_reason_code,
            self.context.safety_hold_message,
            self.context.safety_hold_signed_volume,
            self.context.safety_hold_evidence_status,
            self.context.safety_hold_confirmation_required,
        )
        new_facts = (
            snapshot.reason_code,
            snapshot.message,
            float(snapshot.signed_volume),
            snapshot.evidence_status,
            bool(snapshot.confirmation_required),
        )
        first_entry = not self.context.safety_hold_active
        changed = first_entry or previous_facts != new_facts

        self.context.safety_hold_active = True
        self.context.safety_hold_reason_code = snapshot.reason_code
        self.context.safety_hold_message = snapshot.message
        self.context.safety_hold_signed_volume = float(snapshot.signed_volume)
        self.context.safety_hold_evidence_status = snapshot.evidence_status
        self.context.safety_hold_confirmation_required = bool(
            snapshot.confirmation_required
        )
        self.context.safety_hold_checked_utc = snapshot.checked_utc.astimezone(
            UTC
        ).isoformat()
        self.context.signal_allowed = False
        self.context.signal_block_reason = "external IB FX exposure safety hold"

        if self.context.runtime_state == WORKSPACE_STATE_RUNNING:
            self._transition(
                WORKSPACE_STATE_STARTING,
                "External IB FX exposure entered LGE EXCLUSIVE safety hold.",
            )
        if (
            self.context.startup_phase
            != WORKSPACE_STARTUP_PHASE_SAFETY_HOLD_EXTERNAL_EXPOSURE
        ):
            self._transition_startup_phase(
                WORKSPACE_STARTUP_PHASE_SAFETY_HOLD_EXTERNAL_EXPOSURE,
                "Signals and new LGE execution are blocked; market data "
                "remains read-only.",
            )

        if changed:
            self.context.safety_hold_revision += 1
            self._append_journal(
                "SAFETY",
                ("SAFETY_HOLD_ENTERED" if first_entry else "SAFETY_HOLD_UPDATED"),
                snapshot.message,
                account_id=str(self.context.account_id or ""),
                symbol=self.context.symbol,
                reason_code=snapshot.reason_code,
                signed_volume=snapshot.signed_volume,
                evidence_status=snapshot.evidence_status,
                confirmation_required=snapshot.confirmation_required,
                checked_utc=self.context.safety_hold_checked_utc,
            )

    def _leave_execution_safety_hold(
        self,
        snapshot: WorkspaceExecutionSafetySnapshot,
    ) -> None:
        """Clear a hold only after current evidence and require fresh spread."""
        if not self.context.safety_hold_active:
            return
        previous_message = self.context.safety_hold_message or ""
        self._clear_execution_safety_hold(reset_revision=False)
        self.context.safety_hold_revision += 1
        self.context.current_spread = None
        self.context.spread_ok = False
        self.context.signal_allowed = False
        self.context.signal_block_reason = "waiting for fresh live spread"
        self._append_journal(
            "SAFETY",
            "SAFETY_HOLD_CLEARED",
            "Current broker evidence cleared the external exposure hold; "
            "a fresh live spread is required.",
            account_id=str(self.context.account_id or ""),
            symbol=self.context.symbol,
            previous_message=previous_message,
            checked_utc=snapshot.checked_utc.astimezone(UTC).isoformat(),
        )
        self._transition_startup_phase(
            WORKSPACE_STARTUP_PHASE_WAIT_SPREAD,
            "Execution safety passed; waiting for a fresh live quote.",
        )

    def _clear_execution_safety_hold(self, *, reset_revision: bool) -> None:
        """Clear volatile safety-hold fields without a broker operation."""
        self.context.safety_hold_active = False
        self.context.safety_hold_reason_code = None
        self.context.safety_hold_message = None
        self.context.safety_hold_signed_volume = 0.0
        self.context.safety_hold_evidence_status = None
        self.context.safety_hold_confirmation_required = False
        self.context.safety_hold_checked_utc = None
        if reset_revision:
            self.context.safety_hold_revision = 0

    def _enter_wait_broker(self, reason: str) -> None:
        """Suspend broker processing without clearing chart or algorithm state."""
        provider = self.broker_market_provider
        if provider is not None:
            provider.suspend_workspace(self.context.workspace_uid)
        self.context.signal_allowed = False
        self.context.signal_block_reason = "waiting for broker reconnect"
        self.context.event_processing = False
        self.context.current_spread = None
        self.context.spread_ok = False
        self._live_quote_received = False
        self.clear_risk_account_snapshot("broker disconnected")
        if self.context.startup_phase == WORKSPACE_STARTUP_PHASE_WAIT_BROKER:
            return
        self._append_journal(
            "BROKER",
            "BROKER_DISCONNECTED",
            f"{self.context.broker} connection lost; WSP processing suspended.",
            broker=self.context.broker,
            account_id=self.context.account_id,
            reason=str(reason or "broker connection unavailable"),
        )
        if self.context.runtime_state == WORKSPACE_STATE_RUNNING:
            self._transition(
                WORKSPACE_STATE_STARTING,
                "Broker disconnected; waiting for safe reconnect.",
            )
        self._transition_startup_phase(
            WORKSPACE_STARTUP_PHASE_WAIT_BROKER,
            "Market events and signals are blocked until broker reconnect.",
        )

    def _resume_after_broker_reconnect(
        self,
        events: tuple[WorkspaceMarketEvent, ...],
    ) -> None:
        """Resume one suspended feed and require a fresh live spread."""
        self._append_journal(
            "BROKER",
            "BROKER_RECONNECTED",
            f"{self.context.broker} connection restored; binding revalidated.",
            broker=self.context.broker,
            account_id=self.context.account_id,
        )
        self._append_journal(
            "BROKER",
            "MARKET_DATA_RESUBSCRIBED",
            f"Market-data subscription restored for "
            f"{self.context.symbol} {self.context.timeframe}.",
            broker=self.context.broker,
            symbol=self.context.symbol,
            timeframe=self.context.timeframe,
        )
        if events:
            self.context.warmup_bars_processed = 0
            self.context.warmup_complete = self.context.warmup_bars_required == 0
            self._transition_startup_phase(
                WORKSPACE_STARTUP_PHASE_WARMUP,
                "Broker reconnected; restoring missing warm-up bars.",
            )
            for event in events:
                self._accept_market_event(
                    event,
                    origin="BROKER_WARMUP",
                    warmup_only=True,
                )
            if self.context.warmup_bars_processed < self.context.warmup_bars_required:
                raise WorkspaceRuntimeError(
                    "Broker warm-up did not provide enough market bars"
                )
        self.context.current_spread = None
        self.context.spread_ok = False
        self.context.signal_allowed = False
        self.context.signal_block_reason = "waiting for fresh live spread"
        self.context.event_processing = False
        self._transition_startup_phase(
            WORKSPACE_STARTUP_PHASE_WAIT_SPREAD,
            "Broker reconnected; waiting for a fresh live quote and spread.",
        )

    def start(self) -> None:
        """Synchronously start Replay through warm-up and spread guards."""
        self.begin_start()
        self.complete_start()
        while self.context.runtime_state == WORKSPACE_STATE_STARTING:
            if self.context.data_mode == WORKSPACE_DATA_MODE_REPLAY:
                events = self.advance_replay()
                if not events:
                    break
            else:
                event = self.advance_broker_market()
                if event is None:
                    break
        if self.context.runtime_state == WORKSPACE_STATE_ERROR:
            raise WorkspaceRuntimeError(
                self.context.last_error or "Workspace runtime failed to start"
            )
        if self.context.runtime_state != WORKSPACE_STATE_RUNNING:
            raise WorkspaceRuntimeError("Workspace startup guards did not pass")

    def begin_stop(self, reason: str = "Stop requested.") -> None:
        """Enter STOPPING without closing broker positions."""
        self._require_state(
            {
                WORKSPACE_STATE_STARTING,
                WORKSPACE_STATE_RUNNING,
                WORKSPACE_STATE_ERROR,
            },
            "stop",
        )
        self._transition(WORKSPACE_STATE_STOPPING, reason)

    def complete_stop(self) -> None:
        """Stop local processing and return to STOPPED."""
        self._require_state({WORKSPACE_STATE_STOPPING}, "complete stop")
        if self.replay_session is not None:
            self._complete_replay_execution()
            self.replay_session.stop()
        if (
            self.context.data_mode == WORKSPACE_DATA_MODE_BROKER
            and self.broker_market_provider is not None
        ):
            self.broker_market_provider.stop_workspace(self.context.workspace_uid)
        self._stop_algorithm()
        self.clear_risk_account_snapshot("workspace runtime stopped")
        self.context.event_processing = False
        self.context.signal_allowed = False
        self.context.signal_block_reason = "runtime is stopped"
        self._clear_execution_safety_hold(reset_revision=True)
        self._transition_startup_phase(
            WORKSPACE_STARTUP_PHASE_IDLE,
            "Startup guard reset after Stop.",
        )
        self._transition(
            WORKSPACE_STATE_STOPPED,
            "Runtime stopped; broker positions were not closed automatically.",
        )
        self.evaluate_profit_protection()

    def stop(self, reason: str = "Stop requested.") -> None:
        """Synchronous convenience stop used by runtime checks."""
        self.begin_stop(reason)
        self.complete_stop()

    def fail(self, error: Exception | str) -> None:
        """Move any non-stopped runtime into ERROR and retain the reason."""
        message = str(error or "Unknown workspace runtime error")
        self.context.last_error = message
        self.context.signal_allowed = False
        self.context.signal_block_reason = "runtime error"
        self._clear_execution_safety_hold(reset_revision=False)
        self.context.runtime_state = WORKSPACE_STATE_ERROR
        if (
            self.context.data_mode == WORKSPACE_DATA_MODE_BROKER
            and self.broker_market_provider is not None
        ):
            self.broker_market_provider.stop_workspace(self.context.workspace_uid)
        self._stop_algorithm(suppress_errors=True)
        self._append_journal("ERROR", "RUNTIME_ERROR", message)
        self.evaluate_profit_protection()

    def set_replay_speed(self, speed: int) -> None:
        normalized_speed = int(speed)
        if normalized_speed not in REPLAY_SPEEDS:
            raise WorkspaceRuntimeError(f"Unsupported Replay speed: {normalized_speed}")
        session = self.replay_session
        if session is not None:
            session.set_speed(normalized_speed)
        self.replay_settings["speed"] = normalized_speed
        self._append_journal(
            "REPLAY",
            "SPEED_CHANGED",
            f"Replay speed changed to {replay_speed_label(normalized_speed)}.",
            speed=normalized_speed,
        )

    def toggle_replay_pause(self) -> bool:
        self._require_state(
            {WORKSPACE_STATE_STARTING, WORKSPACE_STATE_RUNNING},
            "pause Replay",
        )
        session = self._require_replay_session()
        paused = session.toggle_pause()
        event_name = "PAUSED" if paused else "RESUMED"
        self._append_journal(
            "REPLAY",
            event_name,
            "Replay paused." if paused else "Replay resumed.",
        )
        return paused

    def modify_replay_position_protection(
        self,
        position_id: str,
        field_name: str,
        price: float,
        *,
        source: str = "CHART_DRAG",
    ) -> WorkspaceOwnedSnapshot:
        """Змінити SL/TP paused Replay position без broker execution."""
        self._require_state(
            {WORKSPACE_STATE_STARTING, WORKSPACE_STATE_RUNNING},
            "modify Replay position protection",
        )
        if self.context.data_mode != WORKSPACE_DATA_MODE_REPLAY:
            raise WorkspaceRuntimeError(
                "Position protection modification is Replay-only"
            )
        session = self._require_replay_session()
        if not session.paused:
            raise WorkspaceRuntimeError(
                "Pause Replay before changing Stop Loss or Take Profit"
            )
        engine = self.replay_execution
        if engine is None:
            raise WorkspaceRuntimeError(
                "Replay virtual execution is not active for this workspace"
            )
        current_event = self.context.current_market_event
        if current_event is None:
            raise WorkspaceRuntimeError(
                "Replay has no processed market event for protection change"
            )
        effective_from = self._next_replay_execution_timestamp(session)
        normalized_field = str(field_name or "").strip().lower()
        kwargs: dict[str, float] = {}
        if normalized_field == "stop_loss":
            kwargs["stop_loss"] = float(price)
        elif normalized_field == "take_profit":
            kwargs["take_profit"] = float(price)
        else:
            raise WorkspaceRuntimeError(f"Unsupported protection field: {field_name}")
        try:
            lifecycle_event = engine.modify_position_protection(
                position_id,
                modified_at=current_event.timestamp,
                effective_from=effective_from,
                source=source,
                **kwargs,
            )
        except ValueError as exc:
            raise WorkspaceRuntimeError(str(exc)) from exc
        self._append_replay_execution_events((lifecycle_event,))
        self._sync_replay_execution_snapshot(snapshot_utc=current_event.timestamp)
        self.evaluate_profit_protection()
        return self.owned_snapshot

    def _next_replay_execution_timestamp(
        self,
        session: WorkspaceReplaySession,
    ) -> datetime:
        """Повернути timestamp першого наступного необробленого execution event."""
        pending = self._pending_replay_execution_event(session)
        if pending is not None:
            return pending.timestamp
        if session.index >= len(session.events):
            raise WorkspaceRuntimeError(
                "Replay has no next event for protection modification"
            )
        if session.multi_resolution:
            for index in range(session.index, len(session.events)):
                execution_events = session.execution_events_for_index(index)
                if execution_events:
                    return execution_events[0].timestamp
        return session.events[session.index].timestamp

    def _clear_pending_replay_execution(self) -> None:
        """Очистити volatile cursor ручного execution stepping."""
        self._pending_replay_execution_window_index = None
        self._pending_replay_execution_offset = 0

    def _pending_replay_execution_event(
        self,
        session: WorkspaceReplaySession,
    ) -> WorkspaceMarketEvent | None:
        """Повернути наступний staged execution event без зміни cursor."""
        window_index = self._pending_replay_execution_window_index
        if window_index is None:
            return None
        window = session.execution_events_for_index(window_index)
        if self._pending_replay_execution_offset >= len(window):
            self._clear_pending_replay_execution()
            return None
        return window[self._pending_replay_execution_offset]

    def _stage_replay_execution_window(
        self,
        session: WorkspaceReplaySession,
        event_index: int,
    ) -> None:
        """Зупинити manual strategy Step перед M1 execution window."""
        window = session.execution_events_for_index(event_index)
        if not window:
            self._clear_pending_replay_execution()
            return
        self._pending_replay_execution_window_index = event_index
        self._pending_replay_execution_offset = 0
        if session.state == REPLAY_STATE_COMPLETED:
            session.state = REPLAY_STATE_PAUSED

    def _consume_one_pending_replay_execution(
        self,
        session: WorkspaceReplaySession,
    ) -> WorkspaceMarketEvent | None:
        """Обробити рівно один staged execution event у правильній chronology."""
        event = self._pending_replay_execution_event(session)
        if event is None:
            return None
        self._pending_replay_execution_offset += 1
        self._advance_replay_execution(event)
        self._apply_replay_profit_protection(event)
        self._pending_replay_execution_event(session)
        if (
            self._pending_replay_execution_window_index is None
            and session.index >= len(session.events)
        ):
            session.state = REPLAY_STATE_COMPLETED
        return event

    def _consume_pending_replay_execution(
        self,
        session: WorkspaceReplaySession,
    ) -> None:
        """Дограти staged execution window перед наступним strategy bar/Resume."""
        while self._pending_replay_execution_event(session) is not None:
            self._consume_one_pending_replay_execution(session)

    def step_replay_strategy_bar(self) -> WorkspaceMarketEvent | None:
        """Зробити UI ``Крок`` до strategy bar, не ковтаючи його M1 window."""
        self._require_state(
            {WORKSPACE_STATE_STARTING, WORKSPACE_STATE_RUNNING},
            "step Replay strategy bar",
        )
        session = self._require_replay_session()
        if not session.paused:
            raise WorkspaceRuntimeError("Pause Replay before Step")
        if not session.multi_resolution:
            return self.step_replay()
        self._consume_pending_replay_execution(session)
        if session.state == REPLAY_STATE_COMPLETED:
            self._handle_replay_completion()
            return None
        event = session.step()
        if event is not None:
            event_index = session.index - 1
            self._accept_market_event(
                event,
                origin="STEP",
                advance_replay_execution=False,
            )
            self._stage_replay_execution_window(session, event_index)
            self._append_journal(
                "REPLAY",
                "STRATEGY_STEP_STAGED",
                f"Strategy Step stopped before {session.source_timeframe} "
                "execution window.",
                strategy_timestamp=event.timestamp.isoformat(),
                source_timeframe=session.source_timeframe,
                strategy_timeframe=session.strategy_timeframe,
            )
        self._handle_replay_completion()
        return event

    @property
    def replay_tick_available(self) -> bool:
        """Чи є staged execution event, який ``Тік`` може обробити без strategy Step."""
        session = self.replay_session
        if session is None or not session.paused or not session.multi_resolution:
            return False
        return self._pending_replay_execution_event(session) is not None

    def step_replay_tick(self) -> WorkspaceMarketEvent | None:
        """Обробити один staged Replay execution event, не просуваючи strategy bar."""
        self._require_state(
            {WORKSPACE_STATE_STARTING, WORKSPACE_STATE_RUNNING},
            "step Replay tick",
        )
        session = self._require_replay_session()
        if not session.paused:
            raise WorkspaceRuntimeError("Pause Replay before Tick")
        if not session.multi_resolution:
            return None

        execution_event = self._pending_replay_execution_event(session)
        if execution_event is None:
            return None

        processed = self._consume_one_pending_replay_execution(session)
        if processed is not None:
            self._append_journal(
                "REPLAY",
                "EXECUTION_TICK_STEPPED",
                f"Replay Tick processed {processed.timeframe} "
                f"event {processed.timestamp.isoformat()}.",
                timestamp=processed.timestamp.isoformat(),
                timeframe=processed.timeframe,
                source_timeframe=session.source_timeframe,
                strategy_timeframe=session.strategy_timeframe,
                broker_execution_attempted=False,
            )
        self._handle_replay_completion()
        return processed

    def step_replay(self) -> WorkspaceMarketEvent | None:
        self._require_state(
            {WORKSPACE_STATE_STARTING, WORKSPACE_STATE_RUNNING},
            "step Replay",
        )
        session = self._require_replay_session()
        if not session.paused:
            raise WorkspaceRuntimeError("Pause Replay before Step")
        if session.multi_resolution:
            self._consume_pending_replay_execution(session)
            if session.state == REPLAY_STATE_COMPLETED:
                self._handle_replay_completion()
                return None
        event = session.step()
        if event is not None:
            self._accept_replay_session_event(
                session,
                event,
                session.index - 1,
                origin="STEP",
            )
        self._handle_replay_completion()
        return event

    def advance_replay(
        self,
        *,
        max_events: int | None = None,
    ) -> list[WorkspaceMarketEvent]:
        """Advance one caller-owned Replay chunk without bypassing chronology."""
        if self.context.runtime_state not in {
            WORKSPACE_STATE_STARTING,
            WORKSPACE_STATE_RUNNING,
        }:
            return []
        session = self._require_replay_session()
        if session.state != REPLAY_STATE_RUNNING:
            return []
        if session.multi_resolution and self._pending_replay_execution_event(session):
            self._consume_pending_replay_execution(session)
            if session.state == REPLAY_STATE_COMPLETED:
                self._handle_replay_completion()
                return []
        events = session.advance(max_events=max_events)
        first_index = session.index - len(events)
        for offset, event in enumerate(events):
            self._accept_replay_session_event(
                session,
                event,
                first_index + offset,
                origin="AUTO",
            )
        self._handle_replay_completion()
        return events

    def apply_owned_snapshots(
        self,
        order_rows: Iterable[WorkspaceOrderSnapshot | Mapping[str, Any]],
        position_rows: Iterable[WorkspacePositionSnapshot | Mapping[str, Any]],
    ) -> WorkspaceOwnedSnapshot:
        """Select exact WSP-owned rows and refresh volatile summary facts."""
        binding = WorkspaceBinding(
            workspace_uid=self.context.workspace_uid,
            broker=self.context.broker,
            account_id=self.context.account_id,
            symbol=self.context.symbol,
        )
        selection = WorkspaceOwnershipFilter(binding).select(
            order_rows,
            position_rows,
        )
        self.owned_snapshot = selection
        self.context.set_runtime_snapshot(
            active_orders_count=len(selection.active_orders),
            positions_count=len(selection.active_positions),
            current_profit=selection.current_profit,
            peak_profit=selection.peak_profit,
        )
        self._append_journal(
            "OWNERSHIP",
            "SNAPSHOT_APPLIED",
            f"Owned snapshot: {len(selection.orders)} orders, "
            f"{len(selection.positions)} positions.",
            orders=len(selection.orders),
            active_orders=len(selection.active_orders),
            positions=len(selection.positions),
            active_positions=len(selection.active_positions),
            rejected_orders=selection.rejected_orders,
            rejected_positions=selection.rejected_positions,
        )
        self.evaluate_profit_protection()
        return selection

    def can_form_signal(self) -> bool:
        """Return whether a proposal may be accepted by runtime guards."""
        return bool(
            self.context.runtime_state == WORKSPACE_STATE_RUNNING
            and self.context.signal_allowed
        )

    def signal_records(self) -> tuple[WorkspaceSignalRecord, ...]:
        """Повернути bounded історію сигналів поточного runtime-прогону."""
        return tuple(self.signals)

    def signal_records_for_ui(self) -> tuple[WorkspaceSignalRecord, ...]:
        """Повернути повну історію завершеного Replay, інакше bounded signals."""
        session = self.replay_session
        if (
            self.context.data_mode == WORKSPACE_DATA_MODE_REPLAY
            and session is not None
            and session.completed
        ):
            return tuple(self._historical_signal_records)
        return tuple(self.signals)

    def chart_snapshot(self) -> WorkspaceChartSnapshot:
        """Return chart viewport plus bounded algorithm visualization series."""
        return self._chart_snapshot_with_series()

    def set_chart_visible_count(self, visible_count: int) -> WorkspaceChartSnapshot:
        """Change the WSP chart zoom level without touching market data."""
        self.chart_model.set_visible_count(visible_count)
        return self._chart_snapshot_with_series()

    def scroll_chart_to(self, visible_start: int) -> WorkspaceChartSnapshot:
        """Move the WSP chart viewport to an absolute history index."""
        self.chart_model.scroll_to(visible_start)
        return self._chart_snapshot_with_series()

    def scroll_chart_to_timestamp(
        self,
        timestamp: datetime,
        *,
        exact: bool = True,
    ) -> WorkspaceChartSnapshot:
        """Перейти до exact signal bar або bar, що містить entry timestamp."""
        if not self.chart_model.scroll_to_timestamp(timestamp, exact=exact):
            raise WorkspaceRuntimeError(
                "Requested chart timestamp is not available in processed history"
            )
        return self._chart_snapshot_with_series()

    def scroll_chart_to_latest(self) -> WorkspaceChartSnapshot:
        """Return the WSP chart viewport to the newest market event."""
        self.chart_model.scroll_to_latest()
        return self._chart_snapshot_with_series()

    def _chart_snapshot_with_series(self) -> WorkspaceChartSnapshot:
        snapshot = self.chart_model.snapshot()
        algorithm = self.algorithm or self._chart_algorithm
        if algorithm is None or not snapshot.visible_events:
            return snapshot
        timestamps = tuple(event.timestamp for event in snapshot.visible_events)
        series = algorithm.chart_series(timestamps)
        if not series:
            return snapshot
        return replace(snapshot, series=series)

    def profit_protection_decisions(
        self,
    ) -> tuple[WorkspaceProfitProtectionDecision, ...]:
        """Return current HOLD/CLOSE decisions for exact owned positions."""
        return tuple(self.profit_decisions)

    def pending_close_decisions(
        self,
    ) -> tuple[WorkspaceProfitProtectionDecision, ...]:
        """Return close requests that have not called any broker service."""
        return tuple(
            decision
            for decision in self.profit_decisions
            if decision.action == WORKSPACE_PROFIT_ACTION_CLOSE
        )

    def evaluate_profit_protection(
        self,
    ) -> tuple[WorkspaceProfitProtectionDecision, ...]:
        """Evaluate current owned positions without broker execution."""
        market_event = self.context.current_market_event
        timestamp = (
            market_event.timestamp if market_event is not None else datetime.now(UTC)
        )
        return self._evaluate_profit_protection_at(timestamp)

    def _evaluate_profit_protection_at(
        self,
        timestamp: datetime,
    ) -> tuple[WorkspaceProfitProtectionDecision, ...]:
        runtime_ready = self.context.runtime_state == WORKSPACE_STATE_RUNNING
        spread_guard_passed = bool(
            self.context.spread_ok and self.context.signal_allowed
        )
        active_positions = self.owned_snapshot.active_positions
        if isinstance(
            self.profit_drawdown_guard,
            WorkspaceCandidateFNegativePdRecoveryGuard,
        ):
            self.profit_drawdown_guard.synchronize_active_positions(
                {position.position_id for position in active_positions}
            )
        decisions = [
            self.profit_drawdown_guard.evaluate(
                position,
                timestamp=timestamp,
                runtime_ready=runtime_ready,
                spread_guard_passed=spread_guard_passed,
            )
            for position in active_positions
        ]
        self._replace_profit_protection_decisions(
            decisions[:MAX_WORKSPACE_PROFIT_DECISIONS]
        )
        return tuple(self.profit_decisions)

    def handle_order_event(self, event: object) -> None:
        """Forward one future broker-neutral order event to the algorithm."""
        algorithm = self.algorithm
        if algorithm is None:
            raise WorkspaceRuntimeError("Workspace algorithm is not started")
        try:
            algorithm.on_order_event(event)
        except Exception as exc:
            self.fail(exc)
            raise WorkspaceRuntimeError(str(exc)) from exc
        self._append_journal(
            "ALGORITHM",
            "ORDER_EVENT_PROCESSED",
            "Order event processed without direct broker access.",
        )

    def close_guard_result(self) -> WorkspaceCloseGuardResult:
        """Return every active blocker that prevents safe WSP deletion."""
        replay_session = self.replay_session
        replay_step_active = bool(replay_session is not None and replay_session.in_step)
        return WorkspaceCloseGuard.evaluate(
            runtime_state=self.context.runtime_state,
            active_orders_count=self.context.active_orders_count,
            open_positions_count=self.context.positions_count,
            broker_operation_active=self.context.broker_operation_active,
            market_event_processing=self.context.event_processing,
            replay_step_active=replay_step_active,
            pending_close_decisions_count=self.context.pending_close_decisions_count,
        )

    def close_block_reason(self) -> str | None:
        """Return the primary close blocker in the legacy string format."""
        return self.close_guard_result().primary_reason

    def journal_from(self, offset: int) -> tuple[WorkspaceJournalEntry, ...]:
        normalized_offset = max(0, int(offset))
        return tuple(self.journal[normalized_offset:])

    def _accept_replay_session_event(
        self,
        session: WorkspaceReplaySession,
        event: WorkspaceMarketEvent,
        event_index: int,
        *,
        origin: str,
    ) -> None:
        if not session.multi_resolution:
            self._accept_market_event(event, origin=origin)
            return
        self._accept_market_event(
            event,
            origin=origin,
            advance_replay_execution=False,
        )
        for execution_event in session.execution_events_for_index(event_index):
            self._advance_replay_execution(execution_event)
            self._apply_replay_profit_protection(execution_event)

    def _accept_market_event(
        self,
        event: WorkspaceMarketEvent,
        *,
        origin: str,
        warmup_only: bool = False,
        advance_replay_execution: bool = True,
    ) -> None:
        self.context.event_processing = True
        try:
            previous_event = self.context.current_market_event
            self.context.current_market_event = event
            self.context.market_event_count += 1
            self.chart_model.append(event)
            self._update_market_guards(event, warmup_only=warmup_only)
            if advance_replay_execution:
                self._advance_replay_execution(event)
                if self.replay_execution is None:
                    self.evaluate_profit_protection()
                else:
                    self._apply_replay_profit_protection(event)
            journal_event = "EVENT_ACCEPTED"
            if origin == "LIVE_READ_ONLY":
                if not self._live_quote_received:
                    journal_event = "LIVE_QUOTE_RECEIVED"
                    self._live_quote_received = True
                elif (
                    previous_event is None or event.timestamp > previous_event.timestamp
                ):
                    journal_event = "LIVE_BAR_OPENED"
            self._append_journal(
                "MARKET",
                journal_event,
                f"{origin} {event.symbol} {event.timeframe} "
                f"close={event.close:.6f} spread={event.spread:.6f}.",
                origin=origin,
                timestamp=event.timestamp.isoformat(),
                close=event.close,
                spread=event.spread,
                signal_allowed=self.context.signal_allowed,
            )
            self._dispatch_market_event_to_algorithm(event)
        finally:
            self.context.event_processing = False

    def _replace_profit_protection_decisions(
        self,
        decisions: list[WorkspaceProfitProtectionDecision],
    ) -> None:
        previous = {
            decision.position_id: decision for decision in self.profit_decisions
        }
        self.profit_decisions = decisions
        self.context.profit_decisions_count = len(decisions)
        self.context.pending_close_decisions_count = sum(
            1
            for decision in decisions
            if decision.action == WORKSPACE_PROFIT_ACTION_CLOSE
        )
        current = {decision.position_id: decision for decision in decisions}
        for position_id, decision in current.items():
            previous_decision = previous.get(position_id)
            if previous_decision is not None:
                same_result = (
                    previous_decision.action == decision.action
                    and previous_decision.reason == decision.reason
                    and previous_decision.current_profit == decision.current_profit
                    and previous_decision.peak_profit == decision.peak_profit
                )
                if same_result:
                    continue
            if decision.action != WORKSPACE_PROFIT_ACTION_CLOSE:
                if (
                    previous_decision is not None
                    and previous_decision.action == WORKSPACE_PROFIT_ACTION_CLOSE
                ):
                    self._append_journal(
                        "RISK",
                        "CLOSE_DECISION_CLEARED",
                        f"Position {position_id}: {decision.reason}.",
                        position_id=position_id,
                        reason=decision.reason,
                    )
                continue
            self._append_journal(
                "RISK",
                "CLOSE_DECISION_CREATED",
                f"Position {position_id}: {decision.reason}.",
                position_id=position_id,
                current_profit=decision.current_profit,
                peak_profit=decision.peak_profit,
                drawdown_percent=decision.drawdown_percent,
                drawdown_limit_percent=decision.drawdown_limit_percent,
                broker_execution_attempted=False,
            )
        removed_position_ids = set(previous) - set(current)
        for position_id in sorted(removed_position_ids):
            previous_decision = previous[position_id]
            if previous_decision.action != WORKSPACE_PROFIT_ACTION_CLOSE:
                continue
            self._append_journal(
                "RISK",
                "CLOSE_DECISION_CLEARED",
                f"Position {position_id} is no longer active or owned.",
                position_id=position_id,
                reason="position is no longer active or owned",
            )

    def _start_algorithm(self) -> None:
        algorithm = self.algorithm_factory(self.context.algorithm_id)
        if not isinstance(algorithm, WorkspaceAlgorithm):
            raise WorkspaceAlgorithmError(
                "algorithm_factory must return WorkspaceAlgorithm"
            )
        self.algorithm = algorithm
        self._chart_algorithm = algorithm
        try:
            algorithm.configure(
                self.context,
                dict(self.algorithm_parameters),
            )
            self._apply_algorithm_warmup_requirements(algorithm)
            self._append_journal(
                "ALGORITHM",
                "CONFIGURED",
                f"Algorithm {self.context.algorithm_id} configured.",
                algorithm_id=self.context.algorithm_id,
            )
            algorithm.start()
        except Exception as exc:
            self._stop_algorithm(suppress_errors=True)
            raise WorkspaceAlgorithmError(str(exc)) from exc
        self._append_journal(
            "ALGORITHM",
            "STARTED",
            "Algorithm started in signal-only workspace mode.",
            control_mode=self.context.control_mode,
        )

    def _apply_algorithm_warmup_requirements(
        self,
        algorithm: WorkspaceAlgorithm,
    ) -> None:
        """Apply computed component warm-up without deleting legacy storage."""
        requirements = algorithm.warmup_requirements()
        if requirements is None:
            return
        normalized_requirements = tuple(requirements)
        plan = build_workspace_warmup_plan(normalized_requirements)
        legacy_required = self.context.warmup_bars_required
        required_by_timeframe = {
            timeframe_plan.timeframe: timeframe_plan.required_bars
            for timeframe_plan in plan.timeframes
        }
        components_by_timeframe = {
            timeframe_plan.timeframe: timeframe_plan.limiting_components
            for timeframe_plan in plan.timeframes
        }
        computed_required = plan.required_bars_for(self.context.timeframe)
        self.context.warmup_bars_required = computed_required
        self.context.warmup_complete = computed_required == 0
        self.context.warmup_required_by_timeframe = required_by_timeframe
        self.context.warmup_components_by_timeframe = components_by_timeframe
        self._append_journal(
            "ALGORITHM",
            "WARMUP_REQUIREMENTS_APPLIED",
            f"Computed warm-up requires {computed_required} bars for "
            f"{self.context.timeframe}; all timeframe requirements preserved.",
            timeframe=self.context.timeframe,
            computed_bars=computed_required,
            legacy_bars_preserved=legacy_required,
            components=tuple(
                requirement.component_code
                for requirement in normalized_requirements
                if requirement.timeframe == self.context.timeframe
            ),
            required_by_timeframe=dict(required_by_timeframe),
            components_by_timeframe=dict(components_by_timeframe),
        )

    def _stop_algorithm(self, *, suppress_errors: bool = False) -> None:
        algorithm = self.algorithm
        self.algorithm = None
        if algorithm is None:
            return
        try:
            algorithm.stop()
        except Exception as exc:
            if not suppress_errors:
                raise WorkspaceRuntimeError(str(exc)) from exc
            self._append_journal(
                "ERROR",
                "ALGORITHM_STOP_ERROR",
                str(exc),
            )
            return
        self._append_journal(
            "ALGORITHM",
            "STOPPED",
            "Algorithm stopped; broker positions were not changed.",
        )

    def _dispatch_market_event_to_algorithm(
        self,
        event: WorkspaceMarketEvent,
    ) -> None:
        algorithm = self.algorithm
        if algorithm is None:
            return
        try:
            output = algorithm.on_market_event(event)
            proposals = normalize_signal_output(output)
        except Exception as exc:
            self.fail(exc)
            raise WorkspaceRuntimeError(str(exc)) from exc
        for proposal in proposals:
            self._record_signal(event, proposal)
        self._apply_candidate_f_lifecycle_events(algorithm)

    def _apply_candidate_f_lifecycle_events(
        self,
        algorithm: WorkspaceAlgorithm,
    ) -> None:
        """Прикріпити terminal evidence Candidate F без нового сигналу."""
        drain = getattr(algorithm, "drain_candidate_f_lifecycle_events", None)
        if not callable(drain):
            return
        drain_events = cast(Callable[[], Iterable[object]], drain)
        for event in tuple(drain_events()):
            self._apply_candidate_f_lifecycle_event(event)

    def _apply_candidate_f_lifecycle_event(self, event: object) -> None:
        """Оновити початковий ARMED record і додати одну подію Journal."""
        original_timestamp = getattr(event, "original_signal_timestamp", None)
        direction = str(getattr(event, "direction", "") or "").strip().upper()
        if not isinstance(original_timestamp, datetime) or not direction:
            return
        original_timestamp = (
            original_timestamp
            if original_timestamp.tzinfo is not None
            else original_timestamp.replace(tzinfo=UTC)
        ).astimezone(UTC)
        matched = next(
            (
                record
                for record in reversed(self._historical_signal_records)
                if record.timestamp == original_timestamp
                and record.direction == direction
                and record.filter_reason_code == "ALLIGATOR_DEFERRED_ARMED"
            ),
            None,
        )
        if matched is None:
            return

        action = str(getattr(event, "action", "") or "").strip().upper()
        reason_code = str(
            getattr(event, "reason_code", "") or ""
        ).strip().upper()
        event_timestamp = getattr(event, "event_timestamp", None)
        if not action or not isinstance(event_timestamp, datetime):
            return
        event_timestamp = (
            event_timestamp
            if event_timestamp.tzinfo is not None
            else event_timestamp.replace(tzinfo=UTC)
        ).astimezone(UTC)
        delay_bars = getattr(event, "delay_bars", None)
        filter_context = getattr(event, "filter_context", None)
        updated = replace(
            matched,
            candidate_f_lifecycle_action=action,
            candidate_f_lifecycle_reason=reason_code or None,
            candidate_f_lifecycle_timestamp=event_timestamp,
            candidate_f_lifecycle_delay_bars=delay_bars,
            candidate_f_lifecycle_context=filter_context,
        )
        self._historical_signal_records = [
            updated if record.signal_uid == matched.signal_uid else record
            for record in self._historical_signal_records
        ]
        self.signals = [
            updated if record.signal_uid == matched.signal_uid else record
            for record in self.signals
        ]
        self._append_journal(
            "SIGNAL",
            f"CANDIDATE_F_{action}",
            f"Candidate F {action}: {reason_code or '—'}.",
            signal_uid=matched.signal_uid,
            signal_timestamp=matched.timestamp,
            lifecycle_timestamp=event_timestamp,
            lifecycle_action=action,
            lifecycle_reason_code=reason_code or None,
            lifecycle_delay_bars=delay_bars,
            broker_execution_attempted=False,
        )

    def _record_signal(
        self,
        event: WorkspaceMarketEvent,
        proposal: WorkspaceSignalProposal,
    ) -> WorkspaceSignalRecord:
        signal_uid = self._signal_uid(event, proposal)
        runtime_allowed = self.can_form_signal()
        filter_allowed = proposal.filter_decision == WORKSPACE_SIGNAL_FILTER_ALLOW
        accepted = runtime_allowed and filter_allowed
        spread_status = WORKSPACE_SIGNAL_SPREAD_UNKNOWN
        if self.context.current_spread is not None:
            spread_status = (
                WORKSPACE_SIGNAL_SPREAD_OK
                if self.context.spread_ok
                else WORKSPACE_SIGNAL_SPREAD_BLOCKED
            )

        risk_decision = None
        if accepted and proposal.trade_intent is not None:
            risk_decision = self._evaluate_signal_risk(
                event,
                proposal,
                proposal.trade_intent,
                signal_uid=signal_uid,
            )
            accepted = risk_decision.allowed

        reason = self._signal_decision_reason(
            proposal,
            accepted,
            runtime_allowed=runtime_allowed,
            risk_decision=risk_decision,
        )
        record = WorkspaceSignalRecord(
            timestamp=event.timestamp,
            signal_uid=signal_uid,
            workspace_uid=self.context.workspace_uid,
            broker=self.context.broker,
            account_id=self.context.account_id,
            symbol=self.context.symbol,
            timeframe=self.context.timeframe,
            source_mode=event.source_mode,
            signal_type=proposal.signal_type,
            direction=proposal.direction,
            strength=proposal.strength,
            macd_state=proposal.macd_state,
            alligator_confirmation=proposal.alligator_confirmation,
            spread_status=spread_status,
            accepted=accepted,
            reason=reason,
            source_reason_code=proposal.source_reason_code,
            source_profile_uid=proposal.source_profile_uid,
            source_profile_revision=proposal.source_profile_revision,
            risk_decision=(
                risk_decision.decision if risk_decision is not None else None
            ),
            risk_reason_code=(
                risk_decision.reason_code if risk_decision is not None else None
            ),
            requested_volume=(
                risk_decision.requested_volume if risk_decision is not None else None
            ),
            approved_volume=(
                risk_decision.approved_volume if risk_decision is not None else None
            ),
            risk_execution_attempted=(
                risk_decision.execution_attempted
                if risk_decision is not None
                else False
            ),
            filter_decision=proposal.filter_decision,
            filter_reason_code=proposal.filter_reason_code,
            filter_context=proposal.filter_context,
        )
        if self.signal_record_observer is not None:
            self.signal_record_observer(record)
        self._historical_signal_records.append(record)
        self.signals.append(record)
        if len(self.signals) > MAX_WORKSPACE_SIGNAL_RECORDS:
            del self.signals[:-MAX_WORKSPACE_SIGNAL_RECORDS]
        self.context.signals_count = len(self.signals)
        self.context.accepted_signals_count = sum(
            1 for signal in self.signals if signal.accepted
        )
        self.context.rejected_signals_count = (
            self.context.signals_count - self.context.accepted_signals_count
        )
        event_name = "SIGNAL_ACCEPTED" if accepted else "SIGNAL_REJECTED"
        self._append_journal(
            "SIGNAL",
            event_name,
            f"{proposal.signal_type} {proposal.direction}: {reason}",
            signal_uid=signal_uid,
            direction=proposal.direction,
            strength=proposal.strength,
            spread_status=spread_status,
            control_mode=self.context.control_mode,
            risk_decision=record.risk_decision,
            risk_reason_code=record.risk_reason_code,
            filter_decision=record.filter_decision,
            filter_reason_code=record.filter_reason_code,
            signal_timestamp=event.timestamp,
        )
        if self.replay_execution is not None and record.accepted:
            lifecycle = self.replay_execution.queue_signal(record, event)
            self._append_replay_execution_events(lifecycle)
            self._sync_replay_execution_snapshot()
        return record

    def _evaluate_signal_risk(
        self,
        event: WorkspaceMarketEvent,
        proposal: WorkspaceSignalProposal,
        trade_intent: WorkspaceTradeIntent,
        *,
        signal_uid: str,
    ) -> WorkspaceRiskDecision:
        snapshot = self.risk_account_snapshot
        snapshot_binding_verified = bool(
            snapshot is not None
            and snapshot.matches_binding(
                workspace_uid=self.context.workspace_uid,
                broker=self.context.broker,
                account_id=self.context.account_id,
                source_mode=self.context.data_mode,
            )
        )
        request = WorkspaceRiskRequest(
            timestamp=event.timestamp,
            workspace_uid=self.context.workspace_uid,
            broker=self.context.broker,
            account_id=self.context.account_id,
            symbol=self.context.symbol,
            side=proposal.direction,
            source_mode=event.source_mode,
            requested_volume=trade_intent.requested_volume,
            equity=snapshot.equity if snapshot is not None else None,
            estimated_loss_at_stop=trade_intent.estimated_loss_at_stop,
            stop_loss=trade_intent.stop_loss,
            open_positions_count=(
                snapshot.open_positions_count if snapshot is not None else None
            ),
            daily_realized_pnl=(
                snapshot.daily_realized_pnl if snapshot is not None else None
            ),
            runtime_ready=self.can_form_signal(),
            binding_verified=bool(
                self._market_event_binding_matches(event) and snapshot_binding_verified
            ),
            market_valid=True,
            spread_guard_passed=self.context.spread_ok,
            signal_uid=signal_uid,
        )
        decision = self.evaluate_risk_request(request)
        event_name = "RISK_ALLOWED" if decision.allowed else "RISK_BLOCKED"
        self._append_journal(
            "RISK",
            event_name,
            f"{decision.reason_code}: {decision.reason_text}",
            signal_uid=signal_uid,
            decision=decision.decision,
            reason_code=decision.reason_code,
            requested_volume=decision.requested_volume,
            approved_volume=decision.approved_volume,
            calculated_risk_percent=decision.calculated_risk_percent,
            daily_loss_percent=decision.daily_loss_percent,
            execution_attempted=decision.execution_attempted,
        )
        return decision

    def _signal_uid(
        self,
        event: WorkspaceMarketEvent,
        proposal: WorkspaceSignalProposal,
    ) -> str:
        trade_intent = proposal.trade_intent
        if trade_intent is not None and trade_intent.signal_uid is not None:
            return trade_intent.signal_uid
        components = (
            self.context.workspace_uid,
            event.timestamp.isoformat(),
            event.source_mode,
            proposal.signal_type,
            proposal.direction,
            f"{proposal.strength:.12f}",
            proposal.macd_state,
            proposal.alligator_confirmation,
        )
        payload = "|".join(components).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:32]

    def _market_event_binding_matches(
        self,
        event: WorkspaceMarketEvent,
    ) -> bool:
        return bool(
            event.broker == self.context.broker
            and event.symbol == self.context.symbol
            and event.timeframe == self.context.timeframe
            and event.source_mode == self.context.data_mode
        )

    def _signal_decision_reason(
        self,
        proposal: WorkspaceSignalProposal,
        accepted: bool,
        *,
        runtime_allowed: bool,
        risk_decision: WorkspaceRiskDecision | None = None,
    ) -> str:
        if risk_decision is not None:
            return f"{risk_decision.reason_code}: " f"{risk_decision.reason_text}"
        if not runtime_allowed:
            return (
                self.context.signal_block_reason or "runtime is not ready for signals"
            )
        if proposal.filter_decision == WORKSPACE_SIGNAL_FILTER_REJECT:
            reason_code = proposal.filter_reason_code or "COMPONENT_FILTER_REJECTED"
            if proposal.reason:
                return proposal.reason
            return f"{reason_code}: signal was rejected by component filter"
        if not accepted:
            return "signal was rejected before risk evaluation"
        if proposal.reason:
            return proposal.reason
        if self.context.control_mode == "MANUAL":
            return "accepted for signal display only"
        if self.context.control_mode == "SEMI":
            return "accepted; user confirmation is required"
        return "accepted; automatic execution is disabled in RoadMap95"

    def _update_market_guards(
        self,
        event: WorkspaceMarketEvent,
        *,
        warmup_only: bool = False,
    ) -> None:
        previous_signal_allowed = self.context.signal_allowed
        previous_block_reason = self.context.signal_block_reason
        self.context.current_spread = event.spread
        self.context.spread_ok = event.spread <= self.context.spread_limit

        if self.context.safety_hold_active:
            self.context.signal_allowed = False
            self.context.signal_block_reason = "external IB FX exposure safety hold"
            return

        if self.context.startup_phase == WORKSPACE_STARTUP_PHASE_WARMUP:
            self.context.warmup_bars_processed += 1
            if self.context.warmup_bars_processed < self.context.warmup_bars_required:
                self.context.signal_allowed = False
                self.context.signal_block_reason = "warmup incomplete"
                self._append_journal(
                    "GUARD",
                    "WARMUP_PROGRESS",
                    f"Warm-up {self.context.warmup_bars_processed}/"
                    f"{self.context.warmup_bars_required}; signals blocked.",
                    processed=self.context.warmup_bars_processed,
                    required=self.context.warmup_bars_required,
                )
                return

            self.context.warmup_complete = True
            self._append_journal(
                "GUARD",
                "WARMUP_COMPLETED",
                f"Warm-up completed after "
                f"{self.context.warmup_bars_processed} bars.",
                processed=self.context.warmup_bars_processed,
            )
            self._transition_startup_phase(
                WORKSPACE_STARTUP_PHASE_WAIT_SPREAD,
                "Indicator warm-up completed; checking spread.",
            )
            if warmup_only:
                self.context.current_spread = None
                self.context.spread_ok = False
                self.context.signal_allowed = False
                self.context.signal_block_reason = "waiting for live spread"
                return

        if self.context.startup_phase == WORKSPACE_STARTUP_PHASE_WAIT_SPREAD:
            if not self.context.spread_ok:
                self.context.signal_allowed = False
                self.context.signal_block_reason = "spread too wide"
                self._append_spread_blocked(event)
                return

            self.context.signal_allowed = True
            self.context.signal_block_reason = None
            self._append_journal(
                "GUARD",
                "SPREAD_ACCEPTED",
                f"Spread {event.spread:.6f} is within "
                f"limit {self.context.spread_limit:.6f}.",
                spread=event.spread,
                spread_limit=self.context.spread_limit,
            )
            self._transition_startup_phase(
                WORKSPACE_STARTUP_PHASE_READY,
                "Warm-up and spread guard passed.",
            )
            self._transition(WORKSPACE_STATE_RUNNING, "Runtime is ready.")
            self._transition_startup_phase(
                WORKSPACE_STARTUP_PHASE_RUNNING,
                "Algorithm market-event processing enabled.",
            )
            return

        if self.context.startup_phase != WORKSPACE_STARTUP_PHASE_RUNNING:
            self.context.signal_allowed = False
            if self.context.signal_block_reason is None:
                self.context.signal_block_reason = "startup guard is not ready"
            return

        self.context.signal_allowed = self.context.spread_ok
        self.context.signal_block_reason = (
            None if self.context.spread_ok else "spread too wide"
        )
        if self.context.signal_allowed == previous_signal_allowed:
            if self.context.signal_block_reason == previous_block_reason:
                return
        if self.context.signal_allowed:
            self._append_journal(
                "GUARD",
                "SIGNALS_RESUMED",
                f"Spread returned within limit: {event.spread:.6f}.",
                spread=event.spread,
                spread_limit=self.context.spread_limit,
            )
        else:
            self._append_spread_blocked(event)

    def _append_spread_blocked(self, event: WorkspaceMarketEvent) -> None:
        self._append_journal(
            "GUARD",
            "SPREAD_BLOCKED",
            f"Spread {event.spread:.6f} exceeds "
            f"limit {self.context.spread_limit:.6f}; signals blocked.",
            spread=event.spread,
            spread_limit=self.context.spread_limit,
        )

    def _handle_replay_completion(self) -> None:
        session = self.replay_session
        if session is None or session.state != REPLAY_STATE_COMPLETED:
            return
        if self._replay_completion_logged:
            return
        self._replay_completion_logged = True
        if self._historical_replay_started_monotonic is not None:
            self._historical_replay_elapsed_seconds = max(
                0.0,
                time.monotonic() - self._historical_replay_started_monotonic,
            )
        self._complete_replay_execution()
        self._build_historical_replay_summary()
        self._append_journal(
            "REPLAY",
            "SESSION_COMPLETED",
            f"Replay completed after {session.index} events.",
            event_count=session.index,
            replay_elapsed_seconds=self._historical_replay_elapsed_seconds,
        )
        if self.context.runtime_state == WORKSPACE_STATE_STARTING:
            self.fail("Replay completed before startup guards became READY")

    def _build_historical_replay_summary(self) -> None:
        """Freeze canonical statistics for one fully completed Replay run."""
        session = self.replay_session
        if session is None or not session.completed:
            return
        if self.historical_summary is not None:
            return
        if not session.events:
            raise WorkspaceRuntimeError("Completed Replay has no market events")

        history_report = session.history_report
        if history_report is None:
            period_start = session.events[0].timestamp
            period_end = session.events[-1].timestamp
            accepted_bars = len(session.events)
            skipped_bars = 0
            gaps = 0
        else:
            period_start = history_report.first_timestamp
            period_end = history_report.last_timestamp
            accepted_bars = len(session.events)
            skipped_bars = history_report.filtered_rows
            gaps = history_report.gap_count

        initial_balance = self.context.replay_initial_balance
        if initial_balance is None:
            raise WorkspaceRuntimeError(
                "Historical Replay summary requires initial balance"
            )
        spread = float(self.replay_settings.get("spread", session.events[0].spread))
        trades = (
            self.replay_execution.trade_diagnostics()
            if self.replay_execution is not None
            else ()
        )
        summary = build_workspace_historical_replay_summary(
            symbol=self.context.symbol,
            timeframe=self.context.timeframe,
            period_start=period_start,
            period_end=period_end,
            accepted_bars=accepted_bars,
            skipped_bars=skipped_bars,
            gaps=gaps,
            spread=spread,
            initial_balance=initial_balance,
            signals=build_workspace_historical_signal_metrics(
                tuple(self._historical_signal_records)
            ),
            trades=trades,
            source_timeframe=(session.source_timeframe or self.context.timeframe),
            csv_selection_elapsed_seconds=(
                self._historical_csv_selection_elapsed_seconds
            ),
            replay_elapsed_seconds=self._historical_replay_elapsed_seconds,
        )
        self.historical_summary = summary
        self._append_journal(
            "REPLAY",
            "HISTORICAL_SUMMARY_READY",
            "Historical Replay summary calculated from completed run facts.",
            trades=summary.opened_trades,
            winning_trades=summary.winning_trades,
            losing_trades=summary.losing_trades,
            win_rate_percent=summary.win_rate_percent,
            net_profit=summary.net_profit,
            profit_factor=summary.profit_factor,
            maximum_drawdown=summary.maximum_drawdown,
            maximum_drawdown_percent=summary.maximum_drawdown_percent,
            source_timeframe=summary.source_timeframe,
            csv_selection_elapsed_seconds=summary.csv_selection_elapsed_seconds,
            replay_elapsed_seconds=summary.replay_elapsed_seconds,
            broker_execution_attempted=False,
        )

    def _transition(self, target_state: str, message: str) -> None:
        previous_state = self.context.runtime_state
        self.context.runtime_state = target_state
        self._append_journal(
            "LIFECYCLE",
            "STATE_CHANGED",
            f"{previous_state} -> {target_state}. {message}",
            previous_state=previous_state,
            target_state=target_state,
        )

    def _transition_startup_phase(self, target_phase: str, message: str) -> None:
        if target_phase not in WORKSPACE_STARTUP_PHASES:
            raise WorkspaceRuntimeError(
                f"Invalid workspace startup phase: {target_phase}"
            )
        previous_phase = self.context.startup_phase
        self.context.startup_phase = target_phase
        self._append_journal(
            "GUARD",
            "STARTUP_PHASE_CHANGED",
            f"{previous_phase} -> {target_phase}. {message}",
            previous_phase=previous_phase,
            target_phase=target_phase,
        )

    def _require_state(self, allowed_states: set[str], operation: str) -> None:
        current_state = self.context.runtime_state
        if current_state not in allowed_states:
            allowed = ", ".join(sorted(allowed_states))
            raise WorkspaceRuntimeError(
                f"Cannot {operation} from {current_state}; expected {allowed}"
            )

    def _require_replay_session(self) -> WorkspaceReplaySession:
        if self.replay_session is None:
            raise WorkspaceRuntimeError("Replay session is not initialized")
        return self.replay_session

    def _append_journal(
        self,
        category: str,
        event: str,
        message: str,
        **details: Any,
    ) -> None:
        self.journal.append(
            WorkspaceJournalEntry(
                timestamp=datetime.now(UTC),
                workspace_uid=self.context.workspace_uid,
                category=category,
                event=event,
                message=message,
                details=dict(details),
            )
        )


def _non_negative_int_parameter(
    value: object,
    default: int,
    field_name: str,
) -> int:
    if value is None or value == "":
        return default
    value_text = str(value).strip()
    try:
        numeric_value = float(value_text)
    except ValueError as exc:
        raise WorkspaceRuntimeError(f"{field_name} must be an integer") from exc
    if not math.isfinite(numeric_value) or not numeric_value.is_integer():
        raise WorkspaceRuntimeError(f"{field_name} must be an integer")
    normalized = int(numeric_value)
    if normalized < 0:
        raise WorkspaceRuntimeError(f"{field_name} cannot be negative")
    return normalized


def _positive_float_parameter(
    value: object,
    default: float,
    field_name: str,
) -> float:
    if value is None or value == "":
        return default
    value_text = str(value).strip()
    try:
        normalized = float(value_text)
    except ValueError as exc:
        raise WorkspaceRuntimeError(f"{field_name} must be numeric") from exc
    if not math.isfinite(normalized) or normalized <= 0.0:
        raise WorkspaceRuntimeError(f"{field_name} must be positive")
    return normalized


def _positive_finite_value(value: object, field_name: str) -> float:
    normalized = _finite_value(value, field_name)
    if normalized <= 0.0:
        raise WorkspaceRuntimeError(f"{field_name} must be positive")
    return normalized


def _finite_value(value: object, field_name: str) -> float:
    value_text = str(value).strip()
    try:
        normalized = float(value_text)
    except ValueError as exc:
        raise WorkspaceRuntimeError(f"{field_name} must be numeric") from exc
    if not math.isfinite(normalized):
        raise WorkspaceRuntimeError(f"{field_name} must be finite")
    return normalized
