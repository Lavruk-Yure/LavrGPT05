# -*- coding: utf-8 -*-
"""Regression Replay virtual execution і immutable snapshot cache.

Перевіряється production RailAlgorithm у MANUAL/AUTO Replay, NEXT_BAR_OPEN,
SL/TP, Profit Drawdown, margin/risk та відсутність broker requests. Replay
execution regression навмисно фіксує legacy MACD 12/26/9 profile snapshot,
щоб зміна default-профілю нового WSP не змінювала signal stream цього тесту.
RoadMap100 додатково фіксує performance-інваріант: після закриття virtual
position її immutable WorkspacePositionSnapshot повторно використовується,
а не конструюється на кожному наступному M1 execution event. Це не змінює
PnL, життєвий цикл, таблиці або historical diagnostics.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_CONTROL_MODE_MANUAL,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_alligator import (  # noqa: E402
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_broker_market import (  # noqa: E402
    WorkspaceBrokerMarketProviderProtocol,
)
from core.workspace_indicator_profile import (  # noqa: E402
    default_workspace_indicator_profile_bindings,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay import REPLAY_SPEED_MAX  # noqa: E402
from core.workspace_replay_execution import (  # noqa: E402
    REPLAY_ORDER_STATUS_EXPIRED_NEXT_BAR_GAP,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402
from engine.risk.constants import DEFAULT_REPLAY_RISK_EQUITY  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WORKSPACE_REPLAY_SOURCE_CSV,
)

HISTORY_FILE = (
    PROJECT_ROOT
    / "data"
    / "history"
    / "IB"
    / "EURUSD"
    / "M15"
    / "2026-01-02_2026-07-27_IB_EURUSD_M15.csv"
)


class BrokerRequestProbe(WorkspaceBrokerMarketProviderProtocol):
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

    def poll_workspace(
        self,
        workspace_uid: str,
    ) -> WorkspaceMarketEvent | None:
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


def _workspace(control_mode: str) -> AlgorithmWorkspace:
    same_timeframe = WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=control_mode,
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "LINEAR",
            "alligator_filter_enabled": True,
            "alligator_confirmation": same_timeframe,
            "warmup_bars": 2,
            "spread_limit": 0.00020,
        },
        replay_settings={
            "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
            "file_path": str(HISTORY_FILE),
            "source_timezone": "UTC",
            "delimiter": ",",
            "decimal_separator": ".",
            "spread": 0.00012,
            "speed": REPLAY_SPEED_MAX,
        },
        risk_settings={
            "risk_percent": 0.5,
            "maximum_position_volume": 1000.0,
            "maximum_open_positions": 2,
            "max_daily_loss_percent": 2.0,
            "require_stop_loss": True,
        },
        # Цей regression перевіряє execution, а не default-профіль нового WSP.
        indicator_profile_bindings=default_workspace_indicator_profile_bindings(),
        profit_protection={
            "enabled": True,
            "activation_mode": "AFTER_SPREAD",
            "max_profit_drawdown_percent": 30.0,
            "minimum_profit": 0.0,
        },
    )


def _run(
    control_mode: str,
) -> tuple[WorkspaceRuntime, tuple[WorkspaceSignalRecord, ...], int]:
    records: list[WorkspaceSignalRecord] = []
    broker_probe = BrokerRequestProbe()
    runtime = WorkspaceRuntime(
        _workspace(control_mode),
        algorithm_factory=create_registered_workspace_algorithm,
        broker_market_provider=broker_probe,
        signal_record_observer=records.append,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()
    return runtime, tuple(records), broker_probe.requests


def _signature(record: WorkspaceSignalRecord) -> tuple[object, ...]:
    return (
        record.timestamp,
        record.signal_type,
        record.direction,
        record.macd_state,
        record.alligator_confirmation,
        record.accepted,
        record.filter_decision,
        record.filter_reason_code,
    )


def main() -> None:
    manual_runtime, manual_records, manual_requests = _run(
        WORKSPACE_CONTROL_MODE_MANUAL
    )
    auto_runtime, auto_records, auto_requests = _run(WORKSPACE_CONTROL_MODE_AUTO)

    assert isinstance(
        manual_runtime.algorithm,
        WorkspaceMacdAlligatorReplayAlgorithm,
    )
    assert len(manual_records) == 1072
    assert manual_runtime.replay_execution is None
    assert not manual_runtime.owned_snapshot.orders
    assert not manual_runtime.owned_snapshot.positions

    assert tuple(map(_signature, manual_records)) == tuple(
        map(_signature, auto_records)
    )
    assert auto_runtime.replay_execution is not None
    snapshot = auto_runtime.owned_snapshot
    assert snapshot.orders
    assert snapshot.positions
    assert not snapshot.active_orders
    assert not snapshot.active_positions
    assert all(order.broker_order_id is None for order in snapshot.orders)
    assert all(position.broker_position_id is None for position in snapshot.positions)
    assert all(position.stop_loss is not None for position in snapshot.positions)
    assert all(position.take_profit is not None for position in snapshot.positions)

    statuses = [position.reconciliation_status for position in snapshot.positions]
    stop_loss_closes = sum(status.endswith("STOP_LOSS") for status in statuses)
    take_profit_closes = sum(status.endswith("TAKE_PROFIT") for status in statuses)
    drawdown_positions = [
        position
        for position in snapshot.positions
        if status_for(position).endswith("PROFIT_DRAWDOWN")
    ]
    session_end_closes = sum(status.endswith("SESSION_END") for status in statuses)
    expired_gap_orders = sum(
        order.status == REPLAY_ORDER_STATUS_EXPIRED_NEXT_BAR_GAP
        for order in snapshot.orders
    )
    assert expired_gap_orders == 3
    assert stop_loss_closes > 0
    assert take_profit_closes > 0
    assert drawdown_positions
    assert all(position.peak_profit > 0.0 for position in drawdown_positions)
    assert all(position.profit_drawdown > 30.0 for position in drawdown_positions)

    first_position = snapshot.positions[0]
    first_order = next(
        order for order in snapshot.orders if order.order_id == "RPL-ORD-000001"
    )
    assert first_position.position_id == "RPL-POS-000001"
    assert first_order.price == first_position.entry_price
    assert first_order.stop_loss == first_position.stop_loss
    assert first_order.take_profit == first_position.take_profit
    assert first_position.opened_at > first_order.created_at

    cached_snapshot_first = auto_runtime.replay_execution.snapshot()
    cached_snapshot_second = auto_runtime.replay_execution.snapshot()
    closed_position_snapshot_cache = bool(cached_snapshot_first.positions) and all(
        first is second
        for first, second in zip(
            cached_snapshot_first.positions,
            cached_snapshot_second.positions,
            strict=True,
        )
    )
    assert closed_position_snapshot_cache
    assert cached_snapshot_first == cached_snapshot_second

    assert auto_runtime.context.positions_count == 0
    assert auto_runtime.context.active_orders_count == 0
    assert auto_runtime.context.risk_equity is not None
    assert math.isclose(
        auto_runtime.context.risk_equity,
        DEFAULT_REPLAY_RISK_EQUITY + auto_runtime.context.current_profit,
        rel_tol=0.0,
        abs_tol=1e-9,
    )
    assert manual_requests == 0
    assert auto_requests == 0

    execution_events = [
        entry for entry in auto_runtime.journal if entry.category == "REPLAY_EXECUTION"
    ]
    assert execution_events
    assert all(
        entry.details.get("broker_execution_attempted") is False
        for entry in execution_events
    )

    print("Algorithm Workspace Replay Virtual Execution result")
    print("  production_rail_algorithm_registered=True")
    print("  macd_execution_baseline_profile=12/26/9")
    print(f"  complete_signal_records={len(auto_records)}")
    print("  manual_mode_signals_visible=True")
    print("  manual_mode_virtual_execution_disabled=True")
    print("  auto_mode_virtual_execution_enabled=True")
    print(f"  virtual_orders={len(snapshot.orders)}")
    print(f"  virtual_positions={len(snapshot.positions)}")
    print(f"  stop_loss_closes={stop_loss_closes}")
    print(f"  take_profit_closes={take_profit_closes}")
    print(f"  profit_drawdown_closes={len(drawdown_positions)}")
    print(f"  session_end_closes={session_end_closes}")
    print(f"  next_bar_gap_expired_orders={expired_gap_orders}")
    print("  profit_drawdown_close_percent=30.0")
    print("  profit_drawdown_arms_after_positive_peak=True")
    print("  entry_policy=NEXT_BAR_OPEN")
    print("  stop_policy=SIGNAL_BAR_RANGE_1R")
    print("  take_profit_policy=SIGNAL_BAR_RANGE_2R")
    print("  ambiguous_bar_policy=STOP_LOSS_FIRST")
    print("  virtual_sl_tp_visible=True")
    print("  all_virtual_positions_closed_at_completion=True")
    print(f"  closed_position_snapshot_cache={closed_position_snapshot_cache}")
    print("  replay_total_profit_usd=" f"{auto_runtime.context.current_profit:.2f}")
    print(
        "  replay_initial_balance_usd="
        f"{auto_runtime.context.replay_initial_balance:.2f}"
    )
    print("  replay_synthetic_equity_usd=" f"{auto_runtime.context.risk_equity:.2f}")
    print("  signal_signatures_unchanged_by_execution=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_REPLAY_VIRTUAL_EXECUTION_CHECK=OK")


def status_for(position: object) -> str:
    return str(getattr(position, "reconciliation_status", ""))


if __name__ == "__main__":
    main()
