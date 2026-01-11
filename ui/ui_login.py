# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'login.ui'
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
    QLineEdit, QMainWindow, QPushButton, QSizePolicy,
    QSpacerItem, QVBoxLayout, QWidget)
import resources_rc
import resources_rc
import resources_rc

class Ui_LoginWindow(object):
    def setupUi(self, LoginWindow):
        if not LoginWindow.objectName():
            LoginWindow.setObjectName(u"LoginWindow")
        LoginWindow.resize(800, 450)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(LoginWindow.sizePolicy().hasHeightForWidth())
        LoginWindow.setSizePolicy(sizePolicy)
        LoginWindow.setMinimumSize(QSize(800, 450))
        LoginWindow.setMaximumSize(QSize(800, 450))
        icon = QIcon()
        icon.addFile(u":/icons/lge_perplexity2_24x24.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        LoginWindow.setWindowIcon(icon)
        LoginWindow.setStyleSheet(u"/* --- \u0417\u0430\u0433\u0430\u043b\u044c\u043d\u0438\u0439 \u0444\u043e\u043d --- */\n"
"QMainWindow {\n"
"    background-color:#ddeaff;\n"
"}\n"
"\n"
"/* --- \u041b\u0456\u0432\u0430 \u043f\u0430\u043d\u0435\u043b\u044c \u0456\u0437 \u043b\u043e\u0433\u043e\u0442\u0438\u043f\u043e\u043c --- */\n"
"QWidget#leftPanel {\n"
"    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,\n"
"        stop:0 #1A2A3A, stop:1 #101820);\n"
"}\n"
"\n"
"/* --- \u041d\u0430\u043f\u0438\u0441 \u043f\u0456\u0434 \u043b\u043e\u0433\u043e\u0442\u0438\u043f\u043e\u043c --- */\n"
"QLabel#lblTitle {\n"
"    color: #CCCCCC;\n"
"    font-size: 12pt;\n"
"    font-weight: bold;\n"
"}\n"
"\n"
"/* --- \u0417\u0430\u0433\u043e\u043b\u043e\u0432\u043e\u043a \u0440\u0435\u0454\u0441\u0442\u0440\u0430\u0446\u0456\u0457 --- */\n"
"QLabel#lblHeader {\n"
"    color: #333333;\n"
"    font-size: 14pt;\n"
"    font-weight: bold;\n"
"}\n"
"\n"
"/* --- \u041f\u043e\u043b\u044f \u0432\u0432\u0435\u0434\u0435\u043d\u043d\u044f --- */\n"
"QLineEdi"
                        "t {\n"
"    border: 1px solid #AAAAAA;\n"
"    border-radius: 4px;\n"
"    padding: 4px;\n"
"    font-size: 10pt;\n"
"}\n"
"\n"
"/* --- \u041a\u043d\u043e\u043f\u043a\u0438 --- */\n"
"QPushButton {\n"
"    border-radius: 6px;\n"
"    height: 30px;\n"
"}\n"
"\n"
"/* --- \u041a\u043d\u043e\u043f\u043a\u0430 \u0417\u0430\u0440\u0435\u0454\u0441\u0442\u0440\u0443\u0432\u0430\u0442\u0438\u0441\u044f --- */\n"
"QPushButton#btnLogin {\n"
"    background-color: #2E7EF9;\n"
"    color: white;\n"
"}\n"
"QPushButton#btnLogin:hover {\n"
"    background-color: #1E5FD0;\n"
"}\n"
"\n"
"/* --- \u041a\u043d\u043e\u043f\u043a\u0430 \u0412\u0438\u0445\u0456\u0434 --- */\n"
"QPushButton#btnExit {\n"
"    background-color: #E0E0E0;\n"
"    color: #000000;\n"
"}\n"
"\n"
"/* --- \u0422\u0435\u043a\u0441\u0442 \u043f\u043e\u043c\u0438\u043b\u043e\u043a --- */\n"
"QLabel#lblError {\n"
"    color: red;\n"
"    font-size: 9pt;\n"
"    font-style: italic;\n"
"}\n"
"")
        self.centralwidget = QWidget(LoginWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        sizePolicy.setHeightForWidth(self.centralwidget.sizePolicy().hasHeightForWidth())
        self.centralwidget.setSizePolicy(sizePolicy)
        self.centralwidget.setMinimumSize(QSize(800, 450))
        self.centralwidget.setMaximumSize(QSize(800, 450))
        self.horizontalLayout_2 = QHBoxLayout(self.centralwidget)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.leftPanel = QWidget(self.centralwidget)
        self.leftPanel.setObjectName(u"leftPanel")
        sizePolicy.setHeightForWidth(self.leftPanel.sizePolicy().hasHeightForWidth())
        self.leftPanel.setSizePolicy(sizePolicy)
        self.leftPanel.setMinimumSize(QSize(330, 430))
        self.leftPanel.setMaximumSize(QSize(800, 500))
        self.leftPanel.setBaseSize(QSize(300, 400))
        self.leftPanel.setStyleSheet(u"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2C7A8C, stop:1 #195D6F);")
        self.verticalLayout_3 = QVBoxLayout(self.leftPanel)
        self.verticalLayout_3.setSpacing(0)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.verticalLayout_3.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout = QVBoxLayout()
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.lblLogo = QLabel(self.leftPanel)
        self.lblLogo.setObjectName(u"lblLogo")
        sizePolicy.setHeightForWidth(self.lblLogo.sizePolicy().hasHeightForWidth())
        self.lblLogo.setSizePolicy(sizePolicy)
        self.lblLogo.setMinimumSize(QSize(150, 200))
        self.lblLogo.setMaximumSize(QSize(330, 400))
        self.lblLogo.setBaseSize(QSize(300, 400))
        self.lblLogo.setPixmap(QPixmap(u":/icons/robot_600x600.png"))
        self.lblLogo.setScaledContents(True)
        self.lblLogo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.verticalLayout.addWidget(self.lblLogo)

        self.lblTitle = QLabel(self.leftPanel)
        self.lblTitle.setObjectName(u"lblTitle")
        sizePolicy.setHeightForWidth(self.lblTitle.sizePolicy().hasHeightForWidth())
        self.lblTitle.setSizePolicy(sizePolicy)
        self.lblTitle.setMinimumSize(QSize(0, 40))
        font = QFont()
        font.setFamilies([u"Segoe UI"])
        font.setPointSize(12)
        font.setBold(False)
        font.setItalic(False)
        self.lblTitle.setFont(font)
        self.lblTitle.setStyleSheet(u"font: 12pt \"Segoe UI\";")

        self.verticalLayout.addWidget(self.lblTitle)

        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout.addItem(self.verticalSpacer)


        self.verticalLayout_3.addLayout(self.verticalLayout)


        self.horizontalLayout_2.addWidget(self.leftPanel)

        self.rightPanel = QWidget(self.centralwidget)
        self.rightPanel.setObjectName(u"rightPanel")
        self.rightPanel.setStyleSheet(u"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2C7A8C, stop:1 #195D6F);")
        self.verticalLayout_4 = QVBoxLayout(self.rightPanel)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.verticalLayout_4.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_2 = QVBoxLayout()
        self.verticalLayout_2.setSpacing(4)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.verticalLayout_2.setContentsMargins(0, 6, -1, 6)
        self.lblHeader = QLabel(self.rightPanel)
        self.lblHeader.setObjectName(u"lblHeader")
        sizePolicy.setHeightForWidth(self.lblHeader.sizePolicy().hasHeightForWidth())
        self.lblHeader.setSizePolicy(sizePolicy)
        self.lblHeader.setMaximumSize(QSize(600, 30))
        self.lblHeader.setStyleSheet(u"font: 700 14pt \"Segoe UI\";")
        self.lblHeader.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.verticalLayout_2.addWidget(self.lblHeader)

        self.formLayout = QFormLayout()
        self.formLayout.setObjectName(u"formLayout")
        self.formLayout.setHorizontalSpacing(20)
        self.formLayout.setVerticalSpacing(60)
        self.formLayout.setContentsMargins(20, 130, 6, 130)
        self.lineEdit = QLineEdit(self.rightPanel)
        self.lineEdit.setObjectName(u"lineEdit")
        sizePolicy.setHeightForWidth(self.lineEdit.sizePolicy().hasHeightForWidth())
        self.lineEdit.setSizePolicy(sizePolicy)
        self.lineEdit.setMinimumSize(QSize(260, 0))
        self.lineEdit.setMaximumSize(QSize(360, 16777215))
        self.lineEdit.setEchoMode(QLineEdit.EchoMode.Password)
        self.lineEdit.setClearButtonEnabled(True)

        self.formLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lineEdit)

        self.lblPassword = QLabel(self.rightPanel)
        self.lblPassword.setObjectName(u"lblPassword")
        sizePolicy.setHeightForWidth(self.lblPassword.sizePolicy().hasHeightForWidth())
        self.lblPassword.setSizePolicy(sizePolicy)
        self.lblPassword.setMaximumSize(QSize(16777215, 28))
        font1 = QFont()
        font1.setPointSize(10)
        self.lblPassword.setFont(font1)
        self.lblPassword.setScaledContents(False)

        self.formLayout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.lblPassword)


        self.verticalLayout_2.addLayout(self.formLayout)

        self.lblError = QLabel(self.rightPanel)
        self.lblError.setObjectName(u"lblError")
        sizePolicy.setHeightForWidth(self.lblError.sizePolicy().hasHeightForWidth())
        self.lblError.setSizePolicy(sizePolicy)
        self.lblError.setMaximumSize(QSize(600, 20))
        font2 = QFont()
        font2.setFamilies([u"Segoe UI"])
        font2.setPointSize(10)
        font2.setBold(False)
        font2.setItalic(False)
        self.lblError.setFont(font2)
        self.lblError.setStyleSheet(u"font: 10pt \"Segoe UI\";")

        self.verticalLayout_2.addWidget(self.lblError)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.btnLogin = QPushButton(self.rightPanel)
        self.btnLogin.setObjectName(u"btnLogin")

        self.horizontalLayout.addWidget(self.btnLogin, 0, Qt.AlignmentFlag.AlignHCenter)

        self.btnExit = QPushButton(self.rightPanel)
        self.btnExit.setObjectName(u"btnExit")

        self.horizontalLayout.addWidget(self.btnExit, 0, Qt.AlignmentFlag.AlignHCenter)


        self.verticalLayout_2.addLayout(self.horizontalLayout)

        self.verticalLayout_2.setStretch(0, 1)
        self.verticalLayout_2.setStretch(2, 1)
        self.verticalLayout_2.setStretch(3, 1)

        self.verticalLayout_4.addLayout(self.verticalLayout_2)


        self.horizontalLayout_2.addWidget(self.rightPanel)

        self.horizontalLayout_2.setStretch(0, 3)
        self.horizontalLayout_2.setStretch(1, 4)
        LoginWindow.setCentralWidget(self.centralwidget)

        self.retranslateUi(LoginWindow)

        QMetaObject.connectSlotsByName(LoginWindow)
    # setupUi

    def retranslateUi(self, LoginWindow):
        LoginWindow.setWindowTitle(QCoreApplication.translate("LoginWindow", u"[LoginWindow.windowTitle]", None))
        self.lblLogo.setText("")
        self.lblTitle.setText(QCoreApplication.translate("LoginWindow", u"[LoginWindow.lblTitle]", None))
        self.lblHeader.setText(QCoreApplication.translate("LoginWindow", u"[LoginWindow.lblHeader]", None))
        self.lineEdit.setPlaceholderText(QCoreApplication.translate("LoginWindow", u"[LoginWindow.lineEdit]", None))
        self.lblPassword.setText(QCoreApplication.translate("LoginWindow", u"[LoginWindow.lblPassword]", None))
        self.lblError.setText("")
        self.btnLogin.setText(QCoreApplication.translate("LoginWindow", u"[LoginWindow.btnLogin]", None))
        self.btnExit.setText(QCoreApplication.translate("LoginWindow", u"[LoginWindow.btnExit]", None))
    # retranslateUi

