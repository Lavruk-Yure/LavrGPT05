# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'settings_page_trading.ui'
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
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)


class Ui_SettingsPageTrading(object):
    def setupUi(self, SettingsPageTrading):
        if not SettingsPageTrading.objectName():
            SettingsPageTrading.setObjectName("SettingsPageTrading")
        SettingsPageTrading.resize(453, 444)
        self.verticalLayout = QVBoxLayout(SettingsPageTrading)
        self.verticalLayout.setObjectName("verticalLayout")
        self.lblHeader = QLabel(SettingsPageTrading)
        self.lblHeader.setObjectName("lblHeader")
        font = QFont()
        font.setBold(True)
        self.lblHeader.setFont(font)
        self.lblHeader.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.verticalLayout.addWidget(self.lblHeader)

        self.grpBroker = QGroupBox(SettingsPageTrading)
        self.grpBroker.setObjectName("grpBroker")
        self.verticalLayout_2 = QVBoxLayout(self.grpBroker)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.comboBroker = QComboBox(self.grpBroker)
        self.comboBroker.setObjectName("comboBroker")

        self.verticalLayout_2.addWidget(self.comboBroker)

        self.verticalLayout.addWidget(self.grpBroker)

        self.grpAccount = QGroupBox(SettingsPageTrading)
        self.grpAccount.setObjectName("grpAccount")
        self.verticalLayout_3 = QVBoxLayout(self.grpAccount)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.comboAccountMode = QComboBox(self.grpAccount)
        self.comboAccountMode.setObjectName("comboAccountMode")

        self.verticalLayout_3.addWidget(self.comboAccountMode)

        self.verticalLayout.addWidget(self.grpAccount)

        self.grpExecution = QGroupBox(SettingsPageTrading)
        self.grpExecution.setObjectName("grpExecution")
        self.verticalLayout_4 = QVBoxLayout(self.grpExecution)
        self.verticalLayout_4.setObjectName("verticalLayout_4")
        self.comboExecutionMode = QComboBox(self.grpExecution)
        self.comboExecutionMode.setObjectName("comboExecutionMode")

        self.verticalLayout_4.addWidget(self.comboExecutionMode)

        self.verticalLayout.addWidget(self.grpExecution)

        self.grpConnection = QGroupBox(SettingsPageTrading)
        self.grpConnection.setObjectName("grpConnection")
        self.verticalLayout_5 = QVBoxLayout(self.grpConnection)
        self.verticalLayout_5.setObjectName("verticalLayout_5")
        self.lblCtraderConnectionStatus = QLabel(self.grpConnection)
        self.lblCtraderConnectionStatus.setObjectName("lblCtraderConnectionStatus")

        self.verticalLayout_5.addWidget(self.lblCtraderConnectionStatus)

        self.btnCtraderConnection = QPushButton(self.grpConnection)
        self.btnCtraderConnection.setObjectName("btnCtraderConnection")

        self.verticalLayout_5.addWidget(self.btnCtraderConnection)

        self.lblBrokerConnectionStatus = QLabel(self.grpConnection)
        self.lblBrokerConnectionStatus.setObjectName("lblBrokerConnectionStatus")

        self.verticalLayout_5.addWidget(self.lblBrokerConnectionStatus)

        self.btnIbConnection = QPushButton(self.grpConnection)
        self.btnIbConnection.setObjectName("btnIbConnection")

        self.verticalLayout_5.addWidget(self.btnIbConnection)

        self.verticalLayout.addWidget(self.grpConnection)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.horizontalLayout.setContentsMargins(9, 9, 9, 9)
        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")

        self.horizontalLayout.addLayout(self.horizontalLayout_2)

        self.btnOK = QPushButton(SettingsPageTrading)
        self.btnOK.setObjectName("btnOK")

        self.horizontalLayout.addWidget(self.btnOK)

        self.btnApply = QPushButton(SettingsPageTrading)
        self.btnApply.setObjectName("btnApply")

        self.horizontalLayout.addWidget(self.btnApply)

        self.btnCancel = QPushButton(SettingsPageTrading)
        self.btnCancel.setObjectName("btnCancel")

        self.horizontalLayout.addWidget(self.btnCancel)

        self.verticalLayout.addLayout(self.horizontalLayout)

        self.verticalSpacer = QSpacerItem(
            20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        )

        self.verticalLayout.addItem(self.verticalSpacer)

        self.retranslateUi(SettingsPageTrading)

        QMetaObject.connectSlotsByName(SettingsPageTrading)

    # setupUi

    def retranslateUi(self, SettingsPageTrading):
        SettingsPageTrading.setWindowTitle(
            QCoreApplication.translate("SettingsPageTrading", "Form", None)
        )
        self.lblHeader.setText(
            QCoreApplication.translate(
                "SettingsPageTrading", "[SettingsPageTrading.header]", None
            )
        )
        self.grpBroker.setTitle(
            QCoreApplication.translate(
                "SettingsPageTrading", "[SettingsPageTrading.grpBroker]", None
            )
        )
        self.grpAccount.setTitle(
            QCoreApplication.translate(
                "SettingsPageTrading", "[SettingsPageTrading.grpAccount]", None
            )
        )
        self.grpExecution.setTitle(
            QCoreApplication.translate(
                "SettingsPageTrading", "[SettingsPageTrading.grpExecution]", None
            )
        )
        self.grpConnection.setTitle(
            QCoreApplication.translate(
                "SettingsPageTrading", "[SettingsPageTrading.grpConnection]", None
            )
        )
        self.lblCtraderConnectionStatus.setText(
            QCoreApplication.translate(
                "SettingsPageTrading",
                "[SettingsPageTrading.lblCtraderConnectionStatus]",
                None,
            )
        )
        self.btnCtraderConnection.setText(
            QCoreApplication.translate(
                "SettingsPageTrading",
                "[SettingsPageTrading.btnCtraderConnection]",
                None,
            )
        )
        self.lblBrokerConnectionStatus.setText(
            QCoreApplication.translate(
                "SettingsPageTrading",
                "[SettingsPageTrading.lblIBConnectionStatus]",
                None,
            )
        )
        self.btnIbConnection.setText(
            QCoreApplication.translate(
                "SettingsPageTrading", "[SettingsPageTrading.btnIbConnection]", None
            )
        )
        self.btnOK.setText(
            QCoreApplication.translate("SettingsPageTrading", "[Common.btnOK]", None)
        )
        self.btnApply.setText(
            QCoreApplication.translate("SettingsPageTrading", "[Common.btnApply]", None)
        )
        self.btnCancel.setText(
            QCoreApplication.translate(
                "SettingsPageTrading", "[SettingsPageTrading.btnClose]", None
            )
        )

    # retranslateUi
