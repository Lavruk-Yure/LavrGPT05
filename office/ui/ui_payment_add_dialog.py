# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'payment_add_dialog.ui'
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
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)
import resources_rc


class Ui_payment_add_dialog(object):
    def setupUi(self, payment_add_dialog):
        if not payment_add_dialog.objectName():
            payment_add_dialog.setObjectName("payment_add_dialog")
        payment_add_dialog.resize(440, 376)
        icon = QIcon()
        icon.addFile(
            ":/office/icons/lgeoffice_gpt_24x24.png",
            QSize(),
            QIcon.Mode.Normal,
            QIcon.State.Off,
        )
        payment_add_dialog.setWindowIcon(icon)
        payment_add_dialog.setModal(True)
        self.verticalLayout = QVBoxLayout(payment_add_dialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.verticalLayout.setContentsMargins(8, 8, 8, 8)
        self.formLayout_9 = QFormLayout()
        self.formLayout_9.setObjectName("formLayout_9")
        self.lblOrderInfo = QLabel(payment_add_dialog)
        self.lblOrderInfo.setObjectName("lblOrderInfo")
        self.lblOrderInfo.setMinimumSize(QSize(120, 0))

        self.formLayout_9.setWidget(
            0, QFormLayout.ItemRole.LabelRole, self.lblOrderInfo
        )

        self.lblOrderInfoValue = QLabel(payment_add_dialog)
        self.lblOrderInfoValue.setObjectName("lblOrderInfoValue")
        self.lblOrderInfoValue.setFrameShape(QFrame.Shape.StyledPanel)

        self.formLayout_9.setWidget(
            0, QFormLayout.ItemRole.FieldRole, self.lblOrderInfoValue
        )

        self.verticalLayout.addLayout(self.formLayout_9)

        self.formLayout_3 = QFormLayout()
        self.formLayout_3.setObjectName("formLayout_3")
        self.lblBank = QLabel(payment_add_dialog)
        self.lblBank.setObjectName("lblBank")
        self.lblBank.setMinimumSize(QSize(120, 0))

        self.formLayout_3.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblBank)

        self.comboBank = QComboBox(payment_add_dialog)
        self.comboBank.addItem("")
        self.comboBank.addItem("")
        self.comboBank.addItem("")
        self.comboBank.setObjectName("comboBank")
        self.comboBank.setEditable(True)

        self.formLayout_3.setWidget(0, QFormLayout.ItemRole.FieldRole, self.comboBank)

        self.verticalLayout.addLayout(self.formLayout_3)

        self.formLayout_5 = QFormLayout()
        self.formLayout_5.setObjectName("formLayout_5")
        self.lblExternalRef = QLabel(payment_add_dialog)
        self.lblExternalRef.setObjectName("lblExternalRef")
        self.lblExternalRef.setMinimumSize(QSize(120, 0))

        self.formLayout_5.setWidget(
            0, QFormLayout.ItemRole.LabelRole, self.lblExternalRef
        )

        self.editExternalRef = QLineEdit(payment_add_dialog)
        self.editExternalRef.setObjectName("editExternalRef")

        self.formLayout_5.setWidget(
            0, QFormLayout.ItemRole.FieldRole, self.editExternalRef
        )

        self.verticalLayout.addLayout(self.formLayout_5)

        self.formLayout = QFormLayout()
        self.formLayout.setObjectName("formLayout")
        self.lblAmount = QLabel(payment_add_dialog)
        self.lblAmount.setObjectName("lblAmount")
        self.lblAmount.setMinimumSize(QSize(120, 0))

        self.formLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblAmount)

        self.editAmount = QLineEdit(payment_add_dialog)
        self.editAmount.setObjectName("editAmount")

        self.formLayout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.editAmount)

        self.verticalLayout.addLayout(self.formLayout)

        self.formLayout_4 = QFormLayout()
        self.formLayout_4.setObjectName("formLayout_4")
        self.lblCurrency = QLabel(payment_add_dialog)
        self.lblCurrency.setObjectName("lblCurrency")
        self.lblCurrency.setMinimumSize(QSize(120, 0))

        self.formLayout_4.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblCurrency)

        self.comboCurrency = QComboBox(payment_add_dialog)
        self.comboCurrency.addItem("")
        self.comboCurrency.addItem("")
        self.comboCurrency.setObjectName("comboCurrency")

        self.formLayout_4.setWidget(
            0, QFormLayout.ItemRole.FieldRole, self.comboCurrency
        )

        self.verticalLayout.addLayout(self.formLayout_4)

        self.formLayout_6 = QFormLayout()
        self.formLayout_6.setObjectName("formLayout_6")
        self.lblFxRate = QLabel(payment_add_dialog)
        self.lblFxRate.setObjectName("lblFxRate")
        self.lblFxRate.setMinimumSize(QSize(120, 0))

        self.formLayout_6.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblFxRate)

        self.editFxRate = QLineEdit(payment_add_dialog)
        self.editFxRate.setObjectName("editFxRate")

        self.formLayout_6.setWidget(0, QFormLayout.ItemRole.FieldRole, self.editFxRate)

        self.verticalLayout.addLayout(self.formLayout_6)

        self.formLayout_7 = QFormLayout()
        self.formLayout_7.setObjectName("formLayout_7")
        self.lblPaidUtc = QLabel(payment_add_dialog)
        self.lblPaidUtc.setObjectName("lblPaidUtc")
        self.lblPaidUtc.setMinimumSize(QSize(120, 0))

        self.formLayout_7.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblPaidUtc)

        self.editPaidUtc = QLineEdit(payment_add_dialog)
        self.editPaidUtc.setObjectName("editPaidUtc")

        self.formLayout_7.setWidget(0, QFormLayout.ItemRole.FieldRole, self.editPaidUtc)

        self.verticalLayout.addLayout(self.formLayout_7)

        self.formLayout_2 = QFormLayout()
        self.formLayout_2.setObjectName("formLayout_2")
        self.lblAmountUsd = QLabel(payment_add_dialog)
        self.lblAmountUsd.setObjectName("lblAmountUsd")
        self.lblAmountUsd.setMinimumSize(QSize(120, 0))

        self.formLayout_2.setWidget(
            0, QFormLayout.ItemRole.LabelRole, self.lblAmountUsd
        )

        self.lblAmountUsdValue = QLabel(payment_add_dialog)
        self.lblAmountUsdValue.setObjectName("lblAmountUsdValue")
        self.lblAmountUsdValue.setFrameShape(QFrame.Shape.StyledPanel)

        self.formLayout_2.setWidget(
            0, QFormLayout.ItemRole.FieldRole, self.lblAmountUsdValue
        )

        self.verticalLayout.addLayout(self.formLayout_2)

        self.formLayout_8 = QFormLayout()
        self.formLayout_8.setObjectName("formLayout_8")
        self.lblNote = QLabel(payment_add_dialog)
        self.lblNote.setObjectName("lblNote")
        self.lblNote.setMinimumSize(QSize(120, 0))

        self.formLayout_8.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblNote)

        self.editNote = QPlainTextEdit(payment_add_dialog)
        self.editNote.setObjectName("editNote")
        self.editNote.setMinimumSize(QSize(0, 90))

        self.formLayout_8.setWidget(0, QFormLayout.ItemRole.FieldRole, self.editNote)

        self.verticalLayout.addLayout(self.formLayout_8)

        self.rowButtons = QHBoxLayout()
        self.rowButtons.setObjectName("rowButtons")
        self.horizontalSpacer = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.rowButtons.addItem(self.horizontalSpacer)

        self.btnOk = QPushButton(payment_add_dialog)
        self.btnOk.setObjectName("btnOk")

        self.rowButtons.addWidget(self.btnOk)

        self.btnCancel = QPushButton(payment_add_dialog)
        self.btnCancel.setObjectName("btnCancel")

        self.rowButtons.addWidget(self.btnCancel)

        self.verticalLayout.addLayout(self.rowButtons)

        self.retranslateUi(payment_add_dialog)

        QMetaObject.connectSlotsByName(payment_add_dialog)

    # setupUi

    def retranslateUi(self, payment_add_dialog):
        payment_add_dialog.setWindowTitle(
            QCoreApplication.translate(
                "payment_add_dialog",
                "\u0414\u043e\u0434\u0430\u0442\u0438 \u043f\u043b\u0430\u0442\u0456\u0436",
                None,
            )
        )
        self.lblOrderInfo.setText(
            QCoreApplication.translate("payment_add_dialog", "Order", None)
        )
        self.lblOrderInfoValue.setText(
            QCoreApplication.translate(
                "payment_add_dialog",
                "\u041d\u0435 \u043f\u0440\u0438\u0432\u2019\u044f\u0437\u0430\u043d\u043e",
                None,
            )
        )
        self.lblBank.setText(
            QCoreApplication.translate("payment_add_dialog", "Bank", None)
        )
        self.comboBank.setItemText(
            0,
            QCoreApplication.translate(
                "payment_add_dialog", "A-\u0411\u0430\u043d\u043a", None
            ),
        )
        self.comboBank.setItemText(
            1,
            QCoreApplication.translate(
                "payment_add_dialog",
                "\u041f\u0440\u0438\u0432\u0430\u0442\u0411\u0430\u043d\u043a",
                None,
            ),
        )
        self.comboBank.setItemText(
            2, QCoreApplication.translate("payment_add_dialog", "MonoBank", None)
        )

        self.lblExternalRef.setText(
            QCoreApplication.translate("payment_add_dialog", "External Ref", None)
        )
        self.editExternalRef.setPlaceholderText(
            QCoreApplication.translate(
                "payment_add_dialog", "LGE-20260215-1236-5904", None
            )
        )
        self.lblAmount.setText(
            QCoreApplication.translate("payment_add_dialog", "Operation Amount", None)
        )
        self.editAmount.setPlaceholderText(
            QCoreApplication.translate("payment_add_dialog", "150.00", None)
        )
        self.lblCurrency.setText(
            QCoreApplication.translate("payment_add_dialog", "Operation Currency", None)
        )
        self.comboCurrency.setItemText(
            0, QCoreApplication.translate("payment_add_dialog", "USD", None)
        )
        self.comboCurrency.setItemText(
            1, QCoreApplication.translate("payment_add_dialog", "UAH", None)
        )

        self.lblFxRate.setText(
            QCoreApplication.translate("payment_add_dialog", "FX Rate", None)
        )
        self.editFxRate.setPlaceholderText(
            QCoreApplication.translate("payment_add_dialog", "43.0900", None)
        )
        self.lblPaidUtc.setText(
            QCoreApplication.translate("payment_add_dialog", "Paid UTC", None)
        )
        self.editPaidUtc.setPlaceholderText(
            QCoreApplication.translate("payment_add_dialog", "2026-03-11 15:08", None)
        )
        self.lblAmountUsd.setText(
            QCoreApplication.translate("payment_add_dialog", "USD for DB", None)
        )
        self.lblAmountUsdValue.setText(
            QCoreApplication.translate("payment_add_dialog", "-", None)
        )
        self.lblNote.setText(
            QCoreApplication.translate("payment_add_dialog", "Note", None)
        )
        self.btnOk.setText(QCoreApplication.translate("payment_add_dialog", "OK", None))
        self.btnCancel.setText(
            QCoreApplication.translate(
                "payment_add_dialog",
                "\u0421\u043a\u0430\u0441\u0443\u0432\u0430\u0442\u0438",
                None,
            )
        )

    # retranslateUi
