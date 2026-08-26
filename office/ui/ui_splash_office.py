# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'splash_office.ui'
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
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
import resources_rc


class Ui_SplashOfficeWindow(object):
    def setupUi(self, SplashOfficeWindow):
        if not SplashOfficeWindow.objectName():
            SplashOfficeWindow.setObjectName("SplashOfficeWindow")
        SplashOfficeWindow.resize(650, 375)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(
            SplashOfficeWindow.sizePolicy().hasHeightForWidth()
        )
        SplashOfficeWindow.setSizePolicy(sizePolicy)
        SplashOfficeWindow.setMinimumSize(QSize(650, 375))
        SplashOfficeWindow.setMaximumSize(QSize(650, 375))
        icon = QIcon()
        icon.addFile(
            ":/office/icons/lgeoffice_gpt_24x24.png",
            QSize(),
            QIcon.Mode.Normal,
            QIcon.State.Off,
        )
        SplashOfficeWindow.setWindowIcon(icon)
        self.layoutWidget = QWidget(SplashOfficeWindow)
        self.layoutWidget.setObjectName("layoutWidget")
        self.layoutWidget.setGeometry(QRect(0, 0, 638, 341))
        self.horizontalLayout = QHBoxLayout(self.layoutWidget)
        self.horizontalLayout.setSpacing(16)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.horizontalLayout.setContentsMargins(10, 10, 10, 10)
        self.lblIcon = QLabel(self.layoutWidget)
        self.lblIcon.setObjectName("lblIcon")
        sizePolicy1 = QSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored
        )
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.lblIcon.sizePolicy().hasHeightForWidth())
        self.lblIcon.setSizePolicy(sizePolicy1)
        self.lblIcon.setMinimumSize(QSize(96, 96))
        self.lblIcon.setPixmap(QPixmap(":/office/icons/robot_400x400.png"))
        self.lblIcon.setScaledContents(True)

        self.horizontalLayout.addWidget(self.lblIcon)

        self.verticalLayout = QVBoxLayout()
        self.verticalLayout.setObjectName("verticalLayout")
        self.lblTitle = QLabel(self.layoutWidget)
        self.lblTitle.setObjectName("lblTitle")
        font = QFont()
        font.setPointSize(20)
        font.setBold(True)
        self.lblTitle.setFont(font)

        self.verticalLayout.addWidget(self.lblTitle)

        self.lblSubtitle = QLabel(self.layoutWidget)
        self.lblSubtitle.setObjectName("lblSubtitle")
        font1 = QFont()
        font1.setPointSize(11)
        self.lblSubtitle.setFont(font1)

        self.verticalLayout.addWidget(self.lblSubtitle)

        self.lblStatus = QLabel(self.layoutWidget)
        self.lblStatus.setObjectName("lblStatus")
        self.lblStatus.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblStatus)

        self.pbProgress = QProgressBar(self.layoutWidget)
        self.pbProgress.setObjectName("pbProgress")
        font2 = QFont()
        font2.setPointSize(12)
        self.pbProgress.setFont(font2)
        self.pbProgress.setMaximum(0)
        self.pbProgress.setValue(-1)
        self.pbProgress.setTextVisible(False)

        self.verticalLayout.addWidget(self.pbProgress)

        self.horizontalLayout.addLayout(self.verticalLayout)

        self.horizontalLayout.setStretch(0, 1)
        self.horizontalLayout.setStretch(1, 1)
        self.lblVersion = QLabel(SplashOfficeWindow)
        self.lblVersion.setObjectName("lblVersion")
        self.lblVersion.setGeometry(QRect(10, 350, 621, 20))
        self.lblVersion.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignTrailing
            | Qt.AlignmentFlag.AlignVCenter
        )

        self.retranslateUi(SplashOfficeWindow)

        QMetaObject.connectSlotsByName(SplashOfficeWindow)

    # setupUi

    def retranslateUi(self, SplashOfficeWindow):
        SplashOfficeWindow.setWindowTitle(
            QCoreApplication.translate("SplashOfficeWindow", "LGE Office", None)
        )
        self.lblIcon.setText("")
        self.lblTitle.setText(
            QCoreApplication.translate("SplashOfficeWindow", "LGE Office", None)
        )
        self.lblSubtitle.setText(
            QCoreApplication.translate(
                "SplashOfficeWindow",
                "\u0412\u0438\u0434\u0430\u0447\u0430 \u043b\u0456\u0446\u0435\u043d\u0437\u0456\u0439 \u0442\u0430 \u043e\u0431\u043b\u0456\u043a \u043a\u043b\u0456\u0454\u043d\u0442\u0456\u0432",
                None,
            )
        )
        self.lblStatus.setText(
            QCoreApplication.translate(
                "SplashOfficeWindow",
                "\u041f\u0435\u0440\u0435\u0432\u0456\u0440\u043a\u0430 \u0456\u043d\u0456\u0446\u0456\u0430\u043b\u0456\u0437\u0430\u0446\u0456\u0457...",
                None,
            )
        )
        self.lblVersion.setText(
            QCoreApplication.translate("SplashOfficeWindow", "v 0.1", None)
        )

    # retranslateUi
