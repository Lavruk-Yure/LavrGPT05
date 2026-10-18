# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'license_payment_preview_dialog.ui'
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
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QSizePolicy, QSpacerItem,
    QVBoxLayout, QWidget)

class Ui_LicensePaymentPreviewDialog(object):
    def setupUi(self, LicensePaymentPreviewDialog):
        if not LicensePaymentPreviewDialog.objectName():
            LicensePaymentPreviewDialog.setObjectName(u"LicensePaymentPreviewDialog")
        LicensePaymentPreviewDialog.resize(690, 520)
        LicensePaymentPreviewDialog.setMinimumSize(QSize(500, 340))
        LicensePaymentPreviewDialog.setStyleSheet(u"background-color: #245e6d;")
        self.verticalLayout = QVBoxLayout(LicensePaymentPreviewDialog)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.lblTestWarning = QLabel(LicensePaymentPreviewDialog)
        self.lblTestWarning.setObjectName(u"lblTestWarning")
        self.lblTestWarning.setStyleSheet(u"color: #ffe5a5; font-weight: bold;")
        self.lblTestWarning.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblTestWarning)

        self.txtPayment = QPlainTextEdit(LicensePaymentPreviewDialog)
        self.txtPayment.setObjectName(u"txtPayment")
        self.txtPayment.setStyleSheet(u"background-color: #f7f9fb; color: #17323b;")
        self.txtPayment.setReadOnly(True)

        self.verticalLayout.addWidget(self.txtPayment)

        self.lblStatus = QLabel(LicensePaymentPreviewDialog)
        self.lblStatus.setObjectName(u"lblStatus")

        self.verticalLayout.addWidget(self.lblStatus)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.btnCopy = QPushButton(LicensePaymentPreviewDialog)
        self.btnCopy.setObjectName(u"btnCopy")

        self.horizontalLayout.addWidget(self.btnCopy)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.btnClose = QPushButton(LicensePaymentPreviewDialog)
        self.btnClose.setObjectName(u"btnClose")

        self.horizontalLayout.addWidget(self.btnClose)


        self.verticalLayout.addLayout(self.horizontalLayout)


        self.retranslateUi(LicensePaymentPreviewDialog)

        QMetaObject.connectSlotsByName(LicensePaymentPreviewDialog)
    # setupUi

    def retranslateUi(self, LicensePaymentPreviewDialog):
        LicensePaymentPreviewDialog.setWindowTitle(QCoreApplication.translate("LicensePaymentPreviewDialog", u"[LicensePaymentPreviewDialog.windowTitle]", None))
        self.lblTestWarning.setText(QCoreApplication.translate("LicensePaymentPreviewDialog", u"[LicensePaymentPreviewDialog.lblTestWarning]", None))
        self.lblStatus.setText("")
        self.btnCopy.setText(QCoreApplication.translate("LicensePaymentPreviewDialog", u"[LicensePaymentPreviewDialog.btnCopy]", None))
        self.btnClose.setText(QCoreApplication.translate("LicensePaymentPreviewDialog", u"[LicensePaymentPreviewDialog.btnClose]", None))
    # retranslateUi

