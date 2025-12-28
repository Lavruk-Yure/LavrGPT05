# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'settings_center.ui'
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
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QHeaderView,
    QSizePolicy, QStackedWidget, QTreeWidget, QTreeWidgetItem,
    QWidget)
import resources_rc

class Ui_SettingsCenter(object):
    def setupUi(self, SettingsCenter):
        if not SettingsCenter.objectName():
            SettingsCenter.setObjectName(u"SettingsCenter")
        SettingsCenter.resize(600, 400)
        SettingsCenter.setMinimumSize(QSize(600, 400))
        SettingsCenter.setMaximumSize(QSize(600, 400))
        icon = QIcon()
        icon.addFile(u":/icons/lge_perplexity2_24x24.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        SettingsCenter.setWindowIcon(icon)
        SettingsCenter.setSizeGripEnabled(True)
        self.horizontalLayoutWidget = QWidget(SettingsCenter)
        self.horizontalLayoutWidget.setObjectName(u"horizontalLayoutWidget")
        self.horizontalLayoutWidget.setGeometry(QRect(10, 10, 581, 381))
        self.horizontalLayout = QHBoxLayout(self.horizontalLayoutWidget)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)
        self.treeNav = QTreeWidget(self.horizontalLayoutWidget)
        __qtreewidgetitem = QTreeWidgetItem()
        __qtreewidgetitem.setText(0, u"1");
        self.treeNav.setHeaderItem(__qtreewidgetitem)
        self.treeNav.setObjectName(u"treeNav")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.treeNav.sizePolicy().hasHeightForWidth())
        self.treeNav.setSizePolicy(sizePolicy)
        self.treeNav.setMinimumSize(QSize(180, 0))
        self.treeNav.setMaximumSize(QSize(220, 16777215))
        self.treeNav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.treeNav.setRootIsDecorated(False)
        self.treeNav.setHeaderHidden(True)

        self.horizontalLayout.addWidget(self.treeNav)

        self.stackPages = QStackedWidget(self.horizontalLayoutWidget)
        self.stackPages.setObjectName(u"stackPages")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.stackPages.sizePolicy().hasHeightForWidth())
        self.stackPages.setSizePolicy(sizePolicy1)
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

