# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'splash.ui'
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
from PySide6.QtWidgets import (QApplication, QLabel, QMainWindow, QProgressBar,
    QSizePolicy, QSpacerItem, QVBoxLayout, QWidget)
import resources_rc

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(600, 400)
        font = QFont()
        font.setPointSize(9)
        font.setBold(False)
        MainWindow.setFont(font)
        icon = QIcon()
        icon.addFile(u":/icons/lge_perplexity2_24x24.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        MainWindow.setWindowIcon(icon)
        self.SplashScreen = QWidget(MainWindow)
        self.SplashScreen.setObjectName(u"SplashScreen")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.SplashScreen.sizePolicy().hasHeightForWidth())
        self.SplashScreen.setSizePolicy(sizePolicy)
        self.SplashScreen.setMinimumSize(QSize(600, 400))
        self.SplashScreen.setMaximumSize(QSize(600, 400))
        font1 = QFont()
        font1.setPointSize(12)
        font1.setBold(False)
        self.SplashScreen.setFont(font1)
        self.SplashScreen.setStyleSheet(u"QWidget#SplashScreen {\n"
"    background-image: url(:/icons/robot_600x600.png);\n"
"    background-position: center;\n"
"    background-repeat: no-repeat;\n"
"}\n"
"")
        self.verticalLayout = QVBoxLayout(self.SplashScreen)
        self.verticalLayout.setSpacing(10)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(9, -1, -1, 40)
        self.verticalSpacer_2 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout.addItem(self.verticalSpacer_2)

        self.lblTitle = QLabel(self.SplashScreen)
        self.lblTitle.setObjectName(u"lblTitle")
        self.lblTitle.setStyleSheet(u"QLabel#lblTitle {\n"
"    color: #E0E0E0;              /* \u0441\u0432\u0456\u0442\u043b\u043e-\u0441\u0456\u0440\u0438\u0439, \u0447\u0438\u0442\u0430\u0431\u0435\u043b\u044c\u043d\u0438\u0439 \u043d\u0430 \u0442\u0435\u043c\u043d\u043e\u043c\u0443 */\n"
"    font-family: \"Segoe UI\";\n"
"    font-size: 18pt;\n"
"    font-weight: bold;\n"
"    letter-spacing: 1px;\n"
"    background-color: transparent;\n"
"	text-shadow: 1px 1px 2px #000000;\n"
"}\n"
"")

        self.verticalLayout.addWidget(self.lblTitle, 0, Qt.AlignmentFlag.AlignHCenter)

        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout.addItem(self.verticalSpacer)

        self.lblStatus = QLabel(self.SplashScreen)
        self.lblStatus.setObjectName(u"lblStatus")
        font2 = QFont()
        font2.setFamilies([u"Segoe UI"])
        font2.setPointSize(16)
        font2.setBold(True)
        font2.setItalic(False)
        self.lblStatus.setFont(font2)
        self.lblStatus.setStyleSheet(u"QLabel#lblStatus {\n"
"	\n"
"	color: rgb(15, 22, 127);\n"
"  \n"
"	font: 700 16pt \"Segoe UI\";\n"
"    background-color: transparent;\n"
"}\n"
"")

        self.verticalLayout.addWidget(self.lblStatus, 0, Qt.AlignmentFlag.AlignHCenter)

        self.progressBar = QProgressBar(self.SplashScreen)
        self.progressBar.setObjectName(u"progressBar")
        sizePolicy.setHeightForWidth(self.progressBar.sizePolicy().hasHeightForWidth())
        self.progressBar.setSizePolicy(sizePolicy)
        self.progressBar.setMinimumSize(QSize(200, 0))
        self.progressBar.setStyleSheet(u"QProgressBar {\n"
"    border: 1px solid #2E7EF9;\n"
"    border-radius: 5px;\n"
"    background-color: rgba(255, 255, 255, 30);\n"
"    height: 12px;\n"
"}\n"
"\n"
"QProgressBar::chunk {\n"
"    background-color: #2E7EF9;\n"
"    border-radius: 5px;\n"
"}\n"
"")
        self.progressBar.setMaximum(100)
        self.progressBar.setValue(50)

        self.verticalLayout.addWidget(self.progressBar, 0, Qt.AlignmentFlag.AlignHCenter)

        self.verticalLayout.setStretch(0, 3)
        self.verticalLayout.setStretch(3, 1)
        MainWindow.setCentralWidget(self.SplashScreen)

        self.retranslateUi(MainWindow)

        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"[SplashWindow.windowTitle]", None))
        self.lblTitle.setText(QCoreApplication.translate("MainWindow", u"[SplashWindow.lblTitle]", None))
        self.lblStatus.setText(QCoreApplication.translate("MainWindow", u"[SplashWindow.lblStatus]", None))
    # retranslateUi

