# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'quick_issue_dialog.ui'
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
    QGroupBox,
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


class Ui_QuickIssueDialog(object):
    def setupUi(self, QuickIssueDialog):
        if not QuickIssueDialog.objectName():
            QuickIssueDialog.setObjectName("QuickIssueDialog")
        QuickIssueDialog.resize(532, 733)
        QuickIssueDialog.setMinimumSize(QSize(475, 560))
        icon = QIcon()
        icon.addFile(
            ":/office/icons/lgeoffice_gpt_24x24.png",
            QSize(),
            QIcon.Mode.Normal,
            QIcon.State.Off,
        )
        QuickIssueDialog.setWindowIcon(icon)
        QuickIssueDialog.setModal(True)
        self.verticalLayoutMain = QVBoxLayout(QuickIssueDialog)
        self.verticalLayoutMain.setObjectName("verticalLayoutMain")
        self.lblTitle = QLabel(QuickIssueDialog)
        self.lblTitle.setObjectName("lblTitle")
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        self.lblTitle.setFont(font)

        self.verticalLayoutMain.addWidget(self.lblTitle)

        self.lblHint = QLabel(QuickIssueDialog)
        self.lblHint.setObjectName("lblHint")
        self.lblHint.setWordWrap(True)

        self.verticalLayoutMain.addWidget(self.lblHint)

        self.grpCustomer = QGroupBox(QuickIssueDialog)
        self.grpCustomer.setObjectName("grpCustomer")
        self.grpCustomer.setMinimumSize(QSize(0, 130))
        self.formLayoutCustomer = QFormLayout(self.grpCustomer)
        self.formLayoutCustomer.setObjectName("formLayoutCustomer")
        self.formLayoutCustomer.setContentsMargins(-1, 20, -1, -1)
        self.lblEmail = QLabel(self.grpCustomer)
        self.lblEmail.setObjectName("lblEmail")

        self.formLayoutCustomer.setWidget(
            0, QFormLayout.ItemRole.LabelRole, self.lblEmail
        )

        self.editEmail = QLineEdit(self.grpCustomer)
        self.editEmail.setObjectName("editEmail")

        self.formLayoutCustomer.setWidget(
            0, QFormLayout.ItemRole.FieldRole, self.editEmail
        )

        self.lblCustomerName = QLabel(self.grpCustomer)
        self.lblCustomerName.setObjectName("lblCustomerName")

        self.formLayoutCustomer.setWidget(
            1, QFormLayout.ItemRole.LabelRole, self.lblCustomerName
        )

        self.editCustomerName = QLineEdit(self.grpCustomer)
        self.editCustomerName.setObjectName("editCustomerName")

        self.formLayoutCustomer.setWidget(
            1, QFormLayout.ItemRole.FieldRole, self.editCustomerName
        )

        self.lblCustomerNote = QLabel(self.grpCustomer)
        self.lblCustomerNote.setObjectName("lblCustomerNote")

        self.formLayoutCustomer.setWidget(
            2, QFormLayout.ItemRole.LabelRole, self.lblCustomerNote
        )

        self.txtCustomerNote = QPlainTextEdit(self.grpCustomer)
        self.txtCustomerNote.setObjectName("txtCustomerNote")
        self.txtCustomerNote.setMaximumSize(QSize(16777215, 80))

        self.formLayoutCustomer.setWidget(
            2, QFormLayout.ItemRole.FieldRole, self.txtCustomerNote
        )

        self.verticalLayoutMain.addWidget(self.grpCustomer)

        self.grpOrder = QGroupBox(QuickIssueDialog)
        self.grpOrder.setObjectName("grpOrder")
        self.grpOrder.setMinimumSize(QSize(0, 180))
        self.formLayoutOrder = QFormLayout(self.grpOrder)
        self.formLayoutOrder.setObjectName("formLayoutOrder")
        self.formLayoutOrder.setContentsMargins(-1, 20, -1, -1)
        self.lblEdition = QLabel(self.grpOrder)
        self.lblEdition.setObjectName("lblEdition")

        self.formLayoutOrder.setWidget(
            2, QFormLayout.ItemRole.LabelRole, self.lblEdition
        )

        self.cmbEdition = QComboBox(self.grpOrder)
        self.cmbEdition.addItem("")
        self.cmbEdition.addItem("")
        self.cmbEdition.setObjectName("cmbEdition")

        self.formLayoutOrder.setWidget(
            2, QFormLayout.ItemRole.FieldRole, self.cmbEdition
        )

        self.lblAppVersion = QLabel(self.grpOrder)
        self.lblAppVersion.setObjectName("lblAppVersion")

        self.formLayoutOrder.setWidget(
            3, QFormLayout.ItemRole.LabelRole, self.lblAppVersion
        )

        self.editAppVersion = QLineEdit(self.grpOrder)
        self.editAppVersion.setObjectName("editAppVersion")

        self.formLayoutOrder.setWidget(
            3, QFormLayout.ItemRole.FieldRole, self.editAppVersion
        )

        self.lblFingerprint = QLabel(self.grpOrder)
        self.lblFingerprint.setObjectName("lblFingerprint")

        self.formLayoutOrder.setWidget(
            4, QFormLayout.ItemRole.LabelRole, self.lblFingerprint
        )

        self.txtFingerprint = QPlainTextEdit(self.grpOrder)
        self.txtFingerprint.setObjectName("txtFingerprint")
        self.txtFingerprint.setMaximumSize(QSize(16777215, 80))
        self.txtFingerprint.setLineWidth(0)

        self.formLayoutOrder.setWidget(
            4, QFormLayout.ItemRole.FieldRole, self.txtFingerprint
        )

        self.lblOrderId = QLabel(self.grpOrder)
        self.lblOrderId.setObjectName("lblOrderId")

        self.formLayoutOrder.setWidget(
            1, QFormLayout.ItemRole.LabelRole, self.lblOrderId
        )

        self.editOrderId = QLineEdit(self.grpOrder)
        self.editOrderId.setObjectName("editOrderId")
        self.editOrderId.setReadOnly(False)

        self.formLayoutOrder.setWidget(
            1, QFormLayout.ItemRole.FieldRole, self.editOrderId
        )

        self.verticalLayoutMain.addWidget(self.grpOrder)

        self.grpPayment = QGroupBox(QuickIssueDialog)
        self.grpPayment.setObjectName("grpPayment")
        self.grpPayment.setMinimumSize(QSize(0, 220))
        self.formLayoutPayment = QFormLayout(self.grpPayment)
        self.formLayoutPayment.setObjectName("formLayoutPayment")
        self.formLayoutPayment.setContentsMargins(-1, 20, -1, -1)
        self.lblBank = QLabel(self.grpPayment)
        self.lblBank.setObjectName("lblBank")

        self.formLayoutPayment.setWidget(
            0, QFormLayout.ItemRole.LabelRole, self.lblBank
        )

        self.editBank = QLineEdit(self.grpPayment)
        self.editBank.setObjectName("editBank")

        self.formLayoutPayment.setWidget(
            0, QFormLayout.ItemRole.FieldRole, self.editBank
        )

        self.lblAmount = QLabel(self.grpPayment)
        self.lblAmount.setObjectName("lblAmount")

        self.formLayoutPayment.setWidget(
            2, QFormLayout.ItemRole.LabelRole, self.lblAmount
        )

        self.editAmount = QLineEdit(self.grpPayment)
        self.editAmount.setObjectName("editAmount")

        self.formLayoutPayment.setWidget(
            2, QFormLayout.ItemRole.FieldRole, self.editAmount
        )

        self.lblCurrency = QLabel(self.grpPayment)
        self.lblCurrency.setObjectName("lblCurrency")

        self.formLayoutPayment.setWidget(
            3, QFormLayout.ItemRole.LabelRole, self.lblCurrency
        )

        self.editCurrency = QLineEdit(self.grpPayment)
        self.editCurrency.setObjectName("editCurrency")
        self.editCurrency.setMaxLength(3)

        self.formLayoutPayment.setWidget(
            3, QFormLayout.ItemRole.FieldRole, self.editCurrency
        )

        self.lblPaidUtc = QLabel(self.grpPayment)
        self.lblPaidUtc.setObjectName("lblPaidUtc")

        self.formLayoutPayment.setWidget(
            4, QFormLayout.ItemRole.LabelRole, self.lblPaidUtc
        )

        self.editPaidUtc = QLineEdit(self.grpPayment)
        self.editPaidUtc.setObjectName("editPaidUtc")

        self.formLayoutPayment.setWidget(
            4, QFormLayout.ItemRole.FieldRole, self.editPaidUtc
        )

        self.lblPaymentNote = QLabel(self.grpPayment)
        self.lblPaymentNote.setObjectName("lblPaymentNote")

        self.formLayoutPayment.setWidget(
            6, QFormLayout.ItemRole.LabelRole, self.lblPaymentNote
        )

        self.txtPaymentNote = QPlainTextEdit(self.grpPayment)
        self.txtPaymentNote.setObjectName("txtPaymentNote")
        self.txtPaymentNote.setMaximumSize(QSize(16777215, 80))

        self.formLayoutPayment.setWidget(
            6, QFormLayout.ItemRole.FieldRole, self.txtPaymentNote
        )

        self.lblPaymentRef = QLabel(self.grpPayment)
        self.lblPaymentRef.setObjectName("lblPaymentRef")

        self.formLayoutPayment.setWidget(
            5, QFormLayout.ItemRole.LabelRole, self.lblPaymentRef
        )

        self.editPaymentRef = QLineEdit(self.grpPayment)
        self.editPaymentRef.setObjectName("editPaymentRef")

        self.formLayoutPayment.setWidget(
            5, QFormLayout.ItemRole.FieldRole, self.editPaymentRef
        )

        self.verticalLayoutMain.addWidget(self.grpPayment)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setSpacing(9)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.horizontalLayout.setContentsMargins(9, 9, 9, 9)
        self.lblEmailLanguage = QLabel(QuickIssueDialog)
        self.lblEmailLanguage.setObjectName("lblEmailLanguage")
        self.lblEmailLanguage.setMaximumSize(QSize(99, 16777215))

        self.horizontalLayout.addWidget(self.lblEmailLanguage)

        self.cmbEmailLanguage = QComboBox(QuickIssueDialog)
        self.cmbEmailLanguage.addItem("")
        self.cmbEmailLanguage.addItem("")
        self.cmbEmailLanguage.setObjectName("cmbEmailLanguage")

        self.horizontalLayout.addWidget(self.cmbEmailLanguage)

        self.verticalLayoutMain.addLayout(self.horizontalLayout)

        self.lblCustomerStatus = QLabel(QuickIssueDialog)
        self.lblCustomerStatus.setObjectName("lblCustomerStatus")

        self.verticalLayoutMain.addWidget(self.lblCustomerStatus)

        self.layoutButtons = QHBoxLayout()
        self.layoutButtons.setObjectName("layoutButtons")
        self.layoutButtons.setContentsMargins(9, 9, 9, 9)
        self.horizontalSpacerButtons = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.layoutButtons.addItem(self.horizontalSpacerButtons)

        self.btnPreviewEmail = QPushButton(QuickIssueDialog)
        self.btnPreviewEmail.setObjectName("btnPreviewEmail")
        self.btnPreviewEmail.setAutoDefault(False)

        self.layoutButtons.addWidget(self.btnPreviewEmail)

        self.btnSendEmail = QPushButton(QuickIssueDialog)
        self.btnSendEmail.setObjectName("btnSendEmail")
        self.btnSendEmail.setAutoDefault(False)

        self.layoutButtons.addWidget(self.btnSendEmail)

        self.btnIssue = QPushButton(QuickIssueDialog)
        self.btnIssue.setObjectName("btnIssue")
        self.btnIssue.setCheckable(True)

        self.layoutButtons.addWidget(self.btnIssue)

        self.btnCancel = QPushButton(QuickIssueDialog)
        self.btnCancel.setObjectName("btnCancel")

        self.layoutButtons.addWidget(self.btnCancel)

        self.verticalLayoutMain.addLayout(self.layoutButtons)

        self.verticalLayoutMain.setStretch(0, 1)
        self.verticalLayoutMain.setStretch(1, 1)
        self.verticalLayoutMain.setStretch(2, 4)
        self.verticalLayoutMain.setStretch(3, 6)
        self.verticalLayoutMain.setStretch(4, 10)
        self.verticalLayoutMain.setStretch(6, 1)
        self.verticalLayoutMain.setStretch(7, 3)

        self.retranslateUi(QuickIssueDialog)

        QMetaObject.connectSlotsByName(QuickIssueDialog)

    # setupUi

    def retranslateUi(self, QuickIssueDialog):
        QuickIssueDialog.setWindowTitle(
            QCoreApplication.translate(
                "QuickIssueDialog",
                "LGE Office \u2014 \u0428\u0432\u0438\u0434\u043a\u0430 \u0432\u0438\u0434\u0430\u0447\u0430 \u043b\u0456\u0446\u0435\u043d\u0437\u0456\u0457",
                None,
            )
        )
        self.lblTitle.setText(
            QCoreApplication.translate(
                "QuickIssueDialog",
                "\u0428\u0432\u0438\u0434\u043a\u0430 \u0432\u0438\u0434\u0430\u0447\u0430 \u043b\u0456\u0446\u0435\u043d\u0437\u0456\u0457",
                None,
            )
        )
        self.lblHint.setText(
            QCoreApplication.translate(
                "QuickIssueDialog",
                "\u041e\u0434\u043d\u0430 \u0444\u043e\u0440\u043c\u0430 \u0434\u043b\u044f \u0441\u0442\u0432\u043e\u0440\u0435\u043d\u043d\u044f \u043a\u043b\u0456\u0454\u043d\u0442\u0430, \u0437\u0430\u043c\u043e\u0432\u043b\u0435\u043d\u043d\u044f, \u043e\u043f\u043b\u0430\u0442\u0438, \u043b\u0456\u0446\u0435\u043d\u0437\u0456\u0457 \u0442\u0430 \u043f\u0456\u0434\u0433\u043e\u0442\u043e\u0432\u043a\u0438 \u043b\u0438\u0441\u0442\u0430.",
                None,
            )
        )
        self.grpCustomer.setTitle(
            QCoreApplication.translate(
                "QuickIssueDialog", "\u041a\u043b\u0456\u0454\u043d\u0442", None
            )
        )
        self.lblEmail.setText(
            QCoreApplication.translate("QuickIssueDialog", "Email *", None)
        )
        self.editEmail.setPlaceholderText(
            QCoreApplication.translate("QuickIssueDialog", "client@example.com", None)
        )
        self.lblCustomerName.setText(
            QCoreApplication.translate("QuickIssueDialog", "\u0406\u043c'\u044f", None)
        )
        self.editCustomerName.setPlaceholderText(
            QCoreApplication.translate(
                "QuickIssueDialog",
                "\u0406\u043c'\u044f \u043a\u043b\u0456\u0454\u043d\u0442\u0430",
                None,
            )
        )
        self.lblCustomerNote.setText(
            QCoreApplication.translate(
                "QuickIssueDialog",
                "\u041f\u0440\u0438\u043c\u0456\u0442\u043a\u0430                  ",
                None,
            )
        )
        self.grpOrder.setTitle(
            QCoreApplication.translate(
                "QuickIssueDialog",
                "\u0417\u0430\u043c\u043e\u0432\u043b\u0435\u043d\u043d\u044f",
                None,
            )
        )
        self.lblEdition.setText(
            QCoreApplication.translate(
                "QuickIssueDialog",
                "\u0420\u0435\u0434\u0430\u043a\u0446\u0456\u044f",
                None,
            )
        )
        self.cmbEdition.setItemText(
            0, QCoreApplication.translate("QuickIssueDialog", "PRO", None)
        )
        self.cmbEdition.setItemText(
            1, QCoreApplication.translate("QuickIssueDialog", "PRO+", None)
        )

        self.lblAppVersion.setText(
            QCoreApplication.translate(
                "QuickIssueDialog", "\u0412\u0435\u0440\u0441\u0456\u044f", None
            )
        )
        self.editAppVersion.setPlaceholderText(
            QCoreApplication.translate("QuickIssueDialog", "1.0.0", None)
        )
        self.lblFingerprint.setText(
            QCoreApplication.translate(
                "QuickIssueDialog", "Fingerprint *            ", None
            )
        )
        self.txtFingerprint.setPlaceholderText(
            QCoreApplication.translate("QuickIssueDialog", "SHA256 fingerprint", None)
        )
        self.lblOrderId.setText(
            QCoreApplication.translate("QuickIssueDialog", "ORDER_ID", None)
        )
        self.editOrderId.setPlaceholderText(
            QCoreApplication.translate(
                "QuickIssueDialog", "LGE-20260215-1236-5904", None
            )
        )
        self.grpPayment.setTitle(
            QCoreApplication.translate(
                "QuickIssueDialog", "\u041e\u043f\u043b\u0430\u0442\u0430", None
            )
        )
        self.lblBank.setText(
            QCoreApplication.translate(
                "QuickIssueDialog", "\u0411\u0430\u043d\u043a", None
            )
        )
        self.editBank.setPlaceholderText(
            QCoreApplication.translate(
                "QuickIssueDialog",
                "\u041d\u0430\u0437\u0432\u0430 \u0431\u0430\u043d\u043a\u0443 / \u0441\u0435\u0440\u0432\u0456\u0441\u0443",
                None,
            )
        )
        self.lblAmount.setText(
            QCoreApplication.translate(
                "QuickIssueDialog", "\u0421\u0443\u043c\u0430", None
            )
        )
        self.editAmount.setInputMask("")
        self.editAmount.setPlaceholderText(
            QCoreApplication.translate("QuickIssueDialog", "0.00", None)
        )
        self.lblCurrency.setText(
            QCoreApplication.translate(
                "QuickIssueDialog", "\u0412\u0430\u043b\u044e\u0442\u0430", None
            )
        )
        self.editCurrency.setText(
            QCoreApplication.translate("QuickIssueDialog", "USD", None)
        )
        self.lblPaidUtc.setText(
            QCoreApplication.translate(
                "QuickIssueDialog",
                "\u0414\u0430\u0442\u0430/\u0447\u0430\u0441 \u043f\u043b\u0430\u0442\u0435\u0436\u0443",
                None,
            )
        )
        self.editPaidUtc.setPlaceholderText(
            QCoreApplication.translate("QuickIssueDialog", "YYYY-MM-DD HH:MM", None)
        )
        self.lblPaymentNote.setText(
            QCoreApplication.translate(
                "QuickIssueDialog",
                "\u041f\u0440\u0438\u043c\u0456\u0442\u043a\u0430:",
                None,
            )
        )
        self.lblPaymentRef.setText(
            QCoreApplication.translate("QuickIssueDialog", "Payment reference", None)
        )
        self.editPaymentRef.setPlaceholderText(
            QCoreApplication.translate(
                "QuickIssueDialog",
                "\u0422\u0435\u043a\u0441\u0442 \u043f\u0440\u0438\u0437\u043d\u0430\u0447\u0435\u043d\u043d\u044f / LGE LGE-20260215-1236-5904",
                None,
            )
        )
        self.lblEmailLanguage.setText(
            QCoreApplication.translate(
                "QuickIssueDialog",
                "\u041c\u043e\u0432\u0430 \u043b\u0438\u0441\u0442\u0430",
                None,
            )
        )
        self.cmbEmailLanguage.setItemText(
            0, QCoreApplication.translate("QuickIssueDialog", "UK", None)
        )
        self.cmbEmailLanguage.setItemText(
            1, QCoreApplication.translate("QuickIssueDialog", "EN", None)
        )

        self.lblCustomerStatus.setText(
            QCoreApplication.translate(
                "QuickIssueDialog", "\u0421\u0442\u0430\u0442\u0443\u0441: \u2014", None
            )
        )
        self.btnPreviewEmail.setText(
            QCoreApplication.translate(
                "QuickIssueDialog",
                "\u041f\u0435\u0440\u0435\u0433\u043b\u044f\u0434 \u043b\u0438\u0441\u0442\u0430",
                None,
            )
        )
        self.btnSendEmail.setText(
            QCoreApplication.translate(
                "QuickIssueDialog",
                "\u041d\u0430\u0434\u0456\u0441\u043b\u0430\u0442\u0438 \u043b\u0438\u0441\u0442",
                None,
            )
        )
        self.btnIssue.setText(
            QCoreApplication.translate(
                "QuickIssueDialog",
                "\u0412\u0438\u0434\u0430\u0442\u0438 \u043b\u0456\u0446\u0435\u043d\u0437\u0456\u044e",
                None,
            )
        )
        self.btnCancel.setText(
            QCoreApplication.translate(
                "QuickIssueDialog",
                "\u0421\u043a\u0430\u0441\u0443\u0432\u0430\u0442\u0438",
                None,
            )
        )

    # retranslateUi
