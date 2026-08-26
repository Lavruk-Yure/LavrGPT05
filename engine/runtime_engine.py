# runtime_engine.py
"""Канонічний runtime engine ATS-двигуна LGE.

Оркеструє runtime state, broker services, події та SQLite без Qt/UI.
Broker-history API підтримує необов'язковий neutral progress callback.
"""

import json
import logging
import math
import time
from datetime import UTC, datetime
from typing import Any, Protocol

from engine.broker_account import BrokerAccount
from engine.broker_connection_state import BrokerConnectionState
from engine.broker_interface import BrokerInterface
from engine.broker_order_identity import (
    ORDER_CONTROL_MODE_MANUAL,
    build_broker_operation_comment,
    build_broker_order_comment,
    get_broker_order_control_mode,
    normalize_order_control_mode,
    strip_broker_order_identity,
)
from engine.broker_position import BrokerPosition
from engine.ctrader_history import (
    CTraderHistoryDownloadResult,
    CTraderHistoryProgressCallback,
)
from engine.db.runtime_db import (
    connect_runtime_db,
    get_runtime_database_path,
    insert_runtime_event,
    insert_session,
)
from engine.ib_history import (
    IBHistoryDownloadResult,
    IBHistoryProgressCallback,
)
from engine.ib_fx_external_exposure import (
    IB_FX_EXTERNAL_EXPOSURE_CONFIRMED,
    IB_FX_GUARD_EVIDENCE_UNAVAILABLE,
    IB_FX_GUARD_MODE_LIVE,
    IB_FX_GUARD_MODE_PAPER,
    IBFxExternalExposure,
    IBFxExternalExposureExecutionBlockedError,
    IBFxExternalExposureGuardDecision,
    evaluate_ib_fx_external_exposure_guard,
)
from engine.ib_order_errors import (
    IBManualOpenConfirmationPendingError,
    IBMarketOrderTimeoutError,
    IBVirtualLegCloseConfirmationPendingError,
)
from engine.ib_position_group import (
    IBPositionGroupSnapshot,
    build_ib_position_group_snapshot,
)
from engine.ib_virtual_position_leg import (
    IBVirtualPositionLeg,
    IBVirtualPositionLegReconciliationSnapshot,
    build_confirmed_ib_virtual_position_leg_after_open,
    build_ib_virtual_position_legs_from_repository_seeds,
    get_ib_cash_fx_virtual_observation_offset,
    reconcile_ib_virtual_position_legs,
)
from engine.market_availability_state import (
    MarketAvailabilityResult,
    detect_market_state,
)
from engine.runtime_account_state import RuntimeAccountState
from engine.runtime_broker_health import RuntimeBrokerHealth
from engine.runtime_constants import (
    CTRADER_RECONNECT_COOLDOWN_SECONDS,
    CTRADER_RECONNECT_FAILURE_BACKOFF_SECONDS,
    CTRADER_RECONNECT_WATCH_INTERVAL_SECONDS,
    IB_LEG_CLOSE_EXECUTION_STATUS_PENDING,
    IB_LEG_ORDER_ROLE_CLOSE,
    IB_LEG_PERSISTENCE_STATUS_ERROR,
    IB_LEG_PERSISTENCE_STATUS_NOT_CREATED,
    IB_LEG_PERSISTENCE_STATUS_RECONCILED,
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_LEG_STATUS_PARTIALLY_CLOSED,
    IB_MANUAL_OPEN_EXECUTION_STATUS_PENDING,
    IB_MANUAL_OPEN_TIMEOUT_RECOVERY_ATTEMPTS,
    IB_MANUAL_OPEN_TIMEOUT_RECOVERY_DELAY_SECONDS,
    IB_POSITION_GROUP_MODE_NET_ONLY,
    IB_POSITION_QUANTITY_ABS_TOLERANCE,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_PROTECTION_STATUS_NONE,
    IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING,
    IB_RECONCILIATION_STATUS_RECONCILED,
    IB_RECONNECT_COOLDOWN_SECONDS,
    IB_RECONNECT_WATCH_INTERVAL_SECONDS,
    IB_VIRTUAL_LEG_CLOSE_TIMEOUT_RECOVERY_ATTEMPTS,
    IB_VIRTUAL_LEG_CLOSE_TIMEOUT_RECOVERY_DELAY_SECONDS,
    IB_VIRTUAL_LEG_POST_MODIFY_RECONCILIATION_ATTEMPTS,
    IB_VIRTUAL_LEG_POST_MODIFY_RECONCILIATION_DELAY_SECONDS,
    RUNTIME_RECONNECT_TASK_INTERVAL_SECONDS,
)
from engine.runtime_context import RuntimeContext
from engine.runtime_events import RuntimeEvent, RuntimeEventType
from engine.runtime_reconnect_task import RuntimeReconnectTask
from engine.runtime_repository import RuntimeRepository
from engine.runtime_scheduler import RuntimeScheduler
from engine.runtime_state import RuntimeState

logger = logging.getLogger(__name__)


class BrokerHealthProtocol(Protocol):
    """
    Мінімальний protocol для broker health.
    """

    last_error: str

    def is_connected(self) -> bool:
        """
        Перевірити connected state.
        """
        ...


class CTraderRuntimeServiceProtocol(Protocol):
    """
    Мінімальний protocol для cTrader runtime service.
    """

    def prepare_startup_connection(
        self,
        account_mode: str,
    ) -> bool:
        """Check bounded cTrader Startup Readiness."""
        ...

    def connect_demo(self) -> object | None:
        """
        Підключити cTrader DEMO.
        """
        ...

    def connect_live(self) -> object | None:
        """
        Підключити cTrader LIVE.
        """
        ...

    def disconnect(self) -> None:
        """
        Відключити cTrader runtime service.
        """
        ...

    def reconnect(self) -> object | None:
        """
        Виконати reconnect cTrader через service layer.
        """
        ...

    def get_forex_quote_snapshot(
        self,
        symbol_names: list[str],
    ) -> dict:
        """Return cached streaming cTrader Forex quotes."""
        ...

    def get_historical_trendbars(
        self,
        symbol_name: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
        progress_callback: CTraderHistoryProgressCallback | None = None,
    ) -> CTraderHistoryDownloadResult:
        """Download cTrader historical bars."""
        ...

    def get_positions(self) -> list:
        """
        Повернути відкриті IB broker positions.
        """
        ...

    def get_broker_health(self) -> RuntimeBrokerHealth:
        """
        Повернути broker health.
        """
        ...

    def get_account_state(self) -> RuntimeAccountState:
        """
        Повернути runtime account state.
        """
        ...

    def get_account_list(self) -> list[dict]:
        """
        Повернути список cTrader accounts.
        """

    def place_market_order(
        self,
        symbol_name: str,
        side: str,
        lots: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual order",
    ) -> dict:
        """
        Відправити MARKET order через cTrader service.
        """
        ...

    def close_position(
        self,
        position_id: int | str,
        lots: float | None = None,
    ) -> object:
        """
        Закрити cTrader position.
        """
        ...

    def modify_position_sl_tp(
        self,
        position_id: int | str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        """
        Змінити SL/TP cTrader position.
        """
        ...


class IBRuntimeServiceProtocol(Protocol):
    """
    Мінімальний protocol для IB runtime service.
    """

    def connect_demo(self) -> object | None:
        """
        Підключити IB DEMO.
        """
        ...

    def disconnect(self) -> None:
        """
        Відключити IB runtime service.
        """
        ...

    def get_broker_health(self) -> RuntimeBrokerHealth:
        """
        Повернути broker health.
        """
        ...

    def get_account_state(self) -> RuntimeAccountState:
        """
        Повернути runtime account state.
        """
        ...

    def reconnect(self) -> object | None:
        """
        Виконати reconnect IB через service layer.
        """
        ...

    def get_virtual_position_leg_evidence_snapshot(self) -> dict:
        """
        Повернути read-only IB virtual-leg evidence snapshot.
        """
        ...

    def get_positions(self) -> list:
        """
        Повернути відкриті IB broker positions.
        """
        ...

    def get_forex_quote_snapshot(
        self,
        symbol_names: list[str],
    ) -> dict:
        """Return cached streaming IB Forex quotes."""
        ...

    def get_managed_accounts(self) -> list[str]:
        """Return IB accounts visible through the active session."""
        ...

    def get_historical_bars(
        self,
        symbol_name: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
        progress_callback: IBHistoryProgressCallback | None = None,
    ) -> IBHistoryDownloadResult:
        """Download one normalized IB historical range."""
        ...

    def place_market_order(
        self,
        symbol_name: str,
        side: str,
        quantity: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual order",
    ) -> dict:
        """
        Відправити MARKET order через IB service.
        """
        ...

    def close_position(
        self,
        position_id: str,
        quantity: float | None = None,
        comment: str = "LGE manual close",
    ) -> dict:
        """
        Закрити IB position через service.
        """
        ...

    def modify_position_sl_tp(
        self,
        position_id: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        """
        Змінити SL/TP IB position через service.
        """
        ...

    def close_virtual_position_leg(
        self,
        position_uid: str,
        position_id: str,
        account_id: str,
        symbol_name: str,
        position_side: str,
        position_volume: float,
        parent_order_id: int,
        stop_loss_order_id: int | None,
        take_profit_order_id: int | None,
        current_oca_group: str,
        comment: str = "LGE virtual-leg close",
    ) -> dict:
        """Close one exact persisted IB virtual leg."""
        ...

    def modify_virtual_position_leg_sl_tp(
        self,
        position_uid: str,
        position_id: str,
        account_id: str,
        symbol_name: str,
        position_side: str,
        position_volume: float,
        parent_order_id: int,
        stop_loss_order_id: int | None,
        take_profit_order_id: int | None,
        current_oca_group: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        order_ref: str = "",
    ) -> dict:
        """Modify one exact persisted IB virtual leg."""
        ...


class RuntimeEngine:
    """
    Базовий runtime engine ATS.
    """

    def __init__(
        self,
        db_path: str | None = None,
    ) -> None:
        """
        Ініціалізація runtime engine.
        """

        self.context = RuntimeContext()
        self.events: list[RuntimeEvent] = []
        self.broker_adapter: BrokerInterface | None = None
        self.ctrader_runtime_service: CTraderRuntimeServiceProtocol | None = None
        self.ib_runtime_service: IBRuntimeServiceProtocol | None = None

        self.scheduler = RuntimeScheduler()

        self._ib_reconnect_task: RuntimeReconnectTask | None = None
        self._ctrader_reconnect_task: RuntimeReconnectTask | None = None

        if db_path is None:
            db_path = str(get_runtime_database_path("DEMO"))

        self.connection = connect_runtime_db(db_path)
        self.context.active_db = db_path

        self.repository = RuntimeRepository(self.connection)

        self._ib_reconnect_watch_started: bool = False
        self._ctrader_reconnect_watch_started: bool = False

        self._active_broker_locked = False
        self._shutdown_complete = False

    def add_event(
        self,
        event_type: RuntimeEventType,
        message: str = "",
        payload: dict | None = None,
    ) -> RuntimeEvent:
        """
        Додати runtime event.
        """

        event = RuntimeEvent(
            event_type=event_type,
            message=message,
            payload=payload or {},
        )

        self.events.append(event)

        insert_runtime_event(
            connection=self.connection,
            runtime_event_type=str(event.event_type.value),
            message=event.message,
            payload_json=json.dumps(event.payload),
            created_utc=event.created_utc,
        )

        return event

    def startup(self) -> None:
        """
        Запустити runtime engine.
        """

        self.context.set_runtime_state(RuntimeState.STARTING)

        self.add_event(
            RuntimeEventType.STARTUP,
            message="Runtime engine startup",
        )

        self.context.set_runtime_state(RuntimeState.RUNNING)

        self.scheduler.start()

        insert_session(
            connection=self.connection,
            session_id=self.context.session_id,
            runtime_state=str(self.context.runtime_state.value),
            broker=self.context.broker,
            account_mode=self.context.account_mode,
            execution_mode=self.context.execution_mode,
            created_utc=self.context.created_utc,
        )

    def shutdown(self) -> None:
        """
        Коректно зупинити runtime engine.
        """

        if self._shutdown_complete:
            return

        self.context.set_runtime_state(RuntimeState.STOPPING)
        if self.scheduler.is_running:
            try:
                self.scheduler.stop()
            except Exception:  # noqa
                logger.exception("Runtime scheduler stop failed.")

        if self.ctrader_runtime_service is not None:
            try:
                self.ctrader_runtime_service.disconnect()
            except Exception:  # noqa
                logger.exception("cTrader runtime service disconnect failed.")

        if self.ib_runtime_service is not None:
            try:
                self.ib_runtime_service.disconnect()
            except Exception:  # noqa
                logger.exception("IB runtime service disconnect failed.")

        if self.broker_adapter is not None and self.broker_adapter.is_connected():
            try:
                self.broker_adapter.disconnect()
            except Exception:  # noqa
                logger.exception("Broker adapter disconnect failed.")

        self.context.set_broker_connection_state(
            BrokerConnectionState.DISCONNECTED,
        )

        try:
            self.add_event(
                RuntimeEventType.SHUTDOWN,
                message="Runtime engine shutdown",
            )
        except Exception:  # noqa
            logger.exception("Runtime shutdown event persistence failed.")

        self.context.set_runtime_state(RuntimeState.OFF)
        self._ib_reconnect_watch_started = False
        self._ctrader_reconnect_watch_started = False
        self._ib_reconnect_task = None
        self._ctrader_reconnect_task = None

        try:
            self.connection.commit()
        except Exception:  # noqa
            logger.exception("Runtime database commit failed during shutdown.")

        try:
            self.connection.close()
        except Exception:  # noqa
            logger.exception("Runtime database close failed during shutdown.")

        self._shutdown_complete = True

    def set_broker(
        self,
        broker_name: str,
    ) -> None:
        """
        Встановити активний broker name у context.
        """

        self.context.broker = str(broker_name).strip().upper()
        self.context.touch()

        self.add_event(
            RuntimeEventType.BROKER_SELECTED,
            message=f"Broker selected: {self.context.broker}",
        )

    def is_named_broker_connected(
        self,
        broker_name: str,
    ) -> bool:
        """
        Перевірити фактичне connection health конкретного named broker.

        Перед відповіддю refresh broker health звіряє cached service state
        з активним adapter. Це закриває race, коли adapter уже disconnect,
        а попередній health snapshot ще лишився CONNECTED.

        Підключених broker-ів може бути декілька.
        Активний broker все одно один.
        """
        broker = str(broker_name).strip().upper()

        service = None

        if broker == "IB":
            service = self.ib_runtime_service
        elif broker == "CTRADER":
            service = self.ctrader_runtime_service

        if service is None:
            return False

        try:
            refresh_health = getattr(service, "refresh_broker_health", None)
            if callable(refresh_health):
                health = refresh_health()
            else:
                health = service.get_broker_health()
        except Exception:  # noqa
            return False

        if health is None:
            return False

        return health.is_connected()

    def validate_workspace_broker_binding(
        self,
        broker_name: str,
        account_id: str | None,
    ) -> None:
        """Validate one read-only WSP binding against connected services."""
        broker = str(broker_name or "").strip().upper()
        account = str(account_id or "").strip()
        if broker not in {"CTRADER", "IB"}:
            raise ValueError(f"Unsupported workspace broker: {broker_name!r}")
        if not self.is_named_broker_connected(broker):
            raise RuntimeError(f"Workspace broker is not connected: {broker}")
        if not account:
            raise RuntimeError(
                f"Workspace account is required for broker mode: {broker}"
            )

        if broker == "CTRADER":
            service = self.ctrader_runtime_service
            if service is None:
                raise RuntimeError("cTrader runtime service is not set")
            state = service.get_account_state()
            active_account = str(getattr(state, "account_id", "") or "").strip()
            if active_account != account:
                raise RuntimeError(
                    "cTrader WSP account does not match the active session"
                )
            return

        service = self.ib_runtime_service
        if service is None:
            raise RuntimeError("IB runtime service is not set")
        managed_accounts = {
            str(value or "").strip()
            for value in service.get_managed_accounts()
            if str(value or "").strip()
        }
        if account not in managed_accounts:
            raise RuntimeError("IB WSP account is not available in the active session")

    def get_workspace_forex_quote_snapshot(
        self,
        broker_name: str,
        symbol_names: list[str],
    ) -> dict:
        """Return one broker-specific quote snapshot for active WSP feeds."""
        broker = str(broker_name or "").strip().upper()
        if broker == "CTRADER":
            service = self.ctrader_runtime_service
        elif broker == "IB":
            service = self.ib_runtime_service
        else:
            raise ValueError(f"Unsupported workspace broker: {broker_name!r}")
        if service is None:
            raise RuntimeError(f"{broker} runtime service is not set")
        if not self.is_named_broker_connected(broker):
            raise RuntimeError(f"Workspace broker is not connected: {broker}")
        return service.get_forex_quote_snapshot(list(symbol_names))

    def set_active_broker(
        self,
        broker_name: str,
        require_connected: bool = True,
    ) -> None:
        """
        Встановити активного broker для trading operations.

        Активний broker завжди один.
        Підключених broker-ів може бути декілька.
        """

        if self._active_broker_locked:
            return

        broker = str(broker_name).strip().upper()

        if broker not in {"IB", "CTRADER"}:
            raise ValueError(f"Unsupported active broker: {broker_name!r}")

        if require_connected and not self.is_named_broker_connected(broker):
            raise RuntimeError(f"Broker is not connected: {broker}")

        self.set_broker(broker)

    def get_active_broker(self) -> str:
        """
        Повернути активного broker з runtime context.
        """
        return str(self.context.broker or "OFF").strip().upper()

    def evaluate_ib_fx_external_exposure_guard(
        self,
        *,
        account_id: str,
        symbol_name: str,
        runtime_mode: str,
    ) -> IBFxExternalExposureGuardDecision:
        """Evaluate the persisted symbol-scoped external IB FX guard."""
        exposures = self.repository.get_active_ib_fx_external_exposures(
            account_id=account_id,
        )
        return evaluate_ib_fx_external_exposure_guard(
            exposures,
            account_id=account_id,
            symbol_name=symbol_name,
            runtime_mode=runtime_mode,
        )

    def refresh_ib_fx_external_exposure_guard(
        self,
        *,
        account_id: str,
        symbol_name: str,
        runtime_mode: str,
    ) -> IBFxExternalExposureGuardDecision:
        """Refresh IB evidence and return one fail-closed LGE EXCLUSIVE decision."""
        account = str(account_id or "").strip()
        symbol = str(symbol_name or "").strip().upper()
        mode = str(runtime_mode or "").strip().upper()

        if mode not in {IB_FX_GUARD_MODE_PAPER, IB_FX_GUARD_MODE_LIVE}:
            return self.evaluate_ib_fx_external_exposure_guard(
                account_id=account,
                symbol_name=symbol,
                runtime_mode=mode,
            )

        service = self.ib_runtime_service

        if service is None:
            return self._ib_fx_evidence_unavailable_decision(
                account_id=account,
                symbol_name=symbol,
                details="IB runtime service is not set",
            )

        try:
            evidence_snapshot = service.get_virtual_position_leg_evidence_snapshot()
            reconciliation_snapshot = self._build_open_runtime_position_leg_snapshot(
                evidence_snapshot,
                require_active_broker=False,
            )
            persistence_block_reason = self._ib_snapshot_persistence_block_reason(
                snapshot=reconciliation_snapshot,
                evidence_snapshot=evidence_snapshot,
            )

            if not persistence_block_reason:
                self.repository.sync_reconciled_ib_virtual_position_leg_snapshot(
                    snapshot=reconciliation_snapshot,
                    evidence_snapshot=evidence_snapshot,
                )

            current_groups = build_ib_position_group_snapshot(
                reconciliation_snapshot=reconciliation_snapshot,
                evidence_snapshot=evidence_snapshot,
            )
        except Exception as error:
            return self._ib_fx_evidence_unavailable_decision(
                account_id=account,
                symbol_name=symbol,
                details=str(error),
            )

        captured_utc = str(
            evidence_snapshot.get("captured_utc") or ""
        ).strip() or datetime.now(UTC).isoformat(timespec="seconds")

        for group in current_groups.groups:
            if group.account_id != account or group.symbol_name != symbol:
                continue

            external_signed_volume = 0.0
            evidence_status = IB_FX_EXTERNAL_EXPOSURE_CONFIRMED

            if group.broker_residual_present:
                external_signed_volume = group.broker_residual_signed_volume
                evidence_status = (
                    group.broker_residual_evidence_status
                    or IB_FX_EXTERNAL_EXPOSURE_CONFIRMED
                )
            elif (
                group.group_mode == IB_POSITION_GROUP_MODE_NET_ONLY
                and group.broker_position_present
                and group.display_volume
                > IB_POSITION_QUANTITY_ABS_TOLERANCE
            ):
                external_signed_volume = group.display_signed_volume

            if abs(external_signed_volume) <= (
                IB_POSITION_QUANTITY_ABS_TOLERANCE
            ):
                continue

            current_exposure = IBFxExternalExposure(
                broker_position_id=group.broker_position_id,
                account_id=account,
                symbol_name=symbol,
                signed_volume=external_signed_volume,
                evidence_status=evidence_status,
                last_confirmed_utc=captured_utc,
                last_observed_utc=captured_utc,
                updated_utc=captured_utc,
            )
            return evaluate_ib_fx_external_exposure_guard(
                (current_exposure,),
                account_id=account,
                symbol_name=symbol,
                runtime_mode=mode,
            )

        return self.evaluate_ib_fx_external_exposure_guard(
            account_id=account,
            symbol_name=symbol,
            runtime_mode=mode,
        )

    @staticmethod
    def _ib_fx_evidence_unavailable_decision(
        *,
        account_id: str,
        symbol_name: str,
        details: str,
    ) -> IBFxExternalExposureGuardDecision:
        """Build a fail-closed decision when current IB evidence is unsafe."""
        return IBFxExternalExposureGuardDecision(
            allowed=False,
            reason_code=IB_FX_GUARD_EVIDENCE_UNAVAILABLE,
            reason_text=(
                "LGE_EXCLUSIVE: IB FX exposure safety evidence is unavailable; "
                "new LGE execution is blocked before Trade persistence and "
                "before the execution request: "
                f"account={account_id}, symbol={symbol_name}, details={details}"
            ),
        )

    def _ib_account_execution_guard_mode(self) -> str:
        """Map the active IB account environment to Paper or Live."""
        account_mode = str(self.context.account_mode or "").strip().upper()

        if account_mode == "LIVE":
            return IB_FX_GUARD_MODE_LIVE

        return IB_FX_GUARD_MODE_PAPER

    def _assert_ib_fx_execution_safe(
        self,
        *,
        account_id: str,
        symbol_name: str,
    ) -> None:
        """Block every new IB Paper/Live LGE order under LGE EXCLUSIVE."""
        decision = self.refresh_ib_fx_external_exposure_guard(
            account_id=account_id,
            symbol_name=symbol_name,
            runtime_mode=self._ib_account_execution_guard_mode(),
        )

        if not decision.allowed:
            raise IBFxExternalExposureExecutionBlockedError(decision)

    def _assert_ib_fx_auto_execution_safe(
        self,
        *,
        account_id: str,
        symbol_name: str,
    ) -> None:
        """Backward-compatible alias for the stricter all-order guard."""
        self._assert_ib_fx_execution_safe(
            account_id=account_id,
            symbol_name=symbol_name,
        )

    def get_active_market_availability(
        self,
        symbol_name: str = "EURUSD",
    ) -> MarketAvailabilityResult:
        """
        Повернути стан ринку для активного broker і symbol.
        """
        return detect_market_state(
            broker=self.get_active_broker(),
            symbol_name=symbol_name,
        )

    def get_ib_virtual_position_leg_evidence_snapshot(self) -> dict:
        """
        Повернути read-only IB evidence для майбутнього leg reconciler.

        Метод не змінює SQLite і не виконує trading operations.
        """
        broker = self.get_active_broker()

        if broker != "IB":
            raise RuntimeError("IB virtual-leg evidence requires active IB broker")

        service = self.ib_runtime_service

        if service is None:
            raise RuntimeError("IB runtime service is not set")

        return service.get_virtual_position_leg_evidence_snapshot()

    def get_open_runtime_position_legs(
        self,
    ) -> IBVirtualPositionLegReconciliationSnapshot:
        """
        Побудувати read-only reconciled IB virtual-leg snapshot.

        Repository надає логічні LGE seeds, а IB evidence підтверджує
        executions, broker net position, active та completed orders.
        Метод не змінює SQLite і не виконує broker operations.
        """
        evidence_snapshot = self.get_ib_virtual_position_leg_evidence_snapshot()
        return self._build_open_runtime_position_leg_snapshot(evidence_snapshot)

    def get_active_broker_position_groups(
        self,
    ) -> IBPositionGroupSnapshot:
        """Build read-only IB broker-net groups with virtual legs."""
        evidence_snapshot = self.get_ib_virtual_position_leg_evidence_snapshot()
        reconciliation_snapshot = self._build_open_runtime_position_leg_snapshot(
            evidence_snapshot
        )
        return self._build_ib_position_group_snapshot(
            evidence_snapshot=evidence_snapshot,
            reconciliation_snapshot=reconciliation_snapshot,
        )

    def sync_active_broker_position_groups(
        self,
    ) -> IBPositionGroupSnapshot:
        """Persist a safe IB snapshot and always return current groups."""
        evidence_snapshot = self.get_ib_virtual_position_leg_evidence_snapshot()
        reconciliation_snapshot = self._build_open_runtime_position_leg_snapshot(
            evidence_snapshot
        )
        persistence_block_reason = self._ib_snapshot_persistence_block_reason(
            snapshot=reconciliation_snapshot,
            evidence_snapshot=evidence_snapshot,
        )

        if persistence_block_reason:
            logger.warning(
                "IB position-group snapshot persistence skipped | reason=%s",
                persistence_block_reason,
            )
        else:
            self.repository.sync_reconciled_ib_virtual_position_leg_snapshot(
                snapshot=reconciliation_snapshot,
                evidence_snapshot=evidence_snapshot,
            )

        return self._build_ib_position_group_snapshot(
            evidence_snapshot=evidence_snapshot,
            reconciliation_snapshot=reconciliation_snapshot,
        )

    @staticmethod
    def _ib_snapshot_persistence_block_reason(
        *,
        snapshot: IBVirtualPositionLegReconciliationSnapshot,
        evidence_snapshot: dict[str, Any],
    ) -> str:
        """Return why a group snapshot must stay read-only for this refresh."""
        if not snapshot.complete:
            return "IB virtual-leg snapshot is incomplete"

        if not bool(evidence_snapshot.get("complete")):
            return "IB virtual-leg evidence is incomplete"

        for flag_name in (
            "positions_complete",
            "open_orders_complete",
            "completed_orders_complete",
            "executions_complete",
        ):
            if not bool(evidence_snapshot.get(flag_name)):
                return f"IB virtual-leg evidence flag is false: {flag_name}"

        if snapshot.unmapped_protective_order_ids:
            return "IB virtual-leg snapshot contains unmapped protective orders"

        if any(
            status != IB_RECONCILIATION_STATUS_RECONCILED
            for status in snapshot.group_statuses.values()
        ):
            return "IB virtual-leg groups are not fully reconciled"

        if any(
            leg.reconciliation_status != IB_RECONCILIATION_STATUS_RECONCILED
            for leg in snapshot.legs
        ):
            return "IB virtual legs are not fully reconciled"

        if any(
            leg.leg_status == IB_LEG_STATUS_PARTIALLY_CLOSED for leg in snapshot.legs
        ):
            return "PARTIALLY_CLOSED persistence requires remaining volume"

        return ""

    def _build_ib_position_group_snapshot(
        self,
        *,
        evidence_snapshot: dict[str, Any],
        reconciliation_snapshot: IBVirtualPositionLegReconciliationSnapshot,
    ) -> IBPositionGroupSnapshot:
        """Build and enrich IB position groups from one evidence set."""
        broker = self.get_active_broker()

        if broker != "IB":
            raise RuntimeError("IB position groups require active IB broker")

        service = self.ib_runtime_service

        if service is None:
            raise RuntimeError("IB runtime service is not set")

        snapshot = build_ib_position_group_snapshot(
            reconciliation_snapshot=reconciliation_snapshot,
            evidence_snapshot=evidence_snapshot,
        )
        positions: list = []

        try:
            positions = self._enrich_ib_positions_from_runtime_repository(
                service.get_positions(),
            )
        except Exception:  # noqa
            logger.warning(
                "IB position-group broker enrichment failed.",
                exc_info=True,
            )

        positions_by_id = {
            str(position.position_id): position
            for position in positions
            if str(getattr(position, "position_id", "") or "").strip()
        }

        for group in snapshot.groups:
            position = positions_by_id.get(group.broker_position_id)

            if position is None:
                continue

            group.current_price = getattr(position, "current_price", None)
            group.unrealized_pnl = getattr(
                position,
                "unrealized_pnl",
                None,
            )
            raw_payload = getattr(position, "raw_payload", None) or {}
            group.pnl_currency = (
                str(raw_payload.get("pnl_currency") or "").strip().upper()
            )
            group.stop_loss = getattr(position, "stop_loss", None)
            group.take_profit = getattr(position, "take_profit", None)
            group.opened_utc = str(getattr(position, "opened_utc", "") or "").strip()

        self._enrich_ib_position_group_quotes(
            snapshot=snapshot,
            service=service,
        )
        return snapshot

    @staticmethod
    def _ib_quote_price(value: Any) -> float | None:
        """Normalize one positive finite quote without inventing zero."""
        try:
            price = float(value)
        except (TypeError, ValueError):
            return None

        if not math.isfinite(price) or price <= 0.0:
            return None

        return price

    @staticmethod
    def _ib_quote_currency(symbol_name: str) -> str:
        """Return the quote currency from a canonical Forex symbol."""
        symbol = "".join(
            character
            for character in str(symbol_name or "").strip().upper()
            if character.isalpha()
        )

        if len(symbol) == 6:
            return symbol[-3:]

        return ""

    def _enrich_ib_position_group_quotes(
        self,
        *,
        snapshot: IBPositionGroupSnapshot,
        service: object,
    ) -> None:
        """Attach side-aware streaming quotes to active virtual legs."""
        quote_method = getattr(service, "get_forex_quote_snapshot", None)

        if not callable(quote_method):
            return

        symbols = sorted(
            {
                group.symbol_name
                for group in snapshot.groups
                if group.open_legs and group.symbol_name
            }
        )

        try:
            quote_payload = quote_method(symbols)
        except Exception:  # noqa
            logger.warning(
                "IB Forex quote enrichment failed.",
                exc_info=True,
            )
            return

        if not isinstance(quote_payload, dict):
            return

        quotes = quote_payload.get("quotes")

        if not isinstance(quotes, dict):
            return

        for group in snapshot.groups:
            if not group.open_legs:
                continue

            row = quotes.get(group.symbol_name)

            if not isinstance(row, dict):
                continue

            bid_price = self._ib_quote_price(row.get("bid"))
            ask_price = self._ib_quote_price(row.get("ask"))

            if bid_price is None and ask_price is None:
                continue

            group.bid_price = bid_price
            group.ask_price = ask_price
            group.quote_timestamp = str(row.get("timestamp") or "").strip()

            try:
                market_data_type = row.get("market_data_type")
                group.quote_market_data_type = (
                    int(market_data_type) if market_data_type is not None else None
                )
            except (TypeError, ValueError):
                group.quote_market_data_type = None

            quote_currency = self._ib_quote_currency(group.symbol_name)

            if quote_currency:
                group.currency = quote_currency
                group.pnl_currency = quote_currency

            group.current_price = group.current_price_for_side(group.display_side)

    def sync_reconciled_ib_virtual_position_legs(
        self,
    ) -> dict[str, Any]:
        """
        Persist one complete and fully reconciled IB virtual-leg snapshot.

        Broker evidence is requested once. BLOCKED, UNRECONCILED,
        incomplete or orphan-containing snapshots are rejected before
        RuntimeRepository performs any SQLite write.
        """
        evidence_snapshot = self.get_ib_virtual_position_leg_evidence_snapshot()
        snapshot = self._build_open_runtime_position_leg_snapshot(evidence_snapshot)
        persistence = self.repository.sync_reconciled_ib_virtual_position_leg_snapshot(
            snapshot=snapshot,
            evidence_snapshot=evidence_snapshot,
        )
        return {
            "snapshot": snapshot,
            "persistence": persistence,
        }

    def _build_open_runtime_position_leg_snapshot(
        self,
        evidence_snapshot: dict[str, Any],
        seed_overrides: dict[str, dict[str, Any]] | None = None,
        cash_fx_virtual_observation_offsets: dict[str, float] | None = None,
        *,
        require_active_broker: bool = True,
    ) -> IBVirtualPositionLegReconciliationSnapshot:
        """Build reconciliation from one already captured IB evidence set."""
        if require_active_broker and self.get_active_broker() != "IB":
            raise RuntimeError("IB virtual position legs require active IB broker")

        account_ids: list[str] = []

        for value in evidence_snapshot.get("account_ids") or []:
            account_id = str(value or "").strip()

            if account_id and account_id not in account_ids:
                account_ids.append(account_id)

        evidence_order_ids = self._ib_evidence_order_ids(evidence_snapshot)
        evidence_order_perm_ids = self._ib_evidence_order_perm_ids(
            evidence_snapshot
        )
        seeds: list[dict[str, Any]] = []

        if account_ids:
            for account_id in account_ids:
                seeds.extend(
                    self.repository.get_open_ib_virtual_position_leg_seeds(
                        account_id=account_id,
                        evidence_order_ids=evidence_order_ids,
                        evidence_order_perm_ids=evidence_order_perm_ids,
                    )
                )
        else:
            seeds = self.repository.get_open_ib_virtual_position_leg_seeds(
                evidence_order_ids=evidence_order_ids,
                evidence_order_perm_ids=evidence_order_perm_ids,
            )

        if seed_overrides:
            normalized_seeds: list[dict[str, Any]] = []

            for source_seed in seeds:
                seed = dict(source_seed)
                position_uid = str(seed.get("position_uid") or "").strip()
                override = seed_overrides.get(position_uid)

                if override:
                    seed.update(override)

                normalized_seeds.append(seed)

            seeds = normalized_seeds

        legs = build_ib_virtual_position_legs_from_repository_seeds(seeds)
        persisted_external_exposures = {
            exposure.broker_position_id: exposure
            for exposure in (
                self.repository.get_active_ib_fx_external_exposures()
            )
        }

        return reconcile_ib_virtual_position_legs(
            legs=legs,
            evidence_snapshot=evidence_snapshot,
            cash_fx_virtual_observation_offsets=cash_fx_virtual_observation_offsets,
            persisted_external_exposures=persisted_external_exposures,
        )

    def resolve_ib_close_evidence_missing(
        self,
        position_uid: str,
    ) -> dict[str, Any]:
        """Resolve one ambiguous IB virtual-leg close without trading.

        A fresh complete IB evidence snapshot is validated immediately before
        the persistence write. This method never sends, modifies, or cancels
        a broker order.
        """
        if self.get_active_broker() != "IB":
            raise RuntimeError("IB manual reconciliation requires active IB broker")

        position_uid_clean = str(position_uid or "").strip()

        if not position_uid_clean:
            raise ValueError("IB virtual-leg position_uid is empty")

        evidence_snapshot = self.get_ib_virtual_position_leg_evidence_snapshot()

        if not bool(evidence_snapshot.get("complete")):
            raise RuntimeError("IB manual reconciliation evidence is incomplete")

        for flag_name in (
            "positions_complete",
            "open_orders_complete",
            "completed_orders_complete",
            "executions_complete",
        ):
            if not bool(evidence_snapshot.get(flag_name)):
                raise RuntimeError(
                    "IB manual reconciliation evidence flag is false: " f"{flag_name}"
                )

        reconciliation_snapshot = self._build_open_runtime_position_leg_snapshot(
            evidence_snapshot
        )
        matching_legs = [
            leg
            for leg in reconciliation_snapshot.legs
            if leg.position_uid == position_uid_clean
        ]

        if len(matching_legs) != 1:
            raise RuntimeError(
                "IB manual reconciliation target is not uniquely available"
            )

        leg = matching_legs[0]

        if leg.leg_status != IB_LEG_STATUS_OPEN:
            raise RuntimeError("IB manual reconciliation target is not an OPEN leg")

        if leg.reconciliation_status != IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING:
            raise RuntimeError("IB virtual leg is not CLOSE_EVIDENCE_MISSING")

        if leg.protection_status != IB_PROTECTION_STATUS_NONE:
            raise RuntimeError(
                "IB virtual leg still has active or ambiguous protection"
            )

        if reconciliation_snapshot.unmapped_protective_order_ids:
            raise RuntimeError("IB evidence contains unmapped protective orders")

        group_snapshot = build_ib_position_group_snapshot(
            reconciliation_snapshot=reconciliation_snapshot,
            evidence_snapshot=evidence_snapshot,
        )
        matching_groups = [
            group
            for group in group_snapshot.groups
            if group.broker_position_id == leg.broker_position_id
        ]

        if len(matching_groups) != 1:
            raise RuntimeError(
                "IB manual reconciliation group is not uniquely available"
            )

        group = matching_groups[0]

        if (
            group.reconciliation_status
            != IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING
        ):
            raise RuntimeError("IB group is not CLOSE_EVIDENCE_MISSING")

        if (
            group.broker_position_present
            and abs(float(group.broker_volume or 0.0))
            > IB_POSITION_QUANTITY_ABS_TOLERANCE
        ):
            raise RuntimeError(
                "IB broker position is still present; manual close recovery "
                "is blocked"
            )

        if group.broker_residual_present:
            raise RuntimeError(
                "IB broker residual is present; manual close recovery is " "blocked"
            )

        active_order_ids = {
            int(order_id)
            for row in list(evidence_snapshot.get("open_orders") or [])
            if (order_id := self._ib_optional_positive_int(row.get("order_id")))
            is not None
        }
        persisted_leg_order_ids = {
            order_id
            for order_id in (
                leg.stop_loss_order_id,
                leg.take_profit_order_id,
                *leg.close_order_ids,
            )
            if order_id is not None
        }

        if active_order_ids & persisted_leg_order_ids:
            raise RuntimeError("IB virtual leg still has an active persisted order")

        reason = (
            "User confirmed in LGE that the broker position was already "
            "closed; current complete IB evidence contains no broker "
            "position, no active persisted protection, and no matching "
            "close execution."
        )
        result = self.repository.resolve_ib_virtual_position_leg_close_evidence_missing(
            position_uid=position_uid_clean,
            expected_broker_position_id=leg.broker_position_id,
            expected_account_id=leg.account_id,
            expected_symbol_name=leg.symbol_name,
            expected_side=leg.side,
            expected_volume=leg.volume,
            resolution_reason=reason,
        )
        self.events.append(
            RuntimeEvent(
                event_type=RuntimeEventType.IB_MANUAL_RECONCILIATION_RESOLVED,
                message=(
                    "IB CLOSE_EVIDENCE_MISSING manually resolved for "
                    f"{leg.symbol_name} {leg.side} {leg.volume:g}"
                ),
                created_utc=str(result.get("resolved_utc") or ""),
                payload=dict(result.get("audit_payload") or {}),
            )
        )
        return result

    @staticmethod
    def _ib_optional_positive_int(value: object) -> int | None:
        """Normalize one positive IB order id for safety checks."""
        if value is None or isinstance(value, bool):
            return None

        if isinstance(value, int):
            order_id = value
        elif isinstance(value, str):
            try:
                order_id = int(value.strip())
            except ValueError:
                return None
        elif isinstance(value, float) and value.is_integer():
            order_id = int(value)
        else:
            return None

        return order_id if order_id > 0 else None

    def modify_runtime_position_leg_sl_tp(
        self,
        position_uid: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict[str, Any]:
        """Modify SL/TP for one exact OPEN LGE-owned IB virtual leg."""
        if self.get_active_broker() != "IB":
            raise RuntimeError("IB virtual-leg Modify requires active IB broker")

        service = self.ib_runtime_service

        if service is None:
            raise RuntimeError("IB runtime service is not set")

        position_uid_clean = str(position_uid or "").strip()

        if not position_uid_clean:
            raise ValueError("IB virtual-leg position_uid is empty")

        stop_loss_value = self._normalize_optional_protection_price(
            stop_loss,
            field_name="Stop Loss",
        )
        take_profit_value = self._normalize_optional_protection_price(
            take_profit,
            field_name="Take Profit",
        )
        evidence_before = self.get_ib_virtual_position_leg_evidence_snapshot()
        provisional_snapshot = self._build_open_runtime_position_leg_snapshot(
            evidence_before
        )
        provisional_leg = self._find_runtime_position_leg(
            snapshot=provisional_snapshot,
            position_uid=position_uid_clean,
        )
        cash_fx_offset = get_ib_cash_fx_virtual_observation_offset(
            legs=provisional_snapshot.legs,
            evidence_snapshot=evidence_before,
            broker_position_id=provisional_leg.broker_position_id,
        )
        cash_fx_offsets = (
            None
            if cash_fx_offset is None
            else {provisional_leg.broker_position_id: cash_fx_offset}
        )
        snapshot_before = self._build_open_runtime_position_leg_snapshot(
            evidence_before,
            cash_fx_virtual_observation_offsets=cash_fx_offsets,
        )
        leg_before = self._find_runtime_position_leg(
            snapshot=snapshot_before,
            position_uid=position_uid_clean,
        )

        if leg_before.leg_status != IB_LEG_STATUS_OPEN:
            raise RuntimeError("Selected IB virtual leg is not OPEN")

        if leg_before.reconciliation_status != IB_RECONCILIATION_STATUS_RECONCILED:
            raise RuntimeError("Selected IB virtual leg is not RECONCILED")

        if snapshot_before.unmapped_protective_order_ids:
            raise RuntimeError(
                "IB virtual-leg Modify is blocked by unmapped protection"
            )

        if leg_before.parent_order_id is None:
            raise RuntimeError("Selected IB virtual leg parent order id is missing")

        modify_order_ref = self._build_ib_virtual_leg_modify_order_ref(
            position_uid=leg_before.position_uid,
            fallback_source=leg_before.source,
        )
        broker_result = service.modify_virtual_position_leg_sl_tp(
            position_uid=leg_before.position_uid,
            position_id=leg_before.broker_position_id,
            account_id=leg_before.account_id,
            symbol_name=leg_before.symbol_name,
            position_side=leg_before.side,
            position_volume=leg_before.volume,
            parent_order_id=leg_before.parent_order_id,
            stop_loss_order_id=leg_before.stop_loss_order_id,
            take_profit_order_id=leg_before.take_profit_order_id,
            current_oca_group=leg_before.oca_group,
            stop_loss=stop_loss_value,
            take_profit=take_profit_value,
            order_ref=modify_order_ref,
        )
        seed_overrides = self._build_post_modify_seed_overrides(
            leg_before=leg_before,
            broker_result=broker_result,
            stop_loss=stop_loss_value,
            take_profit=take_profit_value,
        )
        (
            evidence_after,
            snapshot_after,
            leg_after,
            reconciliation_attempts,
        ) = self._wait_for_runtime_leg_after_modify(
            position_uid=position_uid_clean,
            stop_loss=stop_loss_value,
            take_profit=take_profit_value,
            seed_overrides=seed_overrides,
            cash_fx_virtual_observation_offsets=cash_fx_offsets,
        )

        self._assert_other_runtime_legs_unchanged(
            before=snapshot_before,
            after=snapshot_after,
            excluded_position_uid=position_uid_clean,
        )
        persistence = self.repository.persist_confirmed_ib_virtual_position_leg_modify(
            leg=leg_after,
            evidence_snapshot=evidence_after,
        )
        position_group_snapshot = build_ib_position_group_snapshot(
            reconciliation_snapshot=snapshot_after,
            evidence_snapshot=evidence_after,
        )
        self._enrich_ib_position_group_quotes(
            snapshot=position_group_snapshot,
            service=service,
        )
        return {
            "position_uid": position_uid_clean,
            "broker_position_id": leg_after.broker_position_id,
            "stop_loss": leg_after.stop_loss,
            "take_profit": leg_after.take_profit,
            "stop_loss_order_id": leg_after.stop_loss_order_id,
            "take_profit_order_id": leg_after.take_profit_order_id,
            "oca_group": leg_after.oca_group,
            "broker_result": broker_result,
            "snapshot": snapshot_after,
            "persistence": persistence,
            "post_modify_reconciliation_attempts": reconciliation_attempts,
            "position_group_snapshot": position_group_snapshot,
            "post_modify_group_snapshot_reused": True,
            "cash_fx_virtual_observation_offset": cash_fx_offset,
        }

    def _build_ib_virtual_leg_modify_order_ref(
        self,
        *,
        position_uid: str,
        fallback_source: str,
    ) -> str:
        """Build exact child orderRef for one IB virtual-leg SL/TP modify."""
        identity = self.repository.get_ib_virtual_position_leg_order_identity(
            position_uid
        )
        identity_data = dict(identity or {})
        source = (
            str(identity_data.get("trade_source") or fallback_source or "MANUAL")
            .strip()
            .upper()
        )

        if source.startswith("LGE_"):
            source = source.removeprefix("LGE_")

        control_mode = normalize_order_control_mode(
            source,
            default=ORDER_CONTROL_MODE_MANUAL,
        )
        persisted_ref = str(
            identity_data.get("parent_order_ref")
            or identity_data.get("broker_comment")
            or ""
        ).strip()
        persisted_mode = get_broker_order_control_mode(persisted_ref)

        if persisted_mode is not None:
            control_mode = persisted_mode

        clean_comment = strip_broker_order_identity(persisted_ref)

        if not clean_comment:
            clean_comment = str(identity_data.get("trade_comment") or "").strip()

        base_comment = build_broker_order_comment(
            clean_comment,
            control_mode,
        )
        return build_broker_operation_comment(
            base_comment,
            "SLTP_MODIFY",
            default_control_mode=control_mode,
        )

    def close_runtime_position_leg(
        self,
        position_uid: str,
    ) -> dict[str, Any]:
        """Close one exact OPEN reconciled LGE-owned IB virtual leg."""
        if self.get_active_broker() != "IB":
            raise RuntimeError("IB virtual-leg Close requires active IB broker")

        service = self.ib_runtime_service

        if service is None:
            raise RuntimeError("IB runtime service is not set")

        position_uid_clean = str(position_uid or "").strip()

        if not position_uid_clean:
            raise ValueError("IB virtual-leg position_uid is empty")

        evidence_before = self.get_ib_virtual_position_leg_evidence_snapshot()
        provisional_snapshot = self._build_open_runtime_position_leg_snapshot(
            evidence_before
        )
        provisional_leg = self._find_runtime_position_leg(
            snapshot=provisional_snapshot,
            position_uid=position_uid_clean,
        )
        cash_fx_observation_offset = get_ib_cash_fx_virtual_observation_offset(
            legs=provisional_snapshot.legs,
            evidence_snapshot=evidence_before,
            broker_position_id=provisional_leg.broker_position_id,
        )
        cash_fx_observation_offsets = (
            None
            if cash_fx_observation_offset is None
            else {provisional_leg.broker_position_id: cash_fx_observation_offset}
        )
        snapshot_before = self._build_open_runtime_position_leg_snapshot(
            evidence_before,
            cash_fx_virtual_observation_offsets=cash_fx_observation_offsets,
        )
        leg_before = self._find_runtime_position_leg(
            snapshot=snapshot_before,
            position_uid=position_uid_clean,
        )

        if leg_before.leg_status != IB_LEG_STATUS_OPEN:
            raise RuntimeError("Selected IB virtual leg is not OPEN")

        if leg_before.reconciliation_status != IB_RECONCILIATION_STATUS_RECONCILED:
            raise RuntimeError("Selected IB virtual leg is not RECONCILED")

        if snapshot_before.unmapped_protective_order_ids:
            raise RuntimeError("IB virtual-leg Close is blocked by unmapped protection")

        if leg_before.parent_order_id is None:
            raise RuntimeError("Selected IB virtual leg parent order id is missing")

        try:
            broker_result = service.close_virtual_position_leg(
                position_uid=leg_before.position_uid,
                position_id=leg_before.broker_position_id,
                account_id=leg_before.account_id,
                symbol_name=leg_before.symbol_name,
                position_side=leg_before.side,
                position_volume=leg_before.volume,
                parent_order_id=leg_before.parent_order_id,
                stop_loss_order_id=leg_before.stop_loss_order_id,
                take_profit_order_id=leg_before.take_profit_order_id,
                current_oca_group=leg_before.oca_group,
                comment="LGE virtual-leg close",
            )
        except IBMarketOrderTimeoutError as error:
            return self._recover_runtime_position_leg_close_after_timeout(
                leg_before=leg_before,
                timeout_error=error,
            )

        close_order_id = self._optional_positive_order_id(
            broker_result.get("close_order_id")
        )

        if close_order_id is None:
            raise RuntimeError("IB virtual-leg close order id is missing")

        seed_overrides = {
            leg_before.position_uid: {
                "persisted_close_order_ids": [close_order_id],
                "persisted_leg_status": IB_LEG_STATUS_CLOSED,
            }
        }
        evidence_after, snapshot_after, leg_after, attempts = (
            self._wait_for_runtime_leg_after_close(
                position_uid=position_uid_clean,
                close_order_id=close_order_id,
                seed_overrides=seed_overrides,
                cash_fx_virtual_observation_offsets=cash_fx_observation_offsets,
            )
        )
        self._assert_other_runtime_legs_unchanged(
            before=snapshot_before,
            after=snapshot_after,
            excluded_position_uid=position_uid_clean,
        )
        persistence = self.repository.persist_confirmed_ib_virtual_position_leg_close(
            leg=leg_after,
            close_order_id=close_order_id,
            evidence_snapshot=evidence_after,
        )
        broker_order_uid = self._record_runtime_leg_close_order(
            leg=leg_before,
            close_order_id=close_order_id,
            evidence_snapshot=evidence_after,
        )
        return {
            "position_uid": position_uid_clean,
            "broker_position_id": leg_after.broker_position_id,
            "close_order_id": close_order_id,
            "close_side": leg_before.protective_action,
            "close_quantity": leg_before.volume,
            "leg_status": leg_after.leg_status,
            "broker_result": broker_result,
            "snapshot": snapshot_after,
            "persistence": persistence,
            "broker_order_uid": broker_order_uid,
            "post_close_reconciliation_attempts": attempts,
            "broker_quantity_before": self._broker_signed_quantity(
                evidence_before,
                leg_before.broker_position_id,
            ),
            "broker_quantity_after": self._broker_signed_quantity(
                evidence_after,
                leg_before.broker_position_id,
            ),
            "cash_fx_virtual_observation_offset": cash_fx_observation_offset,
        }

    def _recover_runtime_position_leg_close_after_timeout(
        self,
        *,
        leg_before: IBVirtualPositionLeg,
        timeout_error: IBMarketOrderTimeoutError,
    ) -> dict[str, Any]:
        """Persist a timeout Close automatically when broker evidence arrives."""
        close_order_id = self._optional_positive_order_id(timeout_error.order_id)

        if close_order_id is None:
            raise RuntimeError("Timed-out IB Close order id is invalid")

        self.repository.set_active_ib_virtual_position_leg_order(
            position_uid=leg_before.position_uid,
            order_role=IB_LEG_ORDER_ROLE_CLOSE,
            broker_order_id=close_order_id,
            execution_status=IB_LEG_CLOSE_EXECUTION_STATUS_PENDING,
            client_id=None,
            action=leg_before.protective_action,
            order_type="MKT",
            quantity=leg_before.volume,
            price=None,
            order_ref=timeout_error.comment,
        )
        last_error = str(timeout_error)

        for attempt in range(
            1,
            IB_VIRTUAL_LEG_CLOSE_TIMEOUT_RECOVERY_ATTEMPTS + 1,
        ):
            try:
                recovered = self.recover_confirmed_runtime_position_leg_close(
                    position_uid=leg_before.position_uid,
                    close_order_id=close_order_id,
                )
            except RuntimeError as error:
                last_error = str(error)
            else:
                recovered.update(
                    {
                        "broker_position_id": leg_before.broker_position_id,
                        "close_side": leg_before.protective_action,
                        "close_quantity": leg_before.volume,
                        "closed": True,
                        "automatic_timeout_recovery": True,
                        "timeout_recovery_attempts": attempt,
                    }
                )
                return recovered

            if attempt < IB_VIRTUAL_LEG_CLOSE_TIMEOUT_RECOVERY_ATTEMPTS:
                time.sleep(IB_VIRTUAL_LEG_CLOSE_TIMEOUT_RECOVERY_DELAY_SECONDS)

        raise IBVirtualLegCloseConfirmationPendingError(
            position_uid=leg_before.position_uid,
            close_order_id=close_order_id,
            details=last_error,
        ) from timeout_error

    def recover_pending_runtime_position_leg_closes(
        self,
    ) -> dict[str, Any]:
        """Recover saved timeout Close requests before a normal UI Refresh."""
        if self.get_active_broker() != "IB":
            return {"pending": 0, "recovered": [], "unresolved": []}

        if self.ib_runtime_service is None:
            raise RuntimeError("IB runtime service is not set")

        pending_rows = (
            self.repository.get_pending_ib_virtual_position_leg_close_orders()
        )

        if not pending_rows:
            return {"pending": 0, "recovered": [], "unresolved": []}

        evidence_snapshot = self.get_ib_virtual_position_leg_evidence_snapshot()
        result = self._recover_pending_runtime_position_leg_closes_from_evidence(
            evidence_snapshot,
            pending_rows=pending_rows,
        )

        if result["recovered"]:
            logger.warning(
                "Recovered pending IB virtual-leg Close operations during "
                "Refresh: %s",
                result["recovered"],
            )

        return result

    def _recover_pending_runtime_position_leg_closes_from_evidence(
        self,
        evidence_snapshot: dict[str, Any],
        *,
        pending_rows: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Recover persisted timeout Close requests from broker evidence."""
        rows = (
            list(pending_rows)
            if pending_rows is not None
            else self.repository.get_pending_ib_virtual_position_leg_close_orders()
        )
        evidence_order_ids = self._ib_evidence_order_ids(evidence_snapshot)
        recovered: list[int] = []
        unresolved: list[dict[str, Any]] = []

        for row in rows:
            position_uid = str(row.get("position_uid") or "").strip()
            close_order_id = self._optional_positive_order_id(
                row.get("broker_order_id")
            )

            if not position_uid or close_order_id is None:
                unresolved.append(
                    {
                        "position_uid": position_uid,
                        "close_order_id": close_order_id,
                        "error": "Pending Close identity is incomplete",
                    }
                )
                continue

            if close_order_id not in evidence_order_ids:
                unresolved.append(
                    {
                        "position_uid": position_uid,
                        "close_order_id": close_order_id,
                        "error": "Broker evidence is not available yet",
                    }
                )
                continue

            try:
                self.recover_confirmed_runtime_position_leg_close(
                    position_uid=position_uid,
                    close_order_id=close_order_id,
                )
            except RuntimeError as error:
                unresolved.append(
                    {
                        "position_uid": position_uid,
                        "close_order_id": close_order_id,
                        "error": str(error),
                    }
                )
            else:
                recovered.append(close_order_id)

        return {
            "pending": len(rows),
            "recovered": recovered,
            "unresolved": unresolved,
        }

    def recover_confirmed_runtime_position_leg_close(
        self,
        position_uid: str,
        close_order_id: int,
    ) -> dict[str, Any]:
        """Persist one already executed exact virtual-leg Close safely."""
        if self.get_active_broker() != "IB":
            raise RuntimeError(
                "IB virtual-leg Close recovery requires active IB broker"
            )

        if self.ib_runtime_service is None:
            raise RuntimeError("IB runtime service is not set")

        position_uid_clean = str(position_uid or "").strip()
        close_order_id_value = self._optional_positive_order_id(close_order_id)

        if not position_uid_clean:
            raise ValueError("IB virtual-leg position_uid is empty")

        if close_order_id_value is None:
            raise ValueError("IB virtual-leg close order id is invalid")

        persisted = self.repository.get_ib_virtual_position_leg(position_uid_clean)

        if persisted is None:
            raise RuntimeError("Persisted IB virtual leg was not found")

        persisted_leg_status = str(persisted.get("leg_status") or "").strip().upper()

        if persisted_leg_status == IB_LEG_STATUS_CLOSED:
            history = self.repository.get_ib_virtual_position_leg_orders(
                position_uid=position_uid_clean,
                active_only=False,
            )
            existing_close_ids = {
                self._optional_positive_order_id(row.get("broker_order_id"))
                for row in history
                if str(row.get("order_role") or "").strip().upper()
                == IB_LEG_ORDER_ROLE_CLOSE
            }

            if close_order_id_value in existing_close_ids:
                return {
                    "position_uid": position_uid_clean,
                    "close_order_id": close_order_id_value,
                    "already_recovered": True,
                    "leg_status": IB_LEG_STATUS_CLOSED,
                }

            raise RuntimeError(
                "Persisted IB virtual leg is already CLOSED by another order"
            )

        history = self.repository.get_ib_virtual_position_leg_orders(
            position_uid=position_uid_clean,
            active_only=False,
        )
        pending_mapping = any(
            self._optional_positive_order_id(row.get("broker_order_id"))
            == close_order_id_value
            and str(row.get("order_role") or "").strip().upper()
            == IB_LEG_ORDER_ROLE_CLOSE
            and bool(row.get("is_active"))
            and str(row.get("execution_status") or "").strip().upper()
            == IB_LEG_CLOSE_EXECUTION_STATUS_PENDING
            for row in history
        )

        evidence = self.get_ib_virtual_position_leg_evidence_snapshot()
        evidence_order_ids = self._ib_evidence_order_ids(evidence)
        evidence_order_perm_ids = self._ib_evidence_order_perm_ids(evidence)
        seeds = self.repository.get_open_ib_virtual_position_leg_seeds(
            evidence_order_ids=evidence_order_ids,
            evidence_order_perm_ids=evidence_order_perm_ids,
        )
        matching_seeds = [
            dict(seed)
            for seed in seeds
            if str(seed.get("position_uid") or "").strip() == position_uid_clean
        ]

        if len(matching_seeds) != 1:
            raise RuntimeError(
                "Persisted OPEN IB virtual leg seed was not found uniquely"
            )

        leg_before = build_ib_virtual_position_legs_from_repository_seeds(
            matching_seeds
        )[0]
        self._validate_runtime_leg_close_recovery_candidate(
            leg=leg_before,
            close_order_id=close_order_id_value,
            evidence_snapshot=evidence,
            allow_existing_pending_mapping=pending_mapping,
        )
        seed_overrides = {
            position_uid_clean: {
                "persisted_close_order_ids": [close_order_id_value],
                "persisted_leg_status": IB_LEG_STATUS_CLOSED,
            }
        }
        provisional_snapshot = self._build_open_runtime_position_leg_snapshot(
            evidence,
            seed_overrides=seed_overrides,
        )
        cash_fx_offset = get_ib_cash_fx_virtual_observation_offset(
            legs=provisional_snapshot.legs,
            evidence_snapshot=evidence,
            broker_position_id=leg_before.broker_position_id,
        )
        cash_fx_offsets = (
            None
            if cash_fx_offset is None
            else {leg_before.broker_position_id: cash_fx_offset}
        )
        snapshot = self._build_open_runtime_position_leg_snapshot(
            evidence,
            seed_overrides=seed_overrides,
            cash_fx_virtual_observation_offsets=cash_fx_offsets,
        )
        leg_after = self._find_runtime_position_leg(
            snapshot=snapshot,
            position_uid=position_uid_clean,
        )
        self._validate_recovered_runtime_leg_close_snapshot(
            leg=leg_after,
            snapshot=snapshot,
            evidence_snapshot=evidence,
            close_order_id=close_order_id_value,
        )
        persistence = self.repository.persist_confirmed_ib_virtual_position_leg_close(
            leg=leg_after,
            close_order_id=close_order_id_value,
            evidence_snapshot=evidence,
        )
        broker_order_uid = self._record_runtime_leg_close_order(
            leg=leg_before,
            close_order_id=close_order_id_value,
            evidence_snapshot=evidence,
        )
        return {
            "position_uid": position_uid_clean,
            "close_order_id": close_order_id_value,
            "already_recovered": False,
            "leg_status": leg_after.leg_status,
            "persistence": persistence,
            "broker_order_uid": broker_order_uid,
            "cash_fx_virtual_observation_offset": cash_fx_offset,
        }

    def _record_runtime_leg_close_order(
        self,
        leg: IBVirtualPositionLeg,
        close_order_id: int,
        evidence_snapshot: dict[str, Any],
    ) -> str:
        existing = self.repository.get_broker_order_by_broker_order_id(
            broker="IB",
            broker_order_id=close_order_id,
            trade_uid=leg.trade_uid,
        )

        if existing is not None:
            return str(existing.get("broker_order_uid") or "").strip()

        close_plan_uid = self.repository.create_order_plan(
            trade_uid=leg.trade_uid,
            order_type="CLOSE_MARKET",
            side=leg.protective_action,
            volume=leg.volume,
            source="MANUAL",
        )
        close_order_ref = next(
            (
                str(row.get("order_ref") or "").strip()
                for key in ("completed_orders", "open_orders")
                for row in evidence_snapshot.get(key) or []
                if self._optional_positive_order_id(row.get("order_id"))
                == close_order_id
                and str(row.get("order_ref") or "").strip()
            ),
            "",
        )
        return self.repository.create_broker_order(
            trade_uid=leg.trade_uid,
            order_plan_uid=close_plan_uid,
            broker="IB",
            broker_order_id=str(close_order_id),
            execution_status="FILLED",
            broker_timestamp=self._execution_time_for_order(
                evidence_snapshot,
                close_order_id,
            ),
            source="MANUAL",
            broker_comment=close_order_ref,
        )

    def _validate_runtime_leg_close_recovery_candidate(
        self,
        leg: IBVirtualPositionLeg,
        close_order_id: int,
        evidence_snapshot: dict[str, Any],
        allow_existing_pending_mapping: bool = False,
    ) -> None:
        if leg.leg_status != IB_LEG_STATUS_OPEN:
            raise RuntimeError("Recoverable IB virtual leg is not OPEN")

        known_ids = {
            value
            for value in (
                leg.parent_order_id,
                leg.stop_loss_order_id,
                leg.take_profit_order_id,
                *leg.close_order_ids,
            )
            if value is not None
        }

        if close_order_id in known_ids and not allow_existing_pending_mapping:
            raise RuntimeError("Recovery close order is already mapped")

        execution_rows = [
            row
            for row in evidence_snapshot.get("executions") or []
            if self._optional_positive_order_id(row.get("order_id")) == close_order_id
        ]

        if not self._runtime_leg_close_execution_matches(
            leg=leg,
            rows=execution_rows,
        ):
            raise RuntimeError(
                "Recovery close execution does not match the virtual leg"
            )

        completed_rows = [
            row
            for row in evidence_snapshot.get("completed_orders") or []
            if self._optional_positive_order_id(row.get("order_id")) == close_order_id
        ]

        if len(completed_rows) != 1:
            raise RuntimeError("Recovery close completed order was not found uniquely")

        completed = completed_rows[0]

        if str(completed.get("order_type") or "").strip().upper() != "MKT":
            raise RuntimeError("Recovery close order is not MARKET")

        if str(completed.get("action") or "").strip().upper() != leg.protective_action:
            raise RuntimeError("Recovery close order action differs")

        if completed.get("same_client_id") is not True:
            raise RuntimeError("Recovery close order belongs to another IB clientId")

        if not self._runtime_leg_evidence_row_matches_group(
            row=completed,
            leg=leg,
        ):
            raise RuntimeError("Recovery close order contract differs")

        open_order_ids = {
            self._optional_positive_order_id(row.get("order_id"))
            for row in evidence_snapshot.get("open_orders") or []
        }
        active_child_ids = open_order_ids & {
            value
            for value in (
                leg.stop_loss_order_id,
                leg.take_profit_order_id,
            )
            if value is not None
        }

        if active_child_ids:
            raise RuntimeError(
                "Recovery is blocked because leg protection is still active"
            )

    def _validate_recovered_runtime_leg_close_snapshot(
        self,
        leg: IBVirtualPositionLeg,
        snapshot: IBVirtualPositionLegReconciliationSnapshot,
        evidence_snapshot: dict[str, Any],
        close_order_id: int,
    ) -> None:
        if leg.leg_status != IB_LEG_STATUS_CLOSED:
            raise RuntimeError("Recovered IB virtual leg is not CLOSED")

        if leg.reconciliation_status != IB_RECONCILIATION_STATUS_RECONCILED:
            raise RuntimeError("Recovered IB virtual leg is not RECONCILED")

        if snapshot.unmapped_protective_order_ids:
            raise RuntimeError(
                "Recovered IB virtual-leg snapshot has unmapped protection"
            )

        if close_order_id not in leg.close_order_ids:
            raise RuntimeError("Recovered close order identity was lost")

        if leg.protection_status != IB_PROTECTION_STATUS_NONE:
            raise RuntimeError("Recovered closed leg still has protection")

        group_legs = [
            item
            for item in snapshot.legs
            if item.broker_position_id == leg.broker_position_id
        ]
        known_order_ids = {
            order_id
            for item in group_legs
            for order_id in (
                item.parent_order_id,
                item.stop_loss_order_id,
                item.take_profit_order_id,
                *item.close_order_ids,
            )
            if order_id is not None
        }
        unknown_execution_ids = {
            order_id
            for row in evidence_snapshot.get("executions") or []
            if self._runtime_leg_evidence_row_matches_group(row=row, leg=leg)
            for order_id in [self._optional_positive_order_id(row.get("order_id"))]
            if order_id is not None and order_id not in known_order_ids
        }

        if unknown_execution_ids:
            raise RuntimeError(
                "Recovery is blocked by unknown execution IDs: "
                f"{sorted(unknown_execution_ids)}"
            )

    @classmethod
    def _runtime_leg_close_execution_matches(
        cls,
        leg: IBVirtualPositionLeg,
        rows: list[dict[str, Any]],
    ) -> bool:
        if not rows:
            return False

        quantities = [cls._optional_finite_float(row.get("shares")) for row in rows]

        if any(value is None for value in quantities):
            return False

        quantity = sum(value for value in quantities if value is not None)

        if not math.isclose(
            quantity,
            leg.volume,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            return False

        expected_sides = (
            {"BOT", "BUY"} if leg.protective_action == "BUY" else {"SLD", "SELL"}
        )
        return all(
            cls._runtime_leg_evidence_row_matches_group(row=row, leg=leg)
            and str(row.get("side") or "").strip().upper() in expected_sides
            for row in rows
        )

    @staticmethod
    def _runtime_leg_evidence_row_matches_group(
        row: dict[str, Any],
        leg: IBVirtualPositionLeg,
    ) -> bool:
        account_id = str(row.get("account_id") or row.get("account") or "").strip()
        symbol_name = str(row.get("symbol_name") or "").strip().upper()

        if not symbol_name:
            symbol = str(row.get("symbol") or "").strip().upper()
            currency = str(row.get("currency") or "").strip().upper()
            symbol_name = f"{symbol}{currency}" if symbol and currency else symbol

        return account_id == leg.account_id and symbol_name == leg.symbol_name

    @staticmethod
    def _assert_other_runtime_legs_unchanged(
        before: IBVirtualPositionLegReconciliationSnapshot,
        after: IBVirtualPositionLegReconciliationSnapshot,
        excluded_position_uid: str,
    ) -> None:
        before_by_uid = {
            leg.position_uid: leg
            for leg in before.legs
            if leg.position_uid != excluded_position_uid
            and leg.leg_status == IB_LEG_STATUS_OPEN
        }
        after_by_uid = {leg.position_uid: leg for leg in after.legs}

        for position_uid, before_leg in before_by_uid.items():
            after_leg = after_by_uid.get(position_uid)

            if after_leg is None:
                raise RuntimeError("Another IB virtual leg disappeared during Close")

            before_identity = (
                before_leg.leg_status,
                before_leg.stop_loss_order_id,
                before_leg.take_profit_order_id,
                before_leg.stop_loss,
                before_leg.take_profit,
                before_leg.oca_group,
            )
            after_identity = (
                after_leg.leg_status,
                after_leg.stop_loss_order_id,
                after_leg.take_profit_order_id,
                after_leg.stop_loss,
                after_leg.take_profit,
                after_leg.oca_group,
            )

            if before_identity != after_identity:
                raise RuntimeError(
                    "Another IB virtual leg changed during Close | "
                    f"position_uid={position_uid}"
                )

    @staticmethod
    def _broker_signed_quantity(
        evidence_snapshot: dict[str, Any],
        broker_position_id: str,
    ) -> float:
        values = [
            float(row.get("signed_quantity") or 0.0)
            for row in evidence_snapshot.get("positions") or []
            if str(row.get("broker_position_id") or "").strip() == broker_position_id
        ]
        return sum(values)

    def _wait_for_runtime_leg_after_close(
        self,
        position_uid: str,
        close_order_id: int,
        seed_overrides: dict[str, dict[str, Any]],
        cash_fx_virtual_observation_offsets: dict[str, float] | None,
    ) -> tuple[
        dict[str, Any],
        IBVirtualPositionLegReconciliationSnapshot,
        IBVirtualPositionLeg,
        int,
    ]:
        """Wait until exact close execution and protection removal settle."""
        last_details = "IB evidence was not collected"

        for attempt in range(
            1,
            IB_VIRTUAL_LEG_POST_MODIFY_RECONCILIATION_ATTEMPTS + 1,
        ):
            evidence = self.get_ib_virtual_position_leg_evidence_snapshot()
            snapshot = self._build_open_runtime_position_leg_snapshot(
                evidence,
                seed_overrides=seed_overrides,
                cash_fx_virtual_observation_offsets=(
                    cash_fx_virtual_observation_offsets
                ),
            )

            try:
                leg = self._find_runtime_position_leg(
                    snapshot=snapshot,
                    position_uid=position_uid,
                )
            except RuntimeError as error:
                last_details = str(error)
            else:
                details: list[str] = []

                if leg.leg_status != IB_LEG_STATUS_CLOSED:
                    details.append("leg_status=" + str(leg.leg_status))

                if leg.reconciliation_status != IB_RECONCILIATION_STATUS_RECONCILED:
                    details.append(
                        "reconciliation_status=" + str(leg.reconciliation_status)
                    )
                    details.extend(leg.reconciliation_messages)

                if snapshot.unmapped_protective_order_ids:
                    details.append(
                        "unmapped_order_ids="
                        + str(snapshot.unmapped_protective_order_ids)
                    )

                if close_order_id not in leg.close_order_ids:
                    details.append("close_order_id was not reconciled")

                if (
                    leg.stop_loss_order_id is not None
                    or leg.take_profit_order_id is not None
                ) and leg.protection_status != IB_PROTECTION_STATUS_NONE:
                    details.append("protection_status=" + str(leg.protection_status))

                if not details:
                    return evidence, snapshot, leg, attempt

                last_details = " | ".join(dict.fromkeys(details))

            if attempt < IB_VIRTUAL_LEG_POST_MODIFY_RECONCILIATION_ATTEMPTS:
                time.sleep(IB_VIRTUAL_LEG_POST_MODIFY_RECONCILIATION_DELAY_SECONDS)

        raise RuntimeError(
            "IB virtual-leg broker Close was confirmed, but the "
            "post-operation evidence did not settle safely: "
            f"{last_details}"
        )

    @staticmethod
    def _execution_time_for_order(
        evidence_snapshot: dict[str, Any],
        order_id: int,
    ) -> str | None:
        for row in evidence_snapshot.get("executions") or []:
            if (
                RuntimeEngine._optional_positive_order_id(row.get("order_id"))
                != order_id
            ):
                continue

            value = str(row.get("time") or "").strip()
            return value or None

        return None

    @classmethod
    def _build_post_modify_seed_overrides(
        cls,
        leg_before: IBVirtualPositionLeg,
        broker_result: dict[str, Any],
        stop_loss: float | None,
        take_profit: float | None,
    ) -> dict[str, dict[str, Any]]:
        """Build transient child identity for post-operation evidence."""
        raw_create_order_ids = broker_result.get("create_order_ids")
        create_order_ids = (
            dict(raw_create_order_ids) if isinstance(raw_create_order_ids, dict) else {}
        )
        stop_loss_order_id = cls._post_modify_order_id(
            current_order_id=leg_before.stop_loss_order_id,
            created_order_id=create_order_ids.get("stop_loss"),
            requested_price=stop_loss,
        )
        take_profit_order_id = cls._post_modify_order_id(
            current_order_id=leg_before.take_profit_order_id,
            created_order_id=create_order_ids.get("take_profit"),
            requested_price=take_profit,
        )

        if stop_loss is None or take_profit is None:
            oca_group = ""
        else:
            oca_group = str(
                broker_result.get("oca_group") or leg_before.oca_group
            ).strip()

        stop_loss_perm_id = (
            leg_before.stop_loss_order_perm_id
            if stop_loss_order_id == leg_before.stop_loss_order_id
            else None
        )
        take_profit_perm_id = (
            leg_before.take_profit_order_perm_id
            if take_profit_order_id == leg_before.take_profit_order_id
            else None
        )

        return {
            leg_before.position_uid: {
                "persisted_stop_loss_order_id": stop_loss_order_id,
                "persisted_take_profit_order_id": take_profit_order_id,
                "persisted_stop_loss_perm_id": stop_loss_perm_id,
                "persisted_take_profit_perm_id": take_profit_perm_id,
                "persisted_stop_loss": stop_loss,
                "persisted_take_profit": take_profit,
                "persisted_oca_group": oca_group,
            }
        }

    @classmethod
    def _post_modify_order_id(
        cls,
        current_order_id: int | None,
        created_order_id: object,
        requested_price: float | None,
    ) -> int | None:
        """Resolve the expected active child ID after Modify."""
        if requested_price is None:
            return None

        new_order_id = cls._optional_positive_order_id(created_order_id)

        if new_order_id is not None:
            return new_order_id

        return current_order_id

    @staticmethod
    def _optional_finite_float(value: object) -> float | None:
        """Normalize one finite numeric broker value safely."""
        if value is None or isinstance(value, bool):
            return None

        if isinstance(value, (int, float)):
            result = float(value)
        elif isinstance(value, str):
            text = value.strip()

            if not text:
                return None

            try:
                result = float(text)
            except ValueError:
                return None
        else:
            return None

        return result if math.isfinite(result) else None

    @staticmethod
    def _optional_positive_order_id(value: object) -> int | None:
        """Normalize an internal broker order ID without unsafe casts."""
        if value is None or isinstance(value, bool):
            return None

        if isinstance(value, int):
            order_id = value
        elif isinstance(value, float):
            if not math.isfinite(value) or not value.is_integer():
                return None

            order_id = int(value)
        elif isinstance(value, str):
            text = value.strip()

            if not text:
                return None

            try:
                order_id = int(text)
            except ValueError:
                return None
        else:
            return None

        return order_id if order_id > 0 else None

    def _wait_for_runtime_leg_after_modify(
        self,
        position_uid: str,
        stop_loss: float | None,
        take_profit: float | None,
        seed_overrides: dict[str, dict[str, Any]] | None = None,
        cash_fx_virtual_observation_offsets: dict[str, float] | None = None,
    ) -> tuple[
        dict[str, Any],
        IBVirtualPositionLegReconciliationSnapshot,
        IBVirtualPositionLeg,
        int,
    ]:
        """Wait until IB snapshots expose the confirmed Modify state."""
        last_details = "IB evidence was not collected"

        for attempt in range(
            1,
            IB_VIRTUAL_LEG_POST_MODIFY_RECONCILIATION_ATTEMPTS + 1,
        ):
            evidence = self.get_ib_virtual_position_leg_evidence_snapshot()
            snapshot = self._build_open_runtime_position_leg_snapshot(
                evidence,
                seed_overrides=seed_overrides,
                cash_fx_virtual_observation_offsets=(
                    cash_fx_virtual_observation_offsets
                ),
            )

            try:
                leg = self._find_runtime_position_leg(
                    snapshot=snapshot,
                    position_uid=position_uid,
                )
            except RuntimeError as error:
                last_details = str(error)
            else:
                ready, last_details = self._runtime_leg_modify_snapshot_is_ready(
                    leg=leg,
                    snapshot=snapshot,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )

                if ready:
                    return evidence, snapshot, leg, attempt

            if attempt < IB_VIRTUAL_LEG_POST_MODIFY_RECONCILIATION_ATTEMPTS:
                time.sleep(IB_VIRTUAL_LEG_POST_MODIFY_RECONCILIATION_DELAY_SECONDS)

        raise RuntimeError(
            "IB virtual-leg broker Modify was confirmed, but the "
            "post-operation evidence did not settle safely: "
            f"{last_details}"
        )

    @classmethod
    def _runtime_leg_modify_snapshot_is_ready(
        cls,
        leg: IBVirtualPositionLeg,
        snapshot: IBVirtualPositionLegReconciliationSnapshot,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> tuple[bool, str]:
        """Validate one post-Modify evidence snapshot without writing."""
        details: list[str] = []

        if leg.reconciliation_status != IB_RECONCILIATION_STATUS_RECONCILED:
            details.append("leg_status=" + str(leg.reconciliation_status))
            details.extend(leg.reconciliation_messages)

        if snapshot.unmapped_protective_order_ids:
            details.append(
                "unmapped_order_ids=" + str(snapshot.unmapped_protective_order_ids)
            )

        if not cls._runtime_leg_protection_price_matches(
            actual=leg.stop_loss,
            expected=stop_loss,
        ):
            details.append(f"Stop Loss expected={stop_loss} actual={leg.stop_loss}")

        if not cls._runtime_leg_protection_price_matches(
            actual=leg.take_profit,
            expected=take_profit,
        ):
            details.append(
                "Take Profit " f"expected={take_profit} actual={leg.take_profit}"
            )

        if (
            stop_loss is not None
            and take_profit is not None
            and leg.protection_status != IB_PROTECTION_STATUS_COMPLETE
        ):
            details.append("protection_status=" + str(leg.protection_status))

        if details:
            return False, " | ".join(dict.fromkeys(details))

        return True, "RECONCILED"

    @staticmethod
    def _runtime_leg_protection_price_matches(
        actual: float | None,
        expected: float | None,
    ) -> bool:
        if actual is None or expected is None:
            return actual is expected

        return math.isclose(
            float(actual),
            float(expected),
            rel_tol=1e-9,
            abs_tol=1e-10,
        )

    @staticmethod
    def _find_runtime_position_leg(
        snapshot: IBVirtualPositionLegReconciliationSnapshot,
        position_uid: str,
    ) -> IBVirtualPositionLeg:
        matches = [leg for leg in snapshot.legs if leg.position_uid == position_uid]

        if len(matches) != 1:
            raise RuntimeError("Selected IB virtual leg was not found uniquely")

        return matches[0]

    @staticmethod
    def _validate_runtime_leg_protection_price(
        actual: float | None,
        expected: float | None,
        field_name: str,
    ) -> None:
        if actual is None or expected is None:
            if actual is expected:
                return

            raise RuntimeError(f"IB virtual-leg {field_name} presence differs")

        if not math.isclose(
            float(actual),
            float(expected),
            rel_tol=1e-9,
            abs_tol=1e-10,
        ):
            raise RuntimeError(f"IB virtual-leg {field_name} price differs")

    @staticmethod
    def _ib_evidence_order_ids(
        evidence_snapshot: dict[str, Any],
    ) -> set[int]:
        """Collect exact IB order IDs visible in the current evidence."""
        result: set[int] = set()

        for collection_name in (
            "open_orders",
            "completed_orders",
            "executions",
        ):
            for row in evidence_snapshot.get(collection_name) or []:
                try:
                    order_id = int(row.get("order_id") or 0)
                except (TypeError, ValueError):
                    continue

                if order_id > 0:
                    result.add(order_id)

        return result

    @staticmethod
    def _ib_evidence_order_perm_ids(
        evidence_snapshot: dict[str, Any],
    ) -> set[int]:
        """Collect stable IB permIds visible in the current evidence."""
        result: set[int] = set()

        for collection_name in (
            "open_orders",
            "completed_orders",
            "executions",
        ):
            for row in evidence_snapshot.get(collection_name) or []:
                try:
                    perm_id = int(row.get("perm_id") or 0)
                except (TypeError, ValueError):
                    continue

                if perm_id > 0:
                    result.add(perm_id)

        return result

    def get_active_broker_positions(self) -> list:
        """
        Повернути відкриті positions для активного broker.

        OrdersPage не звертається напряму до adapter/service.
        """
        broker = self.get_active_broker()

        if broker == "CTRADER":
            service = self.ctrader_runtime_service

            if service is None:
                raise RuntimeError("cTrader runtime service is not set")

            return service.get_positions()

        if broker == "IB":
            service = self.ib_runtime_service

            if service is None:
                raise RuntimeError("IB runtime service is not set")

            positions = service.get_positions()

            return self._enrich_ib_positions_from_runtime_repository(
                positions,
            )

        raise RuntimeError(f"Positions are not supported for broker: {broker}")

    def _enrich_ib_positions_from_runtime_repository(
        self,
        positions: list,
    ) -> list:
        """
        Доповнити IB broker positions локальними runtime даними.

        IB position callback не дає opened timestamp. Для LGE-opened
        positions беремо created_utc/opened_utc з SQLite Runtime Position.
        Broker-manual IB positions лишаються без часу.
        """
        for position in positions:
            position_id = self._get_position_id_text(position)

            if not position_id:
                continue

            try:
                runtime_position = (
                    self.repository.get_open_position_by_broker_position_id(
                        broker="IB",
                        broker_position_id=position_id,
                    )
                )
            except Exception:  # noqa
                logger.exception(
                    "Failed to enrich IB position from runtime repository."
                )
                continue

            if runtime_position is None:
                continue

            current_opened = str(getattr(position, "opened_utc", "") or "").strip()

            if not current_opened:
                opened_utc = (
                    runtime_position.get("opened_utc")
                    or runtime_position.get("created_utc")
                    or ""
                )
                position.opened_utc = str(opened_utc or "")

            raw_payload = getattr(position, "raw_payload", None)

            if not isinstance(raw_payload, dict):
                raw_payload = {}
                position.raw_payload = raw_payload

            raw_payload["runtime_position"] = {
                "position_uid": runtime_position.get("position_uid"),
                "trade_uid": runtime_position.get("trade_uid"),
                "source": runtime_position.get("source"),
                "created_utc": runtime_position.get("created_utc"),
                "opened_utc": runtime_position.get("opened_utc"),
            }

        return positions

    def set_broker_adapter(
        self,
        broker_adapter: BrokerInterface,
    ) -> None:
        """
        Встановити активний broker adapter.
        """

        self.broker_adapter = broker_adapter

        self.add_event(
            RuntimeEventType.BROKER_ADAPTER_SELECTED,
            message="Broker adapter selected",
            payload={
                "adapter_class": broker_adapter.__class__.__name__,
            },
        )

    def set_ctrader_runtime_service(
        self,
        service: CTraderRuntimeServiceProtocol,
    ) -> None:
        """
        Встановити cTrader runtime service.
        """
        self.ctrader_runtime_service = service

        self.add_event(
            RuntimeEventType.BROKER_SERVICE_SELECTED,
            message="cTrader runtime service selected",
            payload={
                "service_class": service.__class__.__name__,
            },
        )

    def set_ib_runtime_service(
        self,
        service: IBRuntimeServiceProtocol,
    ) -> None:
        """
        Встановити IB runtime service.
        """
        self.ib_runtime_service = service

        self.add_event(
            RuntimeEventType.BROKER_SERVICE_SELECTED,
            message="IB runtime service selected",
            payload={
                "service_class": service.__class__.__name__,
            },
        )

    def download_ctrader_historical_bars(
        self,
        symbol_name: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
        progress_callback: CTraderHistoryProgressCallback | None = None,
    ) -> CTraderHistoryDownloadResult:
        """Download cTrader OHLC history through the service chain."""
        service = self.ctrader_runtime_service
        if service is None:
            raise RuntimeError("cTrader runtime service is not set")
        return service.get_historical_trendbars(
            symbol_name=symbol_name,
            timeframe=timeframe,
            start_utc=start_utc,
            end_utc=end_utc,
            progress_callback=progress_callback,
        )

    def download_ib_historical_bars(
        self,
        symbol_name: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
        progress_callback: IBHistoryProgressCallback | None = None,
    ) -> IBHistoryDownloadResult:
        """Download IB OHLC history through the service chain."""
        service = self.ib_runtime_service
        if service is None:
            raise RuntimeError("IB runtime service is not set")
        return service.get_historical_bars(
            symbol_name=symbol_name,
            timeframe=timeframe,
            start_utc=start_utc,
            end_utc=end_utc,
            progress_callback=progress_callback,
        )

    def prepare_ctrader_startup_connection(
        self,
        account_mode: str = "DEMO",
    ) -> bool:
        """Run bounded cTrader Startup Readiness through the service layer."""
        service = self.ctrader_runtime_service

        if service is None:
            self.add_event(
                RuntimeEventType.ERROR,
                message="cTrader runtime service is not set",
            )
            return False

        normalized_mode = str(account_mode).strip().upper()
        if normalized_mode not in {"DEMO", "LIVE"}:
            raise ValueError(
                f"Unsupported cTrader account_mode: {account_mode}"
            )

        self.set_broker("CTRADER")
        self.context.account_mode = normalized_mode
        self.context.touch()

        ready = service.prepare_startup_connection(
            account_mode=normalized_mode,
        )
        if ready:
            return True

        self.context.set_broker_connection_state(
            BrokerConnectionState.DISCONNECTED,
        )
        self.add_event(
            RuntimeEventType.BROKER_CONNECTION_ERROR,
            message="cTrader Startup Readiness timeout",
            payload={
                "service_class": service.__class__.__name__,
                "account_mode": normalized_mode,
            },
        )
        return False

    def connect_ctrader_demo(self) -> bool:
        """
        Підключити cTrader DEMO через CTraderRuntimeService.
        """
        service = self.ctrader_runtime_service

        if service is None:
            self.add_event(
                RuntimeEventType.ERROR,
                message="cTrader runtime service is not set",
            )
            return False

        self.set_broker("CTRADER")
        self.context.account_mode = "DEMO"
        self.context.touch()

        self.context.set_broker_connection_state(
            BrokerConnectionState.CONNECTING,
        )

        self.add_event(
            RuntimeEventType.BROKER_CONNECTING,
            message="cTrader DEMO connecting",
            payload={
                "service_class": service.__class__.__name__,
            },
        )

        adapter = service.connect_demo()

        broker_health = service.get_broker_health()

        if adapter is not None and broker_health.is_connected():
            self.context.set_broker_connection_state(
                BrokerConnectionState.CONNECTED,
            )

            self.add_event(
                RuntimeEventType.BROKER_CONNECTED,
                message="cTrader DEMO connected",
                payload={
                    "service_class": service.__class__.__name__,
                },
            )
            return True

        self.context.set_broker_connection_state(
            BrokerConnectionState.ERROR,
        )

        self.add_event(
            RuntimeEventType.BROKER_CONNECTION_ERROR,
            message="cTrader DEMO connection failed",
            payload={
                "service_class": service.__class__.__name__,
                "last_error": broker_health.last_error,
            },
        )

        return False

    def connect_ctrader_live(self) -> bool:
        """
        Підключити cTrader LIVE через CTraderRuntimeService.
        """
        service = self.ctrader_runtime_service

        if service is None:
            self.add_event(
                RuntimeEventType.ERROR,
                message="cTrader runtime service is not set",
            )
            return False

        self.set_broker("CTRADER")
        self.context.account_mode = "LIVE"
        self.context.touch()

        self.context.set_broker_connection_state(
            BrokerConnectionState.CONNECTING,
        )

        self.add_event(
            RuntimeEventType.BROKER_CONNECTING,
            message="cTrader LIVE connecting",
            payload={
                "service_class": service.__class__.__name__,
            },
        )

        adapter = service.connect_live()

        broker_health = service.get_broker_health()

        if adapter is not None and broker_health.is_connected():
            self.context.set_broker_connection_state(
                BrokerConnectionState.CONNECTED,
            )

            self.add_event(
                RuntimeEventType.BROKER_CONNECTED,
                message="cTrader LIVE connected",
                payload={
                    "service_class": service.__class__.__name__,
                },
            )
            return True

        self.context.set_broker_connection_state(
            BrokerConnectionState.ERROR,
        )

        self.add_event(
            RuntimeEventType.BROKER_CONNECTION_ERROR,
            message="cTrader LIVE connection failed",
            payload={
                "service_class": service.__class__.__name__,
                "last_error": broker_health.last_error,
            },
        )

        return False

    def disconnect_ctrader(self) -> None:
        """
        Відключити cTrader через CTraderRuntimeService.
        """
        service = self.ctrader_runtime_service

        if service is None:
            self.add_event(
                RuntimeEventType.ERROR,
                message="cTrader runtime service is not set",
            )
            return

        service.disconnect()

        self.context.set_broker_connection_state(
            BrokerConnectionState.DISCONNECTED,
        )

        self.add_event(
            RuntimeEventType.BROKER_DISCONNECTED,
            message="cTrader disconnected",
            payload={
                "service_class": service.__class__.__name__,
            },
        )

    def connect_ib_demo(self) -> bool:
        """
        Підключити IB DEMO через IBRuntimeService.
        """
        service = self.ib_runtime_service

        if service is None:
            self.add_event(
                RuntimeEventType.ERROR,
                message="IB runtime service is not set",
            )
            return False

        self.set_broker("IB")
        self.context.account_mode = "DEMO"
        self.context.touch()

        self.context.set_broker_connection_state(
            BrokerConnectionState.CONNECTING,
        )

        self.add_event(
            RuntimeEventType.BROKER_CONNECTING,
            message="IB DEMO connecting",
            payload={
                "service_class": service.__class__.__name__,
            },
        )

        adapter = service.connect_demo()

        broker_health = service.get_broker_health()

        if adapter is not None and broker_health.is_connected():
            self.context.set_broker_connection_state(
                BrokerConnectionState.CONNECTED,
            )

            self.add_event(
                RuntimeEventType.BROKER_CONNECTED,
                message="IB DEMO connected",
                payload={
                    "service_class": service.__class__.__name__,
                },
            )
            return True

        self.context.set_broker_connection_state(
            BrokerConnectionState.ERROR,
        )

        self.add_event(
            RuntimeEventType.BROKER_CONNECTION_ERROR,
            message="IB DEMO connection failed",
            payload={
                "service_class": service.__class__.__name__,
                "last_error": broker_health.last_error,
            },
        )

        return False

    def connect_broker(self) -> bool:
        """
        Підключити активний broker adapter.
        """

        if self.broker_adapter is None:
            self.add_event(
                RuntimeEventType.ERROR,
                message="Broker adapter is not set",
            )
            return False

        self.context.set_broker_connection_state(
            BrokerConnectionState.CONNECTING,
        )
        self.add_event(
            RuntimeEventType.BROKER_CONNECTING,
            message="Broker connecting",
            payload={
                "adapter_class": self.broker_adapter.__class__.__name__,
            },
        )

        try:
            connected = self.broker_adapter.connect()
        except Exception as exc:  # noqa: BLE001
            self.context.set_broker_connection_state(
                BrokerConnectionState.ERROR,
            )
            self.add_event(
                RuntimeEventType.BROKER_CONNECTION_ERROR,
                message=f"Broker connection error: {exc}",
                payload={
                    "adapter_class": self.broker_adapter.__class__.__name__,
                },
            )
            return False

        if connected:
            self.context.set_broker_connection_state(
                BrokerConnectionState.CONNECTED,
            )
            self.add_event(
                RuntimeEventType.BROKER_CONNECTED,
                message="Broker connected",
                payload={
                    "adapter_class": self.broker_adapter.__class__.__name__,
                },
            )
            return True

        self.context.set_broker_connection_state(
            BrokerConnectionState.ERROR,
        )
        self.add_event(
            RuntimeEventType.BROKER_CONNECTION_ERROR,
            message="Broker connection failed",
            payload={
                "adapter_class": self.broker_adapter.__class__.__name__,
            },
        )

        return False

    def disconnect_broker(self) -> None:
        """
        Відключити активний broker adapter.
        """

        if self.broker_adapter is None:
            return

        self.broker_adapter.disconnect()

        self.context.set_broker_connection_state(
            BrokerConnectionState.DISCONNECTED,
        )

        self.add_event(
            RuntimeEventType.BROKER_DISCONNECTED,
            message="Broker disconnected",
            payload={
                "adapter_class": self.broker_adapter.__class__.__name__,
            },
        )

    def is_broker_connected(self) -> bool:
        """
        Перевірити, чи broker adapter підключений.
        """

        if self.broker_adapter is None:
            return False

        return self.broker_adapter.is_connected()

    def get_broker_account_info(self) -> BrokerAccount | None:
        """
        Отримати інформацію про broker account.
        """

        if self.broker_adapter is None:
            self.add_event(
                RuntimeEventType.ERROR,
                message="Broker adapter is not set",
            )
            return None

        return self.broker_adapter.get_account_info()

    def set_execution_mode(
        self,
        execution_mode: str,
    ) -> None:
        """
        Встановити execution mode.
        """

        self.context.execution_mode = str(execution_mode).strip().upper()
        self.context.touch()

        self.add_event(
            RuntimeEventType.MODE_CHANGED,
            message=f"Execution mode changed: {self.context.execution_mode}",
        )

    def get_runtime_state(self) -> RuntimeState:
        """
        Повернути поточний runtime state.
        """

        return self.context.runtime_state

    def is_scheduler_running(self) -> bool:
        """
        Повернути стан RuntimeScheduler.
        """
        return self.scheduler.is_running

    def attach_reconnect_task(
        self,
        reconnect_task: RuntimeReconnectTask,
        interval_seconds: float = RUNTIME_RECONNECT_TASK_INTERVAL_SECONDS,
    ) -> None:
        """
        Підключити RuntimeReconnectTask до RuntimeScheduler.

        Engine не зберігає тут task як єдиний runtime reconnect task,
        бо reconnect-watch окремий для IB і cTrader.
        """

        self.scheduler.add_periodic_task(
            interval_seconds=interval_seconds,
            task=reconnect_task.check_and_reconnect,
        )

    def start_ctrader_reconnect_watch(
        self,
        interval_seconds: float = CTRADER_RECONNECT_WATCH_INTERVAL_SECONDS,
    ) -> None:
        """
        Запустити reconnect-watch для cTrader runtime service.

        RoadMap78:
        використовується після failed Startup AutoConnect.
        """

        if self._ctrader_reconnect_watch_started:
            logger.debug("cTrader reconnect watch already active.")
            return

        service = self.ctrader_runtime_service

        if service is None:
            self.add_event(
                RuntimeEventType.ERROR,
                message="Cannot start cTrader reconnect watch: service is not set",
            )
            return

        reconnect_task = RuntimeReconnectTask(
            runtime_service=service,
            reconnect_cooldown_seconds=CTRADER_RECONNECT_COOLDOWN_SECONDS,
            failure_backoff_seconds=(
                CTRADER_RECONNECT_FAILURE_BACKOFF_SECONDS
            ),
        )

        self._ctrader_reconnect_task = reconnect_task

        self.attach_reconnect_task(
            reconnect_task=reconnect_task,
            interval_seconds=interval_seconds,
        )

        self._ctrader_reconnect_watch_started = True

        self.add_event(
            RuntimeEventType.RECONNECT_STARTED,
            message="cTrader reconnect watch started",
            payload={
                "service_class": service.__class__.__name__,
                "interval_seconds": interval_seconds,
            },
        )

    def start_ib_reconnect_watch(
        self,
        interval_seconds: float = IB_RECONNECT_WATCH_INTERVAL_SECONDS,
    ) -> None:
        """
        Запустити reconnect-watch для IB runtime service.

        RoadMap78:
        використовується після failed Startup AutoConnect.
        """
        if self._ib_reconnect_watch_started:
            logger.debug("IB reconnect watch already active.")
            return

        service = self.ib_runtime_service

        if service is None:
            self.add_event(
                RuntimeEventType.ERROR,
                message="Cannot start IB reconnect watch: service is not set",
            )
            return

        reconnect_task = RuntimeReconnectTask(
            runtime_service=service,
            reconnect_cooldown_seconds=IB_RECONNECT_COOLDOWN_SECONDS,
        )

        self._ib_reconnect_task = reconnect_task

        self.attach_reconnect_task(
            reconnect_task=reconnect_task,
            interval_seconds=interval_seconds,
        )

        self._ib_reconnect_watch_started = True

        logger.warning("IB reconnect watch started.")

        self.add_event(
            RuntimeEventType.RECONNECT_STARTED,
            message="IB reconnect watch started",
            payload={
                "service_class": service.__class__.__name__,
                "interval_seconds": interval_seconds,
            },
        )

    def lock_active_broker(self) -> None:
        """
        Заборонити зміну активного брокера.
        """
        self._active_broker_locked = True

    def unlock_active_broker(self) -> None:
        """
        Дозволити зміну активного брокера.
        """
        self._active_broker_locked = False

    def is_active_broker_locked(self) -> bool:
        """
        Перевірити, чи заблокована зміна активного брокера.
        """
        return self._active_broker_locked

    @staticmethod
    def _get_position_id_text(position: Any) -> str:
        """
        Повернути broker position id як текст.
        """
        return str(getattr(position, "position_id", "") or "").strip()

    @staticmethod
    def _get_position_opened_value(position: Any) -> int:
        """
        Повернути opened_utc як число для сортування.

        cTrader зараз дає openTimestamp як raw milliseconds.
        """
        raw_value = str(getattr(position, "opened_utc", "") or "").strip()

        try:
            return int(raw_value)
        except ValueError:
            return 0

    @staticmethod
    def _position_matches_manual_order(
        position: Any,
        symbol_norm: str,
        side_norm: str,
        lots_float: float,
    ) -> bool:
        """
        Перевірити, що broker position відповідає manual order.
        """
        position_symbol = (
            str(
                getattr(position, "symbol_name", "") or "",
            )
            .strip()
            .upper()
        )

        if position_symbol != symbol_norm:
            return False

        position_side = (
            str(
                getattr(position, "side", "") or "",
            )
            .strip()
            .upper()
        )

        if position_side != side_norm:
            return False

        try:
            position_volume = float(getattr(position, "volume", 0.0) or 0.0)
        except (TypeError, ValueError):
            return False

        return abs(position_volume - lots_float) <= 0.0000001

    @staticmethod
    def _extract_broker_order_id(broker_result: Any) -> str | None:
        """
        Витягнути broker order id з результату cTrader order.
        """
        if isinstance(broker_result, dict):
            value = (
                broker_result.get("order_id")
                or broker_result.get("orderId")
                or broker_result.get("broker_order_id")
            )
            return None if value is None else str(value)

        order = getattr(broker_result, "order", None)

        if order is None:
            return None

        value = getattr(order, "orderId", None)

        return None if value is None else str(value)

    @staticmethod
    def _extract_broker_position_id(broker_result: Any) -> str | None:
        """
        Витягнути broker position id з результату cTrader order.
        """
        if isinstance(broker_result, dict):
            value = (
                broker_result.get("position_id")
                or broker_result.get("positionId")
                or broker_result.get("broker_position_id")
            )
            return None if value is None else str(value)

        position = getattr(broker_result, "position", None)

        if position is None:
            return None

        value = getattr(position, "positionId", None)

        return None if value is None else str(value)

    def _find_opened_manual_position(
        self,
        positions_before: list[Any],
        positions_after: list[Any],
        broker_result: Any,
        symbol_norm: str,
        side_norm: str,
        lots_float: float,
    ) -> Any | None:
        """
        Знайти саме нову broker position після manual MARKET order.

        Пріоритет:
        1. positionId з cTrader execution result;
        2. position_id, якого не було before;
        3. symbol + side + volume;
        4. найновіший opened_utc.
        """
        expected_position_id = self._extract_broker_position_id(broker_result)

        if expected_position_id:
            for position in positions_after:
                if self._get_position_id_text(position) != expected_position_id:
                    continue

                if not self._position_matches_manual_order(
                    position=position,
                    symbol_norm=symbol_norm,
                    side_norm=side_norm,
                    lots_float=lots_float,
                ):
                    continue

                return position

        before_ids = {
            self._get_position_id_text(position) for position in positions_before
        }

        candidates = []

        for position in positions_after:
            position_id = self._get_position_id_text(position)

            if not position_id:
                continue

            if position_id in before_ids:
                continue

            if not self._position_matches_manual_order(
                position=position,
                symbol_norm=symbol_norm,
                side_norm=side_norm,
                lots_float=lots_float,
            ):
                continue

            candidates.append(position)

        if not candidates:
            return None

        candidates.sort(
            key=self._get_position_opened_value,
            reverse=True,
        )

        return candidates[0]

    @staticmethod
    def _ib_lots_to_fx_quantity(lots: float) -> float:
        """
        Перетворити LGE lot-size у IB Forex quantity.

        Для Forex: 1.00 lot = 100000 units, 0.01 lot = 1000 units.
        """
        lots_float = float(lots)

        if lots_float <= 0.0:
            raise ValueError("IB lots value must be positive")

        return round(lots_float * 100000.0, 2)

    @staticmethod
    def _get_position_symbol_text(position: Any) -> str:
        """
        Повернути symbol position у нормалізованому вигляді EURUSD.
        """
        return (
            str(getattr(position, "symbol_name", "") or "")
            .strip()
            .upper()
            .replace(".", "")
            .replace("/", "")
        )

    @staticmethod
    def _get_position_signed_volume(position: Any) -> float:
        """
        Повернути IB/net position volume зі знаком.
        """
        side = str(getattr(position, "side", "") or "").strip().upper()

        try:
            volume = abs(float(getattr(position, "volume", 0.0) or 0.0))
        except (TypeError, ValueError):
            return 0.0

        if side == "SELL":
            return -volume

        if side == "BUY":
            return volume

        return 0.0

    def _find_ib_opened_manual_position(
        self,
        positions_before: list[Any],
        positions_after: list[Any],
        symbol_norm: str,
        side_norm: str,
        quantity_float: float,
    ) -> Any | None:
        """
        Знайти IB position через quantity delta.
        """
        symbol_clean = symbol_norm.replace(".", "").replace("/", "")
        expected_delta = quantity_float

        if side_norm == "SELL":
            expected_delta = -quantity_float

        tolerance = max(0.01, abs(quantity_float) * 0.000001)

        before_by_key: dict[tuple[str, str], float] = {}

        for position in positions_before:
            key = (
                str(getattr(position, "account_id", "") or ""),
                self._get_position_symbol_text(position),
            )
            before_by_key[key] = self._get_position_signed_volume(position)

        candidates: list[Any] = []

        for position in positions_after:
            position_symbol = self._get_position_symbol_text(position)

            if position_symbol != symbol_clean:
                continue

            key = (
                str(getattr(position, "account_id", "") or ""),
                position_symbol,
            )
            before_signed = before_by_key.get(key, 0.0)
            after_signed = self._get_position_signed_volume(position)
            delta = after_signed - before_signed

            if abs(delta - expected_delta) <= tolerance:
                candidates.append(position)

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: abs(self._get_position_signed_volume(item)),
            reverse=True,
        )

        return candidates[0]

    def _persist_new_ib_virtual_position_leg(
        self,
        *,
        position_uid: str,
        trade_uid: str,
        account_id: str,
        matched_position: Any,
        broker_result: dict[str, Any],
        evidence_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Persist one newly opened LGE-owned IB leg from exact Open evidence.

        CASH Forex Virtual FX quantity is not terminal identity here. The
        before/after broker delta already proved placement, while this method
        proves the exact parent execution and active child order mappings.
        """
        position_uid_clean = str(position_uid or "").strip()
        trade_uid_clean = str(trade_uid or "").strip()

        if not position_uid_clean or not trade_uid_clean:
            raise RuntimeError("New IB virtual-leg persistence identity is incomplete")

        if evidence_snapshot is None:
            evidence_snapshot = self.get_ib_virtual_position_leg_evidence_snapshot()
        leg = build_confirmed_ib_virtual_position_leg_after_open(
            position_uid=position_uid_clean,
            trade_uid=trade_uid_clean,
            broker_position_id=str(getattr(matched_position, "position_id", "") or ""),
            account_id=str(account_id or "").strip(),
            symbol_name=str(getattr(matched_position, "symbol_name", "") or ""),
            side=str(broker_result.get("side") or "").strip().upper(),
            volume=float(broker_result.get("quantity") or 0.0),
            source=str(
                broker_result.get("control_mode")
                or get_broker_order_control_mode(broker_result.get("broker_comment"))
                or ORDER_CONTROL_MODE_MANUAL
            )
            .strip()
            .upper(),
            broker_result=broker_result,
            evidence_snapshot=evidence_snapshot,
        )
        persistence = self.repository.persist_confirmed_ib_virtual_position_leg_open(
            leg=leg,
            evidence_snapshot=evidence_snapshot,
            parent_order_ref=str(broker_result.get("broker_comment") or "").strip(),
        )
        persisted_leg = self.repository.get_ib_virtual_position_leg(position_uid_clean)

        if persisted_leg is None:
            raise RuntimeError("New IB virtual leg was not written to SQLite")

        if (
            str(persisted_leg.get("leg_status") or "").strip().upper()
            != IB_LEG_STATUS_OPEN
        ):
            raise RuntimeError("Persisted IB virtual leg is not OPEN")

        return {
            "position_uid": position_uid_clean,
            "parent_order_id": leg.parent_order_id,
            "stop_loss_order_id": leg.stop_loss_order_id,
            "take_profit_order_id": leg.take_profit_order_id,
            "oca_group": leg.oca_group,
            "leg_status": leg.leg_status,
            "protection_status": leg.protection_status,
            "reconciliation_status": leg.reconciliation_status,
            "persistence": persistence,
        }

    @staticmethod
    def _ib_evidence_symbol(row: dict[str, Any]) -> str:
        """Return normalized Forex symbol from one IB evidence row."""
        symbol_name = (
            str(row.get("symbol_name") or "")
            .strip()
            .upper()
            .replace(".", "")
            .replace("/", "")
        )

        if symbol_name:
            return symbol_name

        symbol = str(row.get("symbol") or "").strip().upper()
        currency = str(row.get("currency") or "").strip().upper()
        return f"{symbol}{currency}" if symbol and currency else symbol

    @staticmethod
    def _ib_evidence_side(value: Any) -> str:
        """Normalize IB execution/action text to BUY or SELL."""
        side = str(value or "").strip().upper()

        if side in {"BUY", "BOT"}:
            return "BUY"

        if side in {"SELL", "SLD"}:
            return "SELL"

        return ""

    @staticmethod
    def _ib_evidence_order_id(row: dict[str, Any]) -> int | None:
        """Return a positive broker order ID from one evidence row."""
        try:
            order_id = int(row.get("order_id"))
        except (TypeError, ValueError):
            return None

        return order_id if order_id > 0 else None

    @staticmethod
    def _ib_evidence_quantity(row: dict[str, Any]) -> float:
        """Return absolute execution/order quantity from evidence."""
        for key in ("shares", "total_quantity", "filled"):
            try:
                value = abs(float(row.get(key) or 0.0))
            except (TypeError, ValueError):
                continue

            if value > 0.0:
                return value

        return 0.0

    @staticmethod
    def _ib_evidence_price(row: dict[str, Any], order_type: str) -> float | None:
        """Return a positive execution/protective price from evidence."""
        keys = ("price",)

        if order_type == "STP":
            keys = ("aux_price", "stop_price", "price")
        elif order_type == "LMT":
            keys = ("lmt_price", "limit_price", "price")

        for key in keys:
            try:
                value = float(row.get(key) or 0.0)
            except (TypeError, ValueError):
                continue

            if value > 0.0:
                return value

        return None

    def _infer_pending_open_children(
        self,
        *,
        parent_order_id: int,
        account_id: str,
        symbol_name: str,
        side: str,
        quantity: float,
        evidence_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """Infer exact active attached child identities for a legacy Open."""
        protective_side = "SELL" if side == "BUY" else "BUY"
        rows = []

        for row in evidence_snapshot.get("open_orders") or []:
            try:
                row_parent_id = int(row.get("parent_id") or 0)
            except (TypeError, ValueError):
                continue

            if row_parent_id != parent_order_id:
                continue

            if str(row.get("account") or "").strip() != account_id:
                continue

            if self._ib_evidence_symbol(row) != symbol_name:
                continue

            if self._ib_evidence_side(row.get("action")) != protective_side:
                continue

            row_quantity = self._ib_evidence_quantity(row)

            if not math.isclose(
                row_quantity,
                quantity,
                rel_tol=1e-9,
                abs_tol=0.01,
            ):
                continue

            rows.append(row)

        stop_rows = [
            row
            for row in rows
            if str(row.get("order_type") or "").strip().upper() in {"STP", "STOP"}
        ]
        take_profit_rows = [
            row
            for row in rows
            if str(row.get("order_type") or "").strip().upper() in {"LMT", "LIMIT"}
        ]

        if len(stop_rows) > 1 or len(take_profit_rows) > 1:
            raise RuntimeError("Delayed IB Open child-order evidence is ambiguous")

        stop_row = stop_rows[0] if stop_rows else None
        take_profit_row = take_profit_rows[0] if take_profit_rows else None
        stop_order_id = (
            None if stop_row is None else self._ib_evidence_order_id(stop_row)
        )
        take_profit_order_id = (
            None
            if take_profit_row is None
            else self._ib_evidence_order_id(take_profit_row)
        )
        return {
            "stop_loss_order_id": stop_order_id,
            "take_profit_order_id": take_profit_order_id,
            "stop_loss": (
                None if stop_row is None else self._ib_evidence_price(stop_row, "STP")
            ),
            "take_profit": (
                None
                if take_profit_row is None
                else self._ib_evidence_price(take_profit_row, "LMT")
            ),
        }

    def _adopt_legacy_pending_ib_manual_opens(
        self,
        evidence_snapshot: dict[str, Any],
    ) -> list[int]:
        """Adopt pre-RoadMap91 timeout Opens only when evidence is unique."""
        orphan_rows = self.repository.get_orphan_ib_manual_market_order_plans()

        if not orphan_rows:
            return []

        known_order_ids = self.repository.get_known_ib_broker_order_ids()
        adopted: list[int] = []
        execution_rows = list(evidence_snapshot.get("executions") or [])
        completed_rows = list(evidence_snapshot.get("completed_orders") or [])
        current_client_id = self._optional_positive_order_id(
            evidence_snapshot.get("current_client_id")
        )

        for orphan in orphan_rows:
            account_id = str(orphan.get("account_id") or "").strip()
            symbol_name = (
                str(orphan.get("symbol") or "")
                .strip()
                .upper()
                .replace(".", "")
                .replace("/", "")
            )
            side = str(orphan.get("side") or "").strip().upper()
            quantity = abs(float(orphan.get("volume") or 0.0))
            grouped: dict[int, list[dict[str, Any]]] = {}

            for execution in execution_rows:
                order_id = self._ib_evidence_order_id(execution)

                if order_id is None or order_id in known_order_ids:
                    continue

                if str(execution.get("account") or "").strip() != account_id:
                    continue

                if self._ib_evidence_symbol(execution) != symbol_name:
                    continue

                if self._ib_evidence_side(execution.get("side")) != side:
                    continue

                grouped.setdefault(order_id, []).append(execution)

            candidates = []

            for order_id, rows in grouped.items():
                completed_candidates = [
                    row
                    for row in completed_rows
                    if self._ib_evidence_order_id(row) == order_id
                    and str(row.get("account") or "").strip() == account_id
                    and self._ib_evidence_symbol(row) == symbol_name
                    and self._ib_evidence_side(row.get("action")) == side
                    and bool(row.get("same_client_id"))
                    and (
                        current_client_id is None
                        or self._optional_positive_order_id(row.get("client_id"))
                        == current_client_id
                    )
                    and (
                        str(row.get("order_ref") or "")
                        .strip()
                        .upper()
                        .startswith("LGE")
                        or get_broker_order_control_mode(row.get("order_ref"))
                        is not None
                    )
                ]

                if len(completed_candidates) != 1:
                    continue

                executed_quantity = sum(self._ib_evidence_quantity(row) for row in rows)

                if math.isclose(
                    executed_quantity,
                    quantity,
                    rel_tol=1e-9,
                    abs_tol=0.01,
                ):
                    candidates.append((order_id, completed_candidates[0]))

            if len(candidates) != 1:
                continue

            order_id, completed_parent_row = candidates[0]
            broker_comment = str(completed_parent_row.get("order_ref") or "").strip()
            children = self._infer_pending_open_children(
                parent_order_id=order_id,
                account_id=account_id,
                symbol_name=symbol_name,
                side=side,
                quantity=quantity,
                evidence_snapshot=evidence_snapshot,
            )
            broker_order_uid = self.repository.create_broker_order(
                trade_uid=str(orphan.get("trade_uid") or "").strip(),
                order_plan_uid=str(orphan.get("order_plan_uid") or "").strip(),
                broker="IB",
                broker_order_id=str(order_id),
                execution_status=IB_MANUAL_OPEN_EXECUTION_STATUS_PENDING,
                source=str(orphan.get("source") or "MANUAL"),
                broker_comment=broker_comment,
            )
            self.repository.create_pending_ib_manual_open(
                trade_uid=str(orphan.get("trade_uid") or "").strip(),
                order_plan_uid=str(orphan.get("order_plan_uid") or "").strip(),
                broker_order_uid=broker_order_uid,
                broker_order_id=order_id,
                account_id=account_id,
                symbol=symbol_name,
                side=side,
                quantity=quantity,
                stop_loss_order_id=children["stop_loss_order_id"],
                take_profit_order_id=children["take_profit_order_id"],
                stop_loss=children["stop_loss"],
                take_profit=children["take_profit"],
                client_id=evidence_snapshot.get("current_client_id"),
                comment=broker_comment or "[LGE:M] Legacy delayed IB manual Open",
                last_error="Adopted from unique exact execution evidence",
            )
            known_order_ids.add(order_id)
            adopted.append(order_id)

        return adopted

    def _build_recovered_ib_manual_open_result(
        self,
        pending: dict[str, Any],
        evidence_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """Build broker_result for one delayed Open from exact evidence."""
        order_id = self._optional_positive_order_id(pending.get("broker_order_id"))

        if order_id is None:
            raise RuntimeError("Delayed IB Open order id is invalid")

        account_id = str(pending.get("account_id") or "").strip()
        symbol_name = (
            str(pending.get("symbol") or "")
            .strip()
            .upper()
            .replace(".", "")
            .replace("/", "")
        )
        side = str(pending.get("side") or "").strip().upper()
        quantity = abs(float(pending.get("quantity") or 0.0))
        executions = [
            row
            for row in evidence_snapshot.get("executions") or []
            if self._ib_evidence_order_id(row) == order_id
            and str(row.get("account") or "").strip() == account_id
            and self._ib_evidence_symbol(row) == symbol_name
            and self._ib_evidence_side(row.get("side")) == side
        ]

        if not executions:
            raise RuntimeError(f"Delayed IB Open execution was not found: {order_id}")

        filled = sum(self._ib_evidence_quantity(row) for row in executions)

        if not math.isclose(
            filled,
            quantity,
            rel_tol=1e-9,
            abs_tol=0.01,
        ):
            raise RuntimeError("Delayed IB Open execution quantity differs")

        price_numerator = sum(
            self._ib_evidence_quantity(row) * float(row.get("price") or 0.0)
            for row in executions
        )
        avg_fill_price = price_numerator / filled

        if avg_fill_price <= 0.0:
            raise RuntimeError("Delayed IB Open fill price is invalid")

        current_client_id = self._optional_positive_order_id(
            evidence_snapshot.get("current_client_id")
        )
        pending_client_id = self._optional_positive_order_id(pending.get("client_id"))

        if pending_client_id is not None and current_client_id != pending_client_id:
            raise RuntimeError("Delayed IB Open client identity differs")

        stop_loss_order_id = self._optional_positive_order_id(
            pending.get("stop_loss_order_id")
        )
        take_profit_order_id = self._optional_positive_order_id(
            pending.get("take_profit_order_id")
        )
        expected_child_ids = {
            value
            for value in (stop_loss_order_id, take_profit_order_id)
            if value is not None
        }
        open_order_ids = {
            order_id_value
            for row in evidence_snapshot.get("open_orders") or []
            if (order_id_value := self._ib_evidence_order_id(row)) is not None
        }

        if not expected_child_ids.issubset(open_order_ids):
            raise RuntimeError(
                "Delayed IB Open protective order evidence is incomplete"
            )

        return {
            "broker": "IB",
            "order_id": str(order_id),
            "broker_order_id": str(order_id),
            "parent_order_id": str(order_id),
            "child_order_ids": [str(value) for value in sorted(expected_child_ids)],
            "stop_loss_order_id": (
                None if stop_loss_order_id is None else str(stop_loss_order_id)
            ),
            "take_profit_order_id": (
                None if take_profit_order_id is None else str(take_profit_order_id)
            ),
            "current_client_id": current_client_id,
            "symbol_name": symbol_name,
            "side": side,
            "quantity": quantity,
            "status": "FILLED",
            "filled": filled,
            "remaining": 0.0,
            "avg_fill_price": avg_fill_price,
            "stop_loss": pending.get("stop_loss"),
            "take_profit": pending.get("take_profit"),
            "control_mode": (
                get_broker_order_control_mode(pending.get("comment"))
                or ORDER_CONTROL_MODE_MANUAL
            ),
            "display_comment": strip_broker_order_identity(pending.get("comment")),
            "broker_comment": str(pending.get("comment") or "").strip(),
        }

    def _recover_pending_ib_manual_open_row(
        self,
        pending: dict[str, Any],
        evidence_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """Recover one exact delayed IB manual Open idempotently."""
        trade_uid = str(pending.get("trade_uid") or "").strip()
        broker_order_uid = str(pending.get("broker_order_uid") or "").strip()
        broker_result = self._build_recovered_ib_manual_open_result(
            pending,
            evidence_snapshot,
        )
        account_id = str(pending.get("account_id") or "").strip()
        symbol_name = str(pending.get("symbol") or "").strip().upper()
        side = str(pending.get("side") or "").strip().upper()
        quantity = abs(float(pending.get("quantity") or 0.0))
        broker_position_id = f"IB:{account_id}:{symbol_name}"
        position_row = self.repository.get_position_by_trade_uid(trade_uid)

        if position_row is None:
            opened_utc = next(
                (
                    str(row.get("time") or "").strip()
                    for row in evidence_snapshot.get("executions") or []
                    if self._ib_evidence_order_id(row)
                    == int(broker_result["parent_order_id"])
                    and str(row.get("time") or "").strip()
                ),
                str(evidence_snapshot.get("captured_utc") or "").strip(),
            )
            position_uid = self.repository.create_position(
                trade_uid=trade_uid,
                broker_order_uid=broker_order_uid,
                broker="IB",
                broker_position_id=broker_position_id,
                symbol=symbol_name,
                side=side,
                volume=quantity,
                open_price=float(broker_result["avg_fill_price"]),
                opened_utc=opened_utc or None,
                state="OPEN",
                source="BROKER",
            )
        else:
            position_uid = str(position_row.get("position_uid") or "").strip()

        persisted_leg = self.repository.get_ib_virtual_position_leg(position_uid)
        leg_persistence = None

        if persisted_leg is None:
            matched_position = BrokerPosition(
                broker="IB",
                account_id=account_id,
                account_mode=str(self.context.account_mode or "DEMO"),
                position_id=broker_position_id,
                symbol_name=symbol_name,
                side=side,
                volume=quantity,
                entry_price=float(broker_result["avg_fill_price"]),
                opened_utc=str(
                    position_row.get("opened_utc") if position_row is not None else ""
                ),
            )
            leg_persistence = self._persist_new_ib_virtual_position_leg(
                position_uid=position_uid,
                trade_uid=trade_uid,
                account_id=account_id,
                matched_position=matched_position,
                broker_result=broker_result,
                evidence_snapshot=evidence_snapshot,
            )

        self.repository.update_broker_order_execution_status(
            broker_order_uid=broker_order_uid,
            execution_status="FILLED",
        )
        self.repository.resolve_pending_ib_manual_open(trade_uid)
        return {
            "trade_uid": trade_uid,
            "order_plan_uid": str(pending.get("order_plan_uid") or "").strip(),
            "broker_order_uid": broker_order_uid,
            "position_uid": position_uid,
            "broker_result": broker_result,
            "virtual_leg_persistence_status": IB_LEG_PERSISTENCE_STATUS_RECONCILED,
            "virtual_leg_persistence": leg_persistence,
            "virtual_leg_persistence_error": "",
            "automatic_timeout_recovery": True,
        }

    def recover_pending_ib_manual_market_order_opens(
        self,
    ) -> dict[str, Any]:
        """Recover exact delayed manual Opens before a normal UI Refresh."""
        if self.get_active_broker() != "IB":
            return {
                "pending": 0,
                "adopted": [],
                "recovered": [],
                "unresolved": [],
            }

        if self.ib_runtime_service is None:
            raise RuntimeError("IB runtime service is not set")

        pending_before = self.repository.get_pending_ib_manual_opens()
        orphan_rows = self.repository.get_orphan_ib_manual_market_order_plans()

        if not pending_before and not orphan_rows:
            return {
                "pending": 0,
                "adopted": [],
                "recovered": [],
                "unresolved": [],
            }

        evidence_snapshot = self.get_ib_virtual_position_leg_evidence_snapshot()
        adopted = self._adopt_legacy_pending_ib_manual_opens(evidence_snapshot)
        pending_rows = self.repository.get_pending_ib_manual_opens()
        recovered: list[int] = []
        unresolved: list[dict[str, Any]] = []

        for pending in pending_rows:
            order_id = self._optional_positive_order_id(pending.get("broker_order_id"))

            try:
                self._recover_pending_ib_manual_open_row(
                    pending,
                    evidence_snapshot,
                )
            except RuntimeError as error:
                self.repository.update_pending_ib_manual_open_attempt(
                    str(pending.get("trade_uid") or ""),
                    str(error),
                )
                unresolved.append(
                    {
                        "trade_uid": pending.get("trade_uid"),
                        "order_id": order_id,
                        "error": str(error),
                    }
                )
            else:
                if order_id is not None:
                    recovered.append(order_id)

        if recovered:
            logger.warning(
                "Recovered pending IB manual Open operations during " "Refresh: %s",
                recovered,
            )

        return {
            "pending": len(pending_rows),
            "adopted": adopted,
            "recovered": recovered,
            "unresolved": unresolved,
        }

    def _recover_ib_manual_open_after_timeout(
        self,
        *,
        trade_uid: str,
        order_plan_uid: str,
        account_id: str,
        timeout_error: IBMarketOrderTimeoutError,
    ) -> dict[str, Any]:
        """Save exact delayed Open identity and recover without duplication."""
        order_id = self._optional_positive_order_id(timeout_error.order_id)

        if order_id is None:
            raise RuntimeError("Timed-out IB Open order id is invalid")

        timeout_control_mode = (
            get_broker_order_control_mode(timeout_error.comment)
            or ORDER_CONTROL_MODE_MANUAL
        )
        broker_order_uid = self.repository.create_broker_order(
            trade_uid=trade_uid,
            order_plan_uid=order_plan_uid,
            broker="IB",
            broker_order_id=str(order_id),
            execution_status=IB_MANUAL_OPEN_EXECUTION_STATUS_PENDING,
            source=timeout_control_mode,
            broker_comment=timeout_error.comment,
        )
        self.repository.create_pending_ib_manual_open(
            trade_uid=trade_uid,
            order_plan_uid=order_plan_uid,
            broker_order_uid=broker_order_uid,
            broker_order_id=order_id,
            account_id=account_id,
            symbol=timeout_error.symbol_name,
            side=timeout_error.side,
            quantity=timeout_error.quantity,
            stop_loss_order_id=timeout_error.stop_loss_order_id,
            take_profit_order_id=timeout_error.take_profit_order_id,
            stop_loss=timeout_error.stop_loss,
            take_profit=timeout_error.take_profit,
            client_id=timeout_error.current_client_id,
            comment=timeout_error.comment,
            last_error=str(timeout_error),
        )
        last_error = str(timeout_error)

        for attempt in range(
            1,
            IB_MANUAL_OPEN_TIMEOUT_RECOVERY_ATTEMPTS + 1,
        ):
            pending = next(
                (
                    row
                    for row in self.repository.get_pending_ib_manual_opens()
                    if str(row.get("trade_uid") or "") == trade_uid
                ),
                None,
            )

            if pending is None:
                raise RuntimeError("Pending IB Open persistence was lost")

            try:
                evidence_snapshot = self.get_ib_virtual_position_leg_evidence_snapshot()
                recovered = self._recover_pending_ib_manual_open_row(
                    pending,
                    evidence_snapshot,
                )
            except RuntimeError as error:
                last_error = str(error)
                self.repository.update_pending_ib_manual_open_attempt(
                    trade_uid,
                    last_error,
                )
            else:
                recovered["timeout_recovery_attempts"] = attempt
                return recovered

            if attempt < IB_MANUAL_OPEN_TIMEOUT_RECOVERY_ATTEMPTS:
                time.sleep(IB_MANUAL_OPEN_TIMEOUT_RECOVERY_DELAY_SECONDS)

        raise IBManualOpenConfirmationPendingError(
            trade_uid=trade_uid,
            order_id=order_id,
            details=last_error,
        ) from timeout_error

    def _place_manual_market_order_ib(
        self,
        symbol_name: str,
        side: str,
        lots: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual order",
        control_mode: str = ORDER_CONTROL_MODE_MANUAL,
    ) -> dict:
        """
        Відкрити manual MARKET order через IB Paper.
        """

        service = self.ib_runtime_service

        if service is None:
            raise RuntimeError("IB runtime service is not set")

        account_state = service.get_account_state()
        account_id = str(account_state.account_id or "").strip()

        if not account_id:
            account_id = "UNKNOWN"

        pending_opens = self.repository.get_pending_ib_manual_opens()

        if pending_opens:
            self.recover_pending_ib_manual_market_order_opens()
            pending_opens = self.repository.get_pending_ib_manual_opens()

        if pending_opens:
            pending = pending_opens[0]
            raise IBManualOpenConfirmationPendingError(
                trade_uid=str(pending.get("trade_uid") or ""),
                order_id=int(pending.get("broker_order_id") or 0),
                details=str(pending.get("last_error") or ""),
            )

        side_norm = str(side).strip().upper()
        symbol_norm = str(symbol_name).strip().upper()
        lots_float = float(lots)
        quantity_float = self._ib_lots_to_fx_quantity(lots_float)
        control_mode_norm = normalize_order_control_mode(control_mode)

        self._assert_ib_fx_execution_safe(
            account_id=account_id,
            symbol_name=symbol_norm,
        )

        display_comment = strip_broker_order_identity(comment)
        broker_comment = build_broker_order_comment(
            display_comment,
            control_mode_norm,
        )

        trade_uid = self.repository.create_trade(
            broker="IB",
            account_id=account_id,
            symbol=symbol_norm,
            side=side_norm,
            volume=quantity_float,
            source=control_mode_norm,
            comment=display_comment,
        )

        order_plan_uid = self.repository.create_order_plan(
            trade_uid=trade_uid,
            order_type="MARKET",
            side=side_norm,
            volume=quantity_float,
            source=control_mode_norm,
        )

        try:
            positions_before = service.get_positions()
        except Exception:  # noqa
            positions_before = []

        try:
            broker_result = service.place_market_order(
                symbol_name=symbol_norm,
                side=side_norm,
                quantity=quantity_float,
                stop_loss=stop_loss,
                take_profit=take_profit,
                comment=broker_comment,
            )
        except IBMarketOrderTimeoutError as error:
            return self._recover_ib_manual_open_after_timeout(
                trade_uid=trade_uid,
                order_plan_uid=order_plan_uid,
                account_id=account_id,
                timeout_error=error,
            )

        broker_order_id = self._extract_broker_order_id(broker_result)
        execution_status = str(broker_result.get("status") or "FILLED")

        broker_order_uid = self.repository.create_broker_order(
            trade_uid=trade_uid,
            order_plan_uid=order_plan_uid,
            broker="IB",
            broker_order_id=broker_order_id,
            execution_status=execution_status,
            broker_timestamp=None,
            source=control_mode_norm,
            broker_comment=broker_comment,
        )

        position_uid = ""
        leg_persistence_status = IB_LEG_PERSISTENCE_STATUS_NOT_CREATED
        leg_persistence: dict[str, Any] | None = None
        leg_persistence_error = ""

        try:
            positions_after = service.get_positions()
        except Exception:  # noqa
            positions_after = []

        matched_position = self._find_ib_opened_manual_position(
            positions_before=positions_before,
            positions_after=positions_after,
            symbol_norm=symbol_norm,
            side_norm=side_norm,
            quantity_float=quantity_float,
        )

        if matched_position is not None:
            position_uid = self.repository.create_position(
                trade_uid=trade_uid,
                broker_order_uid=broker_order_uid,
                broker="IB",
                broker_position_id=matched_position.position_id,
                symbol=matched_position.symbol_name,
                side=matched_position.side,
                volume=matched_position.volume,
                open_price=matched_position.entry_price,
                opened_utc=matched_position.opened_utc or None,
                state="OPEN",
                source="BROKER",
            )

            try:
                leg_persistence = self._persist_new_ib_virtual_position_leg(
                    position_uid=position_uid,
                    trade_uid=trade_uid,
                    account_id=account_id,
                    matched_position=matched_position,
                    broker_result=broker_result,
                )
                leg_persistence_status = IB_LEG_PERSISTENCE_STATUS_RECONCILED
            except Exception as exc:  # noqa
                leg_persistence_status = IB_LEG_PERSISTENCE_STATUS_ERROR
                leg_persistence_error = str(exc)
                logger.exception(
                    "IB order filled, but virtual-leg persistence failed. "
                    "position_uid=%s parent_order_id=%s",
                    position_uid,
                    broker_order_id,
                )

        return {
            "trade_uid": trade_uid,
            "order_plan_uid": order_plan_uid,
            "broker_order_uid": broker_order_uid,
            "position_uid": position_uid,
            "broker_result": broker_result,
            "virtual_leg_persistence_status": leg_persistence_status,
            "virtual_leg_persistence": leg_persistence,
            "virtual_leg_persistence_error": leg_persistence_error,
            "control_mode": control_mode_norm,
            "display_comment": display_comment,
            "broker_comment": broker_comment,
        }

    def place_manual_market_order(
        self,
        symbol_name: str,
        side: str,
        lots: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual order",
        control_mode: str = ORDER_CONTROL_MODE_MANUAL,
    ) -> dict:
        """
        Відкрити manual MARKET order через активний Runtime broker.

        RoadMap82/RoadMap83:
        cTrader chain:
        Trade -> OrderPlan -> BrokerOrder -> Position

        RoadMap84:
        IB Paper chain:
        Trade -> OrderPlan -> BrokerOrder -> Position
        через quantity delta matching.
        """
        broker = self.get_active_broker()

        if broker == "IB":
            return self._place_manual_market_order_ib(
                symbol_name=symbol_name,
                side=side,
                lots=lots,
                stop_loss=stop_loss,
                take_profit=take_profit,
                comment=comment,
                control_mode=control_mode,
            )

        if broker != "CTRADER":
            raise RuntimeError(f"Manual MARKET order is not supported: {broker}")

        service = self.ctrader_runtime_service

        if service is None:
            raise RuntimeError("cTrader runtime service is not set")

        account_state = service.get_account_state()
        account_id = str(account_state.account_id or "").strip()

        if not account_id:
            account_id = "UNKNOWN"

        side_norm = str(side).strip().upper()
        symbol_norm = str(symbol_name).strip().upper()
        lots_float = float(lots)
        control_mode_norm = normalize_order_control_mode(control_mode)
        display_comment = strip_broker_order_identity(comment)
        broker_comment = build_broker_order_comment(
            display_comment,
            control_mode_norm,
        )

        trade_uid = self.repository.create_trade(
            broker=broker,
            account_id=account_id,
            symbol=symbol_norm,
            side=side_norm,
            volume=lots_float,
            source=control_mode_norm,
            comment=display_comment,
        )

        order_plan_uid = self.repository.create_order_plan(
            trade_uid=trade_uid,
            order_type="MARKET",
            side=side_norm,
            volume=lots_float,
            source=control_mode_norm,
        )

        try:
            positions_before = service.get_positions()
        except Exception:  # noqa
            positions_before = []

        broker_result = service.place_market_order(
            symbol_name=symbol_norm,
            side=side_norm,
            lots=lots_float,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment=broker_comment,
        )

        broker_order_id = self._extract_broker_order_id(broker_result)

        broker_order_uid = self.repository.create_broker_order(
            trade_uid=trade_uid,
            order_plan_uid=order_plan_uid,
            broker=broker,
            broker_order_id=broker_order_id,
            execution_status="FILLED",
            broker_timestamp=None,
            source=control_mode_norm,
            broker_comment=broker_comment,
        )

        position_uid = ""

        try:
            positions_after = service.get_positions()
        except Exception:  # noqa
            positions_after = []

        matched_position = self._find_opened_manual_position(
            positions_before=positions_before,
            positions_after=positions_after,
            broker_result=broker_result,
            symbol_norm=symbol_norm,
            side_norm=side_norm,
            lots_float=lots_float,
        )

        if matched_position is not None:
            position_uid = self.repository.create_position(
                trade_uid=trade_uid,
                broker_order_uid=broker_order_uid,
                broker=broker,
                broker_position_id=matched_position.position_id,
                symbol=matched_position.symbol_name,
                side=matched_position.side,
                volume=matched_position.volume,
                open_price=matched_position.entry_price,
                opened_utc=matched_position.opened_utc or None,
                state="OPEN",
                source="BROKER",
            )

        return {
            "trade_uid": trade_uid,
            "order_plan_uid": order_plan_uid,
            "broker_order_uid": broker_order_uid,
            "position_uid": position_uid,
            "broker_result": broker_result,
            "control_mode": control_mode_norm,
            "display_comment": display_comment,
            "broker_comment": broker_comment,
        }

    @staticmethod
    def _normalize_optional_protection_price(
        value: float | None,
        field_name: str,
    ) -> float | None:
        """
        Нормалізувати optional SL/TP price.

        None означає видалення відповідного захисного рівня.
        """
        if value is None:
            return None

        price = float(value)

        if price <= 0.0:
            raise ValueError(f"{field_name} must be positive")

        return price

    def modify_active_broker_position_sl_tp(
        self,
        broker_position_id: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        """
        Змінити SL/TP відкритої position через активного broker.

        RoadMap87:
        OrdersPage
          -> RuntimeEngine
          -> RuntimeService
          -> SessionManager
          -> Adapter
          -> Broker API
        """
        broker = self.get_active_broker()

        if broker == "CTRADER":
            service = self.ctrader_runtime_service

            if service is None:
                raise RuntimeError("cTrader runtime service is not set")
        elif broker == "IB":
            service = self.ib_runtime_service

            if service is None:
                raise RuntimeError("IB runtime service is not set")
        else:
            raise RuntimeError(f"Modify position SL/TP is not supported: {broker}")

        position_id_clean = str(broker_position_id or "").strip()

        if not position_id_clean:
            raise ValueError("Broker position id is empty")

        stop_loss_value = self._normalize_optional_protection_price(
            stop_loss,
            field_name="Stop Loss",
        )
        take_profit_value = self._normalize_optional_protection_price(
            take_profit,
            field_name="Take Profit",
        )

        positions = self.get_active_broker_positions()

        selected_position = next(
            (
                position
                for position in positions
                if self._get_position_id_text(position) == position_id_clean
            ),
            None,
        )

        if selected_position is None:
            raise RuntimeError("Selected broker position was not found")

        side = str(getattr(selected_position, "side", "") or "").strip().upper()

        if stop_loss_value is not None and take_profit_value is not None:
            if side == "BUY" and stop_loss_value >= take_profit_value:
                raise ValueError("BUY position requires Stop Loss < Take Profit")

            if side == "SELL" and stop_loss_value <= take_profit_value:
                raise ValueError("SELL position requires Stop Loss > Take Profit")

            if side not in {"BUY", "SELL"}:
                raise ValueError(f"Unsupported position side: {side!r}")

        broker_result = service.modify_position_sl_tp(
            position_id=position_id_clean,
            stop_loss=stop_loss_value,
            take_profit=take_profit_value,
        )

        return {
            "broker": broker,
            "broker_position_id": position_id_clean,
            "side": side,
            "stop_loss": stop_loss_value,
            "take_profit": take_profit_value,
            "broker_result": broker_result,
        }

    def _close_active_broker_position_ib(
        self,
        broker_position_id: str,
        lots: float | None = None,
    ) -> dict:
        """
        Закрити IB broker position через протилежний MARKET order.

        Для IB:
        - broker_position_id = IB:<account_id>:<symbol>
        - close виконується не через positionId, а через opposite MARKET order.
        """
        service = self.ib_runtime_service

        if service is None:
            raise RuntimeError("IB runtime service is not set")

        position_id_clean = str(broker_position_id or "").strip()

        if not position_id_clean:
            raise ValueError("Broker position id is empty")

        runtime_position = self.repository.get_open_position_by_broker_position_id(
            broker="IB",
            broker_position_id=position_id_clean,
        )

        close_quantity = None

        if lots is not None:
            close_quantity = self._ib_lots_to_fx_quantity(float(lots))

        broker_result = service.close_position(
            position_id=position_id_clean,
            quantity=close_quantity,
            comment="LGE manual close",
        )

        try:
            positions_after = service.get_positions()
        except Exception:  # noqa
            positions_after = []

        still_open = any(
            self._get_position_id_text(position) == position_id_clean
            for position in positions_after
        )

        broker_order_uid = ""
        db_rows_updated = 0

        if runtime_position is not None:
            trade_uid = str(runtime_position["trade_uid"])

            close_volume = float(runtime_position["volume"])

            if close_quantity is not None:
                close_volume = float(close_quantity)

            order_plan_uid = self.repository.create_order_plan(
                trade_uid=trade_uid,
                order_type="CLOSE_MARKET",
                side=str(broker_result.get("close_side") or ""),
                volume=close_volume,
                source="MANUAL",
            )

            nested_result = broker_result.get("broker_result") or {}
            broker_order_id = self._extract_broker_order_id(nested_result)

            broker_order_uid = self.repository.create_broker_order(
                trade_uid=trade_uid,
                order_plan_uid=order_plan_uid,
                broker="IB",
                broker_order_id=broker_order_id,
                execution_status="FILLED",
                broker_timestamp=None,
                source="MANUAL",
                broker_comment=str(nested_result.get("broker_comment") or "").strip(),
            )

            if not still_open:
                db_rows_updated = (
                    self.repository.mark_position_closed_by_broker_position_id(
                        broker="IB",
                        broker_position_id=position_id_clean,
                    )
                )

        return {
            "broker_position_id": position_id_clean,
            "broker_order_uid": broker_order_uid,
            "closed": not still_open,
            "db_rows_updated": db_rows_updated,
            "broker_result": broker_result,
        }

    def close_active_broker_position(
        self,
        broker_position_id: str,
        lots: float | None = None,
    ) -> dict:
        """
        Закрити broker position через активний Runtime broker.
        """
        broker = self.get_active_broker()

        if broker == "IB":
            return self._close_active_broker_position_ib(
                broker_position_id=broker_position_id,
                lots=lots,
            )

        if broker != "CTRADER":
            raise RuntimeError(f"Close position is not supported: {broker}")

        service = self.ctrader_runtime_service

        if service is None:
            raise RuntimeError("cTrader runtime service is not set")

        position_id_clean = str(broker_position_id or "").strip()

        if not position_id_clean:
            raise ValueError("Broker position id is empty")

        runtime_position = self.repository.get_open_position_by_broker_position_id(
            broker=broker,
            broker_position_id=position_id_clean,
        )

        broker_result = service.close_position(
            position_id=position_id_clean,
            lots=lots,
        )

        try:
            positions_after = service.get_positions()
        except Exception:  # noqa
            positions_after = []

        still_open = any(
            self._get_position_id_text(position) == position_id_clean
            for position in positions_after
        )

        broker_order_uid = ""
        db_rows_updated = 0

        if runtime_position is not None:
            trade_uid = str(runtime_position["trade_uid"])
            close_volume = float(runtime_position["volume"])

            if lots is not None:
                close_volume = float(lots)

            order_plan_uid = self.repository.create_order_plan(
                trade_uid=trade_uid,
                order_type="CLOSE_MARKET",
                side=str(runtime_position["side"]),
                volume=close_volume,
                source="MANUAL",
            )

            broker_order_id = self._extract_broker_order_id(broker_result)

            broker_comment = ""

            if isinstance(broker_result, dict):
                broker_comment = str(broker_result.get("broker_comment") or "").strip()

            broker_order_uid = self.repository.create_broker_order(
                trade_uid=trade_uid,
                order_plan_uid=order_plan_uid,
                broker=broker,
                broker_order_id=broker_order_id,
                execution_status="FILLED",
                broker_timestamp=None,
                source="MANUAL",
                broker_comment=broker_comment,
            )

            if not still_open:
                db_rows_updated = (
                    self.repository.mark_position_closed_by_broker_position_id(
                        broker=broker,
                        broker_position_id=position_id_clean,
                    )
                )

        return {
            "broker_position_id": position_id_clean,
            "broker_order_uid": broker_order_uid,
            "closed": not still_open,
            "db_rows_updated": db_rows_updated,
            "broker_result": broker_result,
        }
