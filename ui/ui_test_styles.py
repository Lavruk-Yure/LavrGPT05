# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'test_styles.ui'
##
## Created by: Qt User Interface Compiler version 6.9.1
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
from PySide6.QtWidgets import (QApplication, QComboBox, QHeaderView, QLabel,
    QLineEdit, QProgressBar, QPushButton, QSizePolicy,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
import resources_rc

class Ui_LGE05StyleTester(object):
    def setupUi(self, LGE05StyleTester):
        if not LGE05StyleTester.objectName():
            LGE05StyleTester.setObjectName(u"LGE05StyleTester")
        LGE05StyleTester.resize(800, 500)
        LGE05StyleTester.setStyleSheet(u"\n"
"QWidget#LGE05StyleTester {\n"
"    background-image: url(:/icons/robot_600x400.png);\n"
"    background-position: center;\n"
"    background-repeat: no-repeat;\n"
"    background-origin: content;\n"
"}\n"
"   ")
        self.verticalLayout = QVBoxLayout(LGE05StyleTester)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.lblTitle = QLabel(LGE05StyleTester)
        self.lblTitle.setObjectName(u"lblTitle")
        self.lblTitle.setStyleSheet(u"color: #2E7EF9;\n"
"font: bold 14pt \"Segoe UI\";\n"
"background-color: transparent;")

        self.verticalLayout.addWidget(self.lblTitle)

        self.editSample = QLineEdit(LGE05StyleTester)
        self.editSample.setObjectName(u"editSample")
        self.editSample.setStyleSheet(u"QLineEdit {\n"
"    border: 1px solid #AAAAAA;\n"
"    border-radius: 4px;\n"
"    padding: 4px;\n"
"    font-size: 10pt;\n"
"    background-color: white;\n"
"}\n"
"QLineEdit:focus {\n"
"    border: 1px solid #2E7EF9;\n"
"}")

        self.verticalLayout.addWidget(self.editSample)

        self.btnTest = QPushButton(LGE05StyleTester)
        self.btnTest.setObjectName(u"btnTest")
        self.btnTest.setStyleSheet(u"QPushButton {\n"
"    background-color: qlineargradient(\n"
"        x1:0, y1:0, x2:0, y2:1,\n"
"        stop:0 #2E7EF9, stop:1 #1E5FD0);\n"
"    color: white;\n"
"    border-radius: 8px;\n"
"    font: bold 11pt \"Segoe UI\";\n"
"    padding: 6px;\n"
"}\n"
"QPushButton:hover { background-color: #558CFF; }\n"
"QPushButton:pressed { background-color: #244FC0; }")
        icon = QIcon()
        icon.addFile(u":/icons/eye_open.svg", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.btnTest.setIcon(icon)

        self.verticalLayout.addWidget(self.btnTest)

        self.comboSample = QComboBox(LGE05StyleTester)
        self.comboSample.addItem("")
        self.comboSample.addItem("")
        self.comboSample.setObjectName(u"comboSample")
        self.comboSample.setStyleSheet(u"QComboBox {\n"
"    border: 1px solid #AAAAAA;\n"
"    border-radius: 4px;\n"
"    padding: 3px;\n"
"    font-size: 10pt;\n"
"    background-color: white;\n"
"}\n"
"QComboBox:focus {\n"
"    border: 1px solid #2E7EF9;\n"
"}")

        self.verticalLayout.addWidget(self.comboSample)

        self.tableSample = QTableWidget(LGE05StyleTester)
        if (self.tableSample.columnCount() < 3):
            self.tableSample.setColumnCount(3)
        if (self.tableSample.rowCount() < 3):
            self.tableSample.setRowCount(3)
        self.tableSample.setObjectName(u"tableSample")
        self.tableSample.setEnabled(True)
        self.tableSample.setStyleSheet(u"QTableWidget {\n"
"    background-color: #101820;\n"
"    alternate-background-color: #182030;\n"
"    color: #E0E0E0;\n"
"    gridline-color: #2E7EF9;\n"
"    selection-background-color: #2E7EF9;\n"
"    selection-color: #FFFFFF;\n"
"}")
        self.tableSample.setAlternatingRowColors(True)
        self.tableSample.setRowCount(3)
        self.tableSample.setColumnCount(3)

        self.verticalLayout.addWidget(self.tableSample)

        self.progressSample = QProgressBar(LGE05StyleTester)
        self.progressSample.setObjectName(u"progressSample")
        self.progressSample.setStyleSheet(u"QProgressBar {\n"
"    border: 1px solid #2E7EF9;\n"
"    border-radius: 5px;\n"
"    background-color: rgba(255, 255, 255, 30);\n"
"    height: 12px;\n"
"}\n"
"QProgressBar::chunk {\n"
"    background-color: #2E7EF9;\n"
"    border-radius: 5px;\n"
"}")
        self.progressSample.setValue(50)

        self.verticalLayout.addWidget(self.progressSample)


        self.retranslateUi(LGE05StyleTester)

        QMetaObject.connectSlotsByName(LGE05StyleTester)
    # setupUi

    def retranslateUi(self, LGE05StyleTester):
        LGE05StyleTester.setWindowTitle(QCoreApplication.translate("LGE05StyleTester", u"LGE05 Style Tester", None))
        self.lblTitle.setText(QCoreApplication.translate("LGE05StyleTester", u"LGE05 Style Test", None))
        self.editSample.setPlaceholderText(QCoreApplication.translate("LGE05StyleTester", u"Type something...", None))
        self.btnTest.setText(QCoreApplication.translate("LGE05StyleTester", u"Test Button", None))
        self.comboSample.setItemText(0, QCoreApplication.translate("LGE05StyleTester", u"Option 1", None))
        self.comboSample.setItemText(1, QCoreApplication.translate("LGE05StyleTester", u"Option 2", None))

    # retranslateUi

