# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ib_connection_dialog.ui'
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
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class Ui_IBConnectionDialog(object):
    def setupUi(self, IBConnectionDialog):
        if not IBConnectionDialog.objectName():
            IBConnectionDialog.setObjectName("IBConnectionDialog")
        IBConnectionDialog.resize(653, 360)
        IBConnectionDialog.setMinimumSize(QSize(640, 0))
        IBConnectionDialog.setMaximumSize(QSize(760, 16777215))
        self.verticalLayout = QVBoxLayout(IBConnectionDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.lblHelp = QLabel(IBConnectionDialog)
        self.lblHelp.setObjectName("lblHelp")
        self.lblHelp.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblHelp)

        self.formLayout = QFormLayout()
        self.formLayout.setObjectName("formLayout")
        self.formLayout.setContentsMargins(6, 6, 6, 6)
        self.lblHost = QLabel(IBConnectionDialog)
        self.lblHost.setObjectName("lblHost")

        self.formLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblHost)

        self.editHost = QLineEdit(IBConnectionDialog)
        self.editHost.setObjectName("editHost")

        self.formLayout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.editHost)

        self.lblPort = QLabel(IBConnectionDialog)
        self.lblPort.setObjectName("lblPort")

        self.formLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblPort)

        self.spinPort = QSpinBox(IBConnectionDialog)
        self.spinPort.setObjectName("spinPort")
        self.spinPort.setMinimum(1)
        self.spinPort.setMaximum(65535)
        self.spinPort.setValue(7497)

        self.formLayout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.spinPort)

        self.lblClientId = QLabel(IBConnectionDialog)
        self.lblClientId.setObjectName("lblClientId")

        self.formLayout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblClientId)

        self.spinClientId = QSpinBox(IBConnectionDialog)
        self.spinClientId.setObjectName("spinClientId")
        self.spinClientId.setMinimum(1)
        self.spinClientId.setMaximum(9999)

        self.formLayout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.spinClientId)

        self.lblSelectedAccount = QLabel(IBConnectionDialog)
        self.lblSelectedAccount.setObjectName("lblSelectedAccount")

        self.formLayout.setWidget(
            3, QFormLayout.ItemRole.LabelRole, self.lblSelectedAccount
        )

        self.comboAccounts = QComboBox(IBConnectionDialog)
        self.comboAccounts.setObjectName("comboAccounts")

        self.formLayout.setWidget(3, QFormLayout.ItemRole.FieldRole, self.comboAccounts)

        self.lblHealth = QLabel(IBConnectionDialog)
        self.lblHealth.setObjectName("lblHealth")

        self.formLayout.setWidget(4, QFormLayout.ItemRole.LabelRole, self.lblHealth)

        self.lblHealthValue = QLabel(IBConnectionDialog)
        self.lblHealthValue.setObjectName("lblHealthValue")

        self.formLayout.setWidget(
            4, QFormLayout.ItemRole.FieldRole, self.lblHealthValue
        )

        self.lblAccount = QLabel(IBConnectionDialog)
        self.lblAccount.setObjectName("lblAccount")

        self.formLayout.setWidget(5, QFormLayout.ItemRole.LabelRole, self.lblAccount)

        self.lblAccountValue = QLabel(IBConnectionDialog)
        self.lblAccountValue.setObjectName("lblAccountValue")

        self.formLayout.setWidget(
            5, QFormLayout.ItemRole.FieldRole, self.lblAccountValue
        )

        self.verticalLayout.addLayout(self.formLayout)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.horizontalLayout.setContentsMargins(6, 6, 6, 6)
        self.horizontalSpacer = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.btnRefresh = QPushButton(IBConnectionDialog)
        self.btnRefresh.setObjectName("btnRefresh")
        self.btnRefresh.setMaximumSize(QSize(120, 16777215))
        self.btnRefresh.setAutoDefault(False)

        self.horizontalLayout.addWidget(self.btnRefresh)

        self.btnConnect = QPushButton(IBConnectionDialog)
        self.btnConnect.setObjectName("btnConnect")
        self.btnConnect.setMaximumSize(QSize(120, 16777215))
        self.btnConnect.setAutoDefault(False)

        self.horizontalLayout.addWidget(self.btnConnect)

        self.btnDisconnect = QPushButton(IBConnectionDialog)
        self.btnDisconnect.setObjectName("btnDisconnect")
        self.btnDisconnect.setMaximumSize(QSize(120, 16777215))
        self.btnDisconnect.setAutoDefault(False)

        self.horizontalLayout.addWidget(self.btnDisconnect)

        self.btnOk = QPushButton(IBConnectionDialog)
        self.btnOk.setObjectName("btnOk")
        self.btnOk.setMaximumSize(QSize(120, 16777215))
        self.btnOk.setAutoDefault(False)

        self.horizontalLayout.addWidget(self.btnOk)

        self.btnCancel = QPushButton(IBConnectionDialog)
        self.btnCancel.setObjectName("btnCancel")
        self.btnCancel.setMaximumSize(QSize(120, 16777215))
        self.btnCancel.setAutoDefault(False)

        self.horizontalLayout.addWidget(self.btnCancel)

        self.verticalLayout.addLayout(self.horizontalLayout)

        self.retranslateUi(IBConnectionDialog)

        QMetaObject.connectSlotsByName(IBConnectionDialog)

    # setupUi

    def retranslateUi(self, IBConnectionDialog):
        IBConnectionDialog.setWindowTitle(
            QCoreApplication.translate(
                "IBConnectionDialog", "[IBConnectionDialog.title]", None
            )
        )
        self.lblHelp.setText(
            QCoreApplication.translate(
                "IBConnectionDialog", "[IBConnectionDialog.lblHelp]", None
            )
        )
        self.lblHost.setText(
            QCoreApplication.translate(
                "IBConnectionDialog", "[IBConnectionDialog.lblHost]", None
            )
        )
        self.lblPort.setText(
            QCoreApplication.translate(
                "IBConnectionDialog", "[IBConnectionDialog.lblPort]", None
            )
        )
        self.lblClientId.setText(
            QCoreApplication.translate(
                "IBConnectionDialog", "[IBConnectionDialog.lblClientId]", None
            )
        )
        self.lblSelectedAccount.setText(
            QCoreApplication.translate(
                "IBConnectionDialog", "[IBConnectionDialog.lblSelectedAccount]", None
            )
        )
        self.lblHealth.setText(
            QCoreApplication.translate(
                "IBConnectionDialog", "[IBConnectionDialog.lblHealth]", None
            )
        )
        self.lblHealthValue.setText(
            QCoreApplication.translate("IBConnectionDialog", "-", None)
        )
        self.lblAccount.setText(
            QCoreApplication.translate(
                "IBConnectionDialog", "[IBConnectionDialog.lblAccount]", None
            )
        )
        self.lblAccountValue.setText(
            QCoreApplication.translate("IBConnectionDialog", "-", None)
        )
        self.btnRefresh.setText(
            QCoreApplication.translate(
                "IBConnectionDialog", "[IBConnectionDialog.btnRefreshState]", None
            )
        )
        self.btnConnect.setText(
            QCoreApplication.translate(
                "IBConnectionDialog", "[IBConnectionDialog.btnConnect]", None
            )
        )
        self.btnDisconnect.setText(
            QCoreApplication.translate(
                "IBConnectionDialog", "[IBConnectionDialog.btnDisconnect]", None
            )
        )
        self.btnOk.setText(
            QCoreApplication.translate("IBConnectionDialog", "[Common.btnOK]", None)
        )
        self.btnCancel.setText(
            QCoreApplication.translate("IBConnectionDialog", "[Common.btnCancel]", None)
        )

    # retranslateUi
