# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'license_request_overwrite_dialog.ui'
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
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
import resources_rc


class Ui_LicenseOverwriteDialog(object):
    def setupUi(self, LicenseOverwriteDialog):
        if not LicenseOverwriteDialog.objectName():
            LicenseOverwriteDialog.setObjectName("LicenseOverwriteDialog")
        LicenseOverwriteDialog.resize(435, 186)
        LicenseOverwriteDialog.setMinimumSize(QSize(200, 0))
        LicenseOverwriteDialog.setMaximumSize(QSize(435, 16777215))
        icon = QIcon()
        icon.addFile(
            ":/icons/lge_perplexity2_24x24.png",
            QSize(),
            QIcon.Mode.Normal,
            QIcon.State.Off,
        )
        LicenseOverwriteDialog.setWindowIcon(icon)
        LicenseOverwriteDialog.setStyleSheet("background-color: rgb(36, 94, 109);")
        self.verticalLayout = QVBoxLayout(LicenseOverwriteDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.lblHeader = QLabel(LicenseOverwriteDialog)
        self.lblHeader.setObjectName("lblHeader")
        self.lblHeader.setStyleSheet("color: rgb(208, 230, 235);")

        self.verticalLayout.addWidget(self.lblHeader)

        self.lblDetails = QLabel(LicenseOverwriteDialog)
        self.lblDetails.setObjectName("lblDetails")
        self.lblDetails.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblDetails)

        self.chkAlsoDeletePayment = QCheckBox(LicenseOverwriteDialog)
        self.chkAlsoDeletePayment.setObjectName("chkAlsoDeletePayment")
        self.chkAlsoDeletePayment.setChecked(True)

        self.verticalLayout.addWidget(self.chkAlsoDeletePayment)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.btnOverwrite = QPushButton(LicenseOverwriteDialog)
        self.btnOverwrite.setObjectName("btnOverwrite")
        self.btnOverwrite.setCheckable(True)
        self.btnOverwrite.setChecked(True)

        self.horizontalLayout.addWidget(self.btnOverwrite)

        self.btnCancel = QPushButton(LicenseOverwriteDialog)
        self.btnCancel.setObjectName("btnCancel")

        self.horizontalLayout.addWidget(self.btnCancel)

        self.verticalLayout.addLayout(self.horizontalLayout)

        self.retranslateUi(LicenseOverwriteDialog)

        QMetaObject.connectSlotsByName(LicenseOverwriteDialog)

    # setupUi

    def retranslateUi(self, LicenseOverwriteDialog):
        LicenseOverwriteDialog.setWindowTitle(
            QCoreApplication.translate(
                "LicenseOverwriteDialog", "[LicenseOverwriteDialog.windowTitle]", None
            )
        )
        self.lblHeader.setText(
            QCoreApplication.translate(
                "LicenseOverwriteDialog", "[LicenseOverwriteDialog.lblHeader]", None
            )
        )
        self.lblDetails.setText(
            QCoreApplication.translate(
                "LicenseOverwriteDialog", "[LicenseOverwriteDialog.lblDetails]", None
            )
        )
        self.chkAlsoDeletePayment.setText(
            QCoreApplication.translate(
                "LicenseOverwriteDialog",
                "[LicenseOverwriteDialog.chkAlsoDeletePayment]",
                None,
            )
        )
        self.btnOverwrite.setText(
            QCoreApplication.translate(
                "LicenseOverwriteDialog", "[LicenseOverwriteDialog.btnOverwrite]", None
            )
        )
        self.btnCancel.setText(
            QCoreApplication.translate(
                "LicenseOverwriteDialog", "[LicenseOverwriteDialog.btnCancel]", None
            )
        )

    # retranslateUi
