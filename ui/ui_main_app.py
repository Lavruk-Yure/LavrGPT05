# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main_app.ui'
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
from PySide6.QtWidgets import (QApplication, QLabel, QMainWindow, QMenuBar,
    QSizePolicy, QStatusBar, QToolBar, QVBoxLayout,
    QWidget)
import resources_rc

class Ui_MainAppWindow(object):
    def setupUi(self, MainAppWindow):
        if not MainAppWindow.objectName():
            MainAppWindow.setObjectName(u"MainAppWindow")
        MainAppWindow.resize(800, 600)
        icon = QIcon()
        icon.addFile(u":/icons/lge_perplexity2_24x24.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        MainAppWindow.setWindowIcon(icon)
        MainAppWindow.setStyleSheet(u"background: qlineargradient(\n"
"    x1:0, y1:0, x2:0, y2:1,\n"
"    stop:0 #1F4F5F, stop:1 #0E2F3A);\n"
"color: #E9F6F7;\n"
"QMainWindow {\n"
"    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,\n"
"                                stop:0 #1F4F5F, stop:1 #0E2F3A);\n"
"    color: #E9F6F7;\n"
"    font: 10pt \"Segoe UI\";\n"
"}\n"
"\n"
"QToolButton {\n"
"    background-color: #2C7A8C;\n"
"    border: none;\n"
"    color: white;\n"
"    padding: 6px;\n"
"    border-radius: 6px;\n"
"}\n"
"\n"
"QToolButton:hover {\n"
"    background-color: #1E5FD0;\n"
"}\n"
"\n"
"")
        self.centralArea = QWidget(MainAppWindow)
        self.centralArea.setObjectName(u"centralArea")
        self.verticalLayout_2 = QVBoxLayout(self.centralArea)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.verticalLayoutCentral = QVBoxLayout()
        self.verticalLayoutCentral.setSpacing(0)
        self.verticalLayoutCentral.setObjectName(u"verticalLayoutCentral")
        self.lblMarketState = QLabel(self.centralArea)
        self.lblMarketState.setObjectName(u"lblMarketState")
        self.lblMarketState.setStyleSheet(u"QLabel {\n"
"    color: #ffffff;\n"
"    background-color: #8b1e1e;\n"
"    border-bottom: 1px solid #d06060;\n"
"    padding: 5px 12px;\n"
"    font-weight: 600;\n"
"}")
        self.lblMarketState.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lblMarketState.setWordWrap(True)

        self.verticalLayoutCentral.addWidget(self.lblMarketState)

        self.contentArea = QWidget(self.centralArea)
        self.contentArea.setObjectName(u"contentArea")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.contentArea.sizePolicy().hasHeightForWidth())
        self.contentArea.setSizePolicy(sizePolicy)

        self.verticalLayoutCentral.addWidget(self.contentArea)


        self.verticalLayout_2.addLayout(self.verticalLayoutCentral)

        MainAppWindow.setCentralWidget(self.centralArea)
        self.menuBarMain = QMenuBar(MainAppWindow)
        self.menuBarMain.setObjectName(u"menuBarMain")
        self.menuBarMain.setGeometry(QRect(0, 0, 800, 29))
        self.menuBarMain.setMaximumSize(QSize(16777215, 29))
        MainAppWindow.setMenuBar(self.menuBarMain)
        self.statusBarMain = QStatusBar(MainAppWindow)
        self.statusBarMain.setObjectName(u"statusBarMain")
        MainAppWindow.setStatusBar(self.statusBarMain)
        self.toolBarMain = QToolBar(MainAppWindow)
        self.toolBarMain.setObjectName(u"toolBarMain")
        MainAppWindow.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolBarMain)

        self.retranslateUi(MainAppWindow)

        QMetaObject.connectSlotsByName(MainAppWindow)
    # setupUi

    def retranslateUi(self, MainAppWindow):
        MainAppWindow.setWindowTitle(QCoreApplication.translate("MainAppWindow", u"[MainAppWindow.windowTitle]", None))
        self.lblMarketState.setText(QCoreApplication.translate("MainAppWindow", u"[MainAppWindow.statusForexMarketClosed]", None))
        self.toolBarMain.setWindowTitle(QCoreApplication.translate("MainAppWindow", u"toolBar", None))
    # retranslateUi

