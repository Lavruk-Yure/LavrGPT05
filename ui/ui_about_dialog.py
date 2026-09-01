# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'about_dialog.ui'
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
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
import resources_rc


class Ui_AboutDialog(object):
    def setupUi(self, AboutDialog):
        if not AboutDialog.objectName():
            AboutDialog.setObjectName("AboutDialog")
        AboutDialog.resize(520, 260)
        AboutDialog.setMinimumSize(QSize(520, 260))
        self.verticalLayout = QVBoxLayout(AboutDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.hlTop = QHBoxLayout()
        self.hlTop.setObjectName("hlTop")
        self.lblIcon = QLabel(AboutDialog)
        self.lblIcon.setObjectName("lblIcon")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.lblIcon.sizePolicy().hasHeightForWidth())
        self.lblIcon.setSizePolicy(sizePolicy)
        self.lblIcon.setMinimumSize(QSize(96, 96))
        self.lblIcon.setMaximumSize(QSize(96, 96))
        self.lblIcon.setPixmap(QPixmap(":/icons/LGE/about_96.png"))
        self.lblIcon.setScaledContents(True)
        self.lblIcon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.hlTop.addWidget(self.lblIcon)

        self.vlText = QVBoxLayout()
        self.vlText.setObjectName("vlText")
        self.vlText.setContentsMargins(0, -1, -1, -1)
        self.lblTitle = QLabel(AboutDialog)
        self.lblTitle.setObjectName("lblTitle")
        self.lblTitle.setWordWrap(True)

        self.vlText.addWidget(self.lblTitle)

        self.textInfo = QTextBrowser(AboutDialog)
        self.textInfo.setObjectName("textInfo")
        self.textInfo.setFrameShape(QFrame.Shape.NoFrame)

        self.vlText.addWidget(self.textInfo)

        self.lblOs = QLabel(AboutDialog)
        self.lblOs.setObjectName("lblOs")
        self.lblOs.setWordWrap(True)

        self.vlText.addWidget(self.lblOs)

        self.lblComment = QLabel(AboutDialog)
        self.lblComment.setObjectName("lblComment")
        self.lblComment.setWordWrap(True)

        self.vlText.addWidget(self.lblComment)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.btnOk = QPushButton(AboutDialog)
        self.btnOk.setObjectName("btnOk")
        self.btnOk.setMinimumSize(QSize(50, 0))
        self.btnOk.setMaximumSize(QSize(100, 16777215))

        self.horizontalLayout.addWidget(self.btnOk)

        self.vlText.addLayout(self.horizontalLayout)

        self.hlTop.addLayout(self.vlText)

        self.verticalLayout.addLayout(self.hlTop)

        self.retranslateUi(AboutDialog)

        QMetaObject.connectSlotsByName(AboutDialog)

    # setupUi

    def retranslateUi(self, AboutDialog):
        AboutDialog.setWindowTitle(
            QCoreApplication.translate("AboutDialog", "[AboutDialog.windowTitle]", None)
        )
        self.lblIcon.setText("")
        self.lblTitle.setText(
            QCoreApplication.translate("AboutDialog", "[AboutDialog.title]", None)
        )
        self.lblOs.setText(
            QCoreApplication.translate("AboutDialog", "[AboutDialog.testedOs]", None)
        )
        self.lblComment.setText(
            QCoreApplication.translate("AboutDialog", "[AboutDialog.comment]", None)
        )
        self.btnOk.setText(
            QCoreApplication.translate("AboutDialog", "[AboutDialog.btnOk]", None)
        )

    # retranslateUi
