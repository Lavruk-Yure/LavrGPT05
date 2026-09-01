# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'settings_page_translator.ui'
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
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
import resources_rc


class Ui_pageTranslator(object):
    def setupUi(self, pageTranslator):
        if not pageTranslator.objectName():
            pageTranslator.setObjectName("pageTranslator")
        pageTranslator.resize(482, 300)
        sizePolicy = QSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(pageTranslator.sizePolicy().hasHeightForWidth())
        pageTranslator.setSizePolicy(sizePolicy)
        icon = QIcon()
        icon.addFile(
            ":/icons/lge_perplexity2_24x24.png",
            QSize(),
            QIcon.Mode.Normal,
            QIcon.State.Off,
        )
        pageTranslator.setWindowIcon(icon)
        self.verticalLayout = QVBoxLayout(pageTranslator)
        self.verticalLayout.setObjectName("verticalLayout")
        self.lblHeader = QLabel(pageTranslator)
        self.lblHeader.setObjectName("lblHeader")
        sizePolicy1 = QSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.lblHeader.sizePolicy().hasHeightForWidth())
        self.lblHeader.setSizePolicy(sizePolicy1)
        self.lblHeader.setMinimumSize(QSize(200, 30))
        self.lblHeader.setMaximumSize(QSize(400, 60))
        self.lblHeader.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.verticalLayout.addWidget(self.lblHeader)

        self.comboProvider = QComboBox(pageTranslator)
        self.comboProvider.setObjectName("comboProvider")
        sizePolicy2 = QSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(
            self.comboProvider.sizePolicy().hasHeightForWidth()
        )
        self.comboProvider.setSizePolicy(sizePolicy2)
        self.comboProvider.setMinimumSize(QSize(200, 30))
        self.comboProvider.setMaximumSize(QSize(400, 16777215))
        self.comboProvider.setStyleSheet(
            "QComboBox QAbstractItemView::item:selected {\n"
            "                background: rgba(255,255,255,80);\n"
            "                color: #FFFFFF;\n"
            "            }\n"
            "QComboBox QAbstractItemView::item:hover {\n"
            "                background: rgba(255,255,255,50);\n"
            "            }\n"
            ""
        )

        self.verticalLayout.addWidget(self.comboProvider)

        self.editDeeplKey1 = QLineEdit(pageTranslator)
        self.editDeeplKey1.setObjectName("editDeeplKey1")
        self.editDeeplKey1.setMinimumSize(QSize(200, 0))
        self.editDeeplKey1.setMaximumSize(QSize(400, 16777215))
        self.editDeeplKey1.setEchoMode(QLineEdit.EchoMode.Password)

        self.verticalLayout.addWidget(self.editDeeplKey1)

        self.editDeeplKey2 = QLineEdit(pageTranslator)
        self.editDeeplKey2.setObjectName("editDeeplKey2")
        self.editDeeplKey2.setMinimumSize(QSize(200, 0))
        self.editDeeplKey2.setMaximumSize(QSize(400, 16777215))
        self.editDeeplKey2.setEchoMode(QLineEdit.EchoMode.Password)

        self.verticalLayout.addWidget(self.editDeeplKey2)

        self.lblDeeplHelp = QLabel(pageTranslator)
        self.lblDeeplHelp.setObjectName("lblDeeplHelp")
        sizePolicy3 = QSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(
            self.lblDeeplHelp.sizePolicy().hasHeightForWidth()
        )
        self.lblDeeplHelp.setSizePolicy(sizePolicy3)
        self.lblDeeplHelp.setMinimumSize(QSize(0, 30))
        self.lblDeeplHelp.setMaximumSize(QSize(16777215, 50))
        self.lblDeeplHelp.setAlignment(
            Qt.AlignmentFlag.AlignLeading
            | Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignTop
        )
        self.lblDeeplHelp.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblDeeplHelp)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.btnOK = QPushButton(pageTranslator)
        self.btnOK.setObjectName("btnOK")
        sizePolicy2.setHeightForWidth(self.btnOK.sizePolicy().hasHeightForWidth())
        self.btnOK.setSizePolicy(sizePolicy2)
        self.btnOK.setMinimumSize(QSize(100, 0))
        self.btnOK.setMaximumSize(QSize(100, 16777215))

        self.horizontalLayout.addWidget(self.btnOK)

        self.btnApply = QPushButton(pageTranslator)
        self.btnApply.setObjectName("btnApply")
        sizePolicy2.setHeightForWidth(self.btnApply.sizePolicy().hasHeightForWidth())
        self.btnApply.setSizePolicy(sizePolicy2)
        self.btnApply.setMinimumSize(QSize(100, 0))
        self.btnApply.setMaximumSize(QSize(100, 16777215))

        self.horizontalLayout.addWidget(self.btnApply)

        self.btnCancel = QPushButton(pageTranslator)
        self.btnCancel.setObjectName("btnCancel")
        sizePolicy2.setHeightForWidth(self.btnCancel.sizePolicy().hasHeightForWidth())
        self.btnCancel.setSizePolicy(sizePolicy2)
        self.btnCancel.setMinimumSize(QSize(100, 0))
        self.btnCancel.setMaximumSize(QSize(100, 16777215))

        self.horizontalLayout.addWidget(self.btnCancel)

        self.verticalLayout.addLayout(self.horizontalLayout)

        self.verticalLayout.setStretch(5, 1)

        self.retranslateUi(pageTranslator)

        QMetaObject.connectSlotsByName(pageTranslator)

    # setupUi

    def retranslateUi(self, pageTranslator):
        pageTranslator.setWindowTitle(
            QCoreApplication.translate("pageTranslator", "Form", None)
        )
        self.lblHeader.setText(
            QCoreApplication.translate(
                "pageTranslator", "[SettingsPageTranslator.header]", None
            )
        )
        self.comboProvider.setPlaceholderText(
            QCoreApplication.translate(
                "pageTranslator", "[SettingsPageTranslator.lblProvider]", None
            )
        )
        self.editDeeplKey1.setPlaceholderText(
            QCoreApplication.translate(
                "pageTranslator", "[SettingsPageTranslator.lblDeeplKey1]", None
            )
        )
        self.editDeeplKey2.setPlaceholderText(
            QCoreApplication.translate(
                "pageTranslator", "[SettingsPageTranslator.lblDeeplKey2]", None
            )
        )
        self.lblDeeplHelp.setText(
            QCoreApplication.translate(
                "pageTranslator", "[SettingsPageTranslator.lblDeeplHelp]", None
            )
        )
        self.btnOK.setText(
            QCoreApplication.translate(
                "pageTranslator", "[SettingsPageTranslator.btnOK]", None
            )
        )
        self.btnApply.setText(
            QCoreApplication.translate(
                "pageTranslator", "[SettingsPageTranslator.btnApply]", None
            )
        )
        self.btnCancel.setText(
            QCoreApplication.translate(
                "pageTranslator", "[SettingsPageTranslator.btnCancel]", None
            )
        )

    # retranslateUi
