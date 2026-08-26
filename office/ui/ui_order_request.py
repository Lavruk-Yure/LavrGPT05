# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'order_request.ui'
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
    QAbstractButton,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
import resources_rc


class Ui_OrderRequestDialog(object):
    def setupUi(self, OrderRequestDialog):
        if not OrderRequestDialog.objectName():
            OrderRequestDialog.setObjectName("OrderRequestDialog")
        OrderRequestDialog.resize(466, 463)
        icon = QIcon()
        icon.addFile(
            ":/office/icons/lgeoffice_gpt_24x24.png",
            QSize(),
            QIcon.Mode.Normal,
            QIcon.State.Off,
        )
        OrderRequestDialog.setWindowIcon(icon)
        self.verticalLayout = QVBoxLayout(OrderRequestDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.formLayout = QFormLayout()
        self.formLayout.setObjectName("formLayout")
        self.formLayout.setHorizontalSpacing(6)
        self.formLayout.setVerticalSpacing(6)
        self.formLayout.setContentsMargins(9, 9, 9, 9)
        self.lblEdition = QLabel(OrderRequestDialog)
        self.lblEdition.setObjectName("lblEdition")

        self.formLayout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblEdition)

        self.cbEdition = QComboBox(OrderRequestDialog)
        self.cbEdition.addItem("")
        self.cbEdition.addItem("")
        self.cbEdition.setObjectName("cbEdition")

        self.formLayout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.cbEdition)

        self.lblAppVersion = QLabel(OrderRequestDialog)
        self.lblAppVersion.setObjectName("lblAppVersion")

        self.formLayout.setWidget(4, QFormLayout.ItemRole.LabelRole, self.lblAppVersion)

        self.leAppVersion = QLineEdit(OrderRequestDialog)
        self.leAppVersion.setObjectName("leAppVersion")

        self.formLayout.setWidget(4, QFormLayout.ItemRole.FieldRole, self.leAppVersion)

        self.lblPaymentRef = QLabel(OrderRequestDialog)
        self.lblPaymentRef.setObjectName("lblPaymentRef")

        self.formLayout.setWidget(5, QFormLayout.ItemRole.LabelRole, self.lblPaymentRef)

        self.lePaymentRef = QLineEdit(OrderRequestDialog)
        self.lePaymentRef.setObjectName("lePaymentRef")

        self.formLayout.setWidget(5, QFormLayout.ItemRole.FieldRole, self.lePaymentRef)

        self.lblFingerprint = QLabel(OrderRequestDialog)
        self.lblFingerprint.setObjectName("lblFingerprint")

        self.formLayout.setWidget(
            6, QFormLayout.ItemRole.LabelRole, self.lblFingerprint
        )

        self.leFingerprint = QLineEdit(OrderRequestDialog)
        self.leFingerprint.setObjectName("leFingerprint")

        self.formLayout.setWidget(6, QFormLayout.ItemRole.FieldRole, self.leFingerprint)

        self.lblNote = QLabel(OrderRequestDialog)
        self.lblNote.setObjectName("lblNote")

        self.formLayout.setWidget(8, QFormLayout.ItemRole.LabelRole, self.lblNote)

        self.pteNote = QPlainTextEdit(OrderRequestDialog)
        self.pteNote.setObjectName("pteNote")

        self.formLayout.setWidget(8, QFormLayout.ItemRole.FieldRole, self.pteNote)

        self.lblRef = QLabel(OrderRequestDialog)
        self.lblRef.setObjectName("lblRef")

        self.formLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblRef)

        self.leRef = QLineEdit(OrderRequestDialog)
        self.leRef.setObjectName("leRef")

        self.formLayout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.leRef)

        self.leName = QLineEdit(OrderRequestDialog)
        self.leName.setObjectName("leName")

        self.formLayout.setWidget(7, QFormLayout.ItemRole.FieldRole, self.leName)

        self.lblName = QLabel(OrderRequestDialog)
        self.lblName.setObjectName("lblName")

        self.formLayout.setWidget(7, QFormLayout.ItemRole.LabelRole, self.lblName)

        self.leEmail = QLineEdit(OrderRequestDialog)
        self.leEmail.setObjectName("leEmail")
        self.leEmail.setReadOnly(False)

        self.formLayout.setWidget(3, QFormLayout.ItemRole.FieldRole, self.leEmail)

        self.lblEmail = QLabel(OrderRequestDialog)
        self.lblEmail.setObjectName("lblEmail")

        self.formLayout.setWidget(3, QFormLayout.ItemRole.LabelRole, self.lblEmail)

        self.verticalLayout.addLayout(self.formLayout)

        self.buttonBox = QDialogButtonBox(OrderRequestDialog)
        self.buttonBox.setObjectName("buttonBox")
        self.buttonBox.setOrientation(Qt.Orientation.Horizontal)
        self.buttonBox.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )

        self.verticalLayout.addWidget(self.buttonBox)

        QWidget.setTabOrder(self.leRef, self.cbEdition)
        QWidget.setTabOrder(self.cbEdition, self.leEmail)
        QWidget.setTabOrder(self.leEmail, self.leAppVersion)
        QWidget.setTabOrder(self.leAppVersion, self.lePaymentRef)
        QWidget.setTabOrder(self.lePaymentRef, self.leFingerprint)
        QWidget.setTabOrder(self.leFingerprint, self.leName)
        QWidget.setTabOrder(self.leName, self.pteNote)

        self.retranslateUi(OrderRequestDialog)

        QMetaObject.connectSlotsByName(OrderRequestDialog)

    # setupUi

    def retranslateUi(self, OrderRequestDialog):
        OrderRequestDialog.setWindowTitle(
            QCoreApplication.translate(
                "OrderRequestDialog",
                "\u0417\u0430\u043c\u043e\u0432\u043b\u0435\u043d\u043d\u044f \u043b\u0456\u0446\u0435\u043d\u0437\u0456\u0457",
                None,
            )
        )
        self.lblEdition.setText(
            QCoreApplication.translate(
                "OrderRequestDialog",
                "\u0420\u0435\u0434\u0430\u043a\u0446\u0456\u044f",
                None,
            )
        )
        self.cbEdition.setItemText(
            0, QCoreApplication.translate("OrderRequestDialog", "PRO", None)
        )
        self.cbEdition.setItemText(
            1, QCoreApplication.translate("OrderRequestDialog", "PRO+", None)
        )

        self.lblAppVersion.setText(
            QCoreApplication.translate(
                "OrderRequestDialog", "\u0412\u0435\u0440\u0441\u0456\u044f", None
            )
        )
        self.leAppVersion.setPlaceholderText(
            QCoreApplication.translate("OrderRequestDialog", "App version", None)
        )
        self.lblPaymentRef.setText(
            QCoreApplication.translate(
                "OrderRequestDialog", "\u041f\u043b\u0430\u0442\u0456\u0436 (Ref)", None
            )
        )
        self.lePaymentRef.setPlaceholderText(
            QCoreApplication.translate("OrderRequestDialog", "Payment reference", None)
        )
        self.lblFingerprint.setText(
            QCoreApplication.translate(
                "OrderRequestDialog",
                "\u0421\u0438\u0433\u043d\u0430\u0442\u0443\u0440\u0430 \u041f\u041a",
                None,
            )
        )
        self.leFingerprint.setPlaceholderText(
            QCoreApplication.translate("OrderRequestDialog", "Fingerprint", None)
        )
        self.lblNote.setText(
            QCoreApplication.translate(
                "OrderRequestDialog",
                "\u041f\u0440\u0438\u043c\u0456\u0442\u043a\u0430",
                None,
            )
        )
        self.pteNote.setPlaceholderText(
            QCoreApplication.translate("OrderRequestDialog", "Note", None)
        )
        self.lblRef.setText(
            QCoreApplication.translate(
                "OrderRequestDialog",
                "\u0417\u0430\u043c\u043e\u0432\u043b\u0435\u043d\u043d\u044f",
                None,
            )
        )
        self.leRef.setPlaceholderText(
            QCoreApplication.translate("OrderRequestDialog", "ORDER_ID", None)
        )
        self.leName.setPlaceholderText(
            QCoreApplication.translate("OrderRequestDialog", "Name", None)
        )
        self.lblName.setText(
            QCoreApplication.translate("OrderRequestDialog", "\u041f\u0406\u0411", None)
        )
        self.leEmail.setPlaceholderText(
            QCoreApplication.translate("OrderRequestDialog", "Customer email", None)
        )
        self.lblEmail.setText(
            QCoreApplication.translate("OrderRequestDialog", "Email", None)
        )

    # retranslateUi
