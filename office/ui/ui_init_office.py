# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'init_office.ui'
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
    QCheckBox,
    QDialog,
    QGroupBox,
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


class Ui_InitOfficeWindow(object):
    def setupUi(self, InitOfficeWindow):
        if not InitOfficeWindow.objectName():
            InitOfficeWindow.setObjectName("InitOfficeWindow")
        InitOfficeWindow.resize(642, 360)
        sizePolicy = QSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(InitOfficeWindow.sizePolicy().hasHeightForWidth())
        InitOfficeWindow.setSizePolicy(sizePolicy)
        InitOfficeWindow.setMinimumSize(QSize(642, 360))
        icon = QIcon()
        icon.addFile(
            ":/office/icons/lgeoffice_gpt_24x24.png",
            QSize(),
            QIcon.Mode.Normal,
            QIcon.State.Off,
        )
        InitOfficeWindow.setWindowIcon(icon)
        self.verticalLayout = QVBoxLayout(InitOfficeWindow)
        self.verticalLayout.setSpacing(10)
        self.verticalLayout.setObjectName("verticalLayout")
        self.verticalLayout.setContentsMargins(16, 16, 16, 16)
        self.lblTitle = QLabel(InitOfficeWindow)
        self.lblTitle.setObjectName("lblTitle")
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        self.lblTitle.setFont(font)

        self.verticalLayout.addWidget(self.lblTitle)

        self.lblHint = QLabel(InitOfficeWindow)
        self.lblHint.setObjectName("lblHint")
        self.lblHint.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblHint)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.lblPassword = QLabel(InitOfficeWindow)
        self.lblPassword.setObjectName("lblPassword")

        self.horizontalLayout.addWidget(self.lblPassword)

        self.edtPassword = QLineEdit(InitOfficeWindow)
        self.edtPassword.setObjectName("edtPassword")
        self.edtPassword.setEchoMode(QLineEdit.EchoMode.Password)

        self.horizontalLayout.addWidget(self.edtPassword)

        self.lblPwStatus = QLabel(InitOfficeWindow)
        self.lblPwStatus.setObjectName("lblPwStatus")
        self.lblPwStatus.setWordWrap(True)

        self.horizontalLayout.addWidget(self.lblPwStatus)

        self.verticalLayout.addLayout(self.horizontalLayout)

        self.grpSteps = QGroupBox(InitOfficeWindow)
        self.grpSteps.setObjectName("grpSteps")
        self.verticalLayout_2 = QVBoxLayout(self.grpSteps)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.verticalLayout_2.setContentsMargins(-1, 20, -1, -1)
        self.chkDirs = QCheckBox(self.grpSteps)
        self.chkDirs.setObjectName("chkDirs")
        self.chkDirs.setEnabled(False)

        self.verticalLayout_2.addWidget(self.chkDirs)

        self.chkConfig = QCheckBox(self.grpSteps)
        self.chkConfig.setObjectName("chkConfig")
        self.chkConfig.setEnabled(False)

        self.verticalLayout_2.addWidget(self.chkConfig)

        self.chkKeys = QCheckBox(self.grpSteps)
        self.chkKeys.setObjectName("chkKeys")
        self.chkKeys.setEnabled(False)

        self.verticalLayout_2.addWidget(self.chkKeys)

        self.chkReady = QCheckBox(self.grpSteps)
        self.chkReady.setObjectName("chkReady")
        self.chkReady.setEnabled(False)

        self.verticalLayout_2.addWidget(self.chkReady)

        self.verticalLayout.addWidget(self.grpSteps)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.horizontalSpacer = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayout_2.addItem(self.horizontalSpacer)

        self.btnInit = QPushButton(InitOfficeWindow)
        self.btnInit.setObjectName("btnInit")
        self.btnInit.setCheckable(True)

        self.horizontalLayout_2.addWidget(self.btnInit)

        self.btnContinue = QPushButton(InitOfficeWindow)
        self.btnContinue.setObjectName("btnContinue")
        self.btnContinue.setEnabled(False)

        self.horizontalLayout_2.addWidget(self.btnContinue)

        self.btnExit = QPushButton(InitOfficeWindow)
        self.btnExit.setObjectName("btnExit")

        self.horizontalLayout_2.addWidget(self.btnExit)

        self.verticalLayout.addLayout(self.horizontalLayout_2)

        self.retranslateUi(InitOfficeWindow)

        QMetaObject.connectSlotsByName(InitOfficeWindow)

    # setupUi

    def retranslateUi(self, InitOfficeWindow):
        InitOfficeWindow.setWindowTitle(
            QCoreApplication.translate(
                "InitOfficeWindow",
                "LGE Office \u2014 \u0406\u043d\u0456\u0446\u0456\u0430\u043b\u0456\u0437\u0430\u0446\u0456\u044f",
                None,
            )
        )
        self.lblTitle.setText(
            QCoreApplication.translate(
                "InitOfficeWindow",
                "\u0406\u043d\u0456\u0446\u0456\u0430\u043b\u0456\u0437\u0430\u0446\u0456\u044f LGE Office",
                None,
            )
        )
        self.lblHint.setText(
            QCoreApplication.translate(
                "InitOfficeWindow",
                "\u0417\u0430\u0434\u0430\u0439\u0442\u0435 \u043f\u0430\u0440\u043e\u043b\u044c \u0430\u0434\u043c\u0456\u043d\u0456\u0441\u0442\u0440\u0430\u0442\u043e\u0440\u0430. \u0412\u0456\u043d \u043f\u043e\u0442\u0440\u0456\u0431\u0435\u043d \u0434\u043b\u044f \u0432\u0445\u043e\u0434\u0443 \u0432 LGE Office.\n"
                "\u0412\u0438\u043c\u043e\u0433\u0438: > 12 \u0441\u0438\u043c\u0432\u043e\u043b\u0456\u0432, \u043c\u0430\u043b\u0430+\u0432\u0435\u043b\u0438\u043a\u0430 \u043b\u0456\u0442\u0435\u0440\u0430, \u0446\u0438\u0444\u0440\u0430.\n"
                "",
                None,
            )
        )
        self.lblPassword.setText(
            QCoreApplication.translate(
                "InitOfficeWindow", "\u041f\u0430\u0440\u043e\u043b\u044c:", None
            )
        )
        self.edtPassword.setPlaceholderText(
            QCoreApplication.translate(
                "InitOfficeWindow",
                "\u0412\u0432\u0435\u0434\u0456\u0442\u044c \u043f\u0430\u0440\u043e\u043b\u044c...",
                None,
            )
        )
        self.lblPwStatus.setText(
            QCoreApplication.translate("InitOfficeWindow", "''", None)
        )
        self.grpSteps.setTitle(
            QCoreApplication.translate(
                "InitOfficeWindow", "\u0421\u0442\u0430\u043d", None
            )
        )
        self.chkDirs.setText(
            QCoreApplication.translate(
                "InitOfficeWindow",
                "\u0421\u0442\u0432\u043e\u0440\u0435\u043d\u043e \u043f\u0430\u043f\u043a\u0438 (keys;licenses;logs)",
                None,
            )
        )
        self.chkConfig.setText(
            QCoreApplication.translate(
                "InitOfficeWindow",
                "\u0421\u0442\u0432\u043e\u0440\u0435\u043d\u043e office_config.json",
                None,
            )
        )
        self.chkKeys.setText(
            QCoreApplication.translate(
                "InitOfficeWindow",
                "\u0421\u0442\u0432\u043e\u0440\u0435\u043d\u043e \u043a\u0440\u0438\u043f\u0442\u043e\u0433\u0440\u0430\u0444\u0456\u0447\u043d\u0456 \u043a\u043b\u044e\u0447\u0456 (Ed25519)",
                None,
            )
        )
        self.chkReady.setText(
            QCoreApplication.translate(
                "InitOfficeWindow",
                "\u0406\u043d\u0456\u0446\u0456\u0430\u043b\u0456\u0437\u0430\u0446\u0456\u044f \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0430",
                None,
            )
        )
        self.btnInit.setText(
            QCoreApplication.translate(
                "InitOfficeWindow",
                "\u0406\u043d\u0456\u0446\u0456\u0430\u043b\u0456\u0437\u0430\u0446\u0456\u044f",
                None,
            )
        )
        self.btnContinue.setText(
            QCoreApplication.translate(
                "InitOfficeWindow",
                "\u041f\u0440\u043e\u0434\u043e\u0432\u0436\u0438\u0442\u0438",
                None,
            )
        )
        self.btnExit.setText(
            QCoreApplication.translate(
                "InitOfficeWindow", "\u0412\u0438\u0445\u0456\u0434", None
            )
        )

    # retranslateUi
