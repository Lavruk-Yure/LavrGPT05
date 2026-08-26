# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'algorithm_workspace_historical_summary_dialog.ui'
##
## Created by: Qt User Interface Compiler version 6.9.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QDialog, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QSpacerItem, QVBoxLayout, QWidget)

class Ui_AlgorithmWorkspaceHistoricalSummaryDialog(object):
    def setupUi(self, AlgorithmWorkspaceHistoricalSummaryDialog):
        if not AlgorithmWorkspaceHistoricalSummaryDialog.objectName():
            AlgorithmWorkspaceHistoricalSummaryDialog.setObjectName(u"AlgorithmWorkspaceHistoricalSummaryDialog")
        AlgorithmWorkspaceHistoricalSummaryDialog.resize(700, 650)
        AlgorithmWorkspaceHistoricalSummaryDialog.setMinimumSize(QSize(620, 580))
        self.verticalLayout = QVBoxLayout(AlgorithmWorkspaceHistoricalSummaryDialog)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.lblTitle = QLabel(AlgorithmWorkspaceHistoricalSummaryDialog)
        self.lblTitle.setObjectName(u"lblTitle")
        self.lblTitle.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblTitle)

        self.grpData = QGroupBox(AlgorithmWorkspaceHistoricalSummaryDialog)
        self.grpData.setObjectName(u"grpData")
        self.gridData = QGridLayout(self.grpData)
        self.gridData.setObjectName(u"gridData")
        self.lblSymbolCaption = QLabel(self.grpData)
        self.lblSymbolCaption.setObjectName(u"lblSymbolCaption")

        self.gridData.addWidget(self.lblSymbolCaption, 0, 0, 1, 1)

        self.lblSymbol = QLabel(self.grpData)
        self.lblSymbol.setObjectName(u"lblSymbol")

        self.gridData.addWidget(self.lblSymbol, 0, 1, 1, 1)

        self.lblTimeframeCaption = QLabel(self.grpData)
        self.lblTimeframeCaption.setObjectName(u"lblTimeframeCaption")

        self.gridData.addWidget(self.lblTimeframeCaption, 0, 2, 1, 1)

        self.lblTimeframe = QLabel(self.grpData)
        self.lblTimeframe.setObjectName(u"lblTimeframe")

        self.gridData.addWidget(self.lblTimeframe, 0, 3, 1, 1)

        self.lblPeriodCaption = QLabel(self.grpData)
        self.lblPeriodCaption.setObjectName(u"lblPeriodCaption")

        self.gridData.addWidget(self.lblPeriodCaption, 1, 0, 1, 1)

        self.lblPeriod = QLabel(self.grpData)
        self.lblPeriod.setObjectName(u"lblPeriod")

        self.gridData.addWidget(self.lblPeriod, 1, 1, 1, 3)

        self.lblBarsCaption = QLabel(self.grpData)
        self.lblBarsCaption.setObjectName(u"lblBarsCaption")

        self.gridData.addWidget(self.lblBarsCaption, 2, 0, 1, 1)

        self.lblBars = QLabel(self.grpData)
        self.lblBars.setObjectName(u"lblBars")

        self.gridData.addWidget(self.lblBars, 2, 1, 1, 1)

        self.lblSpreadCaption = QLabel(self.grpData)
        self.lblSpreadCaption.setObjectName(u"lblSpreadCaption")

        self.gridData.addWidget(self.lblSpreadCaption, 2, 2, 1, 1)

        self.lblSpread = QLabel(self.grpData)
        self.lblSpread.setObjectName(u"lblSpread")

        self.gridData.addWidget(self.lblSpread, 2, 3, 1, 1)

        self.lblSourceTimeframeCaption = QLabel(self.grpData)
        self.lblSourceTimeframeCaption.setObjectName(u"lblSourceTimeframeCaption")

        self.gridData.addWidget(self.lblSourceTimeframeCaption, 3, 0, 1, 1)

        self.lblSourceTimeframe = QLabel(self.grpData)
        self.lblSourceTimeframe.setObjectName(u"lblSourceTimeframe")

        self.gridData.addWidget(self.lblSourceTimeframe, 3, 1, 1, 1)

        self.lblCsvSelectionTimeCaption = QLabel(self.grpData)
        self.lblCsvSelectionTimeCaption.setObjectName(u"lblCsvSelectionTimeCaption")

        self.gridData.addWidget(self.lblCsvSelectionTimeCaption, 3, 2, 1, 1)

        self.lblCsvSelectionTime = QLabel(self.grpData)
        self.lblCsvSelectionTime.setObjectName(u"lblCsvSelectionTime")

        self.gridData.addWidget(self.lblCsvSelectionTime, 3, 3, 1, 1)

        self.lblReplayTimeCaption = QLabel(self.grpData)
        self.lblReplayTimeCaption.setObjectName(u"lblReplayTimeCaption")

        self.gridData.addWidget(self.lblReplayTimeCaption, 4, 0, 1, 1)

        self.lblReplayTime = QLabel(self.grpData)
        self.lblReplayTime.setObjectName(u"lblReplayTime")

        self.gridData.addWidget(self.lblReplayTime, 4, 1, 1, 1)


        self.verticalLayout.addWidget(self.grpData)

        self.grpResult = QGroupBox(AlgorithmWorkspaceHistoricalSummaryDialog)
        self.grpResult.setObjectName(u"grpResult")
        self.gridResult = QGridLayout(self.grpResult)
        self.gridResult.setObjectName(u"gridResult")
        self.lblInitialBalanceCaption = QLabel(self.grpResult)
        self.lblInitialBalanceCaption.setObjectName(u"lblInitialBalanceCaption")

        self.gridResult.addWidget(self.lblInitialBalanceCaption, 0, 0, 1, 1)

        self.lblInitialBalance = QLabel(self.grpResult)
        self.lblInitialBalance.setObjectName(u"lblInitialBalance")

        self.gridResult.addWidget(self.lblInitialBalance, 0, 1, 1, 1)

        self.lblFinalBalanceCaption = QLabel(self.grpResult)
        self.lblFinalBalanceCaption.setObjectName(u"lblFinalBalanceCaption")

        self.gridResult.addWidget(self.lblFinalBalanceCaption, 0, 2, 1, 1)

        self.lblFinalBalance = QLabel(self.grpResult)
        self.lblFinalBalance.setObjectName(u"lblFinalBalance")

        self.gridResult.addWidget(self.lblFinalBalance, 0, 3, 1, 1)

        self.lblNetPnlCaption = QLabel(self.grpResult)
        self.lblNetPnlCaption.setObjectName(u"lblNetPnlCaption")

        self.gridResult.addWidget(self.lblNetPnlCaption, 1, 0, 1, 1)

        self.lblNetPnl = QLabel(self.grpResult)
        self.lblNetPnl.setObjectName(u"lblNetPnl")

        self.gridResult.addWidget(self.lblNetPnl, 1, 1, 1, 1)

        self.lblProfitFactorCaption = QLabel(self.grpResult)
        self.lblProfitFactorCaption.setObjectName(u"lblProfitFactorCaption")

        self.gridResult.addWidget(self.lblProfitFactorCaption, 1, 2, 1, 1)

        self.lblProfitFactor = QLabel(self.grpResult)
        self.lblProfitFactor.setObjectName(u"lblProfitFactor")

        self.gridResult.addWidget(self.lblProfitFactor, 1, 3, 1, 1)

        self.lblTradesCaption = QLabel(self.grpResult)
        self.lblTradesCaption.setObjectName(u"lblTradesCaption")

        self.gridResult.addWidget(self.lblTradesCaption, 2, 0, 1, 1)

        self.lblTrades = QLabel(self.grpResult)
        self.lblTrades.setObjectName(u"lblTrades")

        self.gridResult.addWidget(self.lblTrades, 2, 1, 1, 1)

        self.lblWinRateCaption = QLabel(self.grpResult)
        self.lblWinRateCaption.setObjectName(u"lblWinRateCaption")

        self.gridResult.addWidget(self.lblWinRateCaption, 2, 2, 1, 1)

        self.lblWinRate = QLabel(self.grpResult)
        self.lblWinRate.setObjectName(u"lblWinRate")

        self.gridResult.addWidget(self.lblWinRate, 2, 3, 1, 1)

        self.lblWinnersCaption = QLabel(self.grpResult)
        self.lblWinnersCaption.setObjectName(u"lblWinnersCaption")

        self.gridResult.addWidget(self.lblWinnersCaption, 3, 0, 1, 1)

        self.lblWinners = QLabel(self.grpResult)
        self.lblWinners.setObjectName(u"lblWinners")

        self.gridResult.addWidget(self.lblWinners, 3, 1, 1, 1)

        self.lblLosersCaption = QLabel(self.grpResult)
        self.lblLosersCaption.setObjectName(u"lblLosersCaption")

        self.gridResult.addWidget(self.lblLosersCaption, 3, 2, 1, 1)

        self.lblLosers = QLabel(self.grpResult)
        self.lblLosers.setObjectName(u"lblLosers")

        self.gridResult.addWidget(self.lblLosers, 3, 3, 1, 1)

        self.lblMaxDrawdownCaption = QLabel(self.grpResult)
        self.lblMaxDrawdownCaption.setObjectName(u"lblMaxDrawdownCaption")

        self.gridResult.addWidget(self.lblMaxDrawdownCaption, 4, 0, 1, 1)

        self.lblMaxDrawdown = QLabel(self.grpResult)
        self.lblMaxDrawdown.setObjectName(u"lblMaxDrawdown")

        self.gridResult.addWidget(self.lblMaxDrawdown, 4, 1, 1, 1)

        self.lblAverageTradeCaption = QLabel(self.grpResult)
        self.lblAverageTradeCaption.setObjectName(u"lblAverageTradeCaption")

        self.gridResult.addWidget(self.lblAverageTradeCaption, 4, 2, 1, 1)

        self.lblAverageTrade = QLabel(self.grpResult)
        self.lblAverageTrade.setObjectName(u"lblAverageTrade")

        self.gridResult.addWidget(self.lblAverageTrade, 4, 3, 1, 1)


        self.verticalLayout.addWidget(self.grpResult)

        self.grpSignals = QGroupBox(AlgorithmWorkspaceHistoricalSummaryDialog)
        self.grpSignals.setObjectName(u"grpSignals")
        self.gridSignals = QGridLayout(self.grpSignals)
        self.gridSignals.setObjectName(u"gridSignals")
        self.lblSignalsCaption = QLabel(self.grpSignals)
        self.lblSignalsCaption.setObjectName(u"lblSignalsCaption")

        self.gridSignals.addWidget(self.lblSignalsCaption, 0, 0, 1, 1)

        self.lblSignals = QLabel(self.grpSignals)
        self.lblSignals.setObjectName(u"lblSignals")

        self.gridSignals.addWidget(self.lblSignals, 0, 1, 1, 1)

        self.lblDirectionsCaption = QLabel(self.grpSignals)
        self.lblDirectionsCaption.setObjectName(u"lblDirectionsCaption")

        self.gridSignals.addWidget(self.lblDirectionsCaption, 0, 2, 1, 1)

        self.lblDirections = QLabel(self.grpSignals)
        self.lblDirections.setObjectName(u"lblDirections")

        self.gridSignals.addWidget(self.lblDirections, 0, 3, 1, 1)

        self.lblAlligatorCaption = QLabel(self.grpSignals)
        self.lblAlligatorCaption.setObjectName(u"lblAlligatorCaption")

        self.gridSignals.addWidget(self.lblAlligatorCaption, 1, 0, 1, 1)

        self.lblAlligator = QLabel(self.grpSignals)
        self.lblAlligator.setObjectName(u"lblAlligator")

        self.gridSignals.addWidget(self.lblAlligator, 1, 1, 1, 1)

        self.lblRejectsCaption = QLabel(self.grpSignals)
        self.lblRejectsCaption.setObjectName(u"lblRejectsCaption")

        self.gridSignals.addWidget(self.lblRejectsCaption, 1, 2, 1, 1)

        self.lblRejects = QLabel(self.grpSignals)
        self.lblRejects.setObjectName(u"lblRejects")

        self.gridSignals.addWidget(self.lblRejects, 1, 3, 1, 1)

        self.lblMacdQualityCaption = QLabel(self.grpSignals)
        self.lblMacdQualityCaption.setObjectName(u"lblMacdQualityCaption")

        self.gridSignals.addWidget(self.lblMacdQualityCaption, 2, 0, 1, 1)

        self.lblMacdQuality = QLabel(self.grpSignals)
        self.lblMacdQuality.setObjectName(u"lblMacdQuality")

        self.gridSignals.addWidget(self.lblMacdQuality, 2, 1, 1, 1)

        self.lblMacdQualityRejectsCaption = QLabel(self.grpSignals)
        self.lblMacdQualityRejectsCaption.setObjectName(u"lblMacdQualityRejectsCaption")

        self.gridSignals.addWidget(self.lblMacdQualityRejectsCaption, 2, 2, 1, 1)

        self.lblMacdQualityRejects = QLabel(self.grpSignals)
        self.lblMacdQualityRejects.setObjectName(u"lblMacdQualityRejects")

        self.gridSignals.addWidget(self.lblMacdQualityRejects, 2, 3, 1, 1)


        self.verticalLayout.addWidget(self.grpSignals)

        self.grpExits = QGroupBox(AlgorithmWorkspaceHistoricalSummaryDialog)
        self.grpExits.setObjectName(u"grpExits")
        self.gridExits = QGridLayout(self.grpExits)
        self.gridExits.setObjectName(u"gridExits")
        self.lblStopLossCaption = QLabel(self.grpExits)
        self.lblStopLossCaption.setObjectName(u"lblStopLossCaption")

        self.gridExits.addWidget(self.lblStopLossCaption, 0, 0, 1, 1)

        self.lblStopLoss = QLabel(self.grpExits)
        self.lblStopLoss.setObjectName(u"lblStopLoss")

        self.gridExits.addWidget(self.lblStopLoss, 0, 1, 1, 1)

        self.lblTakeProfitCaption = QLabel(self.grpExits)
        self.lblTakeProfitCaption.setObjectName(u"lblTakeProfitCaption")

        self.gridExits.addWidget(self.lblTakeProfitCaption, 0, 2, 1, 1)

        self.lblTakeProfit = QLabel(self.grpExits)
        self.lblTakeProfit.setObjectName(u"lblTakeProfit")

        self.gridExits.addWidget(self.lblTakeProfit, 0, 3, 1, 1)

        self.lblProfitDrawdownCaption = QLabel(self.grpExits)
        self.lblProfitDrawdownCaption.setObjectName(u"lblProfitDrawdownCaption")

        self.gridExits.addWidget(self.lblProfitDrawdownCaption, 1, 0, 1, 1)

        self.lblProfitDrawdown = QLabel(self.grpExits)
        self.lblProfitDrawdown.setObjectName(u"lblProfitDrawdown")

        self.gridExits.addWidget(self.lblProfitDrawdown, 1, 1, 1, 1)

        self.lblSessionEndCaption = QLabel(self.grpExits)
        self.lblSessionEndCaption.setObjectName(u"lblSessionEndCaption")

        self.gridExits.addWidget(self.lblSessionEndCaption, 1, 2, 1, 1)

        self.lblSessionEnd = QLabel(self.grpExits)
        self.lblSessionEnd.setObjectName(u"lblSessionEnd")

        self.gridExits.addWidget(self.lblSessionEnd, 1, 3, 1, 1)

        self.lblOtherCaption = QLabel(self.grpExits)
        self.lblOtherCaption.setObjectName(u"lblOtherCaption")

        self.gridExits.addWidget(self.lblOtherCaption, 2, 0, 1, 1)

        self.lblOther = QLabel(self.grpExits)
        self.lblOther.setObjectName(u"lblOther")

        self.gridExits.addWidget(self.lblOther, 2, 1, 1, 1)


        self.verticalLayout.addWidget(self.grpExits)

        self.horizontalLayoutButtons = QHBoxLayout()
        self.horizontalLayoutButtons.setObjectName(u"horizontalLayoutButtons")
        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutButtons.addItem(self.horizontalSpacer)

        self.btnClose = QPushButton(AlgorithmWorkspaceHistoricalSummaryDialog)
        self.btnClose.setObjectName(u"btnClose")

        self.horizontalLayoutButtons.addWidget(self.btnClose)


        self.verticalLayout.addLayout(self.horizontalLayoutButtons)


        self.retranslateUi(AlgorithmWorkspaceHistoricalSummaryDialog)

        QMetaObject.connectSlotsByName(AlgorithmWorkspaceHistoricalSummaryDialog)
    # setupUi

    def retranslateUi(self, AlgorithmWorkspaceHistoricalSummaryDialog):
        AlgorithmWorkspaceHistoricalSummaryDialog.setWindowTitle(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.windowTitle]", None))
        self.lblTitle.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.title]", None))
        self.grpData.setTitle(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.grpData]", None))
        self.lblSymbolCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.symbol]", None))
        self.lblSymbol.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblTimeframeCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.timeframe]", None))
        self.lblTimeframe.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblPeriodCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.period]", None))
        self.lblPeriod.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblBarsCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.bars]", None))
        self.lblBars.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblSpreadCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.spread]", None))
        self.lblSpread.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblSourceTimeframeCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.sourceTimeframe]", None))
        self.lblSourceTimeframe.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblCsvSelectionTimeCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.csvSelectionTime]", None))
        self.lblCsvSelectionTime.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblReplayTimeCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.replayTime]", None))
        self.lblReplayTime.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.grpResult.setTitle(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.grpResult]", None))
        self.lblInitialBalanceCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.initialBalance]", None))
        self.lblInitialBalance.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblFinalBalanceCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.finalBalance]", None))
        self.lblFinalBalance.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblNetPnlCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.netPnl]", None))
        self.lblNetPnl.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblProfitFactorCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.profitFactor]", None))
        self.lblProfitFactor.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblTradesCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.trades]", None))
        self.lblTrades.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblWinRateCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.winRate]", None))
        self.lblWinRate.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblWinnersCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.winners]", None))
        self.lblWinners.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblLosersCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.losers]", None))
        self.lblLosers.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblMaxDrawdownCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.maxDrawdown]", None))
        self.lblMaxDrawdown.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblAverageTradeCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.averageTrade]", None))
        self.lblAverageTrade.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.grpSignals.setTitle(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.grpSignals]", None))
        self.lblSignalsCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.signals]", None))
        self.lblSignals.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblDirectionsCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.directions]", None))
        self.lblDirections.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblAlligatorCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.alligator]", None))
        self.lblAlligator.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblRejectsCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.rejects]", None))
        self.lblRejects.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblMacdQualityCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.macdQuality]", None))
        self.lblMacdQuality.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblMacdQualityRejectsCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.macdQualityRejects]", None))
        self.lblMacdQualityRejects.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.grpExits.setTitle(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.grpExits]", None))
        self.lblStopLossCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"STOP_LOSS:", None))
        self.lblStopLoss.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblTakeProfitCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"TAKE_PROFIT:", None))
        self.lblTakeProfit.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblProfitDrawdownCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"PROFIT_DRAWDOWN:", None))
        self.lblProfitDrawdown.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblSessionEndCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"SESSION_END:", None))
        self.lblSessionEnd.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.lblOtherCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.other]", None))
        self.lblOther.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"\u2014", None))
        self.btnClose.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoricalSummaryDialog", u"[AlgorithmWorkspaceHistoricalSummaryDialog.btnClose]", None))
    # retranslateUi

