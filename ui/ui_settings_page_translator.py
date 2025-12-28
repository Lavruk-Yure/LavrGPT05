# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'settings_page_translator.ui'
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
from PySide6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSizePolicy, QVBoxLayout,
    QWidget)
import resources_rc

class Ui_pageTranslator(object):
    def setupUi(self, pageTranslator):
        if not pageTranslator.objectName():
            pageTranslator.setObjectName(u"pageTranslator")
        pageTranslator.resize(600, 300)
        icon = QIcon()
        icon.addFile(u":/icons/lge_perplexity2_24x24.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        pageTranslator.setWindowIcon(icon)
        self.verticalLayout = QVBoxLayout(pageTranslator)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.lblHeader = QLabel(pageTranslator)
        self.lblHeader.setObjectName(u"lblHeader")
        self.lblHeader.setMinimumSize(QSize(200, 0))
        self.lblHeader.setMaximumSize(QSize(400, 16777215))

        self.verticalLayout.addWidget(self.lblHeader)

        self.comboProvider = QComboBox(pageTranslator)
        self.comboProvider.setObjectName(u"comboProvider")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.comboProvider.sizePolicy().hasHeightForWidth())
        self.comboProvider.setSizePolicy(sizePolicy)
        self.comboProvider.setMinimumSize(QSize(200, 30))
        self.comboProvider.setMaximumSize(QSize(400, 16777215))
        self.comboProvider.setStyleSheet(u"/* ===== \u0411\u0410\u0417\u041e\u0412\u0418\u0419 \u0421\u0422\u0410\u041d (\u043d\u0456\u0447\u043e\u0433\u043e \u043d\u0435 \u0441\u0432\u0456\u0442\u0438\u0442\u044c\u0441\u044f) ===== */\n"
"QComboBox {\n"
"    background-color: #227685;\n"
"    color: white;\n"
"    border: 1px solid #173A47;\n"
"    border-radius: 6px;\n"
"    padding: 4px 8px;\n"
"}\n"
"\n"
"/* ===== \u0417\u0410\u0411\u041e\u0420\u041e\u041d\u0410 \u0431\u0443\u0434\u044c-\u044f\u043a\u043e\u0433\u043e \u043f\u0456\u0434\u0441\u0432\u0456\u0447\u0443\u0432\u0430\u043d\u043d\u044f ===== */\n"
"QComboBox:hover,\n"
"QComboBox:focus,\n"
"QComboBox:pressed {\n"
"    background-color: #227685;\n"
"    color: white;\n"
"    border: 1px solid #173A47;\n"
"}\n"
"\n"
"/* ===== \u041a\u041d\u041e\u041f\u041a\u0410 \u0421\u0422\u0420\u0406\u041b\u041a\u0418 ===== */\n"
"QComboBox::drop-down {\n"
"    border: none;\n"
"    width: 22px;\n"
"}\n"
"\n"
"/* ===== \u0412\u0418\u041f\u0410\u0414\u0410\u042e\u0427\u0418\u0419 \u0421\u041f\u0418\u0421\u041e"
                        "\u041a ===== */\n"
"QComboBox QAbstractItemView {\n"
"    background-color: #173A47;\n"
"    color: white;\n"
"    selection-background-color: #1E5FD0;\n"
"    selection-color: white;\n"
"    outline: 0;\n"
"}\n"
"\n"
"/* ===== \u0420\u042f\u0414\u041a\u0418 \u0421\u041f\u0418\u0421\u041a\u0423 ===== */\n"
"QComboBox QAbstractItemView::item {\n"
"    padding: 6px 10px;\n"
"}\n"
"\n"
"/* ===== \u041f\u0406\u0414\u0421\u0412\u0406\u0422\u041a\u0410 \u0422\u0406\u041b\u042c\u041a\u0418 \u0412 \u0421\u041f\u0418\u0421\u041a\u0423 ===== */\n"
"QComboBox QAbstractItemView::item:hover {\n"
"    background-color: #1E5FD0;\n"
"}\n"
"")

        self.verticalLayout.addWidget(self.comboProvider)

        self.editDeeplKey1 = QLineEdit(pageTranslator)
        self.editDeeplKey1.setObjectName(u"editDeeplKey1")
        self.editDeeplKey1.setMinimumSize(QSize(200, 0))
        self.editDeeplKey1.setMaximumSize(QSize(400, 16777215))
        self.editDeeplKey1.setEchoMode(QLineEdit.EchoMode.Password)

        self.verticalLayout.addWidget(self.editDeeplKey1)

        self.editDeeplKey2 = QLineEdit(pageTranslator)
        self.editDeeplKey2.setObjectName(u"editDeeplKey2")
        self.editDeeplKey2.setMinimumSize(QSize(200, 0))
        self.editDeeplKey2.setMaximumSize(QSize(400, 16777215))
        self.editDeeplKey2.setEchoMode(QLineEdit.EchoMode.Password)

        self.verticalLayout.addWidget(self.editDeeplKey2)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.btnOK = QPushButton(pageTranslator)
        self.btnOK.setObjectName(u"btnOK")
        sizePolicy.setHeightForWidth(self.btnOK.sizePolicy().hasHeightForWidth())
        self.btnOK.setSizePolicy(sizePolicy)
        self.btnOK.setMinimumSize(QSize(100, 0))
        self.btnOK.setMaximumSize(QSize(100, 16777215))

        self.horizontalLayout.addWidget(self.btnOK)

        self.btnApply = QPushButton(pageTranslator)
        self.btnApply.setObjectName(u"btnApply")
        sizePolicy.setHeightForWidth(self.btnApply.sizePolicy().hasHeightForWidth())
        self.btnApply.setSizePolicy(sizePolicy)
        self.btnApply.setMinimumSize(QSize(100, 0))
        self.btnApply.setMaximumSize(QSize(100, 16777215))

        self.horizontalLayout.addWidget(self.btnApply)

        self.btnCancel = QPushButton(pageTranslator)
        self.btnCancel.setObjectName(u"btnCancel")
        sizePolicy.setHeightForWidth(self.btnCancel.sizePolicy().hasHeightForWidth())
        self.btnCancel.setSizePolicy(sizePolicy)
        self.btnCancel.setMinimumSize(QSize(100, 0))
        self.btnCancel.setMaximumSize(QSize(100, 16777215))

        self.horizontalLayout.addWidget(self.btnCancel)


        self.verticalLayout.addLayout(self.horizontalLayout)


        self.retranslateUi(pageTranslator)

        QMetaObject.connectSlotsByName(pageTranslator)
    # setupUi

    def retranslateUi(self, pageTranslator):
        pageTranslator.setWindowTitle(QCoreApplication.translate("pageTranslator", u"Form", None))
        self.lblHeader.setText(QCoreApplication.translate("pageTranslator", u"[SettingsPageTranslator.header]", None))
        self.comboProvider.setPlaceholderText(QCoreApplication.translate("pageTranslator", u"[SettingsPageTranslator.lblProvider]", None))
        self.editDeeplKey1.setPlaceholderText(QCoreApplication.translate("pageTranslator", u"[SettingsPageTranslator.lblDeeplKey1]", None))
        self.editDeeplKey2.setPlaceholderText(QCoreApplication.translate("pageTranslator", u"[SettingsPageTranslator.lblDeeplKey2]", None))
        self.btnOK.setText(QCoreApplication.translate("pageTranslator", u"[SettingsPageTranslator.btnOK]", None))
        self.btnApply.setText(QCoreApplication.translate("pageTranslator", u"[SettingsPageTranslator.btnApply]", None))
        self.btnCancel.setText(QCoreApplication.translate("pageTranslator", u"[SettingsPageTranslator.btnCancel]", None))
    # retranslateUi

