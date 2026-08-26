# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'payment_duplicate_confirm_dialog.ui'
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
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)
import resources_rc


class Ui_PayDuplicateConfirmDialog(object):
    def setupUi(self, PayDuplicateConfirmDialog):
        if not PayDuplicateConfirmDialog.objectName():
            PayDuplicateConfirmDialog.setObjectName("PayDuplicateConfirmDialog")
        PayDuplicateConfirmDialog.resize(400, 449)
        icon = QIcon()
        icon.addFile(
            ":/office/icons/lgeoffice_gpt_24x24.png",
            QSize(),
            QIcon.Mode.Normal,
            QIcon.State.Off,
        )
        PayDuplicateConfirmDialog.setWindowIcon(icon)
        PayDuplicateConfirmDialog.setModal(True)
        self.verticalLayout = QVBoxLayout(PayDuplicateConfirmDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.lblTitle = QLabel(PayDuplicateConfirmDialog)
        self.lblTitle.setObjectName("lblTitle")
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        self.lblTitle.setFont(font)
        self.lblTitle.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblTitle)

        self.lblHint = QLabel(PayDuplicateConfirmDialog)
        self.lblHint.setObjectName("lblHint")
        self.lblHint.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblHint)

        self.plainDetails = QPlainTextEdit(PayDuplicateConfirmDialog)
        self.plainDetails.setObjectName("plainDetails")
        self.plainDetails.setMinimumSize(QSize(0, 200))
        self.plainDetails.setReadOnly(True)

        self.verticalLayout.addWidget(self.plainDetails)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.horizontalLayout.setContentsMargins(6, 6, 6, 6)
        self.horizontalSpacer = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.btnAddAnyway = QPushButton(PayDuplicateConfirmDialog)
        self.btnAddAnyway.setObjectName("btnAddAnyway")
        self.btnAddAnyway.setCheckable(True)

        self.horizontalLayout.addWidget(self.btnAddAnyway)

        self.btnCancel = QPushButton(PayDuplicateConfirmDialog)
        self.btnCancel.setObjectName("btnCancel")

        self.horizontalLayout.addWidget(self.btnCancel)

        self.verticalLayout.addLayout(self.horizontalLayout)

        self.verticalLayout.setStretch(0, 1)
        self.verticalLayout.setStretch(1, 2)
        self.verticalLayout.setStretch(2, 4)
        self.verticalLayout.setStretch(3, 2)

        self.retranslateUi(PayDuplicateConfirmDialog)

        QMetaObject.connectSlotsByName(PayDuplicateConfirmDialog)

    # setupUi

    def retranslateUi(self, PayDuplicateConfirmDialog):
        PayDuplicateConfirmDialog.setWindowTitle(
            QCoreApplication.translate(
                "PayDuplicateConfirmDialog",
                "LGE Office \u2014 \u0421\u0445\u043e\u0436\u0438\u0439 \u043f\u043b\u0430\u0442\u0456\u0436",
                None,
            )
        )
        self.lblTitle.setText(
            QCoreApplication.translate(
                "PayDuplicateConfirmDialog",
                "\u0417\u043d\u0430\u0439\u0434\u0435\u043d\u043e \u0441\u0445\u043e\u0436\u0438\u0439 \u043f\u043b\u0430\u0442\u0456\u0436",
                None,
            )
        )
        self.lblHint.setText(
            QCoreApplication.translate(
                "PayDuplicateConfirmDialog",
                '<html><head/><body><p>\u0423 \u0431\u0430\u0437\u0456 \u0432\u0436\u0435 \u0454 \u043f\u043b\u0430\u0442\u0456\u0436 \u0437 \u0442\u0430\u043a\u0438\u043c\u0438 \u0436 \u043e\u0441\u043d\u043e\u0432\u043d\u0438\u043c\u0438 \u0440\u0435\u043a\u0432\u0456\u0437\u0438\u0442\u0430\u043c\u0438.</p><p>\u041f\u0435\u0440\u0435\u0432\u0456\u0440\u0442\u0435 \u0434\u0430\u043d\u0456 \u043d\u0438\u0436\u0447\u0435.</p><p><span style=" font-size:10pt; font-weight:700;">\u0414\u043e\u0434\u0430\u0442\u0438 \u0446\u0435\u0439 \u043f\u043b\u0430\u0442\u0456\u0436?</span></p></body></html>',
                None,
            )
        )
        self.btnAddAnyway.setText(
            QCoreApplication.translate(
                "PayDuplicateConfirmDialog",
                "\u0414\u043e\u0434\u0430\u0442\u0438",
                None,
            )
        )
        self.btnCancel.setText(
            QCoreApplication.translate(
                "PayDuplicateConfirmDialog",
                "\u0421\u043a\u0430\u0441\u0443\u0432\u0430\u0442\u0438",
                None,
            )
        )

    # retranslateUi
