# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'payment_add.ui'
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


class Ui_payment_add(object):
    def setupUi(self, payment_add):
        if not payment_add.objectName():
            payment_add.setObjectName("payment_add")
        payment_add.resize(492, 489)
        icon = QIcon()
        icon.addFile(
            ":/office/icons/lgeoffice_gpt_24x24.png",
            QSize(),
            QIcon.Mode.Normal,
            QIcon.State.Off,
        )
        payment_add.setWindowIcon(icon)
        payment_add.setModal(True)
        self.verticalLayout = QVBoxLayout(payment_add)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout_0 = QHBoxLayout()
        self.horizontalLayout_0.setObjectName("horizontalLayout_0")
        self.horizontalLayout_0.setContentsMargins(6, 6, 6, 6)
        self.lblbank = QLabel(payment_add)
        self.lblbank.setObjectName("lblbank")

        self.horizontalLayout_0.addWidget(self.lblbank)

        self.comboBank = QComboBox(payment_add)
        self.comboBank.addItem("")
        self.comboBank.setObjectName("comboBank")

        self.horizontalLayout_0.addWidget(self.comboBank)

        self.horizontalLayout_0.setStretch(0, 1)
        self.horizontalLayout_0.setStretch(1, 2)

        self.verticalLayout.addLayout(self.horizontalLayout_0)

        self.horizontalLayout_1 = QHBoxLayout()
        self.horizontalLayout_1.setObjectName("horizontalLayout_1")
        self.horizontalLayout_1.setContentsMargins(6, 6, 6, 6)
        self.lblOrderId = QLabel(payment_add)
        self.lblOrderId.setObjectName("lblOrderId")

        self.horizontalLayout_1.addWidget(self.lblOrderId)

        self.editOrderId = QLineEdit(payment_add)
        self.editOrderId.setObjectName("editOrderId")

        self.horizontalLayout_1.addWidget(self.editOrderId)

        self.horizontalLayout_1.setStretch(0, 1)
        self.horizontalLayout_1.setStretch(1, 2)

        self.verticalLayout.addLayout(self.horizontalLayout_1)

        self.horizontalLayout_3 = QHBoxLayout()
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.horizontalLayout_3.setContentsMargins(6, 6, 6, 6)
        self.lblCurrency = QLabel(payment_add)
        self.lblCurrency.setObjectName("lblCurrency")

        self.horizontalLayout_3.addWidget(self.lblCurrency)

        self.comboCurrency = QComboBox(payment_add)
        self.comboCurrency.addItem("")
        self.comboCurrency.addItem("")
        self.comboCurrency.setObjectName("comboCurrency")

        self.horizontalLayout_3.addWidget(self.comboCurrency)

        self.horizontalLayout_3.setStretch(0, 1)
        self.horizontalLayout_3.setStretch(1, 2)

        self.verticalLayout.addLayout(self.horizontalLayout_3)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.horizontalLayout.setContentsMargins(6, 6, 6, 6)
        self.lblFxRate = QLabel(payment_add)
        self.lblFxRate.setObjectName("lblFxRate")

        self.horizontalLayout.addWidget(self.lblFxRate)

        self.editFxRate = QLineEdit(payment_add)
        self.editFxRate.setObjectName("editFxRate")

        self.horizontalLayout.addWidget(self.editFxRate)

        self.horizontalLayout.setStretch(0, 1)
        self.horizontalLayout.setStretch(1, 2)

        self.verticalLayout.addLayout(self.horizontalLayout)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.horizontalLayout_2.setContentsMargins(6, 6, 6, 6)
        self.lblAmount = QLabel(payment_add)
        self.lblAmount.setObjectName("lblAmount")

        self.horizontalLayout_2.addWidget(self.lblAmount)

        self.edit_card_amount = QLineEdit(payment_add)
        self.edit_card_amount.setObjectName("edit_card_amount")

        self.horizontalLayout_2.addWidget(self.edit_card_amount)

        self.horizontalLayout_2.setStretch(0, 1)
        self.horizontalLayout_2.setStretch(1, 2)

        self.verticalLayout.addLayout(self.horizontalLayout_2)

        self.horizontalLayout_5 = QHBoxLayout()
        self.horizontalLayout_5.setObjectName("horizontalLayout_5")
        self.horizontalLayout_5.setContentsMargins(6, 6, 6, 6)
        self.lblBankTxId = QLabel(payment_add)
        self.lblBankTxId.setObjectName("lblBankTxId")

        self.horizontalLayout_5.addWidget(self.lblBankTxId)

        self.edit_op_amount = QLineEdit(payment_add)
        self.edit_op_amount.setObjectName("edit_op_amount")

        self.horizontalLayout_5.addWidget(self.edit_op_amount)

        self.horizontalLayout_5.setStretch(0, 1)
        self.horizontalLayout_5.setStretch(1, 2)

        self.verticalLayout.addLayout(self.horizontalLayout_5)

        self.horizontalLayout_4 = QHBoxLayout()
        self.horizontalLayout_4.setObjectName("horizontalLayout_4")
        self.horizontalLayout_4.setContentsMargins(6, 6, 6, 6)
        self.lblPaymentRef = QLabel(payment_add)
        self.lblPaymentRef.setObjectName("lblPaymentRef")

        self.horizontalLayout_4.addWidget(self.lblPaymentRef)

        self.editPaymentRef = QLineEdit(payment_add)
        self.editPaymentRef.setObjectName("editPaymentRef")

        self.horizontalLayout_4.addWidget(self.editPaymentRef)

        self.horizontalLayout_4.setStretch(0, 1)
        self.horizontalLayout_4.setStretch(1, 2)

        self.verticalLayout.addLayout(self.horizontalLayout_4)

        self.horizontalLayout_6 = QHBoxLayout()
        self.horizontalLayout_6.setObjectName("horizontalLayout_6")
        self.horizontalLayout_6.setContentsMargins(6, 6, 6, 6)
        self.lblPaidUtc = QLabel(payment_add)
        self.lblPaidUtc.setObjectName("lblPaidUtc")

        self.horizontalLayout_6.addWidget(self.lblPaidUtc)

        self.editPaidUtc = QLineEdit(payment_add)
        self.editPaidUtc.setObjectName("editPaidUtc")

        self.horizontalLayout_6.addWidget(self.editPaidUtc)

        self.horizontalLayout_6.setStretch(0, 1)
        self.horizontalLayout_6.setStretch(1, 2)

        self.verticalLayout.addLayout(self.horizontalLayout_6)

        self.horizontalLayout_7 = QHBoxLayout()
        self.horizontalLayout_7.setObjectName("horizontalLayout_7")
        self.horizontalLayout_7.setContentsMargins(6, 6, 6, 6)
        self.lblNote = QLabel(payment_add)
        self.lblNote.setObjectName("lblNote")

        self.horizontalLayout_7.addWidget(self.lblNote)

        self.editNote = QPlainTextEdit(payment_add)
        self.editNote.setObjectName("editNote")

        self.horizontalLayout_7.addWidget(self.editNote)

        self.horizontalLayout_7.setStretch(0, 1)
        self.horizontalLayout_7.setStretch(1, 2)

        self.verticalLayout.addLayout(self.horizontalLayout_7)

        self.horizontalLayout_8 = QHBoxLayout()
        self.horizontalLayout_8.setObjectName("horizontalLayout_8")
        self.horizontalLayout_8.setContentsMargins(6, 6, 6, 6)
        self.horizontalSpacer = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayout_8.addItem(self.horizontalSpacer)

        self.btnOk = QPushButton(payment_add)
        self.btnOk.setObjectName("btnOk")
        self.btnOk.setCheckable(True)

        self.horizontalLayout_8.addWidget(self.btnOk)

        self.btnCancel = QPushButton(payment_add)
        self.btnCancel.setObjectName("btnCancel")

        self.horizontalLayout_8.addWidget(self.btnCancel)

        self.horizontalLayout_8.setStretch(1, 1)
        self.horizontalLayout_8.setStretch(2, 1)

        self.verticalLayout.addLayout(self.horizontalLayout_8)

        self.verticalLayout.setStretch(4, 1)
        self.verticalLayout.setStretch(6, 1)
        self.verticalLayout.setStretch(7, 1)
        self.verticalLayout.setStretch(8, 4)
        self.verticalLayout.setStretch(9, 2)

        self.retranslateUi(payment_add)

        QMetaObject.connectSlotsByName(payment_add)

    # setupUi

    def retranslateUi(self, payment_add):
        payment_add.setWindowTitle(
            QCoreApplication.translate(
                "payment_add",
                "\u0412\u0432\u0456\u0434 \u0432\u0438\u043f\u0438\u0441\u043a\u0438 \u0431\u0430\u043d\u043a\u0430",
                None,
            )
        )
        self.lblbank.setText(
            QCoreApplication.translate("payment_add", "\u0411\u0430\u043d\u043a", None)
        )
        self.comboBank.setItemText(
            0,
            QCoreApplication.translate(
                "payment_add", "A-\u0411\u0430\u043d\u043a", None
            ),
        )

        self.lblOrderId.setText(
            QCoreApplication.translate("payment_add", "Order ID", None)
        )
        self.editOrderId.setPlaceholderText(
            QCoreApplication.translate(
                "payment_add",
                "LGE-YYYYMMDD-HHMM-XXXX/\u041c\u043e\u0436\u0435 \u0431\u0443\u0442\u0438 \u0432\u0456\u0434\u0441\u0443\u0442\u043d\u0456\u0439",
                None,
            )
        )
        self.lblCurrency.setText(
            QCoreApplication.translate(
                "payment_add", "\u0412\u0430\u043b\u044e\u0442\u0430", None
            )
        )
        self.comboCurrency.setItemText(
            0, QCoreApplication.translate("payment_add", "UAH", None)
        )
        self.comboCurrency.setItemText(
            1, QCoreApplication.translate("payment_add", "USD", None)
        )

        self.lblFxRate.setText(
            QCoreApplication.translate(
                "payment_add", "\u041a\u0443\u0440\u0441 USD\u2192UAH", None
            )
        )
        self.editFxRate.setPlaceholderText(
            QCoreApplication.translate(
                "payment_add", "43.0900 \u0430\u0431\u043e 43.09", None
            )
        )
        self.lblAmount.setText(
            QCoreApplication.translate(
                "payment_add", "\u0421\u0443\u043c\u0430 (\u0433\u0440\u043d)", None
            )
        )
        self.edit_card_amount.setPlaceholderText(
            QCoreApplication.translate("payment_add", "432.00", None)
        )
        self.lblBankTxId.setText(
            QCoreApplication.translate(
                "payment_add", "\u0421\u0443\u043c\u0430 (\u0434\u043e\u043b)", None
            )
        )
        self.edit_op_amount.setPlaceholderText(
            QCoreApplication.translate("payment_add", "100.00", None)
        )
        self.lblPaymentRef.setText(
            QCoreApplication.translate("payment_add", "Payment reference", None)
        )
        self.editPaymentRef.setPlaceholderText(
            QCoreApplication.translate(
                "payment_add",
                "\u041c\u043e\u0436\u0435 \u0431\u0443\u0442\u0438 \u0432\u0456\u0434\u0441\u0443\u0442\u043d\u044f",
                None,
            )
        )
        self.lblPaidUtc.setText(
            QCoreApplication.translate(
                "payment_add", "\u0414\u0430\u0442\u0430/\u0447\u0430\u0441 (UTC)", None
            )
        )
        self.editPaidUtc.setPlaceholderText(
            QCoreApplication.translate(
                "payment_add", "06.02.2026 \u0430\u0431\u043e 02.02.2026 21:43", None
            )
        )
        self.lblNote.setText(
            QCoreApplication.translate(
                "payment_add", "\u041a\u043e\u043c\u0435\u043d\u0442\u0430\u0440", None
            )
        )
        self.btnOk.setText(
            QCoreApplication.translate(
                "payment_add", "\u0417\u0431\u0435\u0440\u0435\u0433\u0442\u0438", None
            )
        )
        self.btnCancel.setText(
            QCoreApplication.translate(
                "payment_add",
                "\u0421\u043a\u0430\u0441\u0443\u0432\u0430\u0442\u0438",
                None,
            )
        )

    # retranslateUi
