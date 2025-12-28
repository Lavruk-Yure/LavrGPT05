# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main_app.ui'
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
from PySide6.QtWidgets import (QApplication, QMainWindow, QMenuBar, QSizePolicy,
    QStatusBar, QWidget)
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
        MainAppWindow.setCentralWidget(self.centralArea)
        self.toolBarMain = QMenuBar(MainAppWindow)
        self.toolBarMain.setObjectName(u"toolBarMain")
        self.toolBarMain.setGeometry(QRect(0, 0, 800, 33))
        MainAppWindow.setMenuBar(self.toolBarMain)
        self.statusBarMain = QStatusBar(MainAppWindow)
        self.statusBarMain.setObjectName(u"statusBarMain")
        MainAppWindow.setStatusBar(self.statusBarMain)

        self.retranslateUi(MainAppWindow)

        QMetaObject.connectSlotsByName(MainAppWindow)
    # setupUi

    def retranslateUi(self, MainAppWindow):
        MainAppWindow.setWindowTitle(QCoreApplication.translate("MainAppWindow", u"[MainAppWindow.windowTitle]", None))
    # retranslateUi

