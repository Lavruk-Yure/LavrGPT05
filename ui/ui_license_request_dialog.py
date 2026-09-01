# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'license_request_dialog.ui'
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
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)
import resources_rc


class Ui_LicenseRequestDialog(object):
    def setupUi(self, LicenseRequestDialog):
        if not LicenseRequestDialog.objectName():
            LicenseRequestDialog.setObjectName("LicenseRequestDialog")
        LicenseRequestDialog.resize(558, 300)
        LicenseRequestDialog.setMinimumSize(QSize(400, 250))
        LicenseRequestDialog.setMaximumSize(QSize(16777215, 16777215))
        icon = QIcon()
        icon.addFile(
            ":/icons/lge_perplexity2_24x24.png",
            QSize(),
            QIcon.Mode.Normal,
            QIcon.State.Off,
        )
        LicenseRequestDialog.setWindowIcon(icon)
        LicenseRequestDialog.setStyleSheet("background-color: #245e6d;")
        self.verticalLayout = QVBoxLayout(LicenseRequestDialog)
        self.verticalLayout.setSpacing(8)
        self.verticalLayout.setObjectName("verticalLayout")
        self.verticalLayout.setContentsMargins(12, 12, 12, 12)
        self.gridLayout = QGridLayout()
        self.gridLayout.setObjectName("gridLayout")
        self.lblEmailTitle = QLabel(LicenseRequestDialog)
        self.lblEmailTitle.setObjectName("lblEmailTitle")

        self.gridLayout.addWidget(self.lblEmailTitle, 9, 0, 1, 1)

        self.lblPriceValue = QLabel(LicenseRequestDialog)
        self.lblPriceValue.setObjectName("lblPriceValue")

        self.gridLayout.addWidget(self.lblPriceValue, 6, 1, 1, 1)

        self.lblEditionTitle = QLabel(LicenseRequestDialog)
        self.lblEditionTitle.setObjectName("lblEditionTitle")
        sizePolicy = QSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(
            self.lblEditionTitle.sizePolicy().hasHeightForWidth()
        )
        self.lblEditionTitle.setSizePolicy(sizePolicy)
        self.lblEditionTitle.setMaximumSize(QSize(16777215, 16777215))

        self.gridLayout.addWidget(self.lblEditionTitle, 3, 0, 1, 1)

        self.comboEdition = QComboBox(LicenseRequestDialog)
        self.comboEdition.setObjectName("comboEdition")
        sizePolicy.setHeightForWidth(self.comboEdition.sizePolicy().hasHeightForWidth())
        self.comboEdition.setSizePolicy(sizePolicy)
        self.comboEdition.setMaximumSize(QSize(16777215, 16777215))

        self.gridLayout.addWidget(self.comboEdition, 3, 1, 1, 1)

        self.lblPriceTitle = QLabel(LicenseRequestDialog)
        self.lblPriceTitle.setObjectName("lblPriceTitle")

        self.gridLayout.addWidget(self.lblPriceTitle, 6, 0, 1, 1)

        self.editEmail = QLineEdit(LicenseRequestDialog)
        self.editEmail.setObjectName("editEmail")
        sizePolicy1 = QSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.editEmail.sizePolicy().hasHeightForWidth())
        self.editEmail.setSizePolicy(sizePolicy1)

        self.gridLayout.addWidget(self.editEmail, 9, 1, 1, 1)

        self.lblHeader = QLabel(LicenseRequestDialog)
        self.lblHeader.setObjectName("lblHeader")
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        self.lblHeader.setFont(font)
        self.lblHeader.setStyleSheet("color: rgb(208, 230, 235);")
        self.lblHeader.setWordWrap(True)

        self.gridLayout.addWidget(self.lblHeader, 0, 0, 1, 2)

        self.chkConsent = QCheckBox(LicenseRequestDialog)
        self.chkConsent.setObjectName("chkConsent")
        self.chkConsent.setChecked(True)

        self.gridLayout.addWidget(self.chkConsent, 13, 0, 1, 2)

        self.lblStatus = QLabel(LicenseRequestDialog)
        self.lblStatus.setObjectName("lblStatus")
        self.lblStatus.setMinimumSize(QSize(0, 0))
        self.lblStatus.setWordWrap(True)

        self.gridLayout.addWidget(self.lblStatus, 14, 0, 1, 2)

        self.verticalLayout.addLayout(self.gridLayout)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.btnGenerate = QPushButton(LicenseRequestDialog)
        self.btnGenerate.setObjectName("btnGenerate")

        self.horizontalLayout.addWidget(self.btnGenerate)

        self.btnCopyEmail = QPushButton(LicenseRequestDialog)
        self.btnCopyEmail.setObjectName("btnCopyEmail")

        self.horizontalLayout.addWidget(self.btnCopyEmail)

        self.btnSendEmail = QPushButton(LicenseRequestDialog)
        self.btnSendEmail.setObjectName("btnSendEmail")

        self.horizontalLayout.addWidget(self.btnSendEmail)

        self.horizontalSpacer = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.verticalLayout.addLayout(self.horizontalLayout)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.horizontalSpacer_2 = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayout_2.addItem(self.horizontalSpacer_2)

        self.btnClose = QPushButton(LicenseRequestDialog)
        self.btnClose.setObjectName("btnClose")

        self.horizontalLayout_2.addWidget(self.btnClose)

        self.verticalLayout.addLayout(self.horizontalLayout_2)

        self.verticalLayout.setStretch(0, 4)
        self.verticalLayout.setStretch(1, 1)

        self.retranslateUi(LicenseRequestDialog)

        QMetaObject.connectSlotsByName(LicenseRequestDialog)

    # setupUi

    def retranslateUi(self, LicenseRequestDialog):
        LicenseRequestDialog.setWindowTitle(
            QCoreApplication.translate(
                "LicenseRequestDialog", "[LicenseRequestDialog.windowTitle]", None
            )
        )
        self.lblEmailTitle.setText(
            QCoreApplication.translate(
                "LicenseRequestDialog", "[LicenseRequestDialog.lblEmailTitle]", None
            )
        )
        self.lblPriceValue.setText(
            QCoreApplication.translate("LicenseRequestDialog", "-", None)
        )
        self.lblEditionTitle.setText(
            QCoreApplication.translate(
                "LicenseRequestDialog", "[LicenseRequestDialog.lblEditionTitle]", None
            )
        )
        self.lblPriceTitle.setText(
            QCoreApplication.translate(
                "LicenseRequestDialog", "[LicenseRequestDialog.lblPriceTitle]", None
            )
        )
        self.lblHeader.setText(
            QCoreApplication.translate(
                "LicenseRequestDialog", "[LicenseRequestDialog.lblHeader]", None
            )
        )
        self.chkConsent.setText(
            QCoreApplication.translate(
                "LicenseRequestDialog", "[LicenseRequestDialog.chkConsent]", None
            )
        )
        self.lblStatus.setText(
            QCoreApplication.translate("LicenseRequestDialog", "-", None)
        )
        self.btnGenerate.setText(
            QCoreApplication.translate(
                "LicenseRequestDialog", "[LicenseRequestDialog.btnGenerate]", None
            )
        )
        self.btnCopyEmail.setText(
            QCoreApplication.translate(
                "LicenseRequestDialog", "[LicenseRequestDialog.btnCopyEmail]", None
            )
        )
        self.btnSendEmail.setText(
            QCoreApplication.translate(
                "LicenseRequestDialog", "[LicenseRequestDialog.btnSendEmail]", None
            )
        )
        self.btnClose.setText(
            QCoreApplication.translate(
                "LicenseRequestDialog", "[LicenseRequestDialog.btnClose]", None
            )
        )

    # retranslateUi
