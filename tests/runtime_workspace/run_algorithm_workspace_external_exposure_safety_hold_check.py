# -*- coding: utf-8 -*-
"""Runtime check for WSP LGE EXCLUSIVE external-exposure safety hold."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_DATA_MODE_BROKER,
    WORKSPACE_STATE_RUNNING,
    WORKSPACE_STATE_STARTING,
    WORKSPACE_STATE_STOPPED,
    AlgorithmWorkspace,
)
from core.algorithm_workspace_area import (  # noqa: E402
    AlgorithmWorkspaceWindow,
)
from core.lang_manager import LangManager  # noqa: E402
from core.translation_policy import (  # noqa: E402
    translation_override_for_key,
)
from core.workspace_broker_market import (  # noqa: E402
    WORKSPACE_EXECUTION_SAFETY_HOLD_EXTERNAL_EXPOSURE,
    WorkspaceBrokerMarketProviderProtocol,
    WorkspaceExecutionSafetySnapshot,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_runtime import (  # noqa: E402
    WORKSPACE_STARTUP_PHASE_RUNNING,
    WORKSPACE_STARTUP_PHASE_SAFETY_HOLD_EXTERNAL_EXPOSURE,
    WorkspaceRuntime,
)


class UkrainianLangManager(LangManager):
    """Use central Ukrainian overrides without touching localization files."""

    def __init__(self) -> None:
        super().__init__()
        self._current_lang = "uk"

    def tr(
        self,
        key: str,
        fallback: str,
        localized_fallbacks: Mapping[str, str] | None = None,
    ) -> str:
        centralized = translation_override_for_key(key, "uk")
        if centralized:
            return centralized
        if localized_fallbacks:
            localized = localized_fallbacks.get("uk")
            if localized:
                return localized
        return fallback

    def resolve(self, key: str, fallback: str = "") -> str | None:
        return translation_override_for_key(key, "uk") or fallback or None


class SafetyProvider(WorkspaceBrokerMarketProviderProtocol):
    """Deterministic provider that never sends a broker order."""

    def __init__(self) -> None:
        self.blocked = False
        self.connected = True
        self.poll_count = 0
        self.safety_calls = 0
        self.execution_attempts = 0
        self.stopped = False

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
        del workspace_uid, account_id, spread_limit
        if broker != "IB" or symbol != "EURUSD" or timeframe != "M15":
            raise AssertionError("Unexpected WSP binding")
        if warmup_bars != 0:
            raise AssertionError("Synthetic hold check uses no warm-up")
        return ()

    def poll_workspace(self, workspace_uid: str) -> WorkspaceMarketEvent | None:
        del workspace_uid
        self.poll_count += 1
        timestamp = datetime(2026, 8, 4, 12, 0, tzinfo=UTC) + timedelta(
            seconds=self.poll_count
        )
        bid = 1.15000 + self.poll_count * 0.00001
        ask = bid + 0.00010
        midpoint = (bid + ask) / 2.0
        return WorkspaceMarketEvent(
            timestamp=timestamp,
            broker="IB",
            symbol="EURUSD",
            timeframe="M15",
            bid=bid,
            ask=ask,
            spread=ask - bid,
            open=midpoint,
            high=midpoint,
            low=midpoint,
            close=midpoint,
            volume=0.0,
            source_mode=WORKSPACE_DATA_MODE_BROKER,
        )

    def is_workspace_broker_connected(self, workspace_uid: str) -> bool:
        del workspace_uid
        return self.connected

    def suspend_workspace(self, workspace_uid: str) -> None:
        del workspace_uid

    def resume_workspace(
        self,
        workspace_uid: str,
    ) -> tuple[WorkspaceMarketEvent, ...]:
        del workspace_uid
        return ()

    def stop_workspace(self, workspace_uid: str) -> None:
        del workspace_uid
        self.stopped = True

    def get_workspace_execution_safety(
        self,
        workspace_uid: str,
        *,
        runtime_mode: str,
        force: bool = False,
    ) -> WorkspaceExecutionSafetySnapshot:
        del workspace_uid, force
        self.safety_calls += 1
        if runtime_mode != "PAPER":
            raise AssertionError(f"Unexpected guard mode: {runtime_mode}")
        if not self.blocked:
            return WorkspaceExecutionSafetySnapshot.allowed_snapshot(
                "Current IB evidence is clear"
            )
        return WorkspaceExecutionSafetySnapshot(
            allowed=False,
            reason_code=WORKSPACE_EXECUTION_SAFETY_HOLD_EXTERNAL_EXPOSURE,
            message=(
                "LGE_EXCLUSIVE: external IB FX exposure BUY 1000 blocks "
                "new LGE execution for DUM513747 EURUSD"
            ),
            checked_utc=datetime.now(UTC),
            signed_volume=1000.0,
            evidence_status="CONFIRMED",
            confirmation_required=False,
        )


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    workspace = AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode="PAPER",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_BROKER,
        parameters={
            "warmup_bars": 0,
            "spread_limit": 0.00020,
        },
    )
    provider = SafetyProvider()
    runtime = WorkspaceRuntime(
        workspace,
        broker_market_provider=provider,
    )

    runtime.begin_start()
    runtime.complete_start()
    first_event = runtime.advance_broker_market()
    if first_event is None:
        raise AssertionError("Initial safe quote was not processed")
    if runtime.context.runtime_state != WORKSPACE_STATE_RUNNING:
        raise AssertionError("Initial safe WSP did not enter RUNNING")
    chart_before_hold = len(runtime.chart_snapshot().events)

    provider.blocked = True
    hold_event = runtime.advance_broker_market()
    if hold_event is None:
        raise AssertionError("Read-only quote stopped during safety hold")
    if runtime.context.runtime_state != WORKSPACE_STATE_STARTING:
        raise AssertionError("Safety hold did not leave RUNNING")
    if (
        runtime.context.startup_phase
        != WORKSPACE_STARTUP_PHASE_SAFETY_HOLD_EXTERNAL_EXPOSURE
    ):
        raise AssertionError("External exposure safety phase is missing")
    if not runtime.context.safety_hold_active:
        raise AssertionError("Safety hold flag is not active")
    if runtime.context.signal_allowed or runtime.can_form_signal():
        raise AssertionError("Signals remained enabled during safety hold")
    if len(runtime.chart_snapshot().events) <= chart_before_hold:
        raise AssertionError("Market chart did not continue during safety hold")

    provider.blocked = False
    recovery_event = runtime.advance_broker_market()
    if recovery_event is None:
        raise AssertionError("Fresh recovery quote was not processed")
    if runtime.context.safety_hold_active:
        raise AssertionError("Current clear evidence did not clear safety hold")
    if runtime.context.runtime_state != WORKSPACE_STATE_RUNNING:
        raise AssertionError("WSP did not resume after fresh spread")
    if runtime.context.startup_phase != WORKSPACE_STARTUP_PHASE_RUNNING:
        raise AssertionError("Recovered WSP did not return to RUNNING phase")
    if not runtime.can_form_signal():
        raise AssertionError("Signals did not resume after safety recovery")

    journal_events = [entry.event for entry in runtime.journal]
    if journal_events.count("SAFETY_HOLD_ENTERED") != 1:
        raise AssertionError("Safety hold entry was not journaled exactly once")
    if journal_events.count("SAFETY_HOLD_CLEARED") != 1:
        raise AssertionError("Safety hold clear was not journaled exactly once")
    if provider.execution_attempts != 0:
        raise AssertionError("Safety check attempted broker execution")

    window = AlgorithmWorkspaceWindow(
        workspace,
        lang_mgr=UkrainianLangManager(),
    )
    try:
        window.set_execution_safety_hold(
            active=True,
            message=(
                "LGE_EXCLUSIVE: external IB FX exposure BUY 1000 blocks "
                "new LGE execution for DUM513747 EURUSD"
            ),
            account_id="DUM513747",
            symbol="EURUSD",
            signed_volume=1000.0,
            evidence_status="CONFIRMED",
            confirmation_required=False,
        )
        tooltip = window.lbl_state.toolTip()
        if "Ордери" not in tooltip or "Моніторинг" not in tooltip:
            raise AssertionError("Localized safety tooltip lacks recovery route")
        if "perm" in tooltip.lower():
            raise AssertionError("Tooltip invented unavailable TWS identifiers")
        if "external IB FX exposure BUY" in tooltip:
            raise AssertionError("Raw English safety message leaked to tooltip")

        window.append_journal_entries(runtime.journal)
        app.processEvents()
        journal_text = window.ui.txtLog.toPlainText()
        if "ЗАХИСНУ ПАУЗУ УВІМКНЕНО" not in journal_text:
            raise AssertionError("Safety journal entry was not translated")
        if "ЗАХИСНУ ПАУЗУ ЗНЯТО" not in journal_text:
            raise AssertionError("Safety clear journal entry was not translated")
        if "SAFETY_HOLD_ENTERED" in journal_text:
            raise AssertionError("Raw safety event code leaked to journal")
        if "LGE_EXCLUSIVE: external IB FX exposure" in journal_text:
            raise AssertionError("Raw English guard message leaked to journal")
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()

    runtime.begin_stop()
    runtime.complete_stop()
    if runtime.context.runtime_state != WORKSPACE_STATE_STOPPED:
        raise AssertionError("Recovered WSP did not stop cleanly")
    if not provider.stopped:
        raise AssertionError("Provider was not released on Stop")

    print("Algorithm Workspace external exposure safety hold result")
    print("  lge_exclusive=True")
    print("  initial_running=True")
    print("  hold_state=STARTING")
    print("  hold_phase=SAFETY_HOLD_EXTERNAL_EXPOSURE")
    print("  market_data_continues=True")
    print("  signals_blocked=True")
    print("  current_evidence_clears_hold=True")
    print("  fresh_spread_required=True")
    print("  recovered_running=True")
    print("  journal_entered_once=True")
    print("  journal_cleared_once=True")
    print("  localized_tooltip_route=Orders,Monitoring")
    print("  localized_safety_journal=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_EXTERNAL_EXPOSURE_SAFETY_HOLD_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
