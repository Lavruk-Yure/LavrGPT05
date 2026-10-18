# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ctrader_connection_dialog.ui'
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
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QSpacerItem, QSpinBox, QVBoxLayout,
    QWidget)

class Ui_CTraderConnectionDialog(object):
    def setupUi(self, CTraderConnectionDialog):
        if not CTraderConnectionDialog.objectName():
            CTraderConnectionDialog.setObjectName(u"CTraderConnectionDialog")
        CTraderConnectionDialog.resize(618, 274)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(CTraderConnectionDialog.sizePolicy().hasHeightForWidth())
        CTraderConnectionDialog.setSizePolicy(sizePolicy)
        CTraderConnectionDialog.setMaximumSize(QSize(16777215, 16777215))
        self.verticalLayout = QVBoxLayout(CTraderConnectionDialog)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.lblHelp = QLabel(CTraderConnectionDialog)
        self.lblHelp.setObjectName(u"lblHelp")
        self.lblHelp.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblHelp)

        self.formLayout = QFormLayout()
        self.formLayout.setObjectName(u"formLayout")
        self.formLayout.setContentsMargins(6, 6, 6, 6)
        self.lblHost = QLabel(CTraderConnectionDialog)
        self.lblHost.setObjectName(u"lblHost")

        self.formLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblHost)

        self.editHost = QLineEdit(CTraderConnectionDialog)
        self.editHost.setObjectName(u"editHost")
        self.editHost.setReadOnly(True)

        self.formLayout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.editHost)

        self.lblPort = QLabel(CTraderConnectionDialog)
        self.lblPort.setObjectName(u"lblPort")

        self.formLayout.setWidget(3, QFormLayout.ItemRole.LabelRole, self.lblPort)

        self.spinPort = QSpinBox(CTraderConnectionDialog)
        self.spinPort.setObjectName(u"spinPort")
        self.spinPort.setMinimum(1)
        self.spinPort.setMaximum(65535)
        self.spinPort.setValue(5035)

        self.formLayout.setWidget(3, QFormLayout.ItemRole.FieldRole, self.spinPort)

        self.lblClientId = QLabel(CTraderConnectionDialog)
        self.lblClientId.setObjectName(u"lblClientId")

        self.formLayout.setWidget(4, QFormLayout.ItemRole.LabelRole, self.lblClientId)

        self.editClientId = QLineEdit(CTraderConnectionDialog)
        self.editClientId.setObjectName(u"editClientId")

        self.formLayout.setWidget(4, QFormLayout.ItemRole.FieldRole, self.editClientId)

        self.lblClientSecret = QLabel(CTraderConnectionDialog)
        self.lblClientSecret.setObjectName(u"lblClientSecret")

        self.formLayout.setWidget(5, QFormLayout.ItemRole.LabelRole, self.lblClientSecret)

        self.editClientSecret = QLineEdit(CTraderConnectionDialog)
        self.editClientSecret.setObjectName(u"editClientSecret")
        self.editClientSecret.setEchoMode(QLineEdit.EchoMode.Password)

        self.formLayout.setWidget(5, QFormLayout.ItemRole.FieldRole, self.editClientSecret)

        self.lblAccountId = QLabel(CTraderConnectionDialog)
        self.lblAccountId.setObjectName(u"lblAccountId")

        self.formLayout.setWidget(6, QFormLayout.ItemRole.LabelRole, self.lblAccountId)

        self.comboAccountId = QComboBox(CTraderConnectionDialog)
        self.comboAccountId.setObjectName(u"comboAccountId")
        self.comboAccountId.setEnabled(False)

        self.formLayout.setWidget(6, QFormLayout.ItemRole.FieldRole, self.comboAccountId)

        self.lblAccountMode = QLabel(CTraderConnectionDialog)
        self.lblAccountMode.setObjectName(u"lblAccountMode")

        self.formLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblAccountMode)

        self.comboAccountMode = QComboBox(CTraderConnectionDialog)
        self.comboAccountMode.setObjectName(u"comboAccountMode")

        self.formLayout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.comboAccountMode)


        self.verticalLayout.addLayout(self.formLayout)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalLayout.setContentsMargins(9, 9, 9, 9)
        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.btnAuthorizeCtrader = QPushButton(CTraderConnectionDialog)
        self.btnAuthorizeCtrader.setObjectName(u"btnAuthorizeCtrader")
        self.btnAuthorizeCtrader.setMaximumSize(QSize(150, 16777215))

        self.horizontalLayout.addWidget(self.btnAuthorizeCtrader)

        self.btnTestConnection = QPushButton(CTraderConnectionDialog)
        self.btnTestConnection.setObjectName(u"btnTestConnection")
        self.btnTestConnection.setMaximumSize(QSize(150, 16777215))

        self.horizontalLayout.addWidget(self.btnTestConnection)

        self.btnDisconnect = QPushButton(CTraderConnectionDialog)
        self.btnDisconnect.setObjectName(u"btnDisconnect")

        self.horizontalLayout.addWidget(self.btnDisconnect)

        self.btnOK = QPushButton(CTraderConnectionDialog)
        self.btnOK.setObjectName(u"btnOK")

        self.horizontalLayout.addWidget(self.btnOK)

        self.btnCancel = QPushButton(CTraderConnectionDialog)
        self.btnCancel.setObjectName(u"btnCancel")

        self.horizontalLayout.addWidget(self.btnCancel)


        self.verticalLayout.addLayout(self.horizontalLayout)

        self.verticalLayout.setStretch(1, 6)
        self.verticalLayout.setStretch(2, 1)

        self.retranslateUi(CTraderConnectionDialog)

        QMetaObject.connectSlotsByName(CTraderConnectionDialog)
    # setupUi

    def retranslateUi(self, CTraderConnectionDialog):
        CTraderConnectionDialog.setWindowTitle(QCoreApplication.translate("CTraderConnectionDialog", u"[CTraderConnectionDialog.title]", None))
        self.lblHelp.setText(QCoreApplication.translate("CTraderConnectionDialog", u"[CTraderConnectionDialog.lblHelp]", None))
        self.lblHost.setText(QCoreApplication.translate("CTraderConnectionDialog", u"[CTraderConnectionDialog.lblHost]", None))
        self.lblPort.setText(QCoreApplication.translate("CTraderConnectionDialog", u"[CTraderConnectionDialog.lblPort]", None))
        self.lblClientId.setText(QCoreApplication.translate("CTraderConnectionDialog", u"[CTraderConnectionDialog.lblClientId]", None))
        self.lblClientSecret.setText(QCoreApplication.translate("CTraderConnectionDialog", u"[CTraderConnectionDialog.lblClientSecret]", None))
        self.lblAccountId.setText(QCoreApplication.translate("CTraderConnectionDialog", u"[CTraderConnectionDialog.lblAccountId]", None))
        self.lblAccountMode.setText(QCoreApplication.translate("CTraderConnectionDialog", u"[CTraderConnectionDialog.lblAccountMode]", None))
        self.btnAuthorizeCtrader.setText(QCoreApplication.translate("CTraderConnectionDialog", u"[CTraderConnectionDialog.btnAuthorizeCtrader]", None))
        self.btnTestConnection.setText(QCoreApplication.translate("CTraderConnectionDialog", u"[CTraderConnectionDialog.btnTestConnection]", None))
        self.btnDisconnect.setText(QCoreApplication.translate("CTraderConnectionDialog", u"[CTraderConnectionDialog.btnDisconnect]", None))
        self.btnOK.setText(QCoreApplication.translate("CTraderConnectionDialog", u"[Common.btnOK]", None))
        self.btnCancel.setText(QCoreApplication.translate("CTraderConnectionDialog", u"[Common.btnCancel]", None))
    # retranslateUi

