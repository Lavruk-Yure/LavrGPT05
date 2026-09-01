# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'test_styles.ui'
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
    QComboBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
import resources_rc


class Ui_LGEStyleTester(object):
    def setupUi(self, LGEStyleTester):
        if not LGEStyleTester.objectName():
            LGEStyleTester.setObjectName("LGEStyleTester")
        LGEStyleTester.resize(800, 500)
        LGEStyleTester.setStyleSheet(
            "\n"
            "QWidget#LGEStyleTester {\n"
            "    background-image: url(:/icons/robot_600x400.png);\n"
            "    background-position: center;\n"
            "    background-repeat: no-repeat;\n"
            "    background-origin: content;\n"
            "}\n"
            "   "
        )
        self.verticalLayout = QVBoxLayout(LGEStyleTester)
        self.verticalLayout.setObjectName("verticalLayout")
        self.lblTitle = QLabel(LGEStyleTester)
        self.lblTitle.setObjectName("lblTitle")
        self.lblTitle.setStyleSheet(
            "color: #2E7EF9;\n"
            'font: bold 14pt "Segoe UI";\n'
            "background-color: transparent;"
        )

        self.verticalLayout.addWidget(self.lblTitle)

        self.editSample = QLineEdit(LGEStyleTester)
        self.editSample.setObjectName("editSample")
        self.editSample.setStyleSheet(
            "QLineEdit {\n"
            "    border: 1px solid #AAAAAA;\n"
            "    border-radius: 4px;\n"
            "    padding: 4px;\n"
            "    font-size: 10pt;\n"
            "    background-color: white;\n"
            "}\n"
            "QLineEdit:focus {\n"
            "    border: 1px solid #2E7EF9;\n"
            "}"
        )

        self.verticalLayout.addWidget(self.editSample)

        self.btnTest = QPushButton(LGEStyleTester)
        self.btnTest.setObjectName("btnTest")
        self.btnTest.setStyleSheet(
            "QPushButton {\n"
            "    background-color: qlineargradient(\n"
            "        x1:0, y1:0, x2:0, y2:1,\n"
            "        stop:0 #2E7EF9, stop:1 #1E5FD0);\n"
            "    color: white;\n"
            "    border-radius: 8px;\n"
            '    font: bold 11pt "Segoe UI";\n'
            "    padding: 6px;\n"
            "}\n"
            "QPushButton:hover { background-color: #558CFF; }\n"
            "QPushButton:pressed { background-color: #244FC0; }"
        )
        icon = QIcon()
        icon.addFile(
            ":/icons/eye_open.svg", QSize(), QIcon.Mode.Normal, QIcon.State.Off
        )
        self.btnTest.setIcon(icon)

        self.verticalLayout.addWidget(self.btnTest)

        self.comboSample = QComboBox(LGEStyleTester)
        self.comboSample.addItem("")
        self.comboSample.addItem("")
        self.comboSample.setObjectName("comboSample")
        self.comboSample.setStyleSheet(
            "QComboBox {\n"
            "    border: 1px solid #AAAAAA;\n"
            "    border-radius: 4px;\n"
            "    padding: 3px;\n"
            "    font-size: 10pt;\n"
            "    background-color: white;\n"
            "}\n"
            "QComboBox:focus {\n"
            "    border: 1px solid #2E7EF9;\n"
            "}"
        )

        self.verticalLayout.addWidget(self.comboSample)

        self.tableSample = QTableWidget(LGEStyleTester)
        if self.tableSample.columnCount() < 3:
            self.tableSample.setColumnCount(3)
        if self.tableSample.rowCount() < 3:
            self.tableSample.setRowCount(3)
        self.tableSample.setObjectName("tableSample")
        self.tableSample.setEnabled(True)
        self.tableSample.setStyleSheet(
            "QTableWidget {\n"
            "    background-color: #101820;\n"
            "    alternate-background-color: #182030;\n"
            "    color: #E0E0E0;\n"
            "    gridline-color: #2E7EF9;\n"
            "    selection-background-color: #2E7EF9;\n"
            "    selection-color: #FFFFFF;\n"
            "}"
        )
        self.tableSample.setAlternatingRowColors(True)
        self.tableSample.setRowCount(3)
        self.tableSample.setColumnCount(3)

        self.verticalLayout.addWidget(self.tableSample)

        self.progressSample = QProgressBar(LGEStyleTester)
        self.progressSample.setObjectName("progressSample")
        self.progressSample.setStyleSheet(
            "QProgressBar {\n"
            "    border: 1px solid #2E7EF9;\n"
            "    border-radius: 5px;\n"
            "    background-color: rgba(255, 255, 255, 30);\n"
            "    height: 12px;\n"
            "}\n"
            "QProgressBar::chunk {\n"
            "    background-color: #2E7EF9;\n"
            "    border-radius: 5px;\n"
            "}"
        )
        self.progressSample.setValue(50)

        self.verticalLayout.addWidget(self.progressSample)

        self.retranslateUi(LGEStyleTester)

        QMetaObject.connectSlotsByName(LGEStyleTester)

    # setupUi

    def retranslateUi(self, LGEStyleTester):
        LGEStyleTester.setWindowTitle(
            QCoreApplication.translate("LGEStyleTester", "LGE Style Tester", None)
        )
        self.lblTitle.setText(
            QCoreApplication.translate("LGEStyleTester", "LGE Style Test", None)
        )
        self.editSample.setPlaceholderText(
            QCoreApplication.translate("LGEStyleTester", "Type something...", None)
        )
        self.btnTest.setText(
            QCoreApplication.translate("LGEStyleTester", "Test Button", None)
        )
        self.comboSample.setItemText(
            0, QCoreApplication.translate("LGEStyleTester", "Option 1", None)
        )
        self.comboSample.setItemText(
            1, QCoreApplication.translate("LGEStyleTester", "Option 2", None)
        )

    # retranslateUi
