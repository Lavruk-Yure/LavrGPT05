# -*- coding: utf-8 -*-
"""RoadMap98.4 completed Historical Replay summary check."""

from __future__ import annotations

import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from xml.etree.ElementTree import fromstring

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_MANUAL,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_historical_summary import (  # noqa: E402
    build_workspace_historical_replay_summary,
    build_workspace_historical_signal_metrics,
)
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_replay_execution import (  # noqa: E402
    REPLAY_CLOSE_PROFIT_DRAWDOWN,
    REPLAY_CLOSE_SESSION_END,
    REPLAY_CLOSE_STOP_LOSS,
    REPLAY_CLOSE_TAKE_PROFIT,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import (  # noqa: E402
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WorkspaceSignalRecord,
)
from engine.risk.constants import RISK_DECISION_BLOCK  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED,
)


def _diagnostic(
    index: int,
    profit: float,
    close_reason: str,
) -> WorkspaceHistoricalTradeDiagnostic:
    entry = datetime(2026, 7, 1, 8, 0, tzinfo=UTC) + timedelta(hours=index)
    close = entry + timedelta(minutes=45)
    return WorkspaceHistoricalTradeDiagnostic(
        position_id=f"RPL-POS-{index:06d}",
        order_id=f"RPL-ORD-{index:06d}",
        signal_uid=f"SIG-{index:06d}",
        signal_timestamp=entry - timedelta(minutes=15),
        entry_timestamp=entry,
        close_timestamp=close,
        entry_price=1.1000,
        close_price=1.1001,
        direction="BUY" if index % 2 else "SELL",
        volume=1000.0,
        macd_state="BULLISH" if index % 2 else "BEARISH",
        alligator_state="SAME_TIMEFRAME_BULLISH",
        alligator_timeframe="M15",
        stop_loss_distance=0.0010,
        take_profit_distance=0.0020,
        maximum_favorable_excursion=max(profit, 0.0),
        maximum_adverse_excursion=min(profit, 0.0),
        peak_profit=max(profit, 0.0),
        final_profit=profit,
        close_reason=close_reason,
        holding_seconds=(close - entry).total_seconds(),
    )


def _signal(
    index: int,
    *,
    direction: str,
    confirmation: str,
    filter_decision: str = WORKSPACE_SIGNAL_FILTER_ALLOW,
    risk_decision: str | None = None,
) -> WorkspaceSignalRecord:
    return WorkspaceSignalRecord(
        timestamp=datetime(2026, 7, 1, 8, index, tzinfo=UTC),
        signal_uid=f"SIG-{index:06d}",
        workspace_uid="WSP-SUMMARY",
        broker="IB",
        account_id="DUM513747",
        symbol="EURUSD",
        timeframe="M15",
        source_mode="REPLAY",
        signal_type="MACD_CROSS",
        direction=direction,
        strength=1.0,
        macd_state="BULLISH" if direction == "BUY" else "BEARISH",
        alligator_confirmation=confirmation,
        spread_status="OK",
        accepted=filter_decision == WORKSPACE_SIGNAL_FILTER_ALLOW
        and risk_decision != RISK_DECISION_BLOCK,
        reason="summary fixture",
        risk_decision=risk_decision,
        risk_reason_code="MAXIMUM_POSITION_VOLUME"
        if risk_decision == RISK_DECISION_BLOCK
        else None,
        filter_decision=filter_decision,
        filter_reason_code="ALLIGATOR_NOT_READY"
        if filter_decision == WORKSPACE_SIGNAL_FILTER_REJECT
        else None,
    )


def _check_runtime_summary() -> None:
    workspace = AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode="PAPER",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_MANUAL,
        parameters={"warmup_bars": 2, "spread_limit": 0.00020},
        replay_settings={
            "start_utc": "2026-07-01T08:00:00Z",
            "event_count": 12,
            "speed": 5,
            "spread": 0.00012,
        },
    )
    runtime = WorkspaceRuntime(workspace)
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    summary = runtime.historical_summary
    assert summary is not None
    assert summary.symbol == "EURUSD"
    assert summary.timeframe == "M15"
    assert summary.accepted_bars == 12
    assert summary.skipped_bars == 0
    assert summary.gaps == 0
    assert math.isclose(summary.spread, 0.00012)
    assert summary.opened_trades == 0
    assert summary.signals.total == 0
    assert any(
        entry.event == "HISTORICAL_SUMMARY_READY" for entry in runtime.journal
    )


def _check_designer_dialog_contract() -> None:
    ui_path = (
        PROJECT_ROOT / "ui" / "algorithm_workspace_historical_summary_dialog.ui"
    )
    generated_path = (
        PROJECT_ROOT
        / "ui"
        / "ui_algorithm_workspace_historical_summary_dialog.py"
    )
    area_path = PROJECT_ROOT / "core" / "algorithm_workspace_area.py"
    dialog_path = (
        PROJECT_ROOT / "core" / "algorithm_workspace_historical_summary_dialog.py"
    )
    root = fromstring(ui_path.read_text(encoding="utf-8"))
    assert root.find(".//widget[@name='lblNetPnl']") is not None
    assert root.find(".//widget[@name='lblMaxDrawdown']") is not None
    assert root.find(".//widget[@name='lblProfitDrawdown']") is not None
    assert root.find(".//widget[@name='lblSourceTimeframe']") is not None
    assert root.find(".//widget[@name='lblCsvSelectionTime']") is not None
    assert root.find(".//widget[@name='lblReplayTime']") is not None
    generated = generated_path.read_text(encoding="utf-8")
    assert "Ui_AlgorithmWorkspaceHistoricalSummaryDialog" in generated
    dialog_source = dialog_path.read_text(encoding="utf-8")
    assert "Ui_AlgorithmWorkspaceHistoricalSummaryDialog" in dialog_source
    assert "AlgorithmWorkspaceHistoricalSummaryDialog.stopLoss" in dialog_source
    assert "AlgorithmWorkspaceHistoricalSummaryDialog.takeProfit" in dialog_source
    assert (
        "AlgorithmWorkspaceHistoricalSummaryDialog.profitDrawdown"
        in dialog_source
    )
    assert "AlgorithmWorkspaceHistoricalSummaryDialog.sessionEnd" in dialog_source
    translation_policy_source = (
        PROJECT_ROOT / "core" / "translation_policy.py"
    ).read_text(encoding="utf-8")
    assert "Закриття за відкатом прибутку:" in translation_policy_source
    assert "Закриття в кінці Replay:" in translation_policy_source
    area_source = area_path.read_text(encoding="utf-8")
    assert "_show_historical_summary_if_ready" in area_source
    assert "_historical_summary_shown" in area_source


def main() -> None:
    records = (
        _signal(
            1,
            direction="BUY",
            confirmation=WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED,
        ),
        _signal(2, direction="SELL", confirmation="SAME_TIMEFRAME_BEARISH"),
        _signal(
            3,
            direction="BUY",
            confirmation="SAME_TIMEFRAME_WARMUP",
            filter_decision=WORKSPACE_SIGNAL_FILTER_REJECT,
        ),
        _signal(
            4,
            direction="SELL",
            confirmation="SAME_TIMEFRAME_BEARISH",
            risk_decision=RISK_DECISION_BLOCK,
        ),
    )
    signal_metrics = build_workspace_historical_signal_metrics(records)
    assert signal_metrics.total == 4
    assert signal_metrics.buy == 2
    assert signal_metrics.sell == 2
    assert signal_metrics.alligator_allow == 2
    assert signal_metrics.alligator_reject == 1
    assert signal_metrics.warmup_rejects == 1
    assert signal_metrics.risk_rejects == 1

    trades = (
        _diagnostic(1, 100.0, REPLAY_CLOSE_TAKE_PROFIT),
        _diagnostic(2, -40.0, REPLAY_CLOSE_STOP_LOSS),
        _diagnostic(3, -60.0, REPLAY_CLOSE_STOP_LOSS),
        _diagnostic(4, 30.0, REPLAY_CLOSE_PROFIT_DRAWDOWN),
        _diagnostic(5, -20.0, REPLAY_CLOSE_SESSION_END),
        _diagnostic(6, 50.0, REPLAY_CLOSE_TAKE_PROFIT),
    )
    summary = build_workspace_historical_replay_summary(
        symbol="EURUSD",
        timeframe="M15",
        period_start=datetime(2026, 7, 1, 8, 0, tzinfo=UTC),
        period_end=datetime(2026, 7, 2, 8, 0, tzinfo=UTC),
        accepted_bars=96,
        skipped_bars=3,
        gaps=1,
        spread=0.00012,
        initial_balance=1000.0,
        signals=signal_metrics,
        trades=trades,
        source_timeframe="M1",
        csv_selection_elapsed_seconds=2.5,
        replay_elapsed_seconds=75.0,
    )
    assert summary.source_timeframe == "M1"
    assert math.isclose(summary.csv_selection_elapsed_seconds or -1.0, 2.5)
    assert math.isclose(summary.replay_elapsed_seconds or -1.0, 75.0)
    assert summary.opened_trades == 6
    assert summary.winning_trades == 3
    assert summary.losing_trades == 3
    assert math.isclose(summary.final_balance, 1060.0)
    assert math.isclose(summary.net_profit, 60.0)
    assert math.isclose(summary.average_winner, 60.0)
    assert math.isclose(summary.average_loser, -40.0)
    assert math.isclose(summary.maximum_winner, 100.0)
    assert math.isclose(summary.maximum_loser, -60.0)
    assert math.isclose(summary.maximum_drawdown, 100.0)
    assert math.isclose(summary.maximum_drawdown_percent, 100.0 / 1100.0 * 100.0)
    assert summary.maximum_consecutive_losses == 2
    assert summary.maximum_consecutive_wins == 1
    assert math.isclose(summary.peak_balance, 1100.0)
    assert math.isclose(summary.minimum_balance, 1000.0)
    assert summary.close_reason_count(REPLAY_CLOSE_STOP_LOSS) == 2
    assert summary.close_reason_count(REPLAY_CLOSE_TAKE_PROFIT) == 2
    assert summary.close_reason_count(REPLAY_CLOSE_PROFIT_DRAWDOWN) == 1
    assert summary.close_reason_count(REPLAY_CLOSE_SESSION_END) == 1

    _check_runtime_summary()
    _check_designer_dialog_contract()

    print("Algorithm Workspace Historical Summary result")
    print(f"  trades={summary.opened_trades}")
    print(f"  winners={summary.winning_trades}")
    print(f"  losers={summary.losing_trades}")
    print(f"  final_balance={summary.final_balance:.2f}")
    print(f"  net_profit={summary.net_profit:.2f}")
    print(f"  profit_factor={summary.profit_factor:.2f}")
    print(f"  maximum_drawdown_usd={summary.maximum_drawdown:.2f}")
    print(f"  maximum_drawdown_percent={summary.maximum_drawdown_percent:.4f}")
    print("  full_run_signal_metrics=True")
    print("  runtime_summary_on_completion=True")
    print("  designer_dialog_contract=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_HISTORICAL_SUMMARY_CHECK=OK")


if __name__ == "__main__":
    main()
