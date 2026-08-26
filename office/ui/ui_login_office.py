# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'login_office.ui'
##
## Created by: Qt User Interface Compiler version 6.9.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (
    QCoreApplication,
    QDate,
    QDateTime,
    QLocale,
    QMetaObject,
    QObject,
    QPoint,
    QRect,
    QSize,
    QTime,
    QUrl,
    Qt,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QCursor,
    QFont,
    QFontDatabase,
    QGradient,
    QIcon,
    QImage,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPalette,
    QPixmap,
    QRadialGradient,
    QTransform,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)
import resources_rc


class Ui_LoginOfficeWindow(object):
    def setupUi(self, LoginOfficeWindow):
        if not LoginOfficeWindow.objectName():
            LoginOfficeWindow.setObjectName("LoginOfficeWindow")
        LoginOfficeWindow.resize(420, 220)
        LoginOfficeWindow.setMinimumSize(QSize(420, 220))
        icon = QIcon()
        icon.addFile(
            ":/office/icons/lgeoffice_gpt_24x24.png",
            QSize(),
            QIcon.Mode.Normal,
            QIcon.State.Off,
        )
        LoginOfficeWindow.setWindowIcon(icon)
        LoginOfficeWindow.setModal(True)
        self.verticalLayout = QVBoxLayout(LoginOfficeWindow)
        self.verticalLayout.setSpacing(10)
        self.verticalLayout.setObjectName("verticalLayout")
        self.verticalLayout.setContentsMargins(16, 16, 16, 16)
        self.lblTitle = QLabel(LoginOfficeWindow)
        self.lblTitle.setObjectName("lblTitle")
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        self.lblTitle.setFont(font)

        self.verticalLayout.addWidget(self.lblTitle)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.lblHint = QLabel(LoginOfficeWindow)
        self.lblHint.setObjectName("lblHint")

        self.horizontalLayout_2.addWidget(self.lblHint)

        self.edtPassword = QLineEdit(LoginOfficeWindow)
        self.edtPassword.setObjectName("edtPassword")
        self.edtPassword.setEchoMode(QLineEdit.EchoMode.Password)

        self.horizontalLayout_2.addWidget(self.edtPassword)

        self.btnTogglePassword = QPushButton(LoginOfficeWindow)
        self.btnTogglePassword.setObjectName("btnTogglePassword")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(
            self.btnTogglePassword.sizePolicy().hasHeightForWidth()
        )
        self.btnTogglePassword.setSizePolicy(sizePolicy)
        self.btnTogglePassword.setMinimumSize(QSize(26, 26))
        self.btnTogglePassword.setMaximumSize(QSize(26, 26))
        self.btnTogglePassword.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        icon1 = QIcon()
        icon1.addFile(
            ":/office/icons/eye_closed.svg", QSize(), QIcon.Mode.Normal, QIcon.State.Off
        )
        self.btnTogglePassword.setIcon(icon1)
        self.btnTogglePassword.setCheckable(True)
        self.btnTogglePassword.setFlat(True)

        self.horizontalLayout_2.addWidget(self.btnTogglePassword)

        self.verticalLayout.addLayout(self.horizontalLayout_2)

        self.lblStatus = QLabel(LoginOfficeWindow)
        self.lblStatus.setObjectName("lblStatus")
        self.lblStatus.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblStatus)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.horizontalSpacer = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.btnLogin = QPushButton(LoginOfficeWindow)
        self.btnLogin.setObjectName("btnLogin")
        self.btnLogin.setCheckable(True)

        self.horizontalLayout.addWidget(self.btnLogin)

        self.btnExit = QPushButton(LoginOfficeWindow)
        self.btnExit.setObjectName("btnExit")

        self.horizontalLayout.addWidget(self.btnExit)

        self.verticalLayout.addLayout(self.horizontalLayout)

        self.retranslateUi(LoginOfficeWindow)

        QMetaObject.connectSlotsByName(LoginOfficeWindow)

    # setupUi

    def retranslateUi(self, LoginOfficeWindow):
        LoginOfficeWindow.setWindowTitle(
            QCoreApplication.translate(
                "LoginOfficeWindow", "LGE Office \u2014 \u0412\u0445\u0456\u0434", None
            )
        )
        self.lblTitle.setText(
            QCoreApplication.translate(
                "LoginOfficeWindow",
                "\u0412\u0445\u0456\u0434 \u0434\u043e LGE Office",
                None,
            )
        )
        self.lblHint.setText(
            QCoreApplication.translate(
                "LoginOfficeWindow",
                "\u041f\u0430\u0440\u043e\u043b\u044c \u0430\u0434\u043c\u0456\u043d\u0456\u0441\u0442\u0440\u0430\u0442\u043e\u0440\u0430:",
                None,
            )
        )
        self.edtPassword.setPlaceholderText(
            QCoreApplication.translate(
                "LoginOfficeWindow", "\u041f\u0430\u0440\u043e\u043b\u044c...", None
            )
        )
        self.btnTogglePassword.setText("")
        self.lblStatus.setText("")
        self.btnLogin.setText(
            QCoreApplication.translate(
                "LoginOfficeWindow", "\u0423\u0432\u0456\u0439\u0442\u0438", None
            )
        )
        self.btnExit.setText(
            QCoreApplication.translate(
                "LoginOfficeWindow", "\u0412\u0438\u0445\u0456\u0434", None
            )
        )

    # retranslateUi
