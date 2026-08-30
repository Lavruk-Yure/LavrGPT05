# -*- coding: utf-8 -*-
"""Designer-based final Historical Replay summary dialog."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QWidget

from core.lang_manager import LangManager
from core.workspace_historical_summary import WorkspaceHistoricalReplaySummary
from core.workspace_replay_execution import (
    REPLAY_CLOSE_PROFIT_DRAWDOWN,
    REPLAY_CLOSE_SESSION_END,
    REPLAY_CLOSE_STOP_LOSS,
    REPLAY_CLOSE_TAKE_PROFIT,
)
from ui.ui_algorithm_workspace_historical_summary_dialog import (
    Ui_AlgorithmWorkspaceHistoricalSummaryDialog,
)


def format_replay_elapsed_duration(seconds: float | None) -> str:
    """Format one measured Replay duration for compact UI display."""
    if seconds is None:
        return "—"
    total_seconds = max(0, int(round(float(seconds))))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class AlgorithmWorkspaceHistoricalSummaryDialog(QDialog):
    """Show immutable facts calculated after one completed Replay run."""

    def __init__(
        self,
        summary: WorkspaceHistoricalReplaySummary,
        lang_mgr: LangManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._summary = summary
        self._lang_mgr = lang_mgr
        self.ui = Ui_AlgorithmWorkspaceHistoricalSummaryDialog()
        self.ui.setupUi(self)
        self.ui.btnClose.clicked.connect(self.accept)
        self.apply_translation()
        self._populate_values()

    def apply_translation(self) -> None:
        """Apply fallback-backed labels without editing strings.json."""
        self.setWindowTitle(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.windowTitle",
                "Historical Replay summary",
            )
        )
        self.ui.lblTitle.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.title",
                "Historical Replay completed. The values below are frozen "
                "from this run.",
            )
        )
        self.ui.grpData.setTitle(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.grpData",
                "Data",
            )
        )
        self.ui.lblSymbolCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.symbol",
                "Symbol:",
            )
        )
        self.ui.lblTimeframeCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.timeframe",
                "Timeframe:",
            )
        )
        self.ui.lblSourceTimeframeCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.sourceTimeframe",
                "Source timeframe:",
            )
        )
        self.ui.lblCsvSelectionTimeCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.csvSelectionTime",
                "CSV selection time:",
            )
        )
        self.ui.lblReplayTimeCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.replayTime",
                "Replay run time:",
            )
        )
        self.ui.lblPeriodCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.period",
                "Period:",
            )
        )
        self.ui.lblBarsCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.bars",
                "Bars / skipped / gaps:",
            )
        )
        self.ui.lblSpreadCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.spread",
                "Spread:",
            )
        )
        self.ui.grpResult.setTitle(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.grpResult",
                "Trading result",
            )
        )
        self.ui.lblInitialBalanceCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.initialBalance",
                "Initial balance:",
            )
        )
        self.ui.lblFinalBalanceCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.finalBalance",
                "Final balance:",
            )
        )
        self.ui.lblNetPnlCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.netPnl",
                "Net PnL:",
            )
        )
        self.ui.lblProfitFactorCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.profitFactor",
                "Profit factor:",
            )
        )
        self.ui.lblTradesCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.trades",
                "Trades:",
            )
        )
        self.ui.lblWinRateCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.winRate",
                "Win rate:",
            )
        )
        self.ui.lblWinnersCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.winners",
                "Winners:",
            )
        )
        self.ui.lblLosersCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.losers",
                "Losers:",
            )
        )
        self.ui.lblBreakEvenCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.breakEven",
                "Break-even:",
            )
        )
        self.ui.lblMaxDrawdownCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.maxDrawdown",
                "Max drawdown:",
            )
        )
        self.ui.lblAverageTradeCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.averageTrade",
                "Average trade:",
            )
        )
        self.ui.grpSignals.setTitle(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.grpSignals",
                "Signals",
            )
        )
        self.ui.lblSignalsCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.signals",
                "MACD signals:",
            )
        )
        self.ui.lblDirectionsCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.directions",
                "BUY / SELL:",
            )
        )
        self.ui.lblAlligatorCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.alligator",
                "Alligator ALLOW / REJECT:",
            )
        )
        self.ui.lblRejectsCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.rejects",
                "Warm-up / risk rejects:",
            )
        )
        self.ui.lblMacdQualityCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.macdQuality",
                "MACD Quality accepted / rejected:",
            )
        )
        self.ui.lblMacdQualityRejectsCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.macdQualityRejects",
                "Quality rejects N / W / D / F:",
            )
        )
        self.ui.grpExits.setTitle(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.grpExits",
                "Exit reasons",
            )
        )
        self.ui.lblStopLossCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.stopLoss",
                "Stop loss:",
            )
        )
        self.ui.lblTakeProfitCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.takeProfit",
                "Take profit:",
            )
        )
        self.ui.lblProfitDrawdownCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.profitDrawdown",
                "Profit drawdown:",
            )
        )
        self.ui.lblSessionEndCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.sessionEnd",
                "Replay completion:",
            )
        )
        self.ui.lblOtherCaption.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.other",
                "Other:",
            )
        )
        self.ui.btnClose.setText(
            self._tr(
                "AlgorithmWorkspaceHistoricalSummaryDialog.btnClose",
                "Close",
            )
        )

    def _populate_values(self) -> None:
        summary = self._summary
        self.ui.lblSymbol.setText(summary.symbol)
        self.ui.lblTimeframe.setText(summary.timeframe)
        self.ui.lblSourceTimeframe.setText(summary.source_timeframe)
        self.ui.lblCsvSelectionTime.setText(
            format_replay_elapsed_duration(
                summary.csv_selection_elapsed_seconds
            )
        )
        self.ui.lblReplayTime.setText(
            format_replay_elapsed_duration(summary.replay_elapsed_seconds)
        )
        self.ui.lblPeriod.setText(
            f"{summary.period_start:%Y-%m-%d %H:%M UTC} — "
            f"{summary.period_end:%Y-%m-%d %H:%M UTC}"
        )
        self.ui.lblBars.setText(
            f"{summary.accepted_bars} / {summary.skipped_bars} / {summary.gaps}"
        )
        self.ui.lblSpread.setText(f"{summary.spread:.8f}".rstrip("0").rstrip("."))
        self.ui.lblInitialBalance.setText(f"{summary.initial_balance:.2f} USD")
        self.ui.lblFinalBalance.setText(f"{summary.final_balance:.2f} USD")
        self.ui.lblNetPnl.setText(f"{summary.net_profit:+.2f} USD")
        self.ui.lblProfitFactor.setText(
            "—" if summary.profit_factor is None else f"{summary.profit_factor:.2f}"
        )
        self.ui.lblTrades.setText(str(summary.opened_trades))
        self.ui.lblWinRate.setText(f"{summary.win_rate_percent:.1f}%")
        self.ui.lblWinners.setText(str(summary.winning_trades))
        self.ui.lblLosers.setText(str(summary.losing_trades))
        self.ui.lblBreakEven.setText(str(summary.break_even_trades))
        self.ui.lblMaxDrawdown.setText(
            f"{summary.maximum_drawdown:.2f} USD / "
            f"{summary.maximum_drawdown_percent:.2f}%"
        )
        self.ui.lblAverageTrade.setText(f"{summary.average_trade:+.2f} USD")

        signals = summary.signals
        self.ui.lblSignals.setText(str(signals.total))
        self.ui.lblDirections.setText(f"{signals.buy} / {signals.sell}")
        self.ui.lblAlligator.setText(
            f"{signals.alligator_allow} / {signals.alligator_reject}"
        )
        self.ui.lblRejects.setText(
            f"{signals.warmup_rejects} / {signals.risk_rejects}"
        )
        self.ui.lblMacdQuality.setText(
            f"{signals.macd_quality_accept} / {signals.macd_quality_reject}"
        )
        self.ui.lblMacdQualityRejects.setText(
            f"{signals.macd_extremum_not_found} / "
            f"{signals.macd_extremum_too_weak} / "
            f"{signals.macd_distance_too_small} / "
            f"{signals.macd_cross_too_flat}"
        )

        known_reasons = {
            REPLAY_CLOSE_STOP_LOSS,
            REPLAY_CLOSE_TAKE_PROFIT,
            REPLAY_CLOSE_PROFIT_DRAWDOWN,
            REPLAY_CLOSE_SESSION_END,
        }
        self.ui.lblStopLoss.setText(
            str(summary.close_reason_count(REPLAY_CLOSE_STOP_LOSS))
        )
        self.ui.lblTakeProfit.setText(
            str(summary.close_reason_count(REPLAY_CLOSE_TAKE_PROFIT))
        )
        self.ui.lblProfitDrawdown.setText(
            str(summary.close_reason_count(REPLAY_CLOSE_PROFIT_DRAWDOWN))
        )
        self.ui.lblSessionEnd.setText(
            str(summary.close_reason_count(REPLAY_CLOSE_SESSION_END))
        )
        other = sum(
            count
            for reason, count in summary.close_reasons
            if reason not in known_reasons
        )
        self.ui.lblOther.setText(str(other))

    def _tr(self, key: str, fallback: str) -> str:
        if self._lang_mgr is None:
            return fallback
        return self._lang_mgr.tr(key, fallback)
