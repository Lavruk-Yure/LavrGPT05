"""workspace_broker_market.py — read-only BROKER market feed для WSP.

Модуль перевіряє broker binding, завантажує завершені historical warm-up bars
і перетворює мінливі bid/ask snapshots на canonical timeframe events. Поточний
live bucket зберігається лише у volatile aggregator state; на rollover provider
віддає попередній immutable completed bar рівно один раз. Quote/history request
accounting та IB exposure safety лишаються broker-neutral, а execution requests
цей pipeline не створює. Replay data path модуль навмисно не обробляє.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from time import monotonic
from typing import Any, Protocol

from core.algorithm_workspace import WORKSPACE_DATA_MODE_BROKER
from core.timeframes import get_timeframe
from core.workspace_broker_accounting import (
    WorkspaceBrokerAccountingSnapshot,
    WorkspaceBrokerRequestAccounting,
    WorkspaceBrokerSubscriptionKey,
)
from core.workspace_market_event import (
    WorkspaceMarketEvent,
    normalize_market_timestamp,
)

WORKSPACE_EXECUTION_SAFETY_ALLOWED = "ALLOWED"
WORKSPACE_EXECUTION_SAFETY_HOLD_EXTERNAL_EXPOSURE = "SAFETY_HOLD_EXTERNAL_EXPOSURE"
WORKSPACE_EXECUTION_SAFETY_REFRESH_SECONDS = 10.0


class WorkspaceBrokerMarketError(RuntimeError):
    """Raised when one broker-bound WSP cannot obtain safe market data."""


class _WorkspaceExecutionSafetyExposureProtocol(Protocol):
    """Structural exposure fields returned by the RuntimeEngine guard."""

    signed_volume: float
    evidence_status: str
    confirmation_required: bool


class _WorkspaceExecutionSafetyDecisionProtocol(Protocol):
    """Structural guard decision consumed by the broker market provider."""

    allowed: bool
    reason_code: str
    reason_text: str
    matching_exposure: _WorkspaceExecutionSafetyExposureProtocol | None


class _WorkspaceExecutionSafetyGuardRuntimeProtocol(Protocol):
    """RuntimeEngine method required by the WSP execution guard."""

    def refresh_ib_fx_external_exposure_guard(
        self,
        *,
        account_id: str,
        symbol_name: str,
        runtime_mode: str,
    ) -> _WorkspaceExecutionSafetyDecisionProtocol:
        """Return the current execution-safety decision."""
        ...


@dataclass(frozen=True, slots=True)
class WorkspaceExecutionSafetySnapshot:
    """One broker-neutral execution-safety result for an active WSP."""

    allowed: bool
    reason_code: str
    message: str
    checked_utc: datetime
    signed_volume: float = 0.0
    evidence_status: str = ""
    confirmation_required: bool = False

    @classmethod
    def allowed_snapshot(
        cls,
        message: str = "Execution safety passed",
    ) -> WorkspaceExecutionSafetySnapshot:
        return cls(
            allowed=True,
            reason_code=WORKSPACE_EXECUTION_SAFETY_ALLOWED,
            message=message,
            checked_utc=datetime.now(UTC),
        )


class WorkspaceBrokerMarketProviderProtocol(ABC):
    """Minimal feed contract consumed by WorkspaceRuntime."""

    @abstractmethod
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
        """Validate binding, subscribe and return historical warm-up events."""
        ...

    @abstractmethod
    def poll_workspace(
        self,
        workspace_uid: str,
    ) -> WorkspaceMarketEvent | None:
        """Return one completed live bar or None while its bucket is open."""
        ...

    @abstractmethod
    def is_workspace_broker_connected(self, workspace_uid: str) -> bool:
        """Return whether the bound broker session is currently connected."""
        ...

    @abstractmethod
    def suspend_workspace(self, workspace_uid: str) -> None:
        """Pause one WSP feed binding without discarding its chart state."""
        ...

    @abstractmethod
    def resume_workspace(
        self,
        workspace_uid: str,
    ) -> tuple[WorkspaceMarketEvent, ...]:
        """Revalidate one WSP binding and restore any missing warm-up."""
        ...

    @abstractmethod
    def stop_workspace(self, workspace_uid: str) -> None:
        """Release one volatile WSP feed binding."""
        ...

    def get_workspace_execution_safety(
        self,
        workspace_uid: str,
        *,
        runtime_mode: str,
        force: bool = False,
    ) -> WorkspaceExecutionSafetySnapshot:
        """Return a default safe result for providers without execution."""
        del workspace_uid, runtime_mode, force
        return WorkspaceExecutionSafetySnapshot.allowed_snapshot()


@dataclass(frozen=True, slots=True)
class WorkspaceBrokerBinding:
    """Immutable broker/account/symbol binding owned by one WSP."""

    workspace_uid: str
    broker: str
    account_id: str | None
    symbol: str
    timeframe: str

    def __post_init__(self) -> None:
        workspace_uid = str(self.workspace_uid or "").strip()
        broker = str(self.broker or "").strip().upper()
        account_id = str(self.account_id or "").strip() or None
        symbol = str(self.symbol or "").strip().upper().replace("/", "")
        symbol = symbol.replace(".", "")
        timeframe = str(self.timeframe or "").strip().upper()
        if not workspace_uid:
            raise ValueError("workspace_uid is required")
        if broker not in {"CTRADER", "IB"}:
            raise ValueError("Unsupported workspace broker")
        if len(symbol) != 6 or not symbol.isalpha():
            raise ValueError("Workspace Forex symbol must contain six letters")
        get_timeframe(timeframe)
        object.__setattr__(self, "workspace_uid", workspace_uid)
        object.__setattr__(self, "broker", broker)
        object.__setattr__(self, "account_id", account_id)
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "timeframe", timeframe)


@dataclass(slots=True)
class WorkspaceLiveBarAggregator:
    """Aggregate quotes and release one immutable bar only after rollover."""

    binding: WorkspaceBrokerBinding
    _bucket_timestamp: datetime | None = None
    _bid: float = 0.0
    _ask: float = 0.0
    _open: float = 0.0
    _high: float = 0.0
    _low: float = 0.0
    _close: float = 0.0
    _volume: float = 0.0

    def update(
        self,
        *,
        timestamp: datetime,
        bid: float,
        ask: float,
        volume: float = 0.0,
    ) -> WorkspaceMarketEvent | None:
        """Update the open bucket and release the previous one on rollover."""
        quote_time = normalize_market_timestamp(timestamp)
        bid_value = float(bid)
        ask_value = float(ask)
        volume_value = max(float(volume), 0.0)
        if bid_value <= 0.0 or ask_value <= 0.0:
            raise WorkspaceBrokerMarketError("Live quote prices must be positive")
        if ask_value < bid_value:
            raise WorkspaceBrokerMarketError("Live ask cannot be below bid")

        bucket = self._bucket_start(quote_time)
        midpoint = (bid_value + ask_value) / 2.0
        if self._bucket_timestamp is None:
            self._start_bucket(
                bucket=bucket,
                bid=bid_value,
                ask=ask_value,
                midpoint=midpoint,
                volume=volume_value,
            )
            return None
        if bucket < self._bucket_timestamp:
            raise WorkspaceBrokerMarketError(
                "Live quote buckets must be ordered chronologically"
            )
        if bucket == self._bucket_timestamp:
            self._bid = bid_value
            self._ask = ask_value
            self._high = max(self._high, midpoint)
            self._low = min(self._low, midpoint)
            self._close = midpoint
            self._volume = max(self._volume, volume_value)
            return None

        completed = WorkspaceMarketEvent(
            timestamp=self._bucket_timestamp,
            broker=self.binding.broker,
            symbol=self.binding.symbol,
            timeframe=self.binding.timeframe,
            bid=self._bid,
            ask=self._ask,
            spread=self._ask - self._bid,
            open=self._open,
            high=self._high,
            low=self._low,
            close=self._close,
            volume=self._volume,
            source_mode=WORKSPACE_DATA_MODE_BROKER,
        )
        self._start_bucket(
            bucket=bucket,
            bid=bid_value,
            ask=ask_value,
            midpoint=midpoint,
            volume=volume_value,
        )
        return completed

    def _start_bucket(
        self,
        *,
        bucket: datetime,
        bid: float,
        ask: float,
        midpoint: float,
        volume: float,
    ) -> None:
        """Initialize one open bucket without exposing it to the runtime."""
        self._bucket_timestamp = bucket
        self._bid = bid
        self._ask = ask
        self._open = midpoint
        self._high = midpoint
        self._low = midpoint
        self._close = midpoint
        self._volume = volume

    def _bucket_start(self, value: datetime) -> datetime:
        timeframe = get_timeframe(self.binding.timeframe)
        interval_seconds = timeframe.minutes * 60
        epoch_seconds = int(value.timestamp())
        bucket_seconds = epoch_seconds - epoch_seconds % interval_seconds
        return datetime.fromtimestamp(bucket_seconds, tz=UTC)


class RuntimeEngineWorkspaceMarketProvider(WorkspaceBrokerMarketProviderProtocol):
    """Adapt the shared RuntimeEngine to the WSP broker-feed contract."""

    def __init__(self, runtime_engine: Any) -> None:
        self._runtime_engine = runtime_engine
        self._request_accounting = WorkspaceBrokerRequestAccounting()
        self._bindings: dict[str, WorkspaceBrokerBinding] = {}
        self._aggregators: dict[str, WorkspaceLiveBarAggregator] = {}
        self._last_quote_signatures: dict[str, tuple[object, ...]] = {}
        self._last_quote_timestamps: dict[str, datetime] = {}
        self._suspended_workspaces: set[str] = set()
        self._warmup_requests: dict[str, tuple[int, float]] = {}
        self._warmup_loaded: set[str] = set()
        self._execution_safety: dict[str, WorkspaceExecutionSafetySnapshot] = {}
        self._execution_safety_checked_at: dict[str, float] = {}

    def request_accounting_snapshot(
        self,
    ) -> WorkspaceBrokerAccountingSnapshot:
        """Return immutable WSP broker request/subscription counters."""
        return self._request_accounting.snapshot()

    def get_workspace_execution_safety(
        self,
        workspace_uid: str,
        *,
        runtime_mode: str,
        force: bool = False,
    ) -> WorkspaceExecutionSafetySnapshot:
        """Refresh/cached LGE EXCLUSIVE safety for one bound IB WSP."""
        uid = str(workspace_uid)
        binding = self._bindings.get(uid)

        if binding is None:
            raise WorkspaceBrokerMarketError("Workspace broker feed is not active")

        if binding.broker != "IB":
            snapshot = WorkspaceExecutionSafetySnapshot.allowed_snapshot(
                "External IB FX exposure guard is not applicable"
            )
            self._execution_safety[uid] = snapshot
            return snapshot

        now_monotonic = monotonic()
        last_checked = self._execution_safety_checked_at.get(uid)
        cached = self._execution_safety.get(uid)

        if (
            not force
            and cached is not None
            and last_checked is not None
            and now_monotonic - last_checked
            < WORKSPACE_EXECUTION_SAFETY_REFRESH_SECONDS
        ):
            return cached

        refresh_guard = getattr(
            self._runtime_engine,
            "refresh_ib_fx_external_exposure_guard",
            None,
        )

        if not callable(refresh_guard):
            snapshot = WorkspaceExecutionSafetySnapshot(
                allowed=False,
                reason_code=WORKSPACE_EXECUTION_SAFETY_HOLD_EXTERNAL_EXPOSURE,
                message=(
                    "RuntimeEngine does not provide the IB FX external "
                    "exposure guard"
                ),
                checked_utc=datetime.now(UTC),
                evidence_status="EVIDENCE_UNAVAILABLE",
                confirmation_required=True,
            )
        else:
            guard_runtime: _WorkspaceExecutionSafetyGuardRuntimeProtocol
            guard_runtime = self._runtime_engine
            try:
                decision = guard_runtime.refresh_ib_fx_external_exposure_guard(
                    account_id=binding.account_id or "",
                    symbol_name=binding.symbol,
                    runtime_mode=runtime_mode,
                )
            except Exception as exc:
                snapshot = WorkspaceExecutionSafetySnapshot(
                    allowed=False,
                    reason_code=WORKSPACE_EXECUTION_SAFETY_HOLD_EXTERNAL_EXPOSURE,
                    message=str(exc),
                    checked_utc=datetime.now(UTC),
                    evidence_status="EVIDENCE_UNAVAILABLE",
                    confirmation_required=True,
                )
            else:
                exposure = decision.matching_exposure
                snapshot = WorkspaceExecutionSafetySnapshot(
                    allowed=bool(decision.allowed),
                    reason_code=(
                        WORKSPACE_EXECUTION_SAFETY_ALLOWED
                        if decision.allowed
                        else WORKSPACE_EXECUTION_SAFETY_HOLD_EXTERNAL_EXPOSURE
                    ),
                    message=str(decision.reason_text or ""),
                    checked_utc=datetime.now(UTC),
                    signed_volume=(
                        float(exposure.signed_volume) if exposure is not None else 0.0
                    ),
                    evidence_status=(
                        str(exposure.evidence_status or "")
                        if exposure is not None
                        else str(decision.reason_code or "")
                    ),
                    confirmation_required=bool(
                        exposure is not None and exposure.confirmation_required
                    )
                    or not bool(decision.allowed),
                )

        self._execution_safety[uid] = snapshot
        self._execution_safety_checked_at[uid] = now_monotonic
        return snapshot

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
        binding = WorkspaceBrokerBinding(
            workspace_uid=workspace_uid,
            broker=broker,
            account_id=account_id,
            symbol=symbol,
            timeframe=timeframe,
        )
        if binding.workspace_uid in self._bindings:
            raise WorkspaceBrokerMarketError("Workspace broker feed is already active")
        aggregator = WorkspaceLiveBarAggregator(binding)
        self._request_accounting.acquire_subscription(
            binding.workspace_uid,
            WorkspaceBrokerSubscriptionKey(
                broker=binding.broker,
                symbol=binding.symbol,
            ),
        )
        self._bindings[binding.workspace_uid] = binding
        self._aggregators[binding.workspace_uid] = aggregator
        self._last_quote_signatures.pop(binding.workspace_uid, None)
        self._last_quote_timestamps.pop(binding.workspace_uid, None)
        self._suspended_workspaces.discard(binding.workspace_uid)
        self._warmup_requests[binding.workspace_uid] = (
            max(int(warmup_bars), 0),
            float(spread_limit),
        )
        self._warmup_loaded.discard(binding.workspace_uid)
        self._execution_safety.pop(binding.workspace_uid, None)
        self._execution_safety_checked_at.pop(binding.workspace_uid, None)
        validator = getattr(
            self._runtime_engine,
            "validate_workspace_broker_binding",
            None,
        )
        if not callable(validator):
            raise WorkspaceBrokerMarketError(
                "RuntimeEngine does not support WSP broker bindings"
            )
        try:
            validator(binding.broker, binding.account_id)
        except Exception as exc:
            raise WorkspaceBrokerMarketError(str(exc)) from exc

        events = self._load_warmup_events(
            binding,
            warmup_bars=max(int(warmup_bars), 0),
            spread_limit=float(spread_limit),
        )
        self._warmup_loaded.add(binding.workspace_uid)
        return events

    def poll_workspace(
        self,
        workspace_uid: str,
    ) -> WorkspaceMarketEvent | None:
        binding = self._bindings.get(str(workspace_uid))
        if binding is None:
            raise WorkspaceBrokerMarketError("Workspace broker feed is not active")
        if binding.workspace_uid in self._suspended_workspaces:
            return None
        snapshot_method = getattr(
            self._runtime_engine,
            "get_workspace_forex_quote_snapshot",
            None,
        )
        if not callable(snapshot_method):
            raise WorkspaceBrokerMarketError(
                "RuntimeEngine does not provide Forex quote snapshots"
            )

        symbols = sorted(
            {
                item.symbol
                for item in self._bindings.values()
                if item.broker == binding.broker
            }
        )
        payload = self._request_quote_snapshot(
            binding.broker,
            symbols,
            snapshot_method=snapshot_method,
        )
        quotes = payload.get("quotes")
        if not isinstance(quotes, dict):
            return None
        row = quotes.get(binding.symbol)
        if not isinstance(row, dict):
            return None
        bid = self._positive_float(row.get("bid"))
        ask = self._positive_float(row.get("ask"))
        if bid is None or ask is None or ask < bid:
            return None
        timestamp = self._quote_timestamp(
            row.get("timestamp"),
            payload.get("captured_utc"),
        )
        previous_timestamp = self._last_quote_timestamps.get(binding.workspace_uid)
        if previous_timestamp is not None and timestamp < previous_timestamp:
            return None
        volume = self._non_negative_float(row.get("volume"))
        signature = (
            timestamp.isoformat(),
            round(bid, 12),
            round(ask, 12),
            round(volume, 6),
        )
        if self._last_quote_signatures.get(binding.workspace_uid) == signature:
            return None
        self._last_quote_signatures[binding.workspace_uid] = signature
        self._last_quote_timestamps[binding.workspace_uid] = timestamp
        return self._aggregators[binding.workspace_uid].update(
            timestamp=timestamp,
            bid=bid,
            ask=ask,
            volume=volume,
        )

    def is_workspace_broker_connected(self, workspace_uid: str) -> bool:
        """Return current connectivity for the broker bound to one WSP."""
        binding = self._bindings.get(str(workspace_uid))
        if binding is None:
            return False
        checker = getattr(
            self._runtime_engine,
            "is_named_broker_connected",
            None,
        )
        if not callable(checker):
            return False
        try:
            return bool(checker(binding.broker))
        except Exception:  # noqa
            return False

    def suspend_workspace(self, workspace_uid: str) -> None:
        """Pause one binding while preserving aggregator and chart continuity."""
        uid = str(workspace_uid)
        if uid in self._bindings:
            self._suspended_workspaces.add(uid)

    def resume_workspace(
        self,
        workspace_uid: str,
    ) -> tuple[WorkspaceMarketEvent, ...]:
        """Revalidate one binding after reconnect and restore missing warm-up."""
        uid = str(workspace_uid)
        binding = self._bindings.get(uid)
        if binding is None:
            raise WorkspaceBrokerMarketError("Workspace broker feed is not active")
        validator = getattr(
            self._runtime_engine,
            "validate_workspace_broker_binding",
            None,
        )
        if not callable(validator):
            raise WorkspaceBrokerMarketError(
                "RuntimeEngine does not support WSP broker bindings"
            )
        try:
            validator(binding.broker, binding.account_id)
        except Exception as exc:
            raise WorkspaceBrokerMarketError(str(exc)) from exc

        self._request_accounting.record_retry_request()
        self._suspended_workspaces.discard(uid)
        self._execution_safety_checked_at.pop(uid, None)
        if uid in self._warmup_loaded:
            return ()

        warmup_bars, spread_limit = self._warmup_requests.get(uid, (0, 0.0))
        events = self._load_warmup_events(
            binding,
            warmup_bars=warmup_bars,
            spread_limit=spread_limit,
        )
        self._warmup_loaded.add(uid)
        return events

    def stop_workspace(self, workspace_uid: str) -> None:
        uid = str(workspace_uid)
        binding = self._bindings.pop(uid, None)
        self._aggregators.pop(uid, None)
        self._last_quote_signatures.pop(uid, None)
        self._last_quote_timestamps.pop(uid, None)
        self._suspended_workspaces.discard(uid)
        self._warmup_requests.pop(uid, None)
        self._warmup_loaded.discard(uid)
        self._execution_safety.pop(uid, None)
        self._execution_safety_checked_at.pop(uid, None)
        release = self._request_accounting.release_subscription(uid)
        if binding is None:
            return
        if not release.last_reference:
            return
        snapshot_method = getattr(
            self._runtime_engine,
            "get_workspace_forex_quote_snapshot",
            None,
        )
        if not callable(snapshot_method):
            return
        remaining_symbols = self._symbols_for_broker(binding.broker)
        try:
            self._request_quote_snapshot(
                binding.broker,
                remaining_symbols,
                snapshot_method=snapshot_method,
            )
        except (RuntimeError, TypeError, ValueError):
            return

    def _load_warmup_events(
        self,
        binding: WorkspaceBrokerBinding,
        *,
        warmup_bars: int,
        spread_limit: float,
    ) -> tuple[WorkspaceMarketEvent, ...]:
        if warmup_bars <= 0:
            return ()
        timeframe = get_timeframe(binding.timeframe)
        requested_bars = max(warmup_bars * 4 + 20, 100)
        end_utc = datetime.now(UTC).replace(microsecond=0)
        start_utc = end_utc - timedelta(minutes=timeframe.minutes * requested_bars)
        if binding.broker == "CTRADER":
            method_name = "download_ctrader_historical_bars"
        else:
            method_name = "download_ib_historical_bars"
        history_method = getattr(self._runtime_engine, method_name, None)
        if not callable(history_method):
            raise WorkspaceBrokerMarketError(
                f"RuntimeEngine does not provide {binding.broker} warm-up history"
            )
        self._request_accounting.record_history_download()
        try:
            result = history_method(
                symbol_name=binding.symbol,
                timeframe=binding.timeframe,
                start_utc=start_utc,
                end_utc=end_utc,
            )
        except Exception as exc:
            self._request_accounting.record_failed_request()
            raise WorkspaceBrokerMarketError(str(exc)) from exc
        self._request_accounting.record_history_broker_requests(
            int(getattr(result, "request_count", 0) or 0)
        )
        bars = tuple(getattr(result, "bars", ()) or ())
        if len(bars) < warmup_bars:
            self._request_accounting.record_failed_request()
            raise WorkspaceBrokerMarketError(
                f"{binding.broker} returned {len(bars)} warm-up bars; "
                f"{warmup_bars} required"
            )
        spread = max(min(float(spread_limit), 0.01), 0.000001)
        events: list[WorkspaceMarketEvent] = []
        for bar in bars[-warmup_bars:]:
            close = float(getattr(bar, "close"))
            bid = close - spread / 2.0
            ask = close + spread / 2.0
            events.append(
                WorkspaceMarketEvent(
                    timestamp=getattr(bar, "timestamp"),
                    broker=binding.broker,
                    symbol=binding.symbol,
                    timeframe=binding.timeframe,
                    bid=bid,
                    ask=ask,
                    spread=ask - bid,
                    open=float(getattr(bar, "open")),
                    high=float(getattr(bar, "high")),
                    low=float(getattr(bar, "low")),
                    close=close,
                    volume=max(float(getattr(bar, "volume", 0.0)), 0.0),
                    source_mode=WORKSPACE_DATA_MODE_BROKER,
                )
            )
        return tuple(events)

    def _symbols_for_broker(self, broker: str) -> list[str]:
        """Return one deduplicated sorted symbol set for active WSPs."""
        return sorted(
            {item.symbol for item in self._bindings.values() if item.broker == broker}
        )

    def _request_quote_snapshot(
        self,
        broker: str,
        symbols: list[str],
        *,
        snapshot_method: Any,
    ) -> dict:
        """Dispatch one counted quote/subscription synchronization call."""
        self._request_accounting.record_quote_snapshot_request()
        try:
            payload = snapshot_method(broker, list(symbols))
        except Exception as exc:
            self._request_accounting.record_failed_request()
            raise WorkspaceBrokerMarketError(str(exc)) from exc
        if not isinstance(payload, dict):
            self._request_accounting.record_failed_request()
            raise WorkspaceBrokerMarketError("Invalid broker quote payload")
        return payload

    @staticmethod
    def _positive_float(value: object) -> float | None:
        if not isinstance(value, (str, bytes, bytearray, int, float)):
            return None
        try:
            number = float(value)
        except ValueError:
            return None
        if not isfinite(number) or number <= 0.0:
            return None
        return number

    @staticmethod
    def _non_negative_float(value: object) -> float:
        if not isinstance(value, (str, bytes, bytearray, int, float)):
            return 0.0
        try:
            number = float(value)
        except ValueError:
            return 0.0
        if not isfinite(number):
            return 0.0
        return max(number, 0.0)

    @staticmethod
    def _quote_timestamp(
        value: object,
        fallback: object,
    ) -> datetime:
        for candidate in (value, fallback):
            if candidate is None:
                continue
            if isinstance(candidate, (int, float)):
                raw = float(candidate)
                if raw > 10_000_000_000.0:
                    raw /= 1000.0
                if raw > 0.0:
                    return datetime.fromtimestamp(raw, tz=UTC)
            text = str(candidate or "").strip()
            if text:
                try:
                    return normalize_market_timestamp(text)
                except ValueError:
                    continue
        return datetime.now(UTC).replace(microsecond=0)
