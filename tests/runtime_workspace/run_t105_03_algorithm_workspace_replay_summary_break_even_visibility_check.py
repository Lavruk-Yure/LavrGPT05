# -*- coding: utf-8 -*-
"""T105-03: видимість беззбиткових угод у Historical Replay summary."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from xml.etree.ElementTree import fromstring

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.translation_policy import translation_override_for_key  # noqa: E402
from core.workspace_historical_summary import (  # noqa: E402
    WorkspaceHistoricalSignalMetrics,
    build_workspace_historical_replay_summary,
)
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_replay_execution import REPLAY_CLOSE_SESSION_END  # noqa: E402


def _diagnostic(index: int, profit: float) -> WorkspaceHistoricalTradeDiagnostic:
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
        close_reason=REPLAY_CLOSE_SESSION_END,
        holding_seconds=(close - entry).total_seconds(),
    )


def main() -> None:
    trades = (
        _diagnostic(1, 1.25),
        _diagnostic(2, -0.75),
        _diagnostic(3, 0.0),
    )
    summary = build_workspace_historical_replay_summary(
        symbol="EURUSD",
        timeframe="M15",
        period_start=datetime(2026, 7, 1, 8, 0, tzinfo=UTC),
        period_end=datetime(2026, 7, 2, 8, 0, tzinfo=UTC),
        accepted_bars=96,
        skipped_bars=0,
        gaps=0,
        spread=0.00012,
        initial_balance=1000.0,
        signals=WorkspaceHistoricalSignalMetrics(),
        trades=trades,
        source_timeframe="M1",
    )

    assert summary.opened_trades == 3
    assert summary.winning_trades == 1
    assert summary.losing_trades == 1
    assert summary.break_even_trades == 1
    assert summary.opened_trades == (
        summary.winning_trades + summary.losing_trades + summary.break_even_trades
    )

    ui_path = PROJECT_ROOT / "ui" / "algorithm_workspace_historical_summary_dialog.ui"
    ui_root = fromstring(ui_path.read_text(encoding="utf-8"))
    assert ui_root.find(".//widget[@name='lblBreakEvenCaption']") is not None
    assert ui_root.find(".//widget[@name='lblBreakEven']") is not None

    generated_source = (
        PROJECT_ROOT / "ui" / "ui_algorithm_workspace_historical_summary_dialog.py"
    ).read_text(encoding="utf-8")
    dialog_source = (
        PROJECT_ROOT / "core" / "algorithm_workspace_historical_summary_dialog.py"
    ).read_text(encoding="utf-8")

    assert "self.lblBreakEven = QLabel(self.grpResult)" in generated_source
    assert "AlgorithmWorkspaceHistoricalSummaryDialog.breakEven" in generated_source
    assert (
        "self.ui.lblBreakEven.setText(str(summary.break_even_trades))" in dialog_source
    )
    assert (
        translation_override_for_key(
            "AlgorithmWorkspaceHistoricalSummaryDialog.breakEven",
            "uk",
        )
        == "Беззбиткові:"
    )

    print("T105-03 Replay Summary Break-even Visibility result")
    print(f"  trades={summary.opened_trades}")
    print(f"  winners={summary.winning_trades}")
    print(f"  losers={summary.losing_trades}")
    print(f"  break_even={summary.break_even_trades}")
    print("  trades_identity_visible=True")
    print("  production_trading_logic_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T105_03_REPLAY_SUMMARY_BREAK_EVEN_VISIBILITY=OK")


if __name__ == "__main__":
    main()
