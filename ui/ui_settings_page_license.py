# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'settings_page_license.ui'
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
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)
import resources_rc


class Ui_pageLicense(object):
    def setupUi(self, pageLicense):
        if not pageLicense.objectName():
            pageLicense.setObjectName("pageLicense")
        pageLicense.resize(654, 466)
        sizePolicy = QSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(pageLicense.sizePolicy().hasHeightForWidth())
        pageLicense.setSizePolicy(sizePolicy)
        icon = QIcon()
        icon.addFile(
            ":/icons/lge_perplexity2_24x24.png",
            QSize(),
            QIcon.Mode.Normal,
            QIcon.State.Off,
        )
        pageLicense.setWindowIcon(icon)
        self.verticalLayout = QVBoxLayout(pageLicense)
        self.verticalLayout.setObjectName("verticalLayout")
        self.lblHeader = QLabel(pageLicense)
        self.lblHeader.setObjectName("lblHeader")

        self.verticalLayout.addWidget(self.lblHeader)

        self.formLayout = QFormLayout()
        self.formLayout.setObjectName("formLayout")
        self.lblStatusTitle = QLabel(pageLicense)
        self.lblStatusTitle.setObjectName("lblStatusTitle")

        self.formLayout.setWidget(
            1, QFormLayout.ItemRole.LabelRole, self.lblStatusTitle
        )

        self.lblStatusValue = QLabel(pageLicense)
        self.lblStatusValue.setObjectName("lblStatusValue")

        self.formLayout.setWidget(
            1, QFormLayout.ItemRole.FieldRole, self.lblStatusValue
        )

        self.lblEditionTitle = QLabel(pageLicense)
        self.lblEditionTitle.setObjectName("lblEditionTitle")

        self.formLayout.setWidget(
            3, QFormLayout.ItemRole.LabelRole, self.lblEditionTitle
        )

        self.lblEditionValue = QLabel(pageLicense)
        self.lblEditionValue.setObjectName("lblEditionValue")

        self.formLayout.setWidget(
            3, QFormLayout.ItemRole.FieldRole, self.lblEditionValue
        )

        self.lblDaysTitle = QLabel(pageLicense)
        self.lblDaysTitle.setObjectName("lblDaysTitle")

        self.formLayout.setWidget(4, QFormLayout.ItemRole.LabelRole, self.lblDaysTitle)

        self.lblDaysValue = QLabel(pageLicense)
        self.lblDaysValue.setObjectName("lblDaysValue")

        self.formLayout.setWidget(4, QFormLayout.ItemRole.FieldRole, self.lblDaysValue)

        self.lblMachineTitle = QLabel(pageLicense)
        self.lblMachineTitle.setObjectName("lblMachineTitle")

        self.formLayout.setWidget(
            5, QFormLayout.ItemRole.LabelRole, self.lblMachineTitle
        )

        self.lblMachineValue = QLabel(pageLicense)
        self.lblMachineValue.setObjectName("lblMachineValue")

        self.formLayout.setWidget(
            5, QFormLayout.ItemRole.FieldRole, self.lblMachineValue
        )

        self.lblSourceTitle = QLabel(pageLicense)
        self.lblSourceTitle.setObjectName("lblSourceTitle")

        self.formLayout.setWidget(
            6, QFormLayout.ItemRole.LabelRole, self.lblSourceTitle
        )

        self.lblSourceValue = QLabel(pageLicense)
        self.lblSourceValue.setObjectName("lblSourceValue")

        self.formLayout.setWidget(
            6, QFormLayout.ItemRole.FieldRole, self.lblSourceValue
        )

        self.lblActivatedTitle = QLabel(pageLicense)
        self.lblActivatedTitle.setObjectName("lblActivatedTitle")

        self.formLayout.setWidget(
            7, QFormLayout.ItemRole.LabelRole, self.lblActivatedTitle
        )

        self.lblActivatedValue = QLabel(pageLicense)
        self.lblActivatedValue.setObjectName("lblActivatedValue")

        self.formLayout.setWidget(
            7, QFormLayout.ItemRole.FieldRole, self.lblActivatedValue
        )

        self.lblKeyTitle = QLabel(pageLicense)
        self.lblKeyTitle.setObjectName("lblKeyTitle")

        self.formLayout.setWidget(8, QFormLayout.ItemRole.LabelRole, self.lblKeyTitle)

        self.editLicenseKey = QPlainTextEdit(pageLicense)
        self.editLicenseKey.setObjectName("editLicenseKey")
        sizePolicy1 = QSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(
            self.editLicenseKey.sizePolicy().hasHeightForWidth()
        )
        self.editLicenseKey.setSizePolicy(sizePolicy1)
        self.editLicenseKey.setMinimumSize(QSize(70, 160))
        self.editLicenseKey.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.editLicenseKey.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.editLicenseKey.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self.formLayout.setWidget(
            10, QFormLayout.ItemRole.SpanningRole, self.editLicenseKey
        )

        self.verticalLayout.addLayout(self.formLayout)

        self.verticalLayout_2 = QVBoxLayout()
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.lblActivationInfo = QLabel(pageLicense)
        self.lblActivationInfo.setObjectName("lblActivationInfo")
        self.lblActivationInfo.setStyleSheet("color: lightgray;")
        self.lblActivationInfo.setWordWrap(True)

        self.verticalLayout_2.addWidget(self.lblActivationInfo)

        self.horizontalLayoutRow1 = QHBoxLayout()
        self.horizontalLayoutRow1.setObjectName("horizontalLayoutRow1")
        self.btnEnableTrial = QPushButton(pageLicense)
        self.btnEnableTrial.setObjectName("btnEnableTrial")

        self.horizontalLayoutRow1.addWidget(self.btnEnableTrial)

        self.btnGetLicense = QPushButton(pageLicense)
        self.btnGetLicense.setObjectName("btnGetLicense")

        self.horizontalLayoutRow1.addWidget(self.btnGetLicense)

        self.btnActivate = QPushButton(pageLicense)
        self.btnActivate.setObjectName("btnActivate")

        self.horizontalLayoutRow1.addWidget(self.btnActivate)

        self.verticalLayout_2.addLayout(self.horizontalLayoutRow1)

        self.horizontalLayoutRow2 = QHBoxLayout()
        self.horizontalLayoutRow2.setObjectName("horizontalLayoutRow2")
        self.horizontalSpacer = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayoutRow2.addItem(self.horizontalSpacer)

        self.btnCopyDiag = QPushButton(pageLicense)
        self.btnCopyDiag.setObjectName("btnCopyDiag")

        self.horizontalLayoutRow2.addWidget(self.btnCopyDiag)

        self.btnCancel = QPushButton(pageLicense)
        self.btnCancel.setObjectName("btnCancel")

        self.horizontalLayoutRow2.addWidget(self.btnCancel)

        self.verticalLayout_2.addLayout(self.horizontalLayoutRow2)

        self.verticalLayout.addLayout(self.verticalLayout_2)

        self.retranslateUi(pageLicense)

        QMetaObject.connectSlotsByName(pageLicense)

    # setupUi

    def retranslateUi(self, pageLicense):
        pageLicense.setWindowTitle(
            QCoreApplication.translate("pageLicense", "Form", None)
        )
        self.lblHeader.setText(
            QCoreApplication.translate(
                "pageLicense", "[SettingsPageLicense.lblHeader]", None
            )
        )
        self.lblStatusTitle.setText(
            QCoreApplication.translate(
                "pageLicense", "[SettingsPageLicense.lblStatusTitle]", None
            )
        )
        self.lblStatusValue.setText(
            QCoreApplication.translate("pageLicense", "TextLabel", None)
        )
        self.lblEditionTitle.setText(
            QCoreApplication.translate(
                "pageLicense", "[SettingsPageLicense.lblEditionTitle]", None
            )
        )
        self.lblEditionValue.setText(
            QCoreApplication.translate("pageLicense", "TextLabel", None)
        )
        self.lblDaysTitle.setText(
            QCoreApplication.translate(
                "pageLicense", "[SettingsPageLicense.lblDaysTitle]", None
            )
        )
        self.lblDaysValue.setText(
            QCoreApplication.translate("pageLicense", "TextLabel", None)
        )
        self.lblMachineTitle.setText(
            QCoreApplication.translate(
                "pageLicense", "[SettingsPageLicense.lblMachineTitle]", None
            )
        )
        self.lblMachineValue.setText(
            QCoreApplication.translate("pageLicense", "TextLabel", None)
        )
        self.lblSourceTitle.setText(
            QCoreApplication.translate(
                "pageLicense", "[SettingsPageLicense.lblSourceTitle]", None
            )
        )
        self.lblSourceValue.setText(
            QCoreApplication.translate("pageLicense", "TextLabel", None)
        )
        self.lblActivatedTitle.setText(
            QCoreApplication.translate(
                "pageLicense", "[SettingsPageLicense.lblActivatedTitle]", None
            )
        )
        self.lblActivatedValue.setText(
            QCoreApplication.translate("pageLicense", "TextLabel", None)
        )
        self.lblKeyTitle.setText(
            QCoreApplication.translate(
                "pageLicense", "[SettingsPageLicense.lblKeyTitle]", None
            )
        )
        self.editLicenseKey.setPlaceholderText(
            QCoreApplication.translate(
                "pageLicense", "[SettingsPageLicense.editLicenseKey.placeholder]", None
            )
        )
        self.lblActivationInfo.setText(
            QCoreApplication.translate(
                "pageLicense", "[SettingsPageLicense.lblActivationInfo]", None
            )
        )
        self.btnEnableTrial.setText(
            QCoreApplication.translate(
                "pageLicense", "[SettingsPageLicense.btnEnableTrial]", None
            )
        )
        self.btnGetLicense.setText(
            QCoreApplication.translate(
                "pageLicense", "[SettingsPageLicense.btnGetLicense]", None
            )
        )
        self.btnActivate.setText(
            QCoreApplication.translate(
                "pageLicense", "[SettingsPageLicense.btnActivate]", None
            )
        )
        self.btnCopyDiag.setText(
            QCoreApplication.translate(
                "pageLicense", "[SettingsPageLicense.btnCopyDiag]", None
            )
        )
        self.btnCancel.setText(
            QCoreApplication.translate("pageLicense", "[Common.btnCancel]", None)
        )

    # retranslateUi
