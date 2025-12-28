# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'register.ui'
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
from PySide6.QtWidgets import (QApplication, QComboBox, QFormLayout, QHBoxLayout,
    QLabel, QLayout, QLineEdit, QMainWindow,
    QPushButton, QSizePolicy, QSpacerItem, QVBoxLayout,
    QWidget)
import resources_rc

class Ui_RegistrationWindow(object):
    def setupUi(self, RegistrationWindow):
        if not RegistrationWindow.objectName():
            RegistrationWindow.setObjectName(u"RegistrationWindow")
        RegistrationWindow.resize(800, 450)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(RegistrationWindow.sizePolicy().hasHeightForWidth())
        RegistrationWindow.setSizePolicy(sizePolicy)
        RegistrationWindow.setMinimumSize(QSize(800, 450))
        RegistrationWindow.setMaximumSize(QSize(800, 450))
        icon = QIcon()
        icon.addFile(u":/icons/lge_perplexity2_24x24.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        RegistrationWindow.setWindowIcon(icon)
        RegistrationWindow.setStyleSheet(u"/* --- \u0417\u0430\u0433\u0430\u043b\u044c\u043d\u0438\u0439 \u0444\u043e\u043d --- */\n"
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
"QPushButton#btnRegister {\n"
"    background-color: #2E7EF9;\n"
"    color: white;\n"
"}\n"
"QPushButton#btnRegister:hover {\n"
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
        self.centralwidget = QWidget(RegistrationWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        sizePolicy.setHeightForWidth(self.centralwidget.sizePolicy().hasHeightForWidth())
        self.centralwidget.setSizePolicy(sizePolicy)
        self.centralwidget.setMinimumSize(QSize(800, 450))
        self.centralwidget.setMaximumSize(QSize(800, 450))
        self.horizontalLayout = QHBoxLayout(self.centralwidget)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.leftPanel = QWidget(self.centralwidget)
        self.leftPanel.setObjectName(u"leftPanel")
        sizePolicy.setHeightForWidth(self.leftPanel.sizePolicy().hasHeightForWidth())
        self.leftPanel.setSizePolicy(sizePolicy)
        self.leftPanel.setMinimumSize(QSize(330, 430))
        self.leftPanel.setMaximumSize(QSize(800, 500))
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

        self.verticalLayout.addWidget(self.lblLogo, 0, Qt.AlignmentFlag.AlignVCenter)

        self.lblTitle = QLabel(self.leftPanel)
        self.lblTitle.setObjectName(u"lblTitle")
        sizePolicy.setHeightForWidth(self.lblTitle.sizePolicy().hasHeightForWidth())
        self.lblTitle.setSizePolicy(sizePolicy)
        self.lblTitle.setMinimumSize(QSize(0, 40))
        self.lblTitle.setStyleSheet(u"font: 12pt \"Segoe UI\";")

        self.verticalLayout.addWidget(self.lblTitle)

        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout.addItem(self.verticalSpacer)


        self.verticalLayout_3.addLayout(self.verticalLayout)


        self.horizontalLayout.addWidget(self.leftPanel, 0, Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignVCenter)

        self.rightPanel = QWidget(self.centralwidget)
        self.rightPanel.setObjectName(u"rightPanel")
        self.rightPanel.setStyleSheet(u"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2C7A8C, stop:1 #195D6F);")
        self.verticalLayout_4 = QVBoxLayout(self.rightPanel)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.verticalLayout_2 = QVBoxLayout()
        self.verticalLayout_2.setSpacing(4)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.verticalLayout_2.setContentsMargins(-1, 6, -1, 6)
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
        self.formLayout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.formLayout.setHorizontalSpacing(20)
        self.formLayout.setVerticalSpacing(40)
        self.formLayout.setContentsMargins(20, 30, 6, 0)
        self.comboLanguage = QComboBox(self.rightPanel)
        icon1 = QIcon()
        icon1.addFile(u":/icons/flags/ua_24.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.comboLanguage.addItem(icon1, "")
        icon2 = QIcon()
        icon2.addFile(u":/icons/flags/gb_24.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.comboLanguage.addItem(icon2, "")
        icon3 = QIcon()
        icon3.addFile(u":/icons/flags/de_24.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.comboLanguage.addItem(icon3, "")
        self.comboLanguage.setObjectName(u"comboLanguage")
        self.comboLanguage.setMinimumSize(QSize(0, 29))
        font = QFont()
        font.setPointSize(10)
        self.comboLanguage.setFont(font)
        self.comboLanguage.setEditable(False)
        self.comboLanguage.setMinimumContentsLength(6)

        self.formLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.comboLanguage)

        self.lblLanguage = QLabel(self.rightPanel)
        self.lblLanguage.setObjectName(u"lblLanguage")
        sizePolicy.setHeightForWidth(self.lblLanguage.sizePolicy().hasHeightForWidth())
        self.lblLanguage.setSizePolicy(sizePolicy)
        self.lblLanguage.setMaximumSize(QSize(16777215, 28))
        self.lblLanguage.setFont(font)

        self.formLayout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.lblLanguage)

        self.editEmail = QLineEdit(self.rightPanel)
        self.editEmail.setObjectName(u"editEmail")
        self.editEmail.setMinimumSize(QSize(260, 0))
        self.editEmail.setMaximumSize(QSize(360, 16777215))
        self.editEmail.setStyleSheet(u"/* --- \u041f\u043e\u043b\u044f \u0432\u0432\u0435\u0434\u0435\u043d\u043d\u044f --- */\n"
"QLineEdit {\n"
"border: 1px solid #AAAAAA;\n"
"border-radius: 4px;\n"
"padding: 4px;\n"
"font-size: 10pt;\n"
"}\n"
"")
        self.editEmail.setInputMethodHints(Qt.InputMethodHint.ImhEmailCharactersOnly)

        self.formLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.editEmail)

        self.lblEmail = QLabel(self.rightPanel)
        self.lblEmail.setObjectName(u"lblEmail")
        sizePolicy.setHeightForWidth(self.lblEmail.sizePolicy().hasHeightForWidth())
        self.lblEmail.setSizePolicy(sizePolicy)
        self.lblEmail.setMaximumSize(QSize(16777215, 28))
        self.lblEmail.setFont(font)

        self.formLayout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.lblEmail)

        self.editPassword = QLineEdit(self.rightPanel)
        self.editPassword.setObjectName(u"editPassword")
        self.editPassword.setEnabled(True)
        sizePolicy.setHeightForWidth(self.editPassword.sizePolicy().hasHeightForWidth())
        self.editPassword.setSizePolicy(sizePolicy)
        self.editPassword.setMinimumSize(QSize(260, 0))
        self.editPassword.setMaximumSize(QSize(360, 16777215))
        self.editPassword.setStyleSheet(u"")
        self.editPassword.setEchoMode(QLineEdit.EchoMode.Password)
        self.editPassword.setClearButtonEnabled(True)

        self.formLayout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.editPassword)

        self.lblPassword = QLabel(self.rightPanel)
        self.lblPassword.setObjectName(u"lblPassword")
        sizePolicy.setHeightForWidth(self.lblPassword.sizePolicy().hasHeightForWidth())
        self.lblPassword.setSizePolicy(sizePolicy)
        self.lblPassword.setMaximumSize(QSize(16777215, 28))
        self.lblPassword.setFont(font)
        self.lblPassword.setScaledContents(False)

        self.formLayout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.lblPassword)

        self.editPasswordConfirm = QLineEdit(self.rightPanel)
        self.editPasswordConfirm.setObjectName(u"editPasswordConfirm")
        sizePolicy.setHeightForWidth(self.editPasswordConfirm.sizePolicy().hasHeightForWidth())
        self.editPasswordConfirm.setSizePolicy(sizePolicy)
        self.editPasswordConfirm.setMinimumSize(QSize(260, 0))
        self.editPasswordConfirm.setMaximumSize(QSize(360, 16777215))
        self.editPasswordConfirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.editPasswordConfirm.setClearButtonEnabled(True)

        self.formLayout.setWidget(3, QFormLayout.ItemRole.LabelRole, self.editPasswordConfirm)

        self.lblPasswordConfirm = QLabel(self.rightPanel)
        self.lblPasswordConfirm.setObjectName(u"lblPasswordConfirm")
        sizePolicy.setHeightForWidth(self.lblPasswordConfirm.sizePolicy().hasHeightForWidth())
        self.lblPasswordConfirm.setSizePolicy(sizePolicy)
        self.lblPasswordConfirm.setMinimumSize(QSize(0, 0))
        self.lblPasswordConfirm.setMaximumSize(QSize(16777215, 28))
        self.lblPasswordConfirm.setFont(font)

        self.formLayout.setWidget(3, QFormLayout.ItemRole.FieldRole, self.lblPasswordConfirm)


        self.verticalLayout_2.addLayout(self.formLayout)

        self.lblError = QLabel(self.rightPanel)
        self.lblError.setObjectName(u"lblError")
        self.lblError.setEnabled(True)
        sizePolicy.setHeightForWidth(self.lblError.sizePolicy().hasHeightForWidth())
        self.lblError.setSizePolicy(sizePolicy)
        self.lblError.setMinimumSize(QSize(0, 0))
        self.lblError.setMaximumSize(QSize(600, 20))
        self.lblError.setStyleSheet(u"font: 10pt \"Segoe UI\";")

        self.verticalLayout_2.addWidget(self.lblError)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setSpacing(6)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.horizontalLayout_2.setSizeConstraint(QLayout.SizeConstraint.SetDefaultConstraint)
        self.btnRegister = QPushButton(self.rightPanel)
        self.btnRegister.setObjectName(u"btnRegister")
        sizePolicy.setHeightForWidth(self.btnRegister.sizePolicy().hasHeightForWidth())
        self.btnRegister.setSizePolicy(sizePolicy)
        self.btnRegister.setMaximumSize(QSize(16777215, 16777215))
        self.btnRegister.setFont(font)

        self.horizontalLayout_2.addWidget(self.btnRegister)

        self.btnExit = QPushButton(self.rightPanel)
        self.btnExit.setObjectName(u"btnExit")
        sizePolicy.setHeightForWidth(self.btnExit.sizePolicy().hasHeightForWidth())
        self.btnExit.setSizePolicy(sizePolicy)
        self.btnExit.setMaximumSize(QSize(16777215, 16777215))
        self.btnExit.setFont(font)

        self.horizontalLayout_2.addWidget(self.btnExit)


        self.verticalLayout_2.addLayout(self.horizontalLayout_2)

        self.verticalLayout_2.setStretch(0, 1)
        self.verticalLayout_2.setStretch(2, 1)
        self.verticalLayout_2.setStretch(3, 1)

        self.verticalLayout_4.addLayout(self.verticalLayout_2)


        self.horizontalLayout.addWidget(self.rightPanel)

        self.horizontalLayout.setStretch(0, 3)
        self.horizontalLayout.setStretch(1, 4)
        RegistrationWindow.setCentralWidget(self.centralwidget)

        self.retranslateUi(RegistrationWindow)

        QMetaObject.connectSlotsByName(RegistrationWindow)
    # setupUi

    def retranslateUi(self, RegistrationWindow):
        RegistrationWindow.setWindowTitle(QCoreApplication.translate("RegistrationWindow", u"[RegistrationWindow.windowTitle]", None))
        self.lblLogo.setText("")
        self.lblTitle.setText(QCoreApplication.translate("RegistrationWindow", u"[RegistrationWindow.lblTitle]", None))
        self.lblHeader.setText(QCoreApplication.translate("RegistrationWindow", u"[RegistrationWindow.lblHeader]", None))
        self.comboLanguage.setItemText(0, QCoreApplication.translate("RegistrationWindow", u"ua \u0423\u043a\u0440\u0430\u0457\u043d\u0441\u044c\u043a\u0430", u"ua \u0423\u043a\u0440\u0430\u0457\u043d\u0441\u044c\u043a\u0430"))
        self.comboLanguage.setItemText(1, QCoreApplication.translate("RegistrationWindow", u"\U0001f1ec\U0001f1e7 English", None))
        self.comboLanguage.setItemText(2, QCoreApplication.translate("RegistrationWindow", u"\U0001f1e9\U0001f1ea Deutsch", None))

#if QT_CONFIG(tooltip)
        self.comboLanguage.setToolTip("")
#endif // QT_CONFIG(tooltip)
        self.comboLanguage.setCurrentText(QCoreApplication.translate("RegistrationWindow", u"ua \u0423\u043a\u0440\u0430\u0457\u043d\u0441\u044c\u043a\u0430", None))
        self.comboLanguage.setPlaceholderText("")
        self.lblLanguage.setText(QCoreApplication.translate("RegistrationWindow", u"[RegistrationWindow.lblLanguage]", None))
        self.editEmail.setText("")
        self.editEmail.setPlaceholderText(QCoreApplication.translate("RegistrationWindow", u"[RegistrationWindow.editEmail]", None))
        self.lblEmail.setText(QCoreApplication.translate("RegistrationWindow", u"[RegistrationWindow.lblEmail]", None))
        self.editPassword.setText("")
        self.editPassword.setPlaceholderText(QCoreApplication.translate("RegistrationWindow", u"[RegistrationWindow.editPassword]", None))
        self.lblPassword.setText(QCoreApplication.translate("RegistrationWindow", u"[RegistrationWindow.lblPassword]", None))
        self.editPasswordConfirm.setPlaceholderText(QCoreApplication.translate("RegistrationWindow", u"[RegistrationWindow.editPasswordConfirm]", None))
        self.lblPasswordConfirm.setText(QCoreApplication.translate("RegistrationWindow", u"[RegistrationWindow.lblPasswordConfirm]", None))
        self.lblError.setText(QCoreApplication.translate("RegistrationWindow", u"[RegistrationWindow.lblError]", None))
        self.btnRegister.setText(QCoreApplication.translate("RegistrationWindow", u"[RegistrationWindow.btnRegister]", None))
        self.btnExit.setText(QCoreApplication.translate("RegistrationWindow", u"[RegistrationWindow.btnExit]", None))
    # retranslateUi

