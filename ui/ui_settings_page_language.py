# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'settings_page_language.ui'
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
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QHBoxLayout,
    QLabel, QPushButton, QSizePolicy, QSpacerItem,
    QVBoxLayout, QWidget)
import resources_rc

class Ui_pageLanguage(object):
    def setupUi(self, pageLanguage):
        if not pageLanguage.objectName():
            pageLanguage.setObjectName(u"pageLanguage")
        pageLanguage.resize(592, 300)
        icon = QIcon()
        icon.addFile(u":/icons/lge_perplexity2_24x24.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        pageLanguage.setWindowIcon(icon)
        self.verticalLayout = QVBoxLayout(pageLanguage)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.lblHeader = QLabel(pageLanguage)
        self.lblHeader.setObjectName(u"lblHeader")
        self.lblHeader.setMinimumSize(QSize(0, 30))
        self.lblHeader.setMaximumSize(QSize(16777215, 60))
        self.lblHeader.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.verticalLayout.addWidget(self.lblHeader)

        self.comboLanguage = QComboBox(pageLanguage)
        self.comboLanguage.setObjectName(u"comboLanguage")

        self.verticalLayout.addWidget(self.comboLanguage)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.btnOK = QPushButton(pageLanguage)
        self.btnOK.setObjectName(u"btnOK")
        self.btnOK.setCheckable(True)

        self.horizontalLayout.addWidget(self.btnOK)

        self.btnApply = QPushButton(pageLanguage)
        self.btnApply.setObjectName(u"btnApply")

        self.horizontalLayout.addWidget(self.btnApply)

        self.btnCancel = QPushButton(pageLanguage)
        self.btnCancel.setObjectName(u"btnCancel")

        self.horizontalLayout.addWidget(self.btnCancel)


        self.verticalLayout.addLayout(self.horizontalLayout)


        self.retranslateUi(pageLanguage)

        QMetaObject.connectSlotsByName(pageLanguage)
    # setupUi

    def retranslateUi(self, pageLanguage):
        pageLanguage.setWindowTitle(QCoreApplication.translate("pageLanguage", u"[SettingsPageLanguage.windowTitle] ", None))
        self.lblHeader.setText(QCoreApplication.translate("pageLanguage", u"[SettingsPageLanguage.header]", None))
        self.btnOK.setText(QCoreApplication.translate("pageLanguage", u"[SettingsPageLanguage.btnOK]", None))
        self.btnApply.setText(QCoreApplication.translate("pageLanguage", u"[SettingsPageLanguage.btnApply]", None))
        self.btnCancel.setText(QCoreApplication.translate("pageLanguage", u"[SettingsPageLanguage.btnCancel]", None))
    # retranslateUi

