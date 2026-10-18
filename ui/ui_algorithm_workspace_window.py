# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'algorithm_workspace_window.ui'
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
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit,
    QPushButton, QSizePolicy, QSpacerItem, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

class Ui_AlgorithmWorkspaceWindow(object):
    def setupUi(self, AlgorithmWorkspaceWindow):
        if not AlgorithmWorkspaceWindow.objectName():
            AlgorithmWorkspaceWindow.setObjectName(u"AlgorithmWorkspaceWindow")
        AlgorithmWorkspaceWindow.resize(760, 520)
        AlgorithmWorkspaceWindow.setMinimumSize(QSize(500, 360))
        AlgorithmWorkspaceWindow.setStyleSheet(u"QFrame#AlgorithmWorkspaceWindow {\n"
"    border: 2px solid #6f8f98;\n"
"    border-radius: 7px;\n"
"}\n"
"QFrame#AlgorithmWorkspaceWindow[replayConfigured=\"true\"] {\n"
"    border-color: #4aa3d8;\n"
"}\n"
"QLabel#lblName[replayConfigured=\"true\"] {\n"
"    color: #8ad7ff;\n"
"}\n"
"QFrame#AlgorithmWorkspaceWindow[activeWorkspace=\"true\"] {\n"
"    border: 3px solid #f2c14e;\n"
"}\n"
"QLabel#lblName[activeWorkspace=\"true\"] {\n"
"    background-color: rgba(242, 193, 78, 78);\n"
"    border-left: 6px solid #f2c14e;\n"
"    border-radius: 4px;\n"
"    color: #fff4c2;\n"
"    padding: 0px 6px;\n"
"}\n"
"QPushButton#btnReplaySettings[replayConfigured=\"true\"] {\n"
"    border: 1px solid #4aa3d8;\n"
"    color: #d8f3ff;\n"
"    font-weight: 700;\n"
"}\n"
"QFrame#AlgorithmWorkspaceWindow[runtimeState=\"RUNNING\"] {\n"
"    border-color: #35b96f;\n"
"}\n"
"QFrame#AlgorithmWorkspaceWindow[runtimeState=\"STARTING\"],\n"
"QFrame#AlgorithmWorkspaceWindow[runtimeState=\"STOPPING\"] {\n"
"    border-color: #f2c14e;\n"
""
                        "}\n"
"QFrame#AlgorithmWorkspaceWindow[runtimeState=\"ERROR\"] {\n"
"    border-color: #ef5350;\n"
"}\n"
"QPushButton#btnStartStop[actionMode=\"START\"] {\n"
"    background-color: #237a4b;\n"
"    border: 1px solid #35b96f;\n"
"    color: #ffffff;\n"
"    font-weight: 700;\n"
"    min-height: 0px;\n"
"    max-height: 24px;\n"
"    padding: 0px 10px;\n"
"}\n"
"QPushButton#btnStartStop[actionMode=\"STOP\"] {\n"
"    background-color: #8f2d2d;\n"
"    border: 1px solid #ef5350;\n"
"    color: #ffffff;\n"
"    font-weight: 700;\n"
"    min-height: 0px;\n"
"    max-height: 24px;\n"
"    padding: 0px 10px;\n"
"}\n"
"QLabel#lblState {\n"
"    border: 1px solid #54747d;\n"
"    border-radius: 5px;\n"
"    min-height: 0px;\n"
"    max-height: 24px;\n"
"    padding: 0px 8px;\n"
"    font-weight: 700;\n"
"}\n"
"QPushButton#btnHistoryDownload,\n"
"QPushButton#btnReplaySettings,\n"
"QPushButton#btnParameters,\n"
"QPushButton#btnRename {\n"
"    min-height: 0px;\n"
"    max-height: 22px;\n"
"    padding: 0px 8px;\n"
"    fo"
                        "nt: 9pt \"Segoe UI\";\n"
"}\n"
"QPushButton#btnReplayPause,\n"
"QPushButton#btnReplayStep {\n"
"    min-height: 0px;\n"
"    max-height: 18px;\n"
"    padding: 0px 6px;\n"
"    font: 8pt \"Segoe UI\";\n"
"}\n"
"QComboBox#cmbReplaySpeed {\n"
"    min-height: 0px;\n"
"    max-height: 18px;\n"
"    padding: 0px 4px;\n"
"    font: 8pt \"Segoe UI\";\n"
"}\n"
"QLabel#lblReplayStatus,\n"
"QLabel#lblReplaySpeed {\n"
"    font: 8pt \"Segoe UI\";\n"
"}\n"
"QFrame#frameSummary {\n"
"    border: 1px solid #315965;\n"
"    border-radius: 5px;\n"
"}\n"
"QLabel[summaryValue=\"true\"] {\n"
"    font-weight: 700;\n"
"}\n"
"QTabWidget#tabsWorkspace::pane {\n"
"    border: 1px solid #315965;\n"
"}\n"
"QTabBar::tab {\n"
"    padding: 4px 10px;\n"
"}")
        AlgorithmWorkspaceWindow.setFrameShape(QFrame.Shape.StyledPanel)
        self.verticalLayout = QVBoxLayout(AlgorithmWorkspaceWindow)
        self.verticalLayout.setSpacing(4)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(8, 8, 8, 8)
        self.gridLayoutHeader = QGridLayout()
        self.gridLayoutHeader.setObjectName(u"gridLayoutHeader")
        self.gridLayoutHeader.setHorizontalSpacing(8)
        self.gridLayoutHeader.setVerticalSpacing(2)
        self.lblName = QLabel(AlgorithmWorkspaceWindow)
        self.lblName.setObjectName(u"lblName")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.lblName.sizePolicy().hasHeightForWidth())
        self.lblName.setSizePolicy(sizePolicy)
        self.lblName.setStyleSheet(u"font: 700 13pt \"Segoe UI\";\n"
"color: #ffffff;")

        self.gridLayoutHeader.addWidget(self.lblName, 0, 0, 1, 4)

        self.lblState = QLabel(AlgorithmWorkspaceWindow)
        self.lblState.setObjectName(u"lblState")
        self.lblState.setMinimumSize(QSize(104, 2))
        self.lblState.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.gridLayoutHeader.addWidget(self.lblState, 0, 4, 1, 1)

        self.btnStartStop = QPushButton(AlgorithmWorkspaceWindow)
        self.btnStartStop.setObjectName(u"btnStartStop")
        self.btnStartStop.setMinimumSize(QSize(78, 0))

        self.gridLayoutHeader.addWidget(self.btnStartStop, 0, 5, 1, 1)

        self.horizontalSpacerHeader = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.gridLayoutHeader.addItem(self.horizontalSpacerHeader, 1, 0, 1, 2)

        self.btnHistoryDownload = QPushButton(AlgorithmWorkspaceWindow)
        self.btnHistoryDownload.setObjectName(u"btnHistoryDownload")

        self.gridLayoutHeader.addWidget(self.btnHistoryDownload, 1, 2, 1, 1)

        self.btnReplaySettings = QPushButton(AlgorithmWorkspaceWindow)
        self.btnReplaySettings.setObjectName(u"btnReplaySettings")

        self.gridLayoutHeader.addWidget(self.btnReplaySettings, 1, 3, 1, 1)

        self.btnParameters = QPushButton(AlgorithmWorkspaceWindow)
        self.btnParameters.setObjectName(u"btnParameters")

        self.gridLayoutHeader.addWidget(self.btnParameters, 1, 4, 1, 1)

        self.btnRename = QPushButton(AlgorithmWorkspaceWindow)
        self.btnRename.setObjectName(u"btnRename")

        self.gridLayoutHeader.addWidget(self.btnRename, 1, 5, 1, 1)


        self.verticalLayout.addLayout(self.gridLayoutHeader)

        self.gridLayoutInfo = QGridLayout()
        self.gridLayoutInfo.setObjectName(u"gridLayoutInfo")
        self.gridLayoutInfo.setHorizontalSpacing(7)
        self.gridLayoutInfo.setVerticalSpacing(3)
        self.lblBrokerCaption = QLabel(AlgorithmWorkspaceWindow)
        self.lblBrokerCaption.setObjectName(u"lblBrokerCaption")
        self.lblBrokerCaption.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.gridLayoutInfo.addWidget(self.lblBrokerCaption, 0, 0, 1, 1)

        self.lblBroker = QLabel(AlgorithmWorkspaceWindow)
        self.lblBroker.setObjectName(u"lblBroker")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy1.setHorizontalStretch(1)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.lblBroker.sizePolicy().hasHeightForWidth())
        self.lblBroker.setSizePolicy(sizePolicy1)

        self.gridLayoutInfo.addWidget(self.lblBroker, 0, 1, 1, 1)

        self.lblAccountCaption = QLabel(AlgorithmWorkspaceWindow)
        self.lblAccountCaption.setObjectName(u"lblAccountCaption")
        self.lblAccountCaption.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.gridLayoutInfo.addWidget(self.lblAccountCaption, 0, 2, 1, 1)

        self.lblAccount = QLabel(AlgorithmWorkspaceWindow)
        self.lblAccount.setObjectName(u"lblAccount")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy2.setHorizontalStretch(2)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.lblAccount.sizePolicy().hasHeightForWidth())
        self.lblAccount.setSizePolicy(sizePolicy2)

        self.gridLayoutInfo.addWidget(self.lblAccount, 0, 3, 1, 1)

        self.lblSymbolCaption = QLabel(AlgorithmWorkspaceWindow)
        self.lblSymbolCaption.setObjectName(u"lblSymbolCaption")
        self.lblSymbolCaption.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.gridLayoutInfo.addWidget(self.lblSymbolCaption, 1, 0, 1, 1)

        self.lblSymbol = QLabel(AlgorithmWorkspaceWindow)
        self.lblSymbol.setObjectName(u"lblSymbol")

        self.gridLayoutInfo.addWidget(self.lblSymbol, 1, 1, 1, 1)

        self.lblTimeframeCaption = QLabel(AlgorithmWorkspaceWindow)
        self.lblTimeframeCaption.setObjectName(u"lblTimeframeCaption")
        self.lblTimeframeCaption.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.gridLayoutInfo.addWidget(self.lblTimeframeCaption, 1, 2, 1, 1)

        self.lblTimeframe = QLabel(AlgorithmWorkspaceWindow)
        self.lblTimeframe.setObjectName(u"lblTimeframe")

        self.gridLayoutInfo.addWidget(self.lblTimeframe, 1, 3, 1, 1)

        self.lblAlgorithmCaption = QLabel(AlgorithmWorkspaceWindow)
        self.lblAlgorithmCaption.setObjectName(u"lblAlgorithmCaption")
        self.lblAlgorithmCaption.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.gridLayoutInfo.addWidget(self.lblAlgorithmCaption, 2, 0, 1, 1)

        self.lblAlgorithm = QLabel(AlgorithmWorkspaceWindow)
        self.lblAlgorithm.setObjectName(u"lblAlgorithm")
        sizePolicy1.setHeightForWidth(self.lblAlgorithm.sizePolicy().hasHeightForWidth())
        self.lblAlgorithm.setSizePolicy(sizePolicy1)

        self.gridLayoutInfo.addWidget(self.lblAlgorithm, 2, 1, 1, 1)

        self.lblDataModeCaption = QLabel(AlgorithmWorkspaceWindow)
        self.lblDataModeCaption.setObjectName(u"lblDataModeCaption")
        self.lblDataModeCaption.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.gridLayoutInfo.addWidget(self.lblDataModeCaption, 2, 2, 1, 1)

        self.cmbDataMode = QComboBox(AlgorithmWorkspaceWindow)
        self.cmbDataMode.setObjectName(u"cmbDataMode")

        self.gridLayoutInfo.addWidget(self.cmbDataMode, 2, 3, 1, 1)

        self.lblBalanceCaption = QLabel(AlgorithmWorkspaceWindow)
        self.lblBalanceCaption.setObjectName(u"lblBalanceCaption")
        self.lblBalanceCaption.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.gridLayoutInfo.addWidget(self.lblBalanceCaption, 3, 0, 1, 1)

        self.lblBalance = QLabel(AlgorithmWorkspaceWindow)
        self.lblBalance.setObjectName(u"lblBalance")
        sizePolicy1.setHeightForWidth(self.lblBalance.sizePolicy().hasHeightForWidth())
        self.lblBalance.setSizePolicy(sizePolicy1)

        self.gridLayoutInfo.addWidget(self.lblBalance, 3, 1, 1, 1)

        self.lblControlModeCaption = QLabel(AlgorithmWorkspaceWindow)
        self.lblControlModeCaption.setObjectName(u"lblControlModeCaption")
        self.lblControlModeCaption.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.gridLayoutInfo.addWidget(self.lblControlModeCaption, 3, 2, 1, 1)

        self.cmbControlMode = QComboBox(AlgorithmWorkspaceWindow)
        self.cmbControlMode.setObjectName(u"cmbControlMode")

        self.gridLayoutInfo.addWidget(self.cmbControlMode, 3, 3, 1, 1)


        self.verticalLayout.addLayout(self.gridLayoutInfo)

        self.frameSummary = QFrame(AlgorithmWorkspaceWindow)
        self.frameSummary.setObjectName(u"frameSummary")
        self.frameSummary.setFrameShape(QFrame.Shape.StyledPanel)
        self.horizontalLayoutSummary = QHBoxLayout(self.frameSummary)
        self.horizontalLayoutSummary.setObjectName(u"horizontalLayoutSummary")
        self.horizontalLayoutSummary.setContentsMargins(8, 2, 8, 2)
        self.lblOrdersCaption = QLabel(self.frameSummary)
        self.lblOrdersCaption.setObjectName(u"lblOrdersCaption")

        self.horizontalLayoutSummary.addWidget(self.lblOrdersCaption)

        self.lblOrdersCount = QLabel(self.frameSummary)
        self.lblOrdersCount.setObjectName(u"lblOrdersCount")
        self.lblOrdersCount.setProperty(u"summaryValue", True)

        self.horizontalLayoutSummary.addWidget(self.lblOrdersCount)

        self.lblPositionsCaption = QLabel(self.frameSummary)
        self.lblPositionsCaption.setObjectName(u"lblPositionsCaption")

        self.horizontalLayoutSummary.addWidget(self.lblPositionsCaption)

        self.lblPositionsCount = QLabel(self.frameSummary)
        self.lblPositionsCount.setObjectName(u"lblPositionsCount")
        self.lblPositionsCount.setProperty(u"summaryValue", True)

        self.horizontalLayoutSummary.addWidget(self.lblPositionsCount)

        self.lblCurrentProfitCaption = QLabel(self.frameSummary)
        self.lblCurrentProfitCaption.setObjectName(u"lblCurrentProfitCaption")

        self.horizontalLayoutSummary.addWidget(self.lblCurrentProfitCaption)

        self.lblCurrentProfit = QLabel(self.frameSummary)
        self.lblCurrentProfit.setObjectName(u"lblCurrentProfit")
        self.lblCurrentProfit.setProperty(u"summaryValue", True)

        self.horizontalLayoutSummary.addWidget(self.lblCurrentProfit)

        self.lblPeakProfitCaption = QLabel(self.frameSummary)
        self.lblPeakProfitCaption.setObjectName(u"lblPeakProfitCaption")

        self.horizontalLayoutSummary.addWidget(self.lblPeakProfitCaption)

        self.lblPeakProfit = QLabel(self.frameSummary)
        self.lblPeakProfit.setObjectName(u"lblPeakProfit")
        self.lblPeakProfit.setProperty(u"summaryValue", True)

        self.horizontalLayoutSummary.addWidget(self.lblPeakProfit)

        self.lblProfitDrawdownCaption = QLabel(self.frameSummary)
        self.lblProfitDrawdownCaption.setObjectName(u"lblProfitDrawdownCaption")

        self.horizontalLayoutSummary.addWidget(self.lblProfitDrawdownCaption)

        self.lblProfitDrawdown = QLabel(self.frameSummary)
        self.lblProfitDrawdown.setObjectName(u"lblProfitDrawdown")
        self.lblProfitDrawdown.setProperty(u"summaryValue", True)

        self.horizontalLayoutSummary.addWidget(self.lblProfitDrawdown)

        self.horizontalSpacerSummary = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutSummary.addItem(self.horizontalSpacerSummary)


        self.verticalLayout.addWidget(self.frameSummary)

        self.frameReplayControls = QFrame(AlgorithmWorkspaceWindow)
        self.frameReplayControls.setObjectName(u"frameReplayControls")
        self.frameReplayControls.setFrameShape(QFrame.Shape.StyledPanel)
        self.horizontalLayoutReplay = QHBoxLayout(self.frameReplayControls)
        self.horizontalLayoutReplay.setSpacing(4)
        self.horizontalLayoutReplay.setObjectName(u"horizontalLayoutReplay")
        self.horizontalLayoutReplay.setContentsMargins(6, 1, 6, 1)
        self.lblReplayStatus = QLabel(self.frameReplayControls)
        self.lblReplayStatus.setObjectName(u"lblReplayStatus")

        self.horizontalLayoutReplay.addWidget(self.lblReplayStatus)

        self.horizontalSpacerReplay = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutReplay.addItem(self.horizontalSpacerReplay)

        self.btnReplayPause = QPushButton(self.frameReplayControls)
        self.btnReplayPause.setObjectName(u"btnReplayPause")
        self.btnReplayPause.setMaximumSize(QSize(16777215, 20))

        self.horizontalLayoutReplay.addWidget(self.btnReplayPause)

        self.btnReplayStep = QPushButton(self.frameReplayControls)
        self.btnReplayStep.setObjectName(u"btnReplayStep")
        self.btnReplayStep.setMaximumSize(QSize(16777215, 20))

        self.horizontalLayoutReplay.addWidget(self.btnReplayStep)

        self.lblReplaySpeed = QLabel(self.frameReplayControls)
        self.lblReplaySpeed.setObjectName(u"lblReplaySpeed")

        self.horizontalLayoutReplay.addWidget(self.lblReplaySpeed)

        self.cmbReplaySpeed = QComboBox(self.frameReplayControls)
        self.cmbReplaySpeed.addItem("")
        self.cmbReplaySpeed.addItem("")
        self.cmbReplaySpeed.addItem("")
        self.cmbReplaySpeed.addItem("")
        self.cmbReplaySpeed.addItem("")
        self.cmbReplaySpeed.addItem("")
        self.cmbReplaySpeed.addItem("")
        self.cmbReplaySpeed.addItem("")
        self.cmbReplaySpeed.setObjectName(u"cmbReplaySpeed")
        self.cmbReplaySpeed.setMaximumSize(QSize(16777215, 20))

        self.horizontalLayoutReplay.addWidget(self.cmbReplaySpeed)


        self.verticalLayout.addWidget(self.frameReplayControls)

        self.tabsWorkspace = QTabWidget(AlgorithmWorkspaceWindow)
        self.tabsWorkspace.setObjectName(u"tabsWorkspace")
        self.tabOrders = QWidget()
        self.tabOrders.setObjectName(u"tabOrders")
        self.verticalLayoutOrders = QVBoxLayout(self.tabOrders)
        self.verticalLayoutOrders.setObjectName(u"verticalLayoutOrders")
        self.verticalLayoutOrders.setContentsMargins(6, 6, 6, 6)
        self.tblOrders = QTableWidget(self.tabOrders)
        if (self.tblOrders.columnCount() < 6):
            self.tblOrders.setColumnCount(6)
        __qtablewidgetitem = QTableWidgetItem()
        self.tblOrders.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.tblOrders.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.tblOrders.setHorizontalHeaderItem(2, __qtablewidgetitem2)
        __qtablewidgetitem3 = QTableWidgetItem()
        self.tblOrders.setHorizontalHeaderItem(3, __qtablewidgetitem3)
        __qtablewidgetitem4 = QTableWidgetItem()
        self.tblOrders.setHorizontalHeaderItem(4, __qtablewidgetitem4)
        __qtablewidgetitem5 = QTableWidgetItem()
        self.tblOrders.setHorizontalHeaderItem(5, __qtablewidgetitem5)
        self.tblOrders.setObjectName(u"tblOrders")
        self.tblOrders.setRowCount(0)
        self.tblOrders.setColumnCount(6)

        self.verticalLayoutOrders.addWidget(self.tblOrders)

        self.tabsWorkspace.addTab(self.tabOrders, "")
        self.tabChart = QWidget()
        self.tabChart.setObjectName(u"tabChart")
        self.verticalLayoutChart = QVBoxLayout(self.tabChart)
        self.verticalLayoutChart.setObjectName(u"verticalLayoutChart")
        self.lblChartPlaceholder = QLabel(self.tabChart)
        self.lblChartPlaceholder.setObjectName(u"lblChartPlaceholder")
        self.lblChartPlaceholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lblChartPlaceholder.setWordWrap(True)

        self.verticalLayoutChart.addWidget(self.lblChartPlaceholder)

        self.tabsWorkspace.addTab(self.tabChart, "")
        self.tabPosition = QWidget()
        self.tabPosition.setObjectName(u"tabPosition")
        self.verticalLayoutPosition = QVBoxLayout(self.tabPosition)
        self.verticalLayoutPosition.setObjectName(u"verticalLayoutPosition")
        self.lblPositionPlaceholder = QLabel(self.tabPosition)
        self.lblPositionPlaceholder.setObjectName(u"lblPositionPlaceholder")
        self.lblPositionPlaceholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lblPositionPlaceholder.setWordWrap(True)

        self.verticalLayoutPosition.addWidget(self.lblPositionPlaceholder)

        self.tabsWorkspace.addTab(self.tabPosition, "")
        self.tabSignals = QWidget()
        self.tabSignals.setObjectName(u"tabSignals")
        self.verticalLayoutSignals = QVBoxLayout(self.tabSignals)
        self.verticalLayoutSignals.setObjectName(u"verticalLayoutSignals")
        self.lblSignalsPlaceholder = QLabel(self.tabSignals)
        self.lblSignalsPlaceholder.setObjectName(u"lblSignalsPlaceholder")
        self.lblSignalsPlaceholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lblSignalsPlaceholder.setWordWrap(True)

        self.verticalLayoutSignals.addWidget(self.lblSignalsPlaceholder)

        self.tabsWorkspace.addTab(self.tabSignals, "")
        self.tabLog = QWidget()
        self.tabLog.setObjectName(u"tabLog")
        self.verticalLayoutLog = QVBoxLayout(self.tabLog)
        self.verticalLayoutLog.setObjectName(u"verticalLayoutLog")
        self.txtLog = QPlainTextEdit(self.tabLog)
        self.txtLog.setObjectName(u"txtLog")
        self.txtLog.setReadOnly(True)

        self.verticalLayoutLog.addWidget(self.txtLog)

        self.tabsWorkspace.addTab(self.tabLog, "")

        self.verticalLayout.addWidget(self.tabsWorkspace)


        self.retranslateUi(AlgorithmWorkspaceWindow)

        self.tabsWorkspace.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(AlgorithmWorkspaceWindow)
    # setupUi

    def retranslateUi(self, AlgorithmWorkspaceWindow):
        self.lblName.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"Workspace", None))
        self.lblState.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"STOPPED", None))
        self.btnStartStop.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.btnStart]", None))
        self.btnHistoryDownload.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.btnHistoryDownload]", None))
        self.btnReplaySettings.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.btnReplaySettings]", None))
        self.btnParameters.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.btnParameters]", None))
        self.btnRename.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.btnRename]", None))
        self.lblBrokerCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.lblBroker]", None))
        self.lblBroker.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"\u2014", None))
        self.lblAccountCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.lblAccount]", None))
        self.lblAccount.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"\u2014", None))
        self.lblSymbolCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.lblSymbol]", None))
        self.lblSymbol.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"\u2014", None))
        self.lblTimeframeCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.lblTimeframe]", None))
        self.lblTimeframe.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"\u2014", None))
        self.lblAlgorithmCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.lblAlgorithm]", None))
        self.lblAlgorithm.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"\u2014", None))
        self.lblDataModeCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.lblDataMode]", None))
        self.lblBalanceCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.lblBalance]", None))
        self.lblBalance.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"\u2014", None))
        self.lblControlModeCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.lblControlMode]", None))
        self.lblOrdersCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.lblOrders]", None))
        self.lblOrdersCount.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"0", None))
        self.lblPositionsCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.lblPositions]", None))
        self.lblPositionsCount.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"0", None))
        self.lblCurrentProfitCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.lblCurrentProfit]", None))
        self.lblCurrentProfit.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"0.00", None))
        self.lblPeakProfitCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.lblPeakProfit]", None))
        self.lblPeakProfit.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"0.00", None))
        self.lblProfitDrawdownCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.lblProfitDrawdown]", None))
        self.lblProfitDrawdown.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"0.0%", None))
        self.lblReplayStatus.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.replayNotConnected]", None))
        self.btnReplayPause.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.btnReplayPause]", None))
        self.btnReplayStep.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.btnReplayStep]", None))
        self.lblReplaySpeed.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.lblReplaySpeed]", None))
        self.cmbReplaySpeed.setItemText(0, QCoreApplication.translate("AlgorithmWorkspaceWindow", u"1x", None))
        self.cmbReplaySpeed.setItemText(1, QCoreApplication.translate("AlgorithmWorkspaceWindow", u"2x", None))
        self.cmbReplaySpeed.setItemText(2, QCoreApplication.translate("AlgorithmWorkspaceWindow", u"5x", None))
        self.cmbReplaySpeed.setItemText(3, QCoreApplication.translate("AlgorithmWorkspaceWindow", u"10x", None))
        self.cmbReplaySpeed.setItemText(4, QCoreApplication.translate("AlgorithmWorkspaceWindow", u"100x", None))
        self.cmbReplaySpeed.setItemText(5, QCoreApplication.translate("AlgorithmWorkspaceWindow", u"1000x", None))
        self.cmbReplaySpeed.setItemText(6, QCoreApplication.translate("AlgorithmWorkspaceWindow", u"MAX", None))
        self.cmbReplaySpeed.setItemText(7, QCoreApplication.translate("AlgorithmWorkspaceWindow", u"MAX FAST", None))

        ___qtablewidgetitem = self.tblOrders.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.colOrderId]", None));
        ___qtablewidgetitem1 = self.tblOrders.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.colSide]", None));
        ___qtablewidgetitem2 = self.tblOrders.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.colVolume]", None));
        ___qtablewidgetitem3 = self.tblOrders.horizontalHeaderItem(3)
        ___qtablewidgetitem3.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.colPrice]", None));
        ___qtablewidgetitem4 = self.tblOrders.horizontalHeaderItem(4)
        ___qtablewidgetitem4.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.colStatus]", None));
        ___qtablewidgetitem5 = self.tblOrders.horizontalHeaderItem(5)
        ___qtablewidgetitem5.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.colProfit]", None));
        self.tabsWorkspace.setTabText(self.tabsWorkspace.indexOf(self.tabOrders), QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.tabOrders]", None))
        self.lblChartPlaceholder.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.chartPlaceholder]", None))
        self.tabsWorkspace.setTabText(self.tabsWorkspace.indexOf(self.tabChart), QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.tabChart]", None))
        self.lblPositionPlaceholder.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.positionPlaceholder]", None))
        self.tabsWorkspace.setTabText(self.tabsWorkspace.indexOf(self.tabPosition), QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.tabPosition]", None))
        self.lblSignalsPlaceholder.setText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.signalsPlaceholder]", None))
        self.tabsWorkspace.setTabText(self.tabsWorkspace.indexOf(self.tabSignals), QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.tabSignals]", None))
        self.txtLog.setPlainText(QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.logPlaceholder]", None))
        self.tabsWorkspace.setTabText(self.tabsWorkspace.indexOf(self.tabLog), QCoreApplication.translate("AlgorithmWorkspaceWindow", u"[AlgorithmWorkspaceWindow.tabLog]", None))
        pass
    # retranslateUi

