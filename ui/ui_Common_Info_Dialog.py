# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'Common_Info_Dialog.ui'
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
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)


class Ui_CommonInfoDialog(object):
    def setupUi(self, CommonInfoDialog):
        if not CommonInfoDialog.objectName():
            CommonInfoDialog.setObjectName("CommonInfoDialog")
        CommonInfoDialog.resize(420, 160)
        CommonInfoDialog.setMinimumSize(QSize(420, 160))
        icon = QIcon()
        icon.addFile(
            ":/icons/lge_perplexity2_24x24.png",
            QSize(),
            QIcon.Mode.Normal,
            QIcon.State.Off,
        )
        CommonInfoDialog.setWindowIcon(icon)
        CommonInfoDialog.setSizeGripEnabled(False)
        self.verticalLayout = QVBoxLayout(CommonInfoDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.topRow = QHBoxLayout()
        self.topRow.setSpacing(12)
        self.topRow.setObjectName("topRow")
        self.frameAccent = QFrame(CommonInfoDialog)
        self.frameAccent.setObjectName("frameAccent")
        self.frameAccent.setMinimumSize(QSize(8, 0))
        self.frameAccent.setMaximumSize(QSize(8, 16777215))
        self.frameAccent.setFrameShape(QFrame.Shape.StyledPanel)
        self.frameAccent.setFrameShadow(QFrame.Shadow.Raised)

        self.topRow.addWidget(self.frameAccent)

        self.lblIcon = QLabel(CommonInfoDialog)
        self.lblIcon.setObjectName("lblIcon")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.lblIcon.sizePolicy().hasHeightForWidth())
        self.lblIcon.setSizePolicy(sizePolicy)
        self.lblIcon.setMinimumSize(QSize(36, 36))
        self.lblIcon.setMaximumSize(QSize(36, 36))
        self.lblIcon.setFrameShape(QFrame.Shape.WinPanel)
        self.lblIcon.setScaledContents(True)
        self.lblIcon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.topRow.addWidget(self.lblIcon)

        self.textCol = QVBoxLayout()
        self.textCol.setObjectName("textCol")
        self.lblHeader = QLabel(CommonInfoDialog)
        self.lblHeader.setObjectName("lblHeader")
        sizePolicy1 = QSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.lblHeader.sizePolicy().hasHeightForWidth())
        self.lblHeader.setSizePolicy(sizePolicy1)

        self.textCol.addWidget(self.lblHeader)

        self.lblDetails = QLabel(CommonInfoDialog)
        self.lblDetails.setObjectName("lblDetails")
        self.lblDetails.setWordWrap(True)

        self.textCol.addWidget(self.lblDetails)

        self.topRow.addLayout(self.textCol)

        self.verticalLayout.addLayout(self.topRow)

        self.btnRow = QHBoxLayout()
        self.btnRow.setObjectName("btnRow")
        self.horizontalSpacer = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.btnRow.addItem(self.horizontalSpacer)

        self.btnOk = QPushButton(CommonInfoDialog)
        self.btnOk.setObjectName("btnOk")
        self.btnOk.setCheckable(True)
        self.btnOk.setChecked(False)

        self.btnRow.addWidget(self.btnOk)

        self.verticalLayout.addLayout(self.btnRow)

        self.retranslateUi(CommonInfoDialog)

        QMetaObject.connectSlotsByName(CommonInfoDialog)

    # setupUi

    def retranslateUi(self, CommonInfoDialog):
        CommonInfoDialog.setWindowTitle(
            QCoreApplication.translate(
                "CommonInfoDialog", "[CommonInfoDialog.windowTitle]", None
            )
        )
        self.lblIcon.setText(QCoreApplication.translate("CommonInfoDialog", "I", None))
        self.lblHeader.setText(
            QCoreApplication.translate(
                "CommonInfoDialog", "[CommonInfoDialog.lblHeader]", None
            )
        )
        self.lblDetails.setText(
            QCoreApplication.translate(
                "CommonInfoDialog", "[CommonInfoDialog.lblDetails]", None
            )
        )
        self.btnOk.setText(
            QCoreApplication.translate(
                "CommonInfoDialog", "[CommonInfoDialog.btnOk]", None
            )
        )

    # retranslateUi
