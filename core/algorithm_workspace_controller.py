# core/algorithm_workspace_controller.py — controller algorithm WSP
# -*- coding: utf-8 -*-
"""Координатор algorithm workspace без прямого доступу до broker API.

Controller створює WSP і делегує lifecycle/Replay/chart операції
WorkspaceRuntime без обходу RuntimeEngine/BrokerRuntimeService. RoadMap100
додає окремий Replay-only шлях для manual SL/TP modification та керування
``Крок``/``Тік`` у multi-resolution Replay. UI передає position id, нову ціну
або команду stepping controller-у, а paused-state, M1 chronology і virtual
execution перевіряє WorkspaceRuntime. Broker adapters з цих шляхів не
викликаються. Broker-history progress передається через neutral callback.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from datetime import datetime
from typing import Any

from engine.ctrader_history import CTraderHistoryProgressCallback
from engine.ib_history import IBHistoryProgressCallback
from engine.runtime_constants import WORKSPACE_REPLAY_SOURCE_CSV

from core.algorithm_workspace import (
    WORKSPACE_CONTROL_MODE_SEMI,
    WORKSPACE_DATA_MODE_BROKER,
    WORKSPACE_STATE_RESTORED,
    WORKSPACE_STATE_STOPPED,
    AlgorithmWorkspace,
)
from core.session_repository import SessionRepository
from core.workspace_algorithm import WorkspaceAlgorithm
from core.workspace_chart import WorkspaceChartSnapshot
from core.workspace_close_guard import WorkspaceCloseGuardResult
from core.workspace_history_download_settings import (
    WorkspaceHistoryDownloadSettings,
)
from core.workspace_broker_market import (
    RuntimeEngineWorkspaceMarketProvider,
)
from core.workspace_history_export import (
    WorkspaceHistoryCsvExportResult,
    WorkspaceHistoryCsvWriter,
)
from core.workspace_market_event import WorkspaceMarketEvent
from core.workspace_ownership import (
    WorkspaceOrderSnapshot,
    WorkspaceOwnedSnapshot,
    WorkspacePositionSnapshot,
)
from core.workspace_parameter_adapter import (
    WORKSPACE_ALGORITHM_PARAMETER_ADAPTER,
)
from core.workspace_parameters import WorkspaceAlgorithmParameters
from core.workspace_profit_guard import WorkspaceProfitProtectionDecision
from core.workspace_replay_settings import WorkspaceReplaySettings
from core.workspace_runtime import WorkspaceRuntime, WorkspaceRuntimeError


class WorkspaceLayoutLockedError(RuntimeError):
    """Зміна workspace заборонена замком середовища."""


class AlgorithmWorkspaceController:
    """Координує model і SessionRepository."""

    def __init__(
        self,
        repository: SessionRepository | None = None,
        algorithm_factory: Callable[[str], WorkspaceAlgorithm] | None = None,
    ) -> None:
        self.repository = repository or SessionRepository()
        self._algorithm_factory = algorithm_factory
        self._runtime_engine: Any | None = None
        self._broker_market_provider: RuntimeEngineWorkspaceMarketProvider | None = None
        self._runtimes: dict[str, WorkspaceRuntime] = {}

    def set_runtime_engine(self, runtime_engine: Any | None) -> None:
        """Attach the shared engine used by read-only broker WSP feeds."""
        self._runtime_engine = runtime_engine
        self._broker_market_provider = (
            RuntimeEngineWorkspaceMarketProvider(runtime_engine)
            if runtime_engine is not None
            else None
        )
        for runtime in self._runtimes.values():
            runtime.set_broker_market_provider(self._broker_market_provider)

    def advance_workspace_broker_market(
        self,
        workspace_uid: str,
    ) -> WorkspaceMarketEvent | None:
        """Poll one changed Live Read-only event for the selected WSP."""
        runtime = self.ensure_workspace_runtime(workspace_uid)
        return runtime.advance_broker_market()

    def restore_workspaces(self) -> list[AlgorithmWorkspace]:
        """Відновити workspaces; кожен буде у стані RESTORED."""
        return self.repository.load_ordered_workspaces()

    def ensure_workspace_runtime(
        self,
        workspace_uid: str,
    ) -> WorkspaceRuntime:
        """Return one volatile runtime instance for the requested WSP."""
        runtime = self._runtimes.get(workspace_uid)
        if runtime is not None:
            return runtime

        workspace = self.repository.load_workspace(workspace_uid)
        runtime = self._build_workspace_runtime(workspace)
        self._runtimes[workspace.workspace_uid] = runtime
        return runtime

    def attach_workspace_runtime(
        self,
        workspace: AlgorithmWorkspace,
    ) -> WorkspaceRuntime:
        """Create a runtime from an already loaded/new workspace model."""
        runtime = self._runtimes.get(workspace.workspace_uid)
        if runtime is not None:
            return runtime
        runtime = self._build_workspace_runtime(workspace)
        self._runtimes[workspace.workspace_uid] = runtime
        return runtime

    def workspace_runtime(self, workspace_uid: str) -> WorkspaceRuntime | None:
        """Return the existing runtime without creating it."""
        return self._runtimes.get(workspace_uid)

    def _build_workspace_runtime(
        self,
        workspace: AlgorithmWorkspace,
    ) -> WorkspaceRuntime:
        """Create one volatile runtime and finish safe Session restore."""
        runtime = WorkspaceRuntime(
            workspace,
            algorithm_factory=self._algorithm_factory,
            broker_market_provider=self._broker_market_provider,
        )
        runtime.complete_restore()
        return runtime

    def begin_workspace_runtime_start(
        self,
        workspace_uid: str,
    ) -> WorkspaceRuntime:
        runtime = self.ensure_workspace_runtime(workspace_uid)
        runtime.begin_start()
        return runtime

    def complete_workspace_runtime_start(
        self,
        workspace_uid: str,
    ) -> WorkspaceRuntime:
        runtime = self.ensure_workspace_runtime(workspace_uid)
        runtime.complete_start()
        return runtime

    def begin_workspace_runtime_stop(
        self,
        workspace_uid: str,
    ) -> WorkspaceRuntime:
        runtime = self.ensure_workspace_runtime(workspace_uid)
        runtime.begin_stop()
        return runtime

    def complete_workspace_runtime_stop(
        self,
        workspace_uid: str,
    ) -> WorkspaceRuntime:
        runtime = self.ensure_workspace_runtime(workspace_uid)
        runtime.complete_stop()
        return runtime

    def toggle_workspace_replay_pause(self, workspace_uid: str) -> bool:
        runtime = self.ensure_workspace_runtime(workspace_uid)
        return runtime.toggle_replay_pause()

    def modify_workspace_replay_position_protection(
        self,
        workspace_uid: str,
        position_id: str,
        field_name: str,
        price: float,
        *,
        source: str = "CHART_DRAG",
    ) -> WorkspaceOwnedSnapshot:
        """Делегувати manual SL/TP change тільки у WSP Replay runtime."""
        runtime = self.ensure_workspace_runtime(workspace_uid)
        return runtime.modify_replay_position_protection(
            position_id,
            field_name,
            price,
            source=source,
        )

    def step_workspace_replay(
        self,
        workspace_uid: str,
    ) -> WorkspaceMarketEvent | None:
        runtime = self.ensure_workspace_runtime(workspace_uid)
        return runtime.step_replay()

    def step_workspace_replay_strategy_bar(
        self,
        workspace_uid: str,
    ) -> WorkspaceMarketEvent | None:
        """Зробити UI strategy Step із паузою перед M1 execution window."""
        runtime = self.ensure_workspace_runtime(workspace_uid)
        return runtime.step_replay_strategy_bar()

    def step_workspace_replay_tick(
        self,
        workspace_uid: str,
    ) -> WorkspaceMarketEvent | None:
        """Обробити один найдрібніший execution event paused Replay."""
        runtime = self.ensure_workspace_runtime(workspace_uid)
        return runtime.step_replay_tick()

    def set_workspace_replay_speed(
        self,
        workspace_uid: str,
        speed: int,
    ) -> WorkspaceRuntime:
        runtime = self.ensure_workspace_runtime(workspace_uid)
        runtime.set_replay_speed(speed)
        workspace = self.repository.load_workspace(workspace_uid)
        workspace.replay_settings["speed"] = runtime.replay_settings["speed"]
        self.repository.save_workspace(workspace)
        return runtime

    def advance_workspace_replay(
        self,
        workspace_uid: str,
        *,
        max_events: int | None = None,
    ) -> list[WorkspaceMarketEvent]:
        """Advance one bounded UI chunk while preserving configured Replay speed."""
        runtime = self.ensure_workspace_runtime(workspace_uid)
        return runtime.advance_replay(max_events=max_events)

    def workspace_chart_snapshot(
        self,
        workspace_uid: str,
    ) -> WorkspaceChartSnapshot:
        runtime = self.ensure_workspace_runtime(workspace_uid)
        return runtime.chart_snapshot()

    def set_workspace_chart_visible_count(
        self,
        workspace_uid: str,
        visible_count: int,
    ) -> WorkspaceChartSnapshot:
        runtime = self.ensure_workspace_runtime(workspace_uid)
        return runtime.set_chart_visible_count(visible_count)

    def scroll_workspace_chart_to(
        self,
        workspace_uid: str,
        visible_start: int,
    ) -> WorkspaceChartSnapshot:
        runtime = self.ensure_workspace_runtime(workspace_uid)
        return runtime.scroll_chart_to(visible_start)

    def scroll_workspace_chart_to_timestamp(
        self,
        workspace_uid: str,
        timestamp: datetime,
        *,
        exact: bool = True,
    ) -> WorkspaceChartSnapshot:
        """Перейти до signal bar або strategy bar, що містить entry."""
        runtime = self.ensure_workspace_runtime(workspace_uid)
        return runtime.scroll_chart_to_timestamp(timestamp, exact=exact)

    def scroll_workspace_chart_to_latest(
        self,
        workspace_uid: str,
    ) -> WorkspaceChartSnapshot:
        runtime = self.ensure_workspace_runtime(workspace_uid)
        return runtime.scroll_chart_to_latest()

    def set_workspace_runtime_snapshot(
        self,
        workspace_uid: str,
        *,
        active_orders_count: int = 0,
        positions_count: int = 0,
        current_profit: float = 0.0,
        peak_profit: float = 0.0,
    ) -> WorkspaceRuntime:
        runtime = self.ensure_workspace_runtime(workspace_uid)
        runtime.context.set_runtime_snapshot(
            active_orders_count=active_orders_count,
            positions_count=positions_count,
            current_profit=current_profit,
            peak_profit=peak_profit,
        )
        return runtime

    def set_workspace_owned_snapshots(
        self,
        workspace_uid: str,
        *,
        order_rows: Iterable[WorkspaceOrderSnapshot | Mapping[str, Any]],
        position_rows: Iterable[WorkspacePositionSnapshot | Mapping[str, Any]],
    ) -> WorkspaceOwnedSnapshot:
        """Filter shared rows through the exact WSP ownership boundary."""
        runtime = self.ensure_workspace_runtime(workspace_uid)
        return runtime.apply_owned_snapshots(order_rows, position_rows)

    def workspace_profit_protection_decisions(
        self,
        workspace_uid: str,
    ) -> tuple[WorkspaceProfitProtectionDecision, ...]:
        """Return current WSP-local HOLD/CLOSE decisions."""
        runtime = self.ensure_workspace_runtime(workspace_uid)
        return runtime.profit_protection_decisions()

    def workspace_close_guard(
        self,
        workspace_uid: str,
    ) -> WorkspaceCloseGuardResult:
        """Return the exact controller-level WSP close decision."""
        runtime = self.ensure_workspace_runtime(workspace_uid)
        return runtime.close_guard_result()

    def remove_workspace_runtime(self, workspace_uid: str) -> None:
        """Drop volatile WSP state without touching persisted Session data."""
        self._runtimes.pop(workspace_uid, None)

    def clear_workspace_runtimes(self) -> None:
        """Drop all volatile runtimes during a full Session UI restore."""
        self._runtimes.clear()

    def create_workspace(
        self,
        *,
        broker: str,
        account_id: str | None,
        symbol: str,
        timeframe: str,
        algorithm: str,
        display_name: str | None = None,
        data_mode: str = WORKSPACE_DATA_MODE_BROKER,
        account_mode: str | None = None,
        control_mode: str = WORKSPACE_CONTROL_MODE_SEMI,
        parameters: dict[str, Any] | None = None,
        risk_settings: dict[str, Any] | None = None,
        profit_protection: dict[str, Any] | None = None,
        replay_settings: dict[str, Any] | None = None,
        history_download_settings: dict[str, Any] | None = None,
        indicator_profile_bindings: dict[str, Any] | None = None,
        ui_state: dict[str, Any] | None = None,
    ) -> AlgorithmWorkspace:
        """Створити workspace, файл і запис у manifest."""
        manifest = self.repository.load_manifest()
        self._require_unlocked(manifest)

        workspace = AlgorithmWorkspace.create(
            broker=broker,
            account_id=account_id,
            symbol=symbol,
            timeframe=timeframe,
            algorithm=algorithm,
            display_name=display_name,
            data_mode=data_mode,
            account_mode=account_mode,
            control_mode=control_mode,
            parameters=parameters,
            risk_settings=risk_settings,
            profit_protection=profit_protection,
            replay_settings=replay_settings,
            history_download_settings=history_download_settings,
            indicator_profile_bindings=indicator_profile_bindings,
            ui_state=ui_state,
        )
        workspace.display_name = self._make_unique_name(
            workspace.display_name,
            self.restore_workspaces(),
        )

        self.repository.save_workspace(workspace)
        manifest["workspace_order"].append(workspace.workspace_uid)
        manifest["active_workspace_uid"] = workspace.workspace_uid
        self.repository.save_manifest(manifest)
        return workspace

    def rename_workspace(
        self,
        workspace_uid: str,
        display_name: str,
    ) -> AlgorithmWorkspace:
        """Перейменувати workspace до першого Start."""
        manifest = self.repository.load_manifest()
        self._require_unlocked(manifest)

        workspace = self.repository.load_workspace(workspace_uid)
        existing = [
            item
            for item in self.restore_workspaces()
            if item.workspace_uid != workspace.workspace_uid
        ]
        unique_name = self._make_unique_name(display_name.strip(), existing)
        workspace.set_display_name(unique_name)
        self.repository.save_workspace(workspace)
        return workspace

    def load_workspace(self, workspace_uid: str) -> AlgorithmWorkspace:
        """Load one persisted WSP configuration without creating runtime."""
        return self.repository.load_workspace(workspace_uid)

    def update_workspace_parameters(
        self,
        workspace_uid: str,
        values: WorkspaceAlgorithmParameters,
        *,
        schema_updates: Mapping[str, object] | None = None,
        indicator_profile_bindings: Mapping[str, object] | None = None,
    ) -> AlgorithmWorkspace:
        """Persist one WSP parameter set only while its runtime is stopped."""
        runtime = self._runtimes.get(workspace_uid)
        if runtime is not None and runtime.context.runtime_state not in {
            WORKSPACE_STATE_STOPPED,
            WORKSPACE_STATE_RESTORED,
        }:
            raise WorkspaceRuntimeError(
                "Cannot change workspace parameters while runtime is active"
            )

        workspace = self.repository.load_workspace(workspace_uid)
        if schema_updates is None:
            storage = WORKSPACE_ALGORITHM_PARAMETER_ADAPTER.merge_legacy_values(
                workspace,
                values,
            )
        else:
            storage = WORKSPACE_ALGORITHM_PARAMETER_ADAPTER.merge_dialog_values(
                workspace,
                values,
                schema_updates,
            )
        workspace.set_algorithm_configuration(
            parameters=storage.parameters,
            risk_settings=storage.risk_settings,
            profit_protection=storage.profit_protection,
        )
        if indicator_profile_bindings is not None:
            workspace.set_indicator_profile_bindings(dict(indicator_profile_bindings))
        self.repository.save_workspace(workspace)
        self.remove_workspace_runtime(workspace_uid)
        return workspace

    def update_workspace_replay_settings(
        self,
        workspace_uid: str,
        values: WorkspaceReplaySettings,
    ) -> AlgorithmWorkspace:
        """Persist one WSP Replay source only while runtime is stopped."""
        runtime = self._runtimes.get(workspace_uid)
        if runtime is not None and runtime.context.runtime_state not in {
            WORKSPACE_STATE_STOPPED,
            WORKSPACE_STATE_RESTORED,
        }:
            raise WorkspaceRuntimeError(
                "Cannot change Replay settings while runtime is active"
            )

        workspace = self.repository.load_workspace(workspace_uid)
        if values.source_type == WORKSPACE_REPLAY_SOURCE_CSV:
            resolved_path = values.require_existing_csv()
            values = replace(values, file_path=str(resolved_path))
        workspace.set_replay_settings(values.merge_settings(workspace.replay_settings))
        self.repository.save_workspace(workspace)
        self.remove_workspace_runtime(workspace_uid)
        return workspace

    def update_workspace_history_download_settings(
        self,
        workspace_uid: str,
        values: WorkspaceHistoryDownloadSettings,
    ) -> AlgorithmWorkspace:
        """Persist broker-history download settings while runtime is stopped."""
        runtime = self._runtimes.get(workspace_uid)
        if runtime is not None and runtime.context.runtime_state not in {
            WORKSPACE_STATE_STOPPED,
            WORKSPACE_STATE_RESTORED,
        }:
            raise WorkspaceRuntimeError(
                "Cannot change history download settings while runtime is active"
            )

        workspace = self.repository.load_workspace(workspace_uid)
        workspace.set_history_download_settings(
            values.merge_settings(workspace.history_download_settings)
        )
        self.repository.save_workspace(workspace)
        return workspace

    def download_workspace_ctrader_history(
        self,
        workspace_uid: str,
        runtime_engine: Any,
        start_utc: datetime,
        end_utc: datetime,
        *,
        history_root: str | None = None,
        progress_callback: CTraderHistoryProgressCallback | None = None,
    ) -> WorkspaceHistoryCsvExportResult:
        """Download cTrader bars and write one canonical Replay CSV."""
        runtime = self._runtimes.get(workspace_uid)
        if runtime is not None and runtime.context.runtime_state not in {
            WORKSPACE_STATE_STOPPED,
            WORKSPACE_STATE_RESTORED,
        }:
            raise WorkspaceRuntimeError(
                "Cannot download history while WSP runtime is active"
            )

        workspace = self.repository.load_workspace(workspace_uid)
        if workspace.broker != "CTRADER":
            raise WorkspaceRuntimeError(
                "Historical download is currently implemented for cTrader"
            )
        if runtime_engine is None:
            raise WorkspaceRuntimeError("RuntimeEngine is not connected")

        result = runtime_engine.download_ctrader_historical_bars(
            symbol_name=workspace.symbol,
            timeframe=workspace.timeframe,
            start_utc=start_utc,
            end_utc=end_utc,
            progress_callback=progress_callback,
        )
        writer = WorkspaceHistoryCsvWriter(history_root)
        return writer.write_ctrader(result)

    def download_workspace_ib_history(
        self,
        workspace_uid: str,
        runtime_engine: Any,
        start_utc: datetime,
        end_utc: datetime,
        *,
        history_root: str | None = None,
        progress_callback: IBHistoryProgressCallback | None = None,
    ) -> WorkspaceHistoryCsvExportResult:
        """Download IB bars and write one canonical Replay CSV."""
        runtime = self._runtimes.get(workspace_uid)
        if runtime is not None and runtime.context.runtime_state not in {
            WORKSPACE_STATE_STOPPED,
            WORKSPACE_STATE_RESTORED,
        }:
            raise WorkspaceRuntimeError(
                "Cannot download history while WSP runtime is active"
            )

        workspace = self.repository.load_workspace(workspace_uid)
        if workspace.broker != "IB":
            raise WorkspaceRuntimeError(
                "Historical download is available only for an IB WSP"
            )
        if runtime_engine is None:
            raise WorkspaceRuntimeError("RuntimeEngine is not connected")

        result = runtime_engine.download_ib_historical_bars(
            symbol_name=workspace.symbol,
            timeframe=workspace.timeframe,
            start_utc=start_utc,
            end_utc=end_utc,
            progress_callback=progress_callback,
        )
        writer = WorkspaceHistoryCsvWriter(history_root)
        return writer.write_ib(result)

    def update_workspace_modes(
        self,
        workspace_uid: str,
        *,
        data_mode: str,
        control_mode: str,
    ) -> AlgorithmWorkspace:
        """Зберегти фактичні data/control режими конкретного WSP."""
        runtime = self._runtimes.get(workspace_uid)
        if runtime is not None and runtime.context.runtime_state not in {
            WORKSPACE_STATE_STOPPED,
            WORKSPACE_STATE_RESTORED,
        }:
            raise WorkspaceRuntimeError(
                "Cannot change workspace modes while runtime is active"
            )

        workspace = self.repository.load_workspace(workspace_uid)
        if runtime is not None:
            workspace.runtime_state = runtime.context.runtime_state
        workspace.set_modes(
            data_mode=data_mode,
            control_mode=control_mode,
        )
        self.repository.save_workspace(workspace)
        self.remove_workspace_runtime(workspace_uid)
        return workspace

    def update_workspace_ui_state(
        self,
        workspace_uid: str,
        ui_state: dict[str, Any],
    ) -> AlgorithmWorkspace:
        """Зберегти geometry, стан вікна та активну панель WSP."""
        workspace = self.repository.load_workspace(workspace_uid)
        workspace.set_ui_state(ui_state)
        self.repository.save_workspace(workspace)
        return workspace

    def mark_workspace_started_once(
        self,
        workspace_uid: str,
    ) -> AlgorithmWorkspace:
        """Зафіксувати перший запуск без відновлення RUNNING."""
        workspace = self.repository.load_workspace(workspace_uid)
        workspace.mark_started_once()
        self.repository.save_workspace(workspace)
        return workspace

    def delete_workspace(self, workspace_uid: str) -> str | None:
        """Видалити WSP і повернути UID сусіднього активного workspace."""
        manifest = self.repository.load_manifest()
        self._require_unlocked(manifest)

        workspace = self.repository.load_workspace(workspace_uid)
        runtime = self._runtimes.get(workspace.workspace_uid)
        if runtime is not None:
            close_result = runtime.close_guard_result()
            if not close_result.allowed:
                raise WorkspaceRuntimeError(
                    "Cannot close workspace: "
                    f"{close_result.primary_reason or 'unknown blocker'}"
                )
        workspace_order = list(manifest["workspace_order"])
        try:
            removed_index = workspace_order.index(workspace.workspace_uid)
        except ValueError:
            removed_index = -1

        workspace_order = [
            uid for uid in workspace_order if uid != workspace.workspace_uid
        ]
        self.remove_workspace_runtime(workspace.workspace_uid)
        self.repository.delete_workspace(workspace.workspace_uid)

        next_active_uid: str | None = None
        if workspace_order:
            if removed_index < 0:
                removed_index = 0
            next_active_uid = workspace_order[
                min(removed_index, len(workspace_order) - 1)
            ]

        manifest["workspace_order"] = workspace_order
        manifest["active_workspace_uid"] = next_active_uid
        self.repository.save_manifest(manifest)
        return next_active_uid

    def set_active_workspace(self, workspace_uid: str | None) -> None:
        """Зберегти активний workspace у session.json."""
        manifest = self.repository.load_manifest()
        if workspace_uid is not None:
            workspace_uid = self.repository.load_workspace(workspace_uid).workspace_uid
        manifest["active_workspace_uid"] = workspace_uid
        self.repository.save_manifest(manifest)

    def set_layout_locked(self, locked: bool) -> None:
        """Змінити стан TWS-подібного замка середовища."""
        manifest = self.repository.load_manifest()
        manifest["layout_locked"] = bool(locked)
        self.repository.save_manifest(manifest)

    def is_layout_locked(self) -> bool:
        """Повернути стан замка середовища."""
        return bool(self.repository.load_manifest()["layout_locked"])

    @staticmethod
    def _require_unlocked(manifest: dict[str, Any]) -> None:
        if bool(manifest.get("layout_locked", False)):
            raise WorkspaceLayoutLockedError("Algorithm workspace layout is locked")

    @staticmethod
    def _make_unique_name(
        requested_name: str,
        workspaces: list[AlgorithmWorkspace],
    ) -> str:
        base_name = requested_name.strip()
        if not base_name:
            raise ValueError("display_name is required")

        existing_names = {workspace.display_name.casefold() for workspace in workspaces}
        if base_name.casefold() not in existing_names:
            return base_name

        suffix = 2
        while f"{base_name} ({suffix})".casefold() in existing_names:
            suffix += 1
        return f"{base_name} ({suffix})"
