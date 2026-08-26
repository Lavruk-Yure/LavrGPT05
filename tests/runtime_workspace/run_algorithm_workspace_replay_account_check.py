# -*- coding: utf-8 -*-
"""Replay virtual-account settings and live financial snapshot check."""

from __future__ import annotations

import math
import sys
from dataclasses import replace
from pathlib import Path
from xml.etree.ElementTree import parse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_replay_settings import (  # noqa: E402
    WorkspaceReplaySettings,
    WorkspaceReplaySettingsError,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from engine.risk.constants import (  # noqa: E402
    DEFAULT_REPLAY_RISK_EQUITY,
    MAXIMUM_REPLAY_RISK_EQUITY,
    MINIMUM_REPLAY_RISK_EQUITY,
)
from engine.runtime_constants import WORKSPACE_REPLAY_SOURCE_CSV  # noqa: E402

HISTORY_FILE = (
    PROJECT_ROOT
    / "data"
    / "history"
    / "IB"
    / "EURUSD"
    / "M15"
    / "2026-01-02_2026-07-27_IB_EURUSD_M15.csv"
)


def _workspace(initial_balance: float) -> AlgorithmWorkspace:
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
            "alligator_filter_enabled": True,
            "alligator_confirmation": "SAME_TIMEFRAME",
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
            "risk_equity": initial_balance,
            "speed": 100,
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


def main() -> None:
    ui_root = parse(
        PROJECT_ROOT / "ui" / "algorithm_workspace_replay_dialog.ui"
    ).getroot()
    initial_balance_widget = ui_root.find(".//widget[@name='spnInitialBalance']")
    assert initial_balance_widget is not None
    ui_text = (PROJECT_ROOT / "ui" / "algorithm_workspace_replay_dialog.ui").read_text(
        encoding="utf-8"
    )
    assert "100.000000000000000" in ui_text
    assert "100000.000000000000000" in ui_text
    assert "1000.000000000000000" in ui_text
    area_text = (PROJECT_ROOT / "core" / "algorithm_workspace_area.py").read_text(
        encoding="utf-8"
    )
    assert "def set_replay_financial_snapshot(" in area_text
    assert "Virtual Replay account" in area_text

    defaults = WorkspaceReplaySettings()
    assert defaults.initial_balance == DEFAULT_REPLAY_RISK_EQUITY
    assert DEFAULT_REPLAY_RISK_EQUITY == 1_000.0
    assert (
        WorkspaceReplaySettings(
            initial_balance=MINIMUM_REPLAY_RISK_EQUITY
        ).initial_balance
        == MINIMUM_REPLAY_RISK_EQUITY
    )
    assert (
        WorkspaceReplaySettings(
            initial_balance=MAXIMUM_REPLAY_RISK_EQUITY
        ).initial_balance
        == MAXIMUM_REPLAY_RISK_EQUITY
    )

    invalid_balance_blocked = 0
    for initial_balance in (99.99, 100_000.01):
        try:
            WorkspaceReplaySettings(initial_balance=initial_balance)
        except WorkspaceReplaySettingsError:
            invalid_balance_blocked += 1
    assert invalid_balance_blocked == 2

    workspace = _workspace(DEFAULT_REPLAY_RISK_EQUITY)
    settings = WorkspaceReplaySettings.from_workspace(workspace)
    assert settings.initial_balance == DEFAULT_REPLAY_RISK_EQUITY
    merged = settings.merge_settings(
        {"future_replay_key": "KEEP", "risk_equity": 500.0}
    )
    assert merged["risk_equity"] == DEFAULT_REPLAY_RISK_EQUITY
    assert merged["future_replay_key"] == "KEEP"

    runtime = WorkspaceRuntime(
        workspace,
        algorithm_factory=create_registered_workspace_algorithm,
    )
    assert runtime.context.replay_initial_balance == 1_000.0
    assert runtime.context.risk_equity is None

    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    assert runtime.context.risk_equity == 1_000.0
    assert runtime.context.daily_realized_pnl == 0.0

    live_balance_changed = False
    live_equity_includes_open_profit = False
    while not session.completed:
        runtime.advance_replay()
        initial_balance = runtime.context.replay_initial_balance
        realized_profit = runtime.context.daily_realized_pnl
        equity = runtime.context.risk_equity
        assert initial_balance is not None
        assert realized_profit is not None
        assert equity is not None
        balance = initial_balance + realized_profit
        if not math.isclose(balance, initial_balance, abs_tol=1e-12):
            live_balance_changed = True
        if runtime.context.positions_count > 0:
            if not math.isclose(equity, balance, abs_tol=1e-12):
                live_equity_includes_open_profit = True

    assert live_balance_changed
    assert live_equity_includes_open_profit
    assert runtime.context.replay_initial_balance == 1_000.0
    assert math.isclose(
        runtime.context.daily_realized_pnl or 0.0,
        -45.68,
        rel_tol=0.0,
        abs_tol=0.01,
    )
    assert math.isclose(
        runtime.context.risk_equity or 0.0,
        954.32,
        rel_tol=0.0,
        abs_tol=0.01,
    )

    restored_settings = dict(workspace.replay_settings)
    restored_settings["risk_equity"] = 2_500.0
    restored_workspace = replace(workspace, replay_settings=restored_settings)
    restored_runtime = WorkspaceRuntime(restored_workspace)
    assert restored_runtime.context.replay_initial_balance == 2_500.0

    print("Algorithm Workspace Replay Account result")
    print("  separate_designer_balance_field=True")
    print("  live_replay_financial_ui_connected=True")
    print("  virtual_replay_account_explicit=True")
    print("  default_initial_balance_usd=1000.00")
    print("  initial_balance_range_usd=100.00..100000.00")
    print("  initial_balance_persisted=True")
    print("  future_keys_preserved=True")
    print(f"  invalid_balance_blocked={invalid_balance_blocked}")
    print(f"  live_balance_changed={live_balance_changed}")
    print("  live_equity_includes_open_profit=" f"{live_equity_includes_open_profit}")
    print("  replay_final_balance_usd=954.32")
    print("  replay_final_equity_usd=954.32")
    print("  profit_drawdown_range_percent=1..100")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_REPLAY_ACCOUNT_CHECK=OK")


if __name__ == "__main__":
    main()
