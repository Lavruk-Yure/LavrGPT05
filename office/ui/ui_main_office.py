# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main_office.ui'
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
    QAction,
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
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)
import resources_rc


class Ui_MainOfficeWindow(object):
    def setupUi(self, MainOfficeWindow):
        if not MainOfficeWindow.objectName():
            MainOfficeWindow.setObjectName("MainOfficeWindow")
        MainOfficeWindow.resize(450, 351)
        MainOfficeWindow.setMinimumSize(QSize(450, 300))
        icon = QIcon()
        icon.addFile(
            ":/office/icons/lgeoffice_gpt_24x24.png",
            QSize(),
            QIcon.Mode.Normal,
            QIcon.State.Off,
        )
        MainOfficeWindow.setWindowIcon(icon)
        self.action = QAction(MainOfficeWindow)
        self.action.setObjectName("action")
        self.actExit = QAction(MainOfficeWindow)
        self.actExit.setObjectName("actExit")
        self.actInit = QAction(MainOfficeWindow)
        self.actInit.setObjectName("actInit")
        self.actIssue = QAction(MainOfficeWindow)
        self.actIssue.setObjectName("actIssue")
        self.actPayments = QAction(MainOfficeWindow)
        self.actPayments.setObjectName("actPayments")
        self.actDbGrid = QAction(MainOfficeWindow)
        self.actDbGrid.setObjectName("actDbGrid")
        self.actDbReport = QAction(MainOfficeWindow)
        self.actDbReport.setObjectName("actDbReport")
        self.actQuickIssue = QAction(MainOfficeWindow)
        self.actQuickIssue.setObjectName("actQuickIssue")
        self.centralwidget = QWidget(MainOfficeWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.horizontalLayout = QHBoxLayout(self.centralwidget)
        self.horizontalLayout.setSpacing(9)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.horizontalLayout.setContentsMargins(9, 9, 9, 9)
        self.frame = QFrame(self.centralwidget)
        self.frame.setObjectName("frame")
        self.frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame.setFrameShadow(QFrame.Shadow.Raised)
        self.horizontalLayout_2 = QHBoxLayout(self.frame)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.frmLeft = QFrame(self.frame)
        self.frmLeft.setObjectName("frmLeft")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frmLeft.sizePolicy().hasHeightForWidth())
        self.frmLeft.setSizePolicy(sizePolicy)
        self.frmLeft.setMinimumSize(QSize(150, 0))
        self.frmLeft.setFrameShape(QFrame.Shape.StyledPanel)
        self.frmLeft.setFrameShadow(QFrame.Shadow.Raised)
        self.verticalLayout_2 = QVBoxLayout(self.frmLeft)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.verticalLayout = QVBoxLayout()
        self.verticalLayout.setSpacing(8)
        self.verticalLayout.setObjectName("verticalLayout")
        self.verticalLayout.setContentsMargins(12, 12, 12, 12)
        self.lblLogo = QLabel(self.frmLeft)
        self.lblLogo.setObjectName("lblLogo")
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        self.lblLogo.setFont(font)

        self.verticalLayout.addWidget(self.lblLogo)

        self.btnQuickIssue = QPushButton(self.frmLeft)
        self.btnQuickIssue.setObjectName("btnQuickIssue")

        self.verticalLayout.addWidget(self.btnQuickIssue)

        self.btnPayments = QPushButton(self.frmLeft)
        self.btnPayments.setObjectName("btnPayments")

        self.verticalLayout.addWidget(self.btnPayments)

        self.btnDbGrid = QPushButton(self.frmLeft)
        self.btnDbGrid.setObjectName("btnDbGrid")

        self.verticalLayout.addWidget(self.btnDbGrid)

        self.btnDbReport = QPushButton(self.frmLeft)
        self.btnDbReport.setObjectName("btnDbReport")

        self.verticalLayout.addWidget(self.btnDbReport)

        self.btnInit = QPushButton(self.frmLeft)
        self.btnInit.setObjectName("btnInit")
        self.btnInit.setCheckable(True)

        self.verticalLayout.addWidget(self.btnInit)

        self.btnExit = QPushButton(self.frmLeft)
        self.btnExit.setObjectName("btnExit")

        self.verticalLayout.addWidget(self.btnExit)

        self.verticalSpacer = QSpacerItem(
            20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        )

        self.verticalLayout.addItem(self.verticalSpacer)

        self.verticalLayout_2.addLayout(self.verticalLayout)

        self.horizontalLayout_2.addWidget(self.frmLeft)

        self.frmContent = QFrame(self.frame)
        self.frmContent.setObjectName("frmContent")
        self.frmContent.setFrameShape(QFrame.Shape.StyledPanel)
        self.frmContent.setFrameShadow(QFrame.Shadow.Raised)
        self.verticalLayout_3 = QVBoxLayout(self.frmContent)
        self.verticalLayout_3.setSpacing(10)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.verticalLayout_3.setContentsMargins(16, 16, 16, 16)
        self.lblPageTitle = QLabel(self.frmContent)
        self.lblPageTitle.setObjectName("lblPageTitle")
        self.lblPageTitle.setFont(font)
        self.lblPageTitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.verticalLayout_3.addWidget(self.lblPageTitle)

        self.lblInfo = QLabel(self.frmContent)
        self.lblInfo.setObjectName("lblInfo")
        font1 = QFont()
        font1.setPointSize(10)
        self.lblInfo.setFont(font1)
        self.lblInfo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lblInfo.setWordWrap(True)

        self.verticalLayout_3.addWidget(self.lblInfo)

        self.horizontalLayout_2.addWidget(self.frmContent)

        self.horizontalLayout.addWidget(self.frame)

        MainOfficeWindow.setCentralWidget(self.centralwidget)
        self.menuBar = QMenuBar(MainOfficeWindow)
        self.menuBar.setObjectName("menuBar")
        self.menuBar.setGeometry(QRect(0, 0, 450, 33))
        self.menuFile = QMenu(self.menuBar)
        self.menuFile.setObjectName("menuFile")
        self.menuService = QMenu(self.menuBar)
        self.menuService.setObjectName("menuService")
        MainOfficeWindow.setMenuBar(self.menuBar)
        self.statusBar = QStatusBar(MainOfficeWindow)
        self.statusBar.setObjectName("statusBar")
        MainOfficeWindow.setStatusBar(self.statusBar)

        self.menuBar.addAction(self.menuFile.menuAction())
        self.menuBar.addAction(self.menuService.menuAction())
        self.menuFile.addAction(self.actExit)
        self.menuService.addAction(self.actQuickIssue)
        self.menuService.addAction(self.actPayments)
        self.menuService.addAction(self.actDbGrid)
        self.menuService.addAction(self.actDbReport)
        self.menuService.addAction(self.actInit)

        self.retranslateUi(MainOfficeWindow)

        QMetaObject.connectSlotsByName(MainOfficeWindow)

    # setupUi

    def retranslateUi(self, MainOfficeWindow):
        MainOfficeWindow.setWindowTitle(
            QCoreApplication.translate("MainOfficeWindow", "LGE Office", None)
        )
        self.action.setText(
            QCoreApplication.translate(
                "MainOfficeWindow", "\u0421\u0435\u0440\u0432\u0456\u0441", None
            )
        )
        self.actExit.setText(
            QCoreApplication.translate(
                "MainOfficeWindow", "\u0412\u0438\u0445\u0456\u0434", None
            )
        )
        self.actInit.setText(
            QCoreApplication.translate(
                "MainOfficeWindow",
                "\u0406\u043d\u0456\u0446\u0456\u0430\u043b\u0456\u0437\u0430\u0446\u0456\u044f",
                None,
            )
        )
        self.actIssue.setText(
            QCoreApplication.translate(
                "MainOfficeWindow",
                "\u0412\u0438\u0434\u0430\u0447\u0430 \u043b\u0456\u0446\u0435\u043d\u0437\u0456\u0457",
                None,
            )
        )
        self.actPayments.setText(
            QCoreApplication.translate(
                "MainOfficeWindow",
                "\u0414\u043e\u0434\u0430\u0442\u0438 \u043d\u0435\u0432\u0438\u0437\u043d\u0430\u0447\u0435\u043d\u0438\u0439 \u043f\u043b\u0430\u0442\u0456\u0436",
                None,
            )
        )
        self.actDbGrid.setText(
            QCoreApplication.translate(
                "MainOfficeWindow",
                "\u0420\u0435\u0434\u0430\u043a\u0442\u043e\u0440",
                None,
            )
        )
        self.actDbReport.setText(
            QCoreApplication.translate(
                "MainOfficeWindow",
                "\u0417\u0432\u0456\u0442 \u043f\u043e \u0431\u0430\u0437\u0456 \u0434\u0430\u043d\u0438\u0445",
                None,
            )
        )
        self.actQuickIssue.setText(
            QCoreApplication.translate(
                "MainOfficeWindow",
                "\u0428\u0432\u0438\u0434\u043a\u0430 \u0432\u0438\u0434\u0430\u0447\u0430 \u043b\u0456\u0446\u0435\u043d\u0437\u0456\u0457",
                None,
            )
        )
        # if QT_CONFIG(tooltip)
        self.actQuickIssue.setToolTip(
            QCoreApplication.translate(
                "MainOfficeWindow",
                "\u0412\u0456\u0434\u043a\u0440\u0438\u0442\u0438 \u0434\u0456\u0430\u043b\u043e\u0433 \u0448\u0432\u0438\u0434\u043a\u043e\u0457 \u0432\u0438\u0434\u0430\u0447\u0456 \u043b\u0456\u0446\u0435\u043d\u0437\u0456\u0457",
                None,
            )
        )
        # endif // QT_CONFIG(tooltip)
        self.lblLogo.setText(
            QCoreApplication.translate("MainOfficeWindow", "LGE Office", None)
        )
        # if QT_CONFIG(tooltip)
        self.btnQuickIssue.setToolTip(
            QCoreApplication.translate(
                "MainOfficeWindow",
                "\u0421\u0442\u0432\u043e\u0440\u0438\u0442\u0438 \u043a\u043b\u0456\u0454\u043d\u0442\u0430, \u0437\u0430\u043c\u043e\u0432\u043b\u0435\u043d\u043d\u044f, \u043e\u043f\u043b\u0430\u0442\u0443, \u043b\u0456\u0446\u0435\u043d\u0437\u0456\u044e \u0442\u0430 \u043f\u0456\u0434\u0433\u043e\u0442\u0443\u0432\u0430\u0442\u0438 \u043b\u0438\u0441\u0442",
                None,
            )
        )
        # endif // QT_CONFIG(tooltip)
        self.btnQuickIssue.setText(
            QCoreApplication.translate(
                "MainOfficeWindow",
                "\u0428\u0432\u0438\u0434\u043a\u0430 \u0432\u0438\u0434\u0430\u0447\u0430 \u043b\u0456\u0446\u0435\u043d\u0437\u0456\u0457",
                None,
            )
        )
        self.btnPayments.setText(
            QCoreApplication.translate(
                "MainOfficeWindow",
                "\u0414\u043e\u0434\u0430\u0442\u0438 \u043d\u0435\u0432\u0438\u0437\u043d\u0430\u0447\u0435\u043d\u0438\u0439 \u043f\u043b\u0430\u0442\u0456\u0436",
                None,
            )
        )
        # if QT_CONFIG(tooltip)
        self.btnDbGrid.setToolTip(
            QCoreApplication.translate(
                "MainOfficeWindow",
                "\u0423\u043d\u0456\u0432\u0435\u0440\u0441\u0430\u043b\u044c\u043d\u0438\u0439 \u0440\u0435\u0434\u0430\u043a\u0442\u043e\u0440. \u041e\u0431\u0440\u043e\u0431\u043a\u0430 \u0437\u0430\u043f\u0438\u0442\u0443, \u043e\u043f\u043b\u0430\u0442, \u0432\u0438\u0434\u0430\u0447\u0430 \u043b\u0456\u0446\u0435\u043d\u0437\u0456\u0457",
                None,
            )
        )
        # endif // QT_CONFIG(tooltip)
        self.btnDbGrid.setText(
            QCoreApplication.translate(
                "MainOfficeWindow",
                "\u0420\u0435\u0434\u0430\u043a\u0442\u043e\u0440 \u0434\u0456\u0439 \u0456 \u0442\u0430\u0431\u043b\u0438\u0446\u044c ",
                None,
            )
        )
        # if QT_CONFIG(tooltip)
        self.btnDbReport.setToolTip(
            QCoreApplication.translate(
                "MainOfficeWindow",
                "\u0421\u0444\u043e\u0440\u043c\u0443\u0432\u0430\u0442\u0438 TXT-\u0437\u0432\u0456\u0442 \u043f\u043e \u0441\u0442\u0430\u043d\u0443 \u0431\u0430\u0437\u0438 \u0434\u0430\u043d\u0438\u0445",
                None,
            )
        )
        # endif // QT_CONFIG(tooltip)
        self.btnDbReport.setText(
            QCoreApplication.translate(
                "MainOfficeWindow",
                "\u0417\u0432\u0456\u0442 \u043f\u043e \u0431\u0430\u0437\u0456 \u0434\u0430\u043d\u0438\u0445",
                None,
            )
        )
        # if QT_CONFIG(tooltip)
        self.btnInit.setToolTip(
            QCoreApplication.translate(
                "MainOfficeWindow",
                "\u0421\u0442\u0432\u043e\u0440\u0435\u043d\u043d\u044f \u0411\u0414 \u0456 config",
                None,
            )
        )
        # endif // QT_CONFIG(tooltip)
        self.btnInit.setText(
            QCoreApplication.translate(
                "MainOfficeWindow",
                "\u0406\u043d\u0456\u0446\u0456\u0430\u043b\u0456\u0437\u0430\u0446\u0456\u044f",
                None,
            )
        )
        # if QT_CONFIG(tooltip)
        self.btnExit.setToolTip(
            QCoreApplication.translate(
                "MainOfficeWindow",
                "\u0417\u0430\u043a\u0456\u043d\u0447\u0435\u043d\u043d\u044f",
                None,
            )
        )
        # endif // QT_CONFIG(tooltip)
        self.btnExit.setText(
            QCoreApplication.translate(
                "MainOfficeWindow", "\u0412\u0438\u0445\u0456\u0434", None
            )
        )
        self.lblPageTitle.setText(
            QCoreApplication.translate(
                "MainOfficeWindow",
                "\u0413\u043e\u043b\u043e\u0432\u043d\u0435 \u043c\u0435\u043d\u044e",
                None,
            )
        )
        self.lblInfo.setText(
            QCoreApplication.translate(
                "MainOfficeWindow",
                "\u0412\u0438\u0431\u0435\u0440\u0456\u0442\u044c \u0434\u0456\u044e \u0437 \u043c\u0435\u043d\u044e \u0437\u043b\u0456\u0432\u0430.",
                None,
            )
        )
        self.menuFile.setTitle(
            QCoreApplication.translate(
                "MainOfficeWindow", "\u0424\u0430\u0439\u043b", None
            )
        )
        self.menuService.setTitle(
            QCoreApplication.translate(
                "MainOfficeWindow", "\u0421\u0435\u0440\u0432\u0456\u0441", None
            )
        )

    # retranslateUi
