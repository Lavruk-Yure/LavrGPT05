# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'about_dialog.ui'
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
from PySide6.QtWidgets import (QAbstractButton, QApplication, QDialog, QDialogButtonBox,
    QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout,
    QWidget)

class Ui_AboutDialog(object):
    def setupUi(self, AboutDialog):
        if not AboutDialog.objectName():
            AboutDialog.setObjectName(u"AboutDialog")
        AboutDialog.resize(520, 260)
        AboutDialog.setMinimumSize(QSize(520, 260))
        self.verticalLayout = QVBoxLayout(AboutDialog)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.hlTop = QHBoxLayout()
        self.hlTop.setObjectName(u"hlTop")
        self.lblIcon = QLabel(AboutDialog)
        self.lblIcon.setObjectName(u"lblIcon")
        self.lblIcon.setMinimumSize(QSize(64, 64))
        self.lblIcon.setMaximumSize(QSize(64, 64))

        self.hlTop.addWidget(self.lblIcon)

        self.vlText = QVBoxLayout()
        self.vlText.setObjectName(u"vlText")
        self.lblTitle = QLabel(AboutDialog)
        self.lblTitle.setObjectName(u"lblTitle")
        self.lblTitle.setWordWrap(True)

        self.vlText.addWidget(self.lblTitle)

        self.lblInfo = QLabel(AboutDialog)
        self.lblInfo.setObjectName(u"lblInfo")
        self.lblInfo.setWordWrap(True)

        self.vlText.addWidget(self.lblInfo)

        self.lblOs = QLabel(AboutDialog)
        self.lblOs.setObjectName(u"lblOs")
        self.lblOs.setWordWrap(True)

        self.vlText.addWidget(self.lblOs)

        self.lblComment = QLabel(AboutDialog)
        self.lblComment.setObjectName(u"lblComment")
        self.lblComment.setWordWrap(True)

        self.vlText.addWidget(self.lblComment)


        self.hlTop.addLayout(self.vlText)


        self.verticalLayout.addLayout(self.hlTop)

        self.buttonBox = QDialogButtonBox(AboutDialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setStandardButtons(QDialogButtonBox.StandardButton.NoButton)

        self.verticalLayout.addWidget(self.buttonBox)


        self.retranslateUi(AboutDialog)

        QMetaObject.connectSlotsByName(AboutDialog)
    # setupUi

    def retranslateUi(self, AboutDialog):
        AboutDialog.setWindowTitle(QCoreApplication.translate("AboutDialog", u"[AboutDialog.windowTitle]", None))
        self.lblIcon.setText("")
        self.lblTitle.setText(QCoreApplication.translate("AboutDialog", u"[AboutDialog.title]", None))
        self.lblInfo.setText(QCoreApplication.translate("AboutDialog", u"[AboutDialog.info]", None))
        self.lblOs.setText(QCoreApplication.translate("AboutDialog", u"[AboutDialog.testedOs]", None))
        self.lblComment.setText(QCoreApplication.translate("AboutDialog", u"[AboutDialog.comment]", None))
    # retranslateUi

