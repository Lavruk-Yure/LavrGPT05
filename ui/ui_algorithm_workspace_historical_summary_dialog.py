# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'algorithm_workspace_historical_summary_dialog.ui'
##
## Created by: Qt User Interface Compiler version 6.9.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (
    QCoreApplication,
    QDate,
    QDateTime,
    QLocale,
    QMetaObject,
    QObject,
    QPoint,
    QRect,
    QSize,
    QTime,
    QUrl,
    Qt,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QCursor,
    QFont,
    QFontDatabase,
    QGradient,
    QIcon,
    QImage,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPalette,
    QPixmap,
    QRadialGradient,
    QTransform,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)


class Ui_AlgorithmWorkspaceHistoricalSummaryDialog(object):
    def setupUi(self, AlgorithmWorkspaceHistoricalSummaryDialog):
        if not AlgorithmWorkspaceHistoricalSummaryDialog.objectName():
            AlgorithmWorkspaceHistoricalSummaryDialog.setObjectName(
                "AlgorithmWorkspaceHistoricalSummaryDialog"
            )
        AlgorithmWorkspaceHistoricalSummaryDialog.resize(700, 650)
        AlgorithmWorkspaceHistoricalSummaryDialog.setMinimumSize(QSize(620, 580))
        self.verticalLayout = QVBoxLayout(AlgorithmWorkspaceHistoricalSummaryDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.lblTitle = QLabel(AlgorithmWorkspaceHistoricalSummaryDialog)
        self.lblTitle.setObjectName("lblTitle")
        self.lblTitle.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblTitle)

        self.grpData = QGroupBox(AlgorithmWorkspaceHistoricalSummaryDialog)
        self.grpData.setObjectName("grpData")
        self.gridData = QGridLayout(self.grpData)
        self.gridData.setObjectName("gridData")
        self.lblSymbolCaption = QLabel(self.grpData)
        self.lblSymbolCaption.setObjectName("lblSymbolCaption")

        self.gridData.addWidget(self.lblSymbolCaption, 0, 0, 1, 1)

        self.lblSymbol = QLabel(self.grpData)
        self.lblSymbol.setObjectName("lblSymbol")

        self.gridData.addWidget(self.lblSymbol, 0, 1, 1, 1)

        self.lblTimeframeCaption = QLabel(self.grpData)
        self.lblTimeframeCaption.setObjectName("lblTimeframeCaption")

        self.gridData.addWidget(self.lblTimeframeCaption, 0, 2, 1, 1)

        self.lblTimeframe = QLabel(self.grpData)
        self.lblTimeframe.setObjectName("lblTimeframe")

        self.gridData.addWidget(self.lblTimeframe, 0, 3, 1, 1)

        self.lblPeriodCaption = QLabel(self.grpData)
        self.lblPeriodCaption.setObjectName("lblPeriodCaption")

        self.gridData.addWidget(self.lblPeriodCaption, 1, 0, 1, 1)

        self.lblPeriod = QLabel(self.grpData)
        self.lblPeriod.setObjectName("lblPeriod")

        self.gridData.addWidget(self.lblPeriod, 1, 1, 1, 3)

        self.lblBarsCaption = QLabel(self.grpData)
        self.lblBarsCaption.setObjectName("lblBarsCaption")

        self.gridData.addWidget(self.lblBarsCaption, 2, 0, 1, 1)

        self.lblBars = QLabel(self.grpData)
        self.lblBars.setObjectName("lblBars")

        self.gridData.addWidget(self.lblBars, 2, 1, 1, 1)

        self.lblSpreadCaption = QLabel(self.grpData)
        self.lblSpreadCaption.setObjectName("lblSpreadCaption")

        self.gridData.addWidget(self.lblSpreadCaption, 2, 2, 1, 1)

        self.lblSpread = QLabel(self.grpData)
        self.lblSpread.setObjectName("lblSpread")

        self.gridData.addWidget(self.lblSpread, 2, 3, 1, 1)

        self.lblSourceTimeframeCaption = QLabel(self.grpData)
        self.lblSourceTimeframeCaption.setObjectName("lblSourceTimeframeCaption")

        self.gridData.addWidget(self.lblSourceTimeframeCaption, 3, 0, 1, 1)

        self.lblSourceTimeframe = QLabel(self.grpData)
        self.lblSourceTimeframe.setObjectName("lblSourceTimeframe")

        self.gridData.addWidget(self.lblSourceTimeframe, 3, 1, 1, 1)

        self.lblCsvSelectionTimeCaption = QLabel(self.grpData)
        self.lblCsvSelectionTimeCaption.setObjectName("lblCsvSelectionTimeCaption")

        self.gridData.addWidget(self.lblCsvSelectionTimeCaption, 3, 2, 1, 1)

        self.lblCsvSelectionTime = QLabel(self.grpData)
        self.lblCsvSelectionTime.setObjectName("lblCsvSelectionTime")

        self.gridData.addWidget(self.lblCsvSelectionTime, 3, 3, 1, 1)

        self.lblReplayTimeCaption = QLabel(self.grpData)
        self.lblReplayTimeCaption.setObjectName("lblReplayTimeCaption")

        self.gridData.addWidget(self.lblReplayTimeCaption, 4, 0, 1, 1)

        self.lblReplayTime = QLabel(self.grpData)
        self.lblReplayTime.setObjectName("lblReplayTime")

        self.gridData.addWidget(self.lblReplayTime, 4, 1, 1, 1)

        self.verticalLayout.addWidget(self.grpData)

        self.grpResult = QGroupBox(AlgorithmWorkspaceHistoricalSummaryDialog)
        self.grpResult.setObjectName("grpResult")
        self.gridResult = QGridLayout(self.grpResult)
        self.gridResult.setObjectName("gridResult")
        self.lblInitialBalanceCaption = QLabel(self.grpResult)
        self.lblInitialBalanceCaption.setObjectName("lblInitialBalanceCaption")

        self.gridResult.addWidget(self.lblInitialBalanceCaption, 0, 0, 1, 1)

        self.lblInitialBalance = QLabel(self.grpResult)
        self.lblInitialBalance.setObjectName("lblInitialBalance")

        self.gridResult.addWidget(self.lblInitialBalance, 0, 1, 1, 1)

        self.lblFinalBalanceCaption = QLabel(self.grpResult)
        self.lblFinalBalanceCaption.setObjectName("lblFinalBalanceCaption")

        self.gridResult.addWidget(self.lblFinalBalanceCaption, 0, 2, 1, 1)

        self.lblFinalBalance = QLabel(self.grpResult)
        self.lblFinalBalance.setObjectName("lblFinalBalance")

        self.gridResult.addWidget(self.lblFinalBalance, 0, 3, 1, 1)

        self.lblNetPnlCaption = QLabel(self.grpResult)
        self.lblNetPnlCaption.setObjectName("lblNetPnlCaption")

        self.gridResult.addWidget(self.lblNetPnlCaption, 1, 0, 1, 1)

        self.lblNetPnl = QLabel(self.grpResult)
        self.lblNetPnl.setObjectName("lblNetPnl")

        self.gridResult.addWidget(self.lblNetPnl, 1, 1, 1, 1)

        self.lblProfitFactorCaption = QLabel(self.grpResult)
        self.lblProfitFactorCaption.setObjectName("lblProfitFactorCaption")

        self.gridResult.addWidget(self.lblProfitFactorCaption, 1, 2, 1, 1)

        self.lblProfitFactor = QLabel(self.grpResult)
        self.lblProfitFactor.setObjectName("lblProfitFactor")

        self.gridResult.addWidget(self.lblProfitFactor, 1, 3, 1, 1)

        self.lblTradesCaption = QLabel(self.grpResult)
        self.lblTradesCaption.setObjectName("lblTradesCaption")

        self.gridResult.addWidget(self.lblTradesCaption, 2, 0, 1, 1)

        self.lblTrades = QLabel(self.grpResult)
        self.lblTrades.setObjectName("lblTrades")

        self.gridResult.addWidget(self.lblTrades, 2, 1, 1, 1)

        self.lblWinRateCaption = QLabel(self.grpResult)
        self.lblWinRateCaption.setObjectName("lblWinRateCaption")

        self.gridResult.addWidget(self.lblWinRateCaption, 2, 2, 1, 1)

        self.lblWinRate = QLabel(self.grpResult)
        self.lblWinRate.setObjectName("lblWinRate")

        self.gridResult.addWidget(self.lblWinRate, 2, 3, 1, 1)

        self.lblWinnersCaption = QLabel(self.grpResult)
        self.lblWinnersCaption.setObjectName("lblWinnersCaption")

        self.gridResult.addWidget(self.lblWinnersCaption, 3, 0, 1, 1)

        self.lblWinners = QLabel(self.grpResult)
        self.lblWinners.setObjectName("lblWinners")

        self.gridResult.addWidget(self.lblWinners, 3, 1, 1, 1)

        self.lblLosersCaption = QLabel(self.grpResult)
        self.lblLosersCaption.setObjectName("lblLosersCaption")

        self.gridResult.addWidget(self.lblLosersCaption, 3, 2, 1, 1)

        self.lblLosers = QLabel(self.grpResult)
        self.lblLosers.setObjectName("lblLosers")

        self.gridResult.addWidget(self.lblLosers, 3, 3, 1, 1)

        self.lblBreakEvenCaption = QLabel(self.grpResult)
        self.lblBreakEvenCaption.setObjectName("lblBreakEvenCaption")

        self.gridResult.addWidget(self.lblBreakEvenCaption, 4, 0, 1, 1)

        self.lblBreakEven = QLabel(self.grpResult)
        self.lblBreakEven.setObjectName("lblBreakEven")

        self.gridResult.addWidget(self.lblBreakEven, 4, 1, 1, 1)

        self.lblMaxDrawdownCaption = QLabel(self.grpResult)
        self.lblMaxDrawdownCaption.setObjectName("lblMaxDrawdownCaption")

        self.gridResult.addWidget(self.lblMaxDrawdownCaption, 5, 0, 1, 1)

        self.lblMaxDrawdown = QLabel(self.grpResult)
        self.lblMaxDrawdown.setObjectName("lblMaxDrawdown")

        self.gridResult.addWidget(self.lblMaxDrawdown, 5, 1, 1, 1)

        self.lblAverageTradeCaption = QLabel(self.grpResult)
        self.lblAverageTradeCaption.setObjectName("lblAverageTradeCaption")

        self.gridResult.addWidget(self.lblAverageTradeCaption, 5, 2, 1, 1)

        self.lblAverageTrade = QLabel(self.grpResult)
        self.lblAverageTrade.setObjectName("lblAverageTrade")

        self.gridResult.addWidget(self.lblAverageTrade, 5, 3, 1, 1)

        self.verticalLayout.addWidget(self.grpResult)

        self.grpSignals = QGroupBox(AlgorithmWorkspaceHistoricalSummaryDialog)
        self.grpSignals.setObjectName("grpSignals")
        self.gridSignals = QGridLayout(self.grpSignals)
        self.gridSignals.setObjectName("gridSignals")
        self.lblSignalsCaption = QLabel(self.grpSignals)
        self.lblSignalsCaption.setObjectName("lblSignalsCaption")

        self.gridSignals.addWidget(self.lblSignalsCaption, 0, 0, 1, 1)

        self.lblSignals = QLabel(self.grpSignals)
        self.lblSignals.setObjectName("lblSignals")

        self.gridSignals.addWidget(self.lblSignals, 0, 1, 1, 1)

        self.lblDirectionsCaption = QLabel(self.grpSignals)
        self.lblDirectionsCaption.setObjectName("lblDirectionsCaption")

        self.gridSignals.addWidget(self.lblDirectionsCaption, 0, 2, 1, 1)

        self.lblDirections = QLabel(self.grpSignals)
        self.lblDirections.setObjectName("lblDirections")

        self.gridSignals.addWidget(self.lblDirections, 0, 3, 1, 1)

        self.lblAlligatorCaption = QLabel(self.grpSignals)
        self.lblAlligatorCaption.setObjectName("lblAlligatorCaption")

        self.gridSignals.addWidget(self.lblAlligatorCaption, 1, 0, 1, 1)

        self.lblAlligator = QLabel(self.grpSignals)
        self.lblAlligator.setObjectName("lblAlligator")

        self.gridSignals.addWidget(self.lblAlligator, 1, 1, 1, 1)

        self.lblRejectsCaption = QLabel(self.grpSignals)
        self.lblRejectsCaption.setObjectName("lblRejectsCaption")

        self.gridSignals.addWidget(self.lblRejectsCaption, 1, 2, 1, 1)

        self.lblRejects = QLabel(self.grpSignals)
        self.lblRejects.setObjectName("lblRejects")

        self.gridSignals.addWidget(self.lblRejects, 1, 3, 1, 1)

        self.lblMacdQualityCaption = QLabel(self.grpSignals)
        self.lblMacdQualityCaption.setObjectName("lblMacdQualityCaption")

        self.gridSignals.addWidget(self.lblMacdQualityCaption, 2, 0, 1, 1)

        self.lblMacdQuality = QLabel(self.grpSignals)
        self.lblMacdQuality.setObjectName("lblMacdQuality")

        self.gridSignals.addWidget(self.lblMacdQuality, 2, 1, 1, 1)

        self.lblMacdQualityRejectsCaption = QLabel(self.grpSignals)
        self.lblMacdQualityRejectsCaption.setObjectName("lblMacdQualityRejectsCaption")

        self.gridSignals.addWidget(self.lblMacdQualityRejectsCaption, 2, 2, 1, 1)

        self.lblMacdQualityRejects = QLabel(self.grpSignals)
        self.lblMacdQualityRejects.setObjectName("lblMacdQualityRejects")

        self.gridSignals.addWidget(self.lblMacdQualityRejects, 2, 3, 1, 1)

        self.verticalLayout.addWidget(self.grpSignals)

        self.grpExits = QGroupBox(AlgorithmWorkspaceHistoricalSummaryDialog)
        self.grpExits.setObjectName("grpExits")
        self.gridExits = QGridLayout(self.grpExits)
        self.gridExits.setObjectName("gridExits")
        self.lblStopLossCaption = QLabel(self.grpExits)
        self.lblStopLossCaption.setObjectName("lblStopLossCaption")

        self.gridExits.addWidget(self.lblStopLossCaption, 0, 0, 1, 1)

        self.lblStopLoss = QLabel(self.grpExits)
        self.lblStopLoss.setObjectName("lblStopLoss")

        self.gridExits.addWidget(self.lblStopLoss, 0, 1, 1, 1)

        self.lblTakeProfitCaption = QLabel(self.grpExits)
        self.lblTakeProfitCaption.setObjectName("lblTakeProfitCaption")

        self.gridExits.addWidget(self.lblTakeProfitCaption, 0, 2, 1, 1)

        self.lblTakeProfit = QLabel(self.grpExits)
        self.lblTakeProfit.setObjectName("lblTakeProfit")

        self.gridExits.addWidget(self.lblTakeProfit, 0, 3, 1, 1)

        self.lblProfitDrawdownCaption = QLabel(self.grpExits)
        self.lblProfitDrawdownCaption.setObjectName("lblProfitDrawdownCaption")

        self.gridExits.addWidget(self.lblProfitDrawdownCaption, 1, 0, 1, 1)

        self.lblProfitDrawdown = QLabel(self.grpExits)
        self.lblProfitDrawdown.setObjectName("lblProfitDrawdown")

        self.gridExits.addWidget(self.lblProfitDrawdown, 1, 1, 1, 1)

        self.lblSessionEndCaption = QLabel(self.grpExits)
        self.lblSessionEndCaption.setObjectName("lblSessionEndCaption")

        self.gridExits.addWidget(self.lblSessionEndCaption, 1, 2, 1, 1)

        self.lblSessionEnd = QLabel(self.grpExits)
        self.lblSessionEnd.setObjectName("lblSessionEnd")

        self.gridExits.addWidget(self.lblSessionEnd, 1, 3, 1, 1)

        self.lblOtherCaption = QLabel(self.grpExits)
        self.lblOtherCaption.setObjectName("lblOtherCaption")

        self.gridExits.addWidget(self.lblOtherCaption, 2, 0, 1, 1)

        self.lblOther = QLabel(self.grpExits)
        self.lblOther.setObjectName("lblOther")

        self.gridExits.addWidget(self.lblOther, 2, 1, 1, 1)

        self.verticalLayout.addWidget(self.grpExits)

        self.horizontalLayoutButtons = QHBoxLayout()
        self.horizontalLayoutButtons.setObjectName("horizontalLayoutButtons")
        self.horizontalSpacer = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayoutButtons.addItem(self.horizontalSpacer)

        self.btnClose = QPushButton(AlgorithmWorkspaceHistoricalSummaryDialog)
        self.btnClose.setObjectName("btnClose")

        self.horizontalLayoutButtons.addWidget(self.btnClose)

        self.verticalLayout.addLayout(self.horizontalLayoutButtons)

        self.retranslateUi(AlgorithmWorkspaceHistoricalSummaryDialog)

        QMetaObject.connectSlotsByName(AlgorithmWorkspaceHistoricalSummaryDialog)

    # setupUi

    def retranslateUi(self, AlgorithmWorkspaceHistoricalSummaryDialog):
        AlgorithmWorkspaceHistoricalSummaryDialog.setWindowTitle(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.windowTitle]",
                None,
            )
        )
        self.lblTitle.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.title]",
                None,
            )
        )
        self.grpData.setTitle(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.grpData]",
                None,
            )
        )
        self.lblSymbolCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.symbol]",
                None,
            )
        )
        self.lblSymbol.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblTimeframeCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.timeframe]",
                None,
            )
        )
        self.lblTimeframe.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblPeriodCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.period]",
                None,
            )
        )
        self.lblPeriod.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblBarsCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.bars]",
                None,
            )
        )
        self.lblBars.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblSpreadCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.spread]",
                None,
            )
        )
        self.lblSpread.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblSourceTimeframeCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.sourceTimeframe]",
                None,
            )
        )
        self.lblSourceTimeframe.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblCsvSelectionTimeCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.csvSelectionTime]",
                None,
            )
        )
        self.lblCsvSelectionTime.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblReplayTimeCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.replayTime]",
                None,
            )
        )
        self.lblReplayTime.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.grpResult.setTitle(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.grpResult]",
                None,
            )
        )
        self.lblInitialBalanceCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.initialBalance]",
                None,
            )
        )
        self.lblInitialBalance.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblFinalBalanceCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.finalBalance]",
                None,
            )
        )
        self.lblFinalBalance.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblNetPnlCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.netPnl]",
                None,
            )
        )
        self.lblNetPnl.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblProfitFactorCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.profitFactor]",
                None,
            )
        )
        self.lblProfitFactor.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblTradesCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.trades]",
                None,
            )
        )
        self.lblTrades.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblWinRateCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.winRate]",
                None,
            )
        )
        self.lblWinRate.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblWinnersCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.winners]",
                None,
            )
        )
        self.lblWinners.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblLosersCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.losers]",
                None,
            )
        )
        self.lblLosers.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblBreakEvenCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.breakEven]",
                None,
            )
        )
        self.lblBreakEven.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblMaxDrawdownCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.maxDrawdown]",
                None,
            )
        )
        self.lblMaxDrawdown.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblAverageTradeCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.averageTrade]",
                None,
            )
        )
        self.lblAverageTrade.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.grpSignals.setTitle(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.grpSignals]",
                None,
            )
        )
        self.lblSignalsCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.signals]",
                None,
            )
        )
        self.lblSignals.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblDirectionsCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.directions]",
                None,
            )
        )
        self.lblDirections.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblAlligatorCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.alligator]",
                None,
            )
        )
        self.lblAlligator.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblRejectsCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.rejects]",
                None,
            )
        )
        self.lblRejects.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblMacdQualityCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.macdQuality]",
                None,
            )
        )
        self.lblMacdQuality.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblMacdQualityRejectsCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.macdQualityRejects]",
                None,
            )
        )
        self.lblMacdQualityRejects.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.grpExits.setTitle(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.grpExits]",
                None,
            )
        )
        self.lblStopLossCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "STOP_LOSS:", None
            )
        )
        self.lblStopLoss.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblTakeProfitCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "TAKE_PROFIT:", None
            )
        )
        self.lblTakeProfit.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblProfitDrawdownCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "PROFIT_DRAWDOWN:", None
            )
        )
        self.lblProfitDrawdown.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblSessionEndCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "SESSION_END:", None
            )
        )
        self.lblSessionEnd.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.lblOtherCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.other]",
                None,
            )
        )
        self.lblOther.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog", "\u2014", None
            )
        )
        self.btnClose.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoricalSummaryDialog",
                "[AlgorithmWorkspaceHistoricalSummaryDialog.btnClose]",
                None,
            )
        )

    # retranslateUi
