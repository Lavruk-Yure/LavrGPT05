# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'algorithm_workspace_card.ui'
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
from PySide6.QtWidgets import (QApplication, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QPushButton, QSizePolicy, QSpacerItem,
    QVBoxLayout, QWidget)

class Ui_AlgorithmWorkspaceCard(object):
    def setupUi(self, AlgorithmWorkspaceCard):
        if not AlgorithmWorkspaceCard.objectName():
            AlgorithmWorkspaceCard.setObjectName(u"AlgorithmWorkspaceCard")
        AlgorithmWorkspaceCard.resize(700, 430)
        AlgorithmWorkspaceCard.setFrameShape(QFrame.Shape.StyledPanel)
        self.verticalLayout = QVBoxLayout(AlgorithmWorkspaceCard)
        self.verticalLayout.setSpacing(14)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(18, 18, 18, 18)
        self.horizontalLayoutHeader = QHBoxLayout()
        self.horizontalLayoutHeader.setObjectName(u"horizontalLayoutHeader")
        self.lblName = QLabel(AlgorithmWorkspaceCard)
        self.lblName.setObjectName(u"lblName")
        self.lblName.setStyleSheet(u"font: 700 14pt \"Segoe UI\";\n"
"color: #ffffff;")

        self.horizontalLayoutHeader.addWidget(self.lblName)

        self.horizontalSpacerHeader = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutHeader.addItem(self.horizontalSpacerHeader)

        self.lblState = QLabel(AlgorithmWorkspaceCard)
        self.lblState.setObjectName(u"lblState")
        self.lblState.setMinimumSize(QSize(110, 0))
        self.lblState.setStyleSheet(u"background-color: #2d3b42;\n"
"color: #d7edf1;\n"
"border-radius: 6px;\n"
"padding: 5px 10px;\n"
"font-weight: 600;")
        self.lblState.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.horizontalLayoutHeader.addWidget(self.lblState)

        self.btnRename = QPushButton(AlgorithmWorkspaceCard)
        self.btnRename.setObjectName(u"btnRename")

        self.horizontalLayoutHeader.addWidget(self.btnRename)


        self.verticalLayout.addLayout(self.horizontalLayoutHeader)

        self.formLayout = QFormLayout()
        self.formLayout.setObjectName(u"formLayout")
        self.formLayout.setLabelAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)
        self.formLayout.setHorizontalSpacing(18)
        self.formLayout.setVerticalSpacing(10)
        self.lblBrokerCaption = QLabel(AlgorithmWorkspaceCard)
        self.lblBrokerCaption.setObjectName(u"lblBrokerCaption")

        self.formLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblBrokerCaption)

        self.lblBroker = QLabel(AlgorithmWorkspaceCard)
        self.lblBroker.setObjectName(u"lblBroker")

        self.formLayout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.lblBroker)

        self.lblAccountCaption = QLabel(AlgorithmWorkspaceCard)
        self.lblAccountCaption.setObjectName(u"lblAccountCaption")

        self.formLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblAccountCaption)

        self.lblAccount = QLabel(AlgorithmWorkspaceCard)
        self.lblAccount.setObjectName(u"lblAccount")

        self.formLayout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.lblAccount)

        self.lblSymbolCaption = QLabel(AlgorithmWorkspaceCard)
        self.lblSymbolCaption.setObjectName(u"lblSymbolCaption")

        self.formLayout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblSymbolCaption)

        self.lblSymbol = QLabel(AlgorithmWorkspaceCard)
        self.lblSymbol.setObjectName(u"lblSymbol")

        self.formLayout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.lblSymbol)

        self.lblTimeframeCaption = QLabel(AlgorithmWorkspaceCard)
        self.lblTimeframeCaption.setObjectName(u"lblTimeframeCaption")

        self.formLayout.setWidget(3, QFormLayout.ItemRole.LabelRole, self.lblTimeframeCaption)

        self.lblTimeframe = QLabel(AlgorithmWorkspaceCard)
        self.lblTimeframe.setObjectName(u"lblTimeframe")

        self.formLayout.setWidget(3, QFormLayout.ItemRole.FieldRole, self.lblTimeframe)

        self.lblAlgorithmCaption = QLabel(AlgorithmWorkspaceCard)
        self.lblAlgorithmCaption.setObjectName(u"lblAlgorithmCaption")

        self.formLayout.setWidget(4, QFormLayout.ItemRole.LabelRole, self.lblAlgorithmCaption)

        self.lblAlgorithm = QLabel(AlgorithmWorkspaceCard)
        self.lblAlgorithm.setObjectName(u"lblAlgorithm")

        self.formLayout.setWidget(4, QFormLayout.ItemRole.FieldRole, self.lblAlgorithm)

        self.lblUidCaption = QLabel(AlgorithmWorkspaceCard)
        self.lblUidCaption.setObjectName(u"lblUidCaption")

        self.formLayout.setWidget(5, QFormLayout.ItemRole.LabelRole, self.lblUidCaption)

        self.lblUid = QLabel(AlgorithmWorkspaceCard)
        self.lblUid.setObjectName(u"lblUid")
        self.lblUid.setStyleSheet(u"color: #a7cbd2;")
        self.lblUid.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.formLayout.setWidget(5, QFormLayout.ItemRole.FieldRole, self.lblUid)


        self.verticalLayout.addLayout(self.formLayout)

        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout.addItem(self.verticalSpacer)


        self.retranslateUi(AlgorithmWorkspaceCard)

        QMetaObject.connectSlotsByName(AlgorithmWorkspaceCard)
    # setupUi

    def retranslateUi(self, AlgorithmWorkspaceCard):
        self.lblName.setText(QCoreApplication.translate("AlgorithmWorkspaceCard", u"Workspace", None))
        self.lblState.setText(QCoreApplication.translate("AlgorithmWorkspaceCard", u"STOPPED", None))
        self.btnRename.setText(QCoreApplication.translate("AlgorithmWorkspaceCard", u"[AlgorithmWorkspaceCard.btnRename]", None))
        self.lblBrokerCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceCard", u"[AlgorithmWorkspaceCard.lblBroker]", None))
        self.lblBroker.setText(QCoreApplication.translate("AlgorithmWorkspaceCard", u"\u2014", None))
        self.lblAccountCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceCard", u"[AlgorithmWorkspaceCard.lblAccount]", None))
        self.lblAccount.setText(QCoreApplication.translate("AlgorithmWorkspaceCard", u"\u2014", None))
        self.lblSymbolCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceCard", u"[AlgorithmWorkspaceCard.lblSymbol]", None))
        self.lblSymbol.setText(QCoreApplication.translate("AlgorithmWorkspaceCard", u"\u2014", None))
        self.lblTimeframeCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceCard", u"[AlgorithmWorkspaceCard.lblTimeframe]", None))
        self.lblTimeframe.setText(QCoreApplication.translate("AlgorithmWorkspaceCard", u"\u2014", None))
        self.lblAlgorithmCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceCard", u"[AlgorithmWorkspaceCard.lblAlgorithm]", None))
        self.lblAlgorithm.setText(QCoreApplication.translate("AlgorithmWorkspaceCard", u"\u2014", None))
        self.lblUidCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceCard", u"[AlgorithmWorkspaceCard.lblUid]", None))
        self.lblUid.setText(QCoreApplication.translate("AlgorithmWorkspaceCard", u"\u2014", None))
        pass
    # retranslateUi

