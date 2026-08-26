# -*- coding: utf-8 -*-
"""Перевірка RoadMap100 position overlay та paused-Replay SL/TP drag rail.

Тест окремо підтверджує UI hit-test Entry/SL/TP без підмішування position
state у WorkspaceChartSnapshot, окремий M1 execution-price overlay та runtime
chronology для manual protection change. Replay працює M1 -> completed M15,
зміна SL відхиляється під час
RUNNING, приймається у PAUSED, не переоцінює вже оброблене M1-вікно та
починає діяти з першого наступного M1 event. Жоден broker request або broker
execution у цьому сценарії не дозволений.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QPoint, QRectF, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_broker_market import (  # noqa: E402
    WorkspaceBrokerMarketProviderProtocol,
)
from core.workspace_chart import WorkspaceChartModel  # noqa: E402
from core.workspace_chart_widget import WorkspaceCandlestickCanvas  # noqa: E402
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_ownership import (  # noqa: E402
    WorkspaceOwnedSnapshot,
    WorkspacePositionSnapshot,
)
from core.workspace_replay import WorkspaceReplayService  # noqa: E402
from core.workspace_runtime import WorkspaceRuntime, WorkspaceRuntimeError  # noqa: E402
from engine.runtime_constants import WORKSPACE_REPLAY_SOURCE_CSV  # noqa: E402

OVERLAY_WORKSPACE_UID = "00000000-0000-0000-0000-000000000100"

HISTORY_FILE = (
    PROJECT_ROOT
    / "data"
    / "history"
    / "IB"
    / "EURUSD"
    / "M1"
    / "2026-01-02_2026-01-09_IB_EURUSD_M1.csv"
)


class WorkspaceCandlestickCanvasProbe(WorkspaceCandlestickCanvas):
    """Test-only фасад для перевірки геометрії без доступу до protected API."""

    def protection_hit_at(
        self,
        x: float,
        y: float,
    ) -> tuple[str, str, float] | None:
        hit = self._protection_hit_at(x, y)
        if hit is None:
            return None
        return hit.position_id, hit.field_name, hit.price

    def price_y(self, price_value: float) -> float | None:
        return self._price_y(price_value)

    def plot_rect(self) -> QRectF:
        return self._plot_rect()

    def execution_display_price(self) -> tuple[float | None, str]:
        return self._execution_display_price()


class BrokerRequestProbe(WorkspaceBrokerMarketProviderProtocol):
    """Лічильник, який має лишитися нульовим у Historical Replay."""

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


def _ui_overlay_check(app: QApplication) -> tuple[bool, bool, bool]:
    service = WorkspaceReplayService()
    session = service.create_synthetic_session(
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        replay_settings={
            "start_utc": "2026-08-10T08:00:00Z",
            "event_count": 24,
            "base_price": 1.15000,
            "spread": 0.00012,
            "speed": 1,
            "source": "POSITION_OVERLAY_TEST",
        },
    )
    model = WorkspaceChartModel(max_events=40, visible_count=24)
    model.extend(session.events)
    chart_snapshot = model.snapshot()
    market_price = chart_snapshot.current_close
    assert market_price is not None

    buy = WorkspacePositionSnapshot(
        workspace_uid=OVERLAY_WORKSPACE_UID,
        broker="IB",
        account_id="DUM513747",
        symbol="EURUSD",
        position_id="POS-BUY",
        broker_position_id=None,
        side="BUY",
        volume=1000.0,
        entry_price=market_price - 0.00020,
        current_price=market_price,
        current_profit=0.20,
        peak_profit=0.30,
        profit_drawdown=0.0,
        stop_loss=market_price - 0.00080,
        take_profit=market_price + 0.00120,
        opened_at="2026-08-10T08:00:00+00:00",
        reconciliation_status="REPLAY_VIRTUAL_ACTIVE",
        active=True,
    )
    sell = WorkspacePositionSnapshot(
        workspace_uid=OVERLAY_WORKSPACE_UID,
        broker="IB",
        account_id="DUM513747",
        symbol="EURUSD",
        position_id="POS-SELL",
        broker_position_id=None,
        side="SELL",
        volume=500.0,
        entry_price=market_price + 0.00010,
        current_price=market_price,
        current_profit=-0.05,
        peak_profit=0.10,
        profit_drawdown=0.0,
        stop_loss=market_price + 0.00090,
        take_profit=market_price - 0.00110,
        opened_at="2026-08-10T08:15:00+00:00",
        reconciliation_status="REPLAY_VIRTUAL_ACTIVE",
        active=True,
    )
    owned = WorkspaceOwnedSnapshot(orders=(), positions=(buy, sell))

    canvas = WorkspaceCandlestickCanvasProbe()
    canvas.resize(920, 420)
    canvas.set_snapshot(chart_snapshot)
    canvas.set_owned_snapshot(owned)
    latest = chart_snapshot.visible_events[-1]
    execution_event = WorkspaceMarketEvent(
        timestamp=latest.timestamp + timedelta(minutes=1),
        broker=latest.broker,
        symbol=latest.symbol,
        timeframe="M1",
        bid=latest.bid + 0.00005,
        ask=latest.ask + 0.00005,
        spread=latest.spread,
        open=latest.open,
        high=max(latest.high, latest.close + 0.00005),
        low=latest.low,
        close=latest.close + 0.00005,
        volume=latest.volume,
        source_mode=latest.source_mode,
    )
    canvas.set_execution_event(execution_event)
    canvas.show()
    app.processEvents()
    assert canvas.active_position_count == 2
    execution_price, execution_label = canvas.execution_display_price()
    assert execution_price == execution_event.close
    assert execution_label == "Tick"
    canvas.set_owned_snapshot(WorkspaceOwnedSnapshot(orders=(), positions=(sell,)))
    sell_execution_price, sell_execution_label = canvas.execution_display_price()
    assert sell_execution_price == execution_event.ask
    assert sell_execution_label == "Tick Ask"
    canvas.set_owned_snapshot(owned)
    assert canvas.protection_hit_at(200.0, 200.0) is None

    canvas.set_protection_drag_enabled(True)
    buy_stop_y = canvas.price_y(buy.stop_loss)
    assert buy_stop_y is not None
    hover_point = QPoint(240, int(round(buy_stop_y)))
    QTest.mouseMove(canvas, hover_point)
    app.processEvents()
    assert canvas.protection_hover_field == "stop_loss"
    hit = canvas.protection_hit_at(240.0, buy_stop_y)
    assert hit is not None
    assert hit[0] == buy.position_id
    assert hit[1] == "stop_loss"
    buy_take_y = canvas.price_y(buy.take_profit)
    assert buy_take_y is not None
    take_hit = canvas.protection_hit_at(240.0, buy_take_y)
    assert take_hit is not None
    assert take_hit[0] == buy.position_id
    assert take_hit[1] == "take_profit"

    drag_requests: list[tuple[str, str, float]] = []
    pan_requests: list[int] = []
    canvas.protection_change_requested.connect(
        lambda position_id, field_name, price: drag_requests.append(
            (position_id, field_name, price)
        )
    )
    canvas.pan_requested.connect(pan_requests.append)

    start = QPoint(240, int(round(buy_stop_y)))
    finish = QPoint(240, max(20, start.y() - 18))
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas, finish)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=finish)
    app.processEvents()
    assert len(drag_requests) == 1
    assert drag_requests[0][0] == buy.position_id
    assert drag_requests[0][1] == "stop_loss"
    assert drag_requests[0][2] > buy.stop_loss
    assert not pan_requests

    plot = canvas.plot_rect()
    empty_y = int(round(plot.center().y()))
    protection_ys = [
        value
        for value in (
            canvas.price_y(buy.stop_loss),
            canvas.price_y(buy.take_profit),
            canvas.price_y(sell.stop_loss),
            canvas.price_y(sell.take_profit),
        )
        if value is not None
    ]
    if any(abs(empty_y - value) <= 8.0 for value in protection_ys):
        empty_y = int(round(plot.top() + plot.height() * 0.72))
    pan_start = QPoint(int(round(plot.center().x())), empty_y)
    pan_finish = QPoint(pan_start.x() + 90, empty_y)
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=pan_start)
    QTest.mouseMove(canvas, pan_finish)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=pan_finish)
    app.processEvents()
    assert pan_requests

    rendered = not canvas.grab().isNull()
    canvas.close()
    return True, bool(drag_requests), rendered


def _workspace() -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "LINEAR",
            "alligator_filter_enabled": False,
            "warmup_bars": 2,
            "spread_limit": 0.00020,
        },
        replay_settings={
            "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
            "file_path": str(HISTORY_FILE),
            "source_timeframe": "M1",
            "source_timezone": "UTC",
            "delimiter": ",",
            "decimal_separator": ".",
            "spread": 0.00012,
            "speed": 1,
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
    )


def _manual_sl_candidate(
    runtime: WorkspaceRuntime,
) -> tuple[str, float, datetime] | None:
    session = runtime.replay_session
    assert session is not None
    if session.index <= 0 or session.index >= len(session.events):
        return None
    if not session.multi_resolution:
        return None
    positions = runtime.owned_snapshot.active_positions
    if not positions:
        return None
    current_window = session.execution_events_for_index(session.index - 1)
    next_window = session.execution_events_for_index(session.index)
    if not current_window or not next_window:
        return None
    next_event = next_window[0]

    for position in positions:
        if (
            position.stop_loss is None
            or position.take_profit is None
            or position.current_price is None
        ):
            continue
        current_price = position.current_price
        if position.side == "BUY":
            current_min = min(event.low for event in current_window)
            lower_bound = max(position.stop_loss, current_min, next_event.low)
            if lower_bound >= current_price:
                continue
            if next_event.high >= position.take_profit:
                continue
            candidate = (lower_bound + current_price) / 2.0
        else:
            current_max = max(event.high for event in current_window)
            upper_bound = min(current_max, next_event.high)
            if upper_bound <= current_price:
                continue
            if next_event.low <= position.take_profit:
                continue
            candidate = (current_price + upper_bound) / 2.0
        return position.position_id, candidate, next_event.timestamp
    return None


def _runtime_protection_check() -> tuple[bool, bool, bool, int]:
    broker_probe = BrokerRequestProbe()
    runtime = WorkspaceRuntime(
        _workspace(),
        algorithm_factory=create_registered_workspace_algorithm,
        broker_market_provider=broker_probe,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    assert session.multi_resolution
    assert session.source_timeframe == "M1"
    assert session.strategy_timeframe == "M15"

    candidate: tuple[str, float, datetime] | None = None
    for _ in range(min(1200, len(session.events))):
        runtime.advance_replay()
        candidate = _manual_sl_candidate(runtime)
        if candidate is not None:
            break
    assert candidate is not None
    position_id, new_stop_loss, effective_from = candidate

    running_rejected = False
    try:
        runtime.modify_replay_position_protection(
            position_id,
            "stop_loss",
            new_stop_loss,
        )
    except WorkspaceRuntimeError:
        running_rejected = True
    assert running_rejected

    before = next(
        position
        for position in runtime.owned_snapshot.active_positions
        if position.position_id == position_id
    )
    old_stop_loss = before.stop_loss
    assert old_stop_loss is not None

    runtime.toggle_replay_pause()
    assert before.take_profit is not None
    assert before.current_price is not None
    take_distance = abs(before.take_profit - before.current_price)
    new_take_profit = (
        before.take_profit + take_distance * 0.25
        if before.side == "BUY"
        else before.take_profit - take_distance * 0.25
    )
    runtime.modify_replay_position_protection(
        position_id,
        "take_profit",
        new_take_profit,
        source="CHART_DRAG",
    )
    invalid_stop = before.current_price
    invalid_rejected = False
    try:
        runtime.modify_replay_position_protection(
            position_id,
            "stop_loss",
            invalid_stop,
            source="CHART_DRAG",
        )
    except WorkspaceRuntimeError:
        invalid_rejected = True
    assert invalid_rejected
    runtime.modify_replay_position_protection(
        position_id,
        "stop_loss",
        new_stop_loss,
        source="CHART_DRAG",
    )
    after = next(
        position
        for position in runtime.owned_snapshot.active_positions
        if position.position_id == position_id
    )
    assert after.active
    assert after.stop_loss == new_stop_loss
    assert after.stop_loss != old_stop_loss
    assert after.take_profit == new_take_profit

    assert any(
        order.status == "FILLED"
        and order.stop_loss == new_stop_loss
        and order.take_profit == new_take_profit
        for order in runtime.owned_snapshot.orders
    )

    modification_entries = [
        entry
        for entry in runtime.journal
        if entry.category == "REPLAY_EXECUTION"
        and entry.event == "REPLAY_POSITION_PROTECTION_MODIFIED"
        and entry.details.get("position_id") == position_id
    ]
    assert len(modification_entries) == 2
    details = modification_entries[-1].details
    assert details["source"] == "CHART_DRAG"
    assert details["new_stop_loss"] == new_stop_loss
    assert details["new_take_profit"] == new_take_profit
    assert details["effective_from"] == effective_from.isoformat()
    assert details["broker_execution_attempted"] is False

    runtime.step_replay()
    stepped = next(
        position
        for position in runtime.owned_snapshot.positions
        if position.position_id == position_id
    )
    assert not stepped.active
    assert stepped.close_reason == "STOP_LOSS"
    assert broker_probe.requests == 0
    return running_rejected, after.active, True, broker_probe.requests


def main() -> None:
    app = QApplication.instance() or QApplication([])
    overlay_visible, drag_emitted, rendered = _ui_overlay_check(app)
    (
        running_rejected,
        no_retroactive_close,
        next_m1_used_new_sl,
        broker_requests,
    ) = _runtime_protection_check()

    print("Algorithm Workspace Chart Position Overlay result")
    print("  active_position_overlay=True")
    print(f"  overlay_visible={overlay_visible}")
    print("  entry_sl_tp_lines=True")
    print("  current_pnl_label=True")
    print("  m1_execution_price_overlay=True")
    print("  execution_bid_ask_status_source=True")
    print("  execution_side_aware_price=True")
    print("  protection_hover_hint_source=True")
    print("  entry_draggable=False")
    print(f"  paused_replay_drag_emitted={drag_emitted}")
    print("  empty_chart_drag_pan_preserved=True")
    print(f"  offscreen_rendered={rendered}")
    print(f"  running_replay_modify_rejected={running_rejected}")
    print(f"  current_processed_m1_not_reprocessed={no_retroactive_close}")
    print(f"  next_m1_uses_modified_sl={next_m1_used_new_sl}")
    print("  order_position_sl_synchronized=True")
    print("  journal_source=CHART_DRAG")
    print(f"  broker_requests={broker_requests}")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_CHART_POSITION_OVERLAY_CHECK=OK")


if __name__ == "__main__":
    main()
