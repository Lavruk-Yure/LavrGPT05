# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'settings_center.ui'
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
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QHeaderView,
    QSizePolicy, QStackedWidget, QTreeWidget, QTreeWidgetItem,
    QWidget)
import resources_rc

class Ui_SettingsCenter(object):
    def setupUi(self, SettingsCenter):
        if not SettingsCenter.objectName():
            SettingsCenter.setObjectName(u"SettingsCenter")
        SettingsCenter.resize(605, 380)
        icon = QIcon()
        icon.addFile(u":/icons/lge_perplexity2_24x24.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        SettingsCenter.setWindowIcon(icon)
        self.horizontalLayout = QHBoxLayout(SettingsCenter)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.treeNav = QTreeWidget(SettingsCenter)
        __qtreewidgetitem = QTreeWidgetItem()
        __qtreewidgetitem.setText(0, u"1");
        self.treeNav.setHeaderItem(__qtreewidgetitem)
        self.treeNav.setObjectName(u"treeNav")

        self.horizontalLayout.addWidget(self.treeNav)

        self.stackPages = QStackedWidget(SettingsCenter)
        self.stackPages.setObjectName(u"stackPages")
        self.page = QWidget()
        self.page.setObjectName(u"page")
        self.stackPages.addWidget(self.page)
        self.page_2 = QWidget()
        self.page_2.setObjectName(u"page_2")
        self.stackPages.addWidget(self.page_2)

        self.horizontalLayout.addWidget(self.stackPages)


        self.retranslateUi(SettingsCenter)

        QMetaObject.connectSlotsByName(SettingsCenter)
    # setupUi

    def retranslateUi(self, SettingsCenter):
        SettingsCenter.setWindowTitle(QCoreApplication.translate("SettingsCenter", u"[SettingsCenter.windowTitle]", None))
    # retranslateUi

