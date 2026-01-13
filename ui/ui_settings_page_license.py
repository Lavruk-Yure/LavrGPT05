# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'settings_page_license.ui'
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
from PySide6.QtWidgets import (QApplication, QFormLayout, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QSizePolicy, QVBoxLayout,
    QWidget)
import resources_rc

class Ui_pageLicense(object):
    def setupUi(self, pageLicense):
        if not pageLicense.objectName():
            pageLicense.setObjectName(u"pageLicense")
        pageLicense.resize(539, 388)
        icon = QIcon()
        icon.addFile(u":/icons/lge_perplexity2_24x24.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        pageLicense.setWindowIcon(icon)
        self.verticalLayout = QVBoxLayout(pageLicense)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.lblHeader = QLabel(pageLicense)
        self.lblHeader.setObjectName(u"lblHeader")

        self.verticalLayout.addWidget(self.lblHeader)

        self.formLayout = QFormLayout()
        self.formLayout.setObjectName(u"formLayout")
        self.lblStatusTitle = QLabel(pageLicense)
        self.lblStatusTitle.setObjectName(u"lblStatusTitle")

        self.formLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblStatusTitle)

        self.lblStatusValue = QLabel(pageLicense)
        self.lblStatusValue.setObjectName(u"lblStatusValue")

        self.formLayout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.lblStatusValue)

        self.lblEditionTitle = QLabel(pageLicense)
        self.lblEditionTitle.setObjectName(u"lblEditionTitle")

        self.formLayout.setWidget(3, QFormLayout.ItemRole.LabelRole, self.lblEditionTitle)

        self.lblEditionValue = QLabel(pageLicense)
        self.lblEditionValue.setObjectName(u"lblEditionValue")

        self.formLayout.setWidget(3, QFormLayout.ItemRole.FieldRole, self.lblEditionValue)

        self.lblDaysTitle = QLabel(pageLicense)
        self.lblDaysTitle.setObjectName(u"lblDaysTitle")

        self.formLayout.setWidget(4, QFormLayout.ItemRole.LabelRole, self.lblDaysTitle)

        self.lblDaysValue = QLabel(pageLicense)
        self.lblDaysValue.setObjectName(u"lblDaysValue")

        self.formLayout.setWidget(4, QFormLayout.ItemRole.FieldRole, self.lblDaysValue)

        self.lblMachineTitle = QLabel(pageLicense)
        self.lblMachineTitle.setObjectName(u"lblMachineTitle")

        self.formLayout.setWidget(5, QFormLayout.ItemRole.LabelRole, self.lblMachineTitle)

        self.lblMachineValue = QLabel(pageLicense)
        self.lblMachineValue.setObjectName(u"lblMachineValue")

        self.formLayout.setWidget(5, QFormLayout.ItemRole.FieldRole, self.lblMachineValue)

        self.lblSourceTitle = QLabel(pageLicense)
        self.lblSourceTitle.setObjectName(u"lblSourceTitle")

        self.formLayout.setWidget(6, QFormLayout.ItemRole.LabelRole, self.lblSourceTitle)

        self.lblSourceValue = QLabel(pageLicense)
        self.lblSourceValue.setObjectName(u"lblSourceValue")

        self.formLayout.setWidget(6, QFormLayout.ItemRole.FieldRole, self.lblSourceValue)

        self.lblActivatedTitle = QLabel(pageLicense)
        self.lblActivatedTitle.setObjectName(u"lblActivatedTitle")

        self.formLayout.setWidget(7, QFormLayout.ItemRole.LabelRole, self.lblActivatedTitle)

        self.lblActivatedValue = QLabel(pageLicense)
        self.lblActivatedValue.setObjectName(u"lblActivatedValue")

        self.formLayout.setWidget(7, QFormLayout.ItemRole.FieldRole, self.lblActivatedValue)

        self.lblKeyTitle = QLabel(pageLicense)
        self.lblKeyTitle.setObjectName(u"lblKeyTitle")

        self.formLayout.setWidget(8, QFormLayout.ItemRole.LabelRole, self.lblKeyTitle)

        self.editLicenseKey = QPlainTextEdit(pageLicense)
        self.editLicenseKey.setObjectName(u"editLicenseKey")
        self.editLicenseKey.setMinimumSize(QSize(70, 90))
        self.editLicenseKey.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.editLicenseKey.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.formLayout.setWidget(10, QFormLayout.ItemRole.SpanningRole, self.editLicenseKey)


        self.verticalLayout.addLayout(self.formLayout)

        self.lblActivationInfo = QLabel(pageLicense)
        self.lblActivationInfo.setObjectName(u"lblActivationInfo")
        self.lblActivationInfo.setStyleSheet(u"color: lightgray;")
        self.lblActivationInfo.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblActivationInfo)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.btnActivate = QPushButton(pageLicense)
        self.btnActivate.setObjectName(u"btnActivate")

        self.horizontalLayout.addWidget(self.btnActivate)

        self.btnCopyDiag = QPushButton(pageLicense)
        self.btnCopyDiag.setObjectName(u"btnCopyDiag")

        self.horizontalLayout.addWidget(self.btnCopyDiag)

        self.btnCancel = QPushButton(pageLicense)
        self.btnCancel.setObjectName(u"btnCancel")

        self.horizontalLayout.addWidget(self.btnCancel)


        self.verticalLayout.addLayout(self.horizontalLayout)


        self.retranslateUi(pageLicense)

        QMetaObject.connectSlotsByName(pageLicense)
    # setupUi

    def retranslateUi(self, pageLicense):
        pageLicense.setWindowTitle(QCoreApplication.translate("pageLicense", u"Form", None))
        self.lblHeader.setText(QCoreApplication.translate("pageLicense", u"[SettingsPageLicense.lblHeader]", None))
        self.lblStatusTitle.setText(QCoreApplication.translate("pageLicense", u"[SettingsPageLicense.lblStatusTitle]", None))
        self.lblStatusValue.setText(QCoreApplication.translate("pageLicense", u"TextLabel", None))
        self.lblEditionTitle.setText(QCoreApplication.translate("pageLicense", u"[SettingsPageLicense.lblEditionTitle]", None))
        self.lblEditionValue.setText(QCoreApplication.translate("pageLicense", u"TextLabel", None))
        self.lblDaysTitle.setText(QCoreApplication.translate("pageLicense", u"[SettingsPageLicense.lblDaysTitle]", None))
        self.lblDaysValue.setText(QCoreApplication.translate("pageLicense", u"TextLabel", None))
        self.lblMachineTitle.setText(QCoreApplication.translate("pageLicense", u"[SettingsPageLicense.lblMachineTitle]", None))
        self.lblMachineValue.setText(QCoreApplication.translate("pageLicense", u"TextLabel", None))
        self.lblSourceTitle.setText(QCoreApplication.translate("pageLicense", u"[SettingsPageLicense.lblSourceTitle]", None))
        self.lblSourceValue.setText(QCoreApplication.translate("pageLicense", u"TextLabel", None))
        self.lblActivatedTitle.setText(QCoreApplication.translate("pageLicense", u"[SettingsPageLicense.lblActivatedTitle]", None))
        self.lblActivatedValue.setText(QCoreApplication.translate("pageLicense", u"TextLabel", None))
        self.lblKeyTitle.setText(QCoreApplication.translate("pageLicense", u"[SettingsPageLicense.lblKeyTitle]", None))
        self.editLicenseKey.setPlaceholderText(QCoreApplication.translate("pageLicense", u"[SettingsPageLicense.editLicenseKey.placeholder]", None))
        self.lblActivationInfo.setText(QCoreApplication.translate("pageLicense", u"[SettingsPageLicense.lblActivationInfo]", None))
        self.btnActivate.setText(QCoreApplication.translate("pageLicense", u"[SettingsPageLicense.btnActivate]", None))
        self.btnCopyDiag.setText(QCoreApplication.translate("pageLicense", u"[SettingsPageLicense.btnCopyDiag]", None))
        self.btnCancel.setText(QCoreApplication.translate("pageLicense", u"[Common.btnCancel]", None))
    # retranslateUi

