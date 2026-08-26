# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'email_preview.ui'
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
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
import resources_rc


class Ui_EmailPreviewWindow(object):
    def setupUi(self, EmailPreviewWindow):
        if not EmailPreviewWindow.objectName():
            EmailPreviewWindow.setObjectName("EmailPreviewWindow")
        EmailPreviewWindow.resize(488, 353)
        icon = QIcon()
        icon.addFile(
            ":/office/icons/lgeoffice_gpt_24x24.png",
            QSize(),
            QIcon.Mode.Normal,
            QIcon.State.Off,
        )
        EmailPreviewWindow.setWindowIcon(icon)
        self.verticalLayout = QVBoxLayout(EmailPreviewWindow)
        self.verticalLayout.setObjectName("verticalLayout")
        self.txtEmail = QTextEdit(EmailPreviewWindow)
        self.txtEmail.setObjectName("txtEmail")
        self.txtEmail.setReadOnly(True)

        self.verticalLayout.addWidget(self.txtEmail)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.horizontalSpacer = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.btnSend = QPushButton(EmailPreviewWindow)
        self.btnSend.setObjectName("btnSend")
        self.btnSend.setCheckable(True)

        self.horizontalLayout.addWidget(self.btnSend)

        self.btnEdit = QPushButton(EmailPreviewWindow)
        self.btnEdit.setObjectName("btnEdit")

        self.horizontalLayout.addWidget(self.btnEdit)

        self.btnCancel = QPushButton(EmailPreviewWindow)
        self.btnCancel.setObjectName("btnCancel")

        self.horizontalLayout.addWidget(self.btnCancel)

        self.verticalLayout.addLayout(self.horizontalLayout)

        self.retranslateUi(EmailPreviewWindow)

        QMetaObject.connectSlotsByName(EmailPreviewWindow)

    # setupUi

    def retranslateUi(self, EmailPreviewWindow):
        EmailPreviewWindow.setWindowTitle(
            QCoreApplication.translate(
                "EmailPreviewWindow",
                "\u041f\u043e\u043f\u0435\u0440\u0435\u0434\u043d\u0456\u0439 \u043f\u0435\u0440\u0435\u0433\u043b\u044f\u0434 \u043b\u0438\u0441\u0442\u0430 \u043f\u0435\u0440\u0435\u0434 \u0432\u0456\u0434\u043f\u0440\u0430\u0432\u043a\u043e\u044e",
                None,
            )
        )
        self.btnSend.setText(
            QCoreApplication.translate(
                "EmailPreviewWindow",
                "\u041d\u0430\u0434\u0456\u0441\u043b\u0430\u0442\u0438",
                None,
            )
        )
        self.btnEdit.setText(
            QCoreApplication.translate(
                "EmailPreviewWindow",
                "\u0420\u0435\u0434\u0430\u0433\u0443\u0432\u0430\u0442\u0438",
                None,
            )
        )
        self.btnCancel.setText(
            QCoreApplication.translate(
                "EmailPreviewWindow",
                "\u0412\u0456\u0434\u043c\u0456\u043d\u0438\u0442\u0438",
                None,
            )
        )

    # retranslateUi
