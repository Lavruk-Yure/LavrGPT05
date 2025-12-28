# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'settings_page_language.ui'
##
## Created by: Qt User Interface Compiler version 6.9.3
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
from PySide6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QSpacerItem, QVBoxLayout,
    QWidget)
import resources_rc

class Ui_pageLanguage(object):
    def setupUi(self, pageLanguage):
        if not pageLanguage.objectName():
            pageLanguage.setObjectName(u"pageLanguage")
        pageLanguage.resize(600, 300)
        icon = QIcon()
        icon.addFile(u":/icons/lge_perplexity2_24x24.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        pageLanguage.setWindowIcon(icon)
        self.verticalLayout = QVBoxLayout(pageLanguage)
        self.verticalLayout.setSpacing(10)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.lblHeader = QLabel(pageLanguage)
        self.lblHeader.setObjectName(u"lblHeader")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.lblHeader.sizePolicy().hasHeightForWidth())
        self.lblHeader.setSizePolicy(sizePolicy)

        self.verticalLayout.addWidget(self.lblHeader)

        self.comboLanguage = QComboBox(pageLanguage)
        self.comboLanguage.setObjectName(u"comboLanguage")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.comboLanguage.sizePolicy().hasHeightForWidth())
        self.comboLanguage.setSizePolicy(sizePolicy1)
        self.comboLanguage.setMinimumSize(QSize(320, 30))

        self.verticalLayout.addWidget(self.comboLanguage)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.btnOK = QPushButton(pageLanguage)
        self.btnOK.setObjectName(u"btnOK")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.btnOK.sizePolicy().hasHeightForWidth())
        self.btnOK.setSizePolicy(sizePolicy2)
        self.btnOK.setMinimumSize(QSize(110, 0))

        self.horizontalLayout.addWidget(self.btnOK)

        self.btnApply = QPushButton(pageLanguage)
        self.btnApply.setObjectName(u"btnApply")
        sizePolicy2.setHeightForWidth(self.btnApply.sizePolicy().hasHeightForWidth())
        self.btnApply.setSizePolicy(sizePolicy2)
        self.btnApply.setMinimumSize(QSize(110, 0))

        self.horizontalLayout.addWidget(self.btnApply)

        self.btnCancel = QPushButton(pageLanguage)
        self.btnCancel.setObjectName(u"btnCancel")
        sizePolicy2.setHeightForWidth(self.btnCancel.sizePolicy().hasHeightForWidth())
        self.btnCancel.setSizePolicy(sizePolicy2)
        self.btnCancel.setMinimumSize(QSize(110, 0))

        self.horizontalLayout.addWidget(self.btnCancel)


        self.verticalLayout.addLayout(self.horizontalLayout)

        self.verticalLayout.setStretch(0, 12)
        self.verticalLayout.setStretch(1, 12)
        self.verticalLayout.setStretch(2, 12)

        self.retranslateUi(pageLanguage)

        QMetaObject.connectSlotsByName(pageLanguage)
    # setupUi

    def retranslateUi(self, pageLanguage):
        pageLanguage.setWindowTitle(QCoreApplication.translate("pageLanguage", u"Form", None))
        self.lblHeader.setText(QCoreApplication.translate("pageLanguage", u"[SettingsPageLanguage.header]", None))
        self.btnOK.setText(QCoreApplication.translate("pageLanguage", u"[SettingsPageLanguage.btnOK]", None))
        self.btnApply.setText(QCoreApplication.translate("pageLanguage", u"[SettingsPageLanguage.btnApply]", None))
        self.btnCancel.setText(QCoreApplication.translate("pageLanguage", u"[SettingsPageLanguage.btnCancel]", None))
    # retranslateUi

