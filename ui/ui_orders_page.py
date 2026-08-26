# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'orders_page.ui'
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
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox,
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QSizePolicy,
    QSpacerItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget)

class Ui_OrdersPage(object):
    def setupUi(self, OrdersPage):
        if not OrdersPage.objectName():
            OrdersPage.setObjectName(u"OrdersPage")
        OrdersPage.resize(1099, 564)
        self.verticalLayout = QVBoxLayout(OrdersPage)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.lblHeader = QLabel(OrdersPage)
        self.lblHeader.setObjectName(u"lblHeader")

        self.verticalLayout.addWidget(self.lblHeader)

        self.formLayout = QFormLayout()
        self.formLayout.setObjectName(u"formLayout")
        self.formLayout.setContentsMargins(6, 6, 6, 6)
        self.lblSymbol = QLabel(OrdersPage)
        self.lblSymbol.setObjectName(u"lblSymbol")

        self.formLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblSymbol)

        self.cmbSymbol = QComboBox(OrdersPage)
        self.cmbSymbol.setObjectName(u"cmbSymbol")

        self.formLayout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.cmbSymbol)

        self.lblSide = QLabel(OrdersPage)
        self.lblSide.setObjectName(u"lblSide")

        self.formLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblSide)

        self.lblLots = QLabel(OrdersPage)
        self.lblLots.setObjectName(u"lblLots")

        self.formLayout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblLots)

        self.lblStopLoss = QLabel(OrdersPage)
        self.lblStopLoss.setObjectName(u"lblStopLoss")

        self.formLayout.setWidget(4, QFormLayout.ItemRole.LabelRole, self.lblStopLoss)

        self.lblTakeProfit = QLabel(OrdersPage)
        self.lblTakeProfit.setObjectName(u"lblTakeProfit")

        self.formLayout.setWidget(5, QFormLayout.ItemRole.LabelRole, self.lblTakeProfit)

        self.lblComment = QLabel(OrdersPage)
        self.lblComment.setObjectName(u"lblComment")

        self.formLayout.setWidget(6, QFormLayout.ItemRole.LabelRole, self.lblComment)

        self.cmbSide = QComboBox(OrdersPage)
        self.cmbSide.setObjectName(u"cmbSide")

        self.formLayout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.cmbSide)

        self.editStopLoss = QLineEdit(OrdersPage)
        self.editStopLoss.setObjectName(u"editStopLoss")

        self.formLayout.setWidget(4, QFormLayout.ItemRole.FieldRole, self.editStopLoss)

        self.editTakeProfit = QLineEdit(OrdersPage)
        self.editTakeProfit.setObjectName(u"editTakeProfit")

        self.formLayout.setWidget(5, QFormLayout.ItemRole.FieldRole, self.editTakeProfit)

        self.editComment = QLineEdit(OrdersPage)
        self.editComment.setObjectName(u"editComment")

        self.formLayout.setWidget(6, QFormLayout.ItemRole.FieldRole, self.editComment)

        self.spinLots = QDoubleSpinBox(OrdersPage)
        self.spinLots.setObjectName(u"spinLots")
        self.spinLots.setMinimumSize(QSize(0, 26))
        self.spinLots.setMinimum(0.010000000000000)
        self.spinLots.setMaximum(100.000000000000000)
        self.spinLots.setSingleStep(0.010000000000000)
        self.spinLots.setValue(0.010000000000000)

        self.formLayout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.spinLots)


        self.verticalLayout.addLayout(self.formLayout)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalLayout.setContentsMargins(6, 6, 6, 6)
        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.btnPlaceOrder = QPushButton(OrdersPage)
        self.btnPlaceOrder.setObjectName(u"btnPlaceOrder")
        self.btnPlaceOrder.setCheckable(False)
        self.btnPlaceOrder.setChecked(False)

        self.horizontalLayout.addWidget(self.btnPlaceOrder)

        self.btnRefreshPositions = QPushButton(OrdersPage)
        self.btnRefreshPositions.setObjectName(u"btnRefreshPositions")

        self.horizontalLayout.addWidget(self.btnRefreshPositions)

        self.btnModifySlTp = QPushButton(OrdersPage)
        self.btnModifySlTp.setObjectName(u"btnModifySlTp")

        self.horizontalLayout.addWidget(self.btnModifySlTp)

        self.btnResolveReconciliation = QPushButton(OrdersPage)
        self.btnResolveReconciliation.setObjectName(u"btnResolveReconciliation")

        self.horizontalLayout.addWidget(self.btnResolveReconciliation)

        self.btnClosePosition = QPushButton(OrdersPage)
        self.btnClosePosition.setObjectName(u"btnClosePosition")

        self.horizontalLayout.addWidget(self.btnClosePosition)

        self.btnExitOrders = QPushButton(OrdersPage)
        self.btnExitOrders.setObjectName(u"btnExitOrders")

        self.horizontalLayout.addWidget(self.btnExitOrders)


        self.verticalLayout.addLayout(self.horizontalLayout)

        self.filterLayout = QHBoxLayout()
        self.filterLayout.setObjectName(u"filterLayout")
        self.filterLayout.setContentsMargins(6, 0, 6, 0)
        self.lblPositionFilter = QLabel(OrdersPage)
        self.lblPositionFilter.setObjectName(u"lblPositionFilter")

        self.filterLayout.addWidget(self.lblPositionFilter)

        self.chkFilterManual = QCheckBox(OrdersPage)
        self.chkFilterManual.setObjectName(u"chkFilterManual")
        self.chkFilterManual.setChecked(True)

        self.filterLayout.addWidget(self.chkFilterManual)

        self.chkFilterSemi = QCheckBox(OrdersPage)
        self.chkFilterSemi.setObjectName(u"chkFilterSemi")
        self.chkFilterSemi.setChecked(True)

        self.filterLayout.addWidget(self.chkFilterSemi)

        self.chkFilterAuto = QCheckBox(OrdersPage)
        self.chkFilterAuto.setObjectName(u"chkFilterAuto")
        self.chkFilterAuto.setChecked(True)

        self.filterLayout.addWidget(self.chkFilterAuto)

        self.chkFilterBroker = QCheckBox(OrdersPage)
        self.chkFilterBroker.setObjectName(u"chkFilterBroker")
        self.chkFilterBroker.setChecked(True)

        self.filterLayout.addWidget(self.chkFilterBroker)

        self.filterSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.filterLayout.addItem(self.filterSpacer)


        self.verticalLayout.addLayout(self.filterLayout)

        self.grpOpenPositions = QGroupBox(OrdersPage)
        self.grpOpenPositions.setObjectName(u"grpOpenPositions")
        self.verticalLayout_2 = QVBoxLayout(self.grpOpenPositions)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.tblOpenPositions = QTreeWidget(self.grpOpenPositions)
        __qtreewidgetitem = QTreeWidgetItem()
        __qtreewidgetitem.setText(12, u"13");
        __qtreewidgetitem.setText(11, u"12");
        __qtreewidgetitem.setText(10, u"11");
        __qtreewidgetitem.setText(9, u"10");
        __qtreewidgetitem.setText(8, u"9");
        __qtreewidgetitem.setText(7, u"8");
        __qtreewidgetitem.setText(6, u"7");
        __qtreewidgetitem.setText(5, u"6");
        __qtreewidgetitem.setText(4, u"5");
        __qtreewidgetitem.setText(3, u"4");
        __qtreewidgetitem.setText(2, u"3");
        __qtreewidgetitem.setText(1, u"2");
        __qtreewidgetitem.setText(0, u"1");
        self.tblOpenPositions.setHeaderItem(__qtreewidgetitem)
        self.tblOpenPositions.setObjectName(u"tblOpenPositions")
        self.tblOpenPositions.setColumnCount(13)

        self.verticalLayout_2.addWidget(self.tblOpenPositions)


        self.verticalLayout.addWidget(self.grpOpenPositions)

        self.statusLayout = QHBoxLayout()
        self.statusLayout.setObjectName(u"statusLayout")
        self.lblOrdersStatus = QLabel(OrdersPage)
        self.lblOrdersStatus.setObjectName(u"lblOrdersStatus")

        self.statusLayout.addWidget(self.lblOrdersStatus)

        self.statusSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.statusLayout.addItem(self.statusSpacer)

        self.lblPnlSummary = QLabel(OrdersPage)
        self.lblPnlSummary.setObjectName(u"lblPnlSummary")
        self.lblPnlSummary.setMinimumSize(QSize(130, 0))
        self.lblPnlSummary.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.statusLayout.addWidget(self.lblPnlSummary)


        self.verticalLayout.addLayout(self.statusLayout)

        self.verticalLayout.setStretch(0, 1)
        self.verticalLayout.setStretch(1, 4)
        self.verticalLayout.setStretch(2, 1)
        self.verticalLayout.setStretch(4, 8)
        self.verticalLayout.setStretch(5, 1)

        self.retranslateUi(OrdersPage)

        QMetaObject.connectSlotsByName(OrdersPage)
    # setupUi

    def retranslateUi(self, OrdersPage):
        OrdersPage.setWindowTitle(QCoreApplication.translate("OrdersPage", u"Form", None))
        self.lblHeader.setText(QCoreApplication.translate("OrdersPage", u"[OrdersPage.header]", None))
        self.lblSymbol.setText(QCoreApplication.translate("OrdersPage", u"[OrdersPage.lblSymbol]", None))
        self.lblSide.setText(QCoreApplication.translate("OrdersPage", u"[OrdersPage.lblSide]", None))
        self.lblLots.setText(QCoreApplication.translate("OrdersPage", u"[OrdersPage.lblLots]", None))
        self.lblStopLoss.setText(QCoreApplication.translate("OrdersPage", u"[OrdersPage.lblStopLoss]", None))
        self.lblTakeProfit.setText(QCoreApplication.translate("OrdersPage", u"[OrdersPage.lblTakeProfit]", None))
        self.lblComment.setText(QCoreApplication.translate("OrdersPage", u"[OrdersPage.lblComment]", None))
        self.btnPlaceOrder.setText(QCoreApplication.translate("OrdersPage", u"[OrdersPage.btnPlaceOrder]", None))
        self.btnRefreshPositions.setText(QCoreApplication.translate("OrdersPage", u"[OrdersPage.btnRefreshPositions]", None))
        self.btnModifySlTp.setText(QCoreApplication.translate("OrdersPage", u"[OrdersPage.btnModifySlTp]", None))
        self.btnResolveReconciliation.setText(QCoreApplication.translate("OrdersPage", u"[OrdersPage.btnResolveReconciliation]", None))
        self.btnClosePosition.setText(QCoreApplication.translate("OrdersPage", u"[OrdersPage.btnClosePosition]", None))
        self.btnExitOrders.setText(QCoreApplication.translate("OrdersPage", u"[OrdersPage.btnExitOrders]", None))
        self.lblPositionFilter.setText(QCoreApplication.translate("OrdersPage", u"[OrdersPage.lblPositionFilter]", None))
        self.chkFilterManual.setText(QCoreApplication.translate("OrdersPage", u"[OrdersPage.filterManual]", None))
        self.chkFilterSemi.setText(QCoreApplication.translate("OrdersPage", u"[OrdersPage.filterSemi]", None))
        self.chkFilterAuto.setText(QCoreApplication.translate("OrdersPage", u"[OrdersPage.filterAuto]", None))
        self.chkFilterBroker.setText(QCoreApplication.translate("OrdersPage", u"[OrdersPage.filterBroker]", None))
        self.grpOpenPositions.setTitle(QCoreApplication.translate("OrdersPage", u"[OrdersPage.grpOpenPositions]", None))
        self.lblOrdersStatus.setText(QCoreApplication.translate("OrdersPage", u"[OrdersPage.statusReady]", None))
        self.lblPnlSummary.setText(QCoreApplication.translate("OrdersPage", u"\u03a3 PnL: \u2014", None))
    # retranslateUi

