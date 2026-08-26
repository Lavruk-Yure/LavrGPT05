# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'algorithm_workspace_create_dialog.ui'
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
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QSpacerItem, QVBoxLayout, QWidget)

class Ui_AlgorithmWorkspaceCreateDialog(object):
    def setupUi(self, AlgorithmWorkspaceCreateDialog):
        if not AlgorithmWorkspaceCreateDialog.objectName():
            AlgorithmWorkspaceCreateDialog.setObjectName(u"AlgorithmWorkspaceCreateDialog")
        AlgorithmWorkspaceCreateDialog.resize(600, 430)
        AlgorithmWorkspaceCreateDialog.setModal(True)
        self.verticalLayout = QVBoxLayout(AlgorithmWorkspaceCreateDialog)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.formLayout = QFormLayout()
        self.formLayout.setObjectName(u"formLayout")
        self.formLayout.setLabelAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)
        self.formLayout.setHorizontalSpacing(12)
        self.formLayout.setVerticalSpacing(10)
        self.lblDisplayName = QLabel(AlgorithmWorkspaceCreateDialog)
        self.lblDisplayName.setObjectName(u"lblDisplayName")

        self.formLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblDisplayName)

        self.edtDisplayName = QLineEdit(AlgorithmWorkspaceCreateDialog)
        self.edtDisplayName.setObjectName(u"edtDisplayName")

        self.formLayout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.edtDisplayName)

        self.lblBroker = QLabel(AlgorithmWorkspaceCreateDialog)
        self.lblBroker.setObjectName(u"lblBroker")

        self.formLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblBroker)

        self.cmbBroker = QComboBox(AlgorithmWorkspaceCreateDialog)
        self.cmbBroker.setObjectName(u"cmbBroker")

        self.formLayout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.cmbBroker)

        self.lblAccount = QLabel(AlgorithmWorkspaceCreateDialog)
        self.lblAccount.setObjectName(u"lblAccount")

        self.formLayout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblAccount)

        self.accountRow = QWidget(AlgorithmWorkspaceCreateDialog)
        self.accountRow.setObjectName(u"accountRow")
        self.horizontalLayoutAccount = QHBoxLayout(self.accountRow)
        self.horizontalLayoutAccount.setObjectName(u"horizontalLayoutAccount")
        self.horizontalLayoutAccount.setContentsMargins(0, 0, 0, 0)
        self.cmbAccount = QComboBox(self.accountRow)
        self.cmbAccount.setObjectName(u"cmbAccount")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.cmbAccount.sizePolicy().hasHeightForWidth())
        self.cmbAccount.setSizePolicy(sizePolicy)

        self.horizontalLayoutAccount.addWidget(self.cmbAccount)

        self.lblAccountMode = QLabel(self.accountRow)
        self.lblAccountMode.setObjectName(u"lblAccountMode")

        self.horizontalLayoutAccount.addWidget(self.lblAccountMode)

        self.lblAccountModeValue = QLabel(self.accountRow)
        self.lblAccountModeValue.setObjectName(u"lblAccountModeValue")
        self.lblAccountModeValue.setMinimumSize(QSize(92, 0))

        self.horizontalLayoutAccount.addWidget(self.lblAccountModeValue)


        self.formLayout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.accountRow)

        self.lblSymbol = QLabel(AlgorithmWorkspaceCreateDialog)
        self.lblSymbol.setObjectName(u"lblSymbol")

        self.formLayout.setWidget(3, QFormLayout.ItemRole.LabelRole, self.lblSymbol)

        self.cmbSymbol = QComboBox(AlgorithmWorkspaceCreateDialog)
        self.cmbSymbol.setObjectName(u"cmbSymbol")

        self.formLayout.setWidget(3, QFormLayout.ItemRole.FieldRole, self.cmbSymbol)

        self.lblTimeframe = QLabel(AlgorithmWorkspaceCreateDialog)
        self.lblTimeframe.setObjectName(u"lblTimeframe")

        self.formLayout.setWidget(4, QFormLayout.ItemRole.LabelRole, self.lblTimeframe)

        self.cmbTimeframe = QComboBox(AlgorithmWorkspaceCreateDialog)
        self.cmbTimeframe.setObjectName(u"cmbTimeframe")

        self.formLayout.setWidget(4, QFormLayout.ItemRole.FieldRole, self.cmbTimeframe)

        self.lblAlgorithm = QLabel(AlgorithmWorkspaceCreateDialog)
        self.lblAlgorithm.setObjectName(u"lblAlgorithm")

        self.formLayout.setWidget(5, QFormLayout.ItemRole.LabelRole, self.lblAlgorithm)

        self.cmbAlgorithm = QComboBox(AlgorithmWorkspaceCreateDialog)
        self.cmbAlgorithm.setObjectName(u"cmbAlgorithm")

        self.formLayout.setWidget(5, QFormLayout.ItemRole.FieldRole, self.cmbAlgorithm)

        self.lblDataMode = QLabel(AlgorithmWorkspaceCreateDialog)
        self.lblDataMode.setObjectName(u"lblDataMode")

        self.formLayout.setWidget(6, QFormLayout.ItemRole.LabelRole, self.lblDataMode)

        self.cmbDataMode = QComboBox(AlgorithmWorkspaceCreateDialog)
        self.cmbDataMode.setObjectName(u"cmbDataMode")

        self.formLayout.setWidget(6, QFormLayout.ItemRole.FieldRole, self.cmbDataMode)

        self.lblControlMode = QLabel(AlgorithmWorkspaceCreateDialog)
        self.lblControlMode.setObjectName(u"lblControlMode")

        self.formLayout.setWidget(7, QFormLayout.ItemRole.LabelRole, self.lblControlMode)

        self.cmbControlMode = QComboBox(AlgorithmWorkspaceCreateDialog)
        self.cmbControlMode.setObjectName(u"cmbControlMode")

        self.formLayout.setWidget(7, QFormLayout.ItemRole.FieldRole, self.cmbControlMode)


        self.verticalLayout.addLayout(self.formLayout)

        self.lblNote = QLabel(AlgorithmWorkspaceCreateDialog)
        self.lblNote.setObjectName(u"lblNote")
        self.lblNote.setStyleSheet(u"color: #b7d6dc;\n"
"padding-top: 8px;")
        self.lblNote.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblNote)

        self.verticalSpacer = QSpacerItem(20, 18, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout.addItem(self.verticalSpacer)

        self.horizontalLayoutButtons = QHBoxLayout()
        self.horizontalLayoutButtons.setObjectName(u"horizontalLayoutButtons")
        self.horizontalSpacerButtons = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutButtons.addItem(self.horizontalSpacerButtons)

        self.btnCreate = QPushButton(AlgorithmWorkspaceCreateDialog)
        self.btnCreate.setObjectName(u"btnCreate")

        self.horizontalLayoutButtons.addWidget(self.btnCreate)

        self.btnCancel = QPushButton(AlgorithmWorkspaceCreateDialog)
        self.btnCancel.setObjectName(u"btnCancel")

        self.horizontalLayoutButtons.addWidget(self.btnCancel)


        self.verticalLayout.addLayout(self.horizontalLayoutButtons)


        self.retranslateUi(AlgorithmWorkspaceCreateDialog)

        self.btnCreate.setDefault(True)


        QMetaObject.connectSlotsByName(AlgorithmWorkspaceCreateDialog)
    # setupUi

    def retranslateUi(self, AlgorithmWorkspaceCreateDialog):
        AlgorithmWorkspaceCreateDialog.setWindowTitle(QCoreApplication.translate("AlgorithmWorkspaceCreateDialog", u"[AlgorithmWorkspaceCreateDialog.windowTitle]", None))
        self.lblDisplayName.setText(QCoreApplication.translate("AlgorithmWorkspaceCreateDialog", u"[AlgorithmWorkspaceCreateDialog.lblDisplayName]", None))
        self.edtDisplayName.setPlaceholderText(QCoreApplication.translate("AlgorithmWorkspaceCreateDialog", u"[AlgorithmWorkspaceCreateDialog.phDisplayName]", None))
        self.lblBroker.setText(QCoreApplication.translate("AlgorithmWorkspaceCreateDialog", u"[AlgorithmWorkspaceCreateDialog.lblBroker]", None))
        self.lblAccount.setText(QCoreApplication.translate("AlgorithmWorkspaceCreateDialog", u"[AlgorithmWorkspaceCreateDialog.lblAccount]", None))
        self.lblAccountMode.setText(QCoreApplication.translate("AlgorithmWorkspaceCreateDialog", u"[AlgorithmWorkspaceCreateDialog.lblAccountMode]", None))
        self.lblAccountModeValue.setText(QCoreApplication.translate("AlgorithmWorkspaceCreateDialog", u"\u2014", None))
        self.lblSymbol.setText(QCoreApplication.translate("AlgorithmWorkspaceCreateDialog", u"[AlgorithmWorkspaceCreateDialog.lblSymbol]", None))
        self.lblTimeframe.setText(QCoreApplication.translate("AlgorithmWorkspaceCreateDialog", u"[AlgorithmWorkspaceCreateDialog.lblTimeframe]", None))
        self.lblAlgorithm.setText(QCoreApplication.translate("AlgorithmWorkspaceCreateDialog", u"[AlgorithmWorkspaceCreateDialog.lblAlgorithm]", None))
        self.lblDataMode.setText(QCoreApplication.translate("AlgorithmWorkspaceCreateDialog", u"[AlgorithmWorkspaceCreateDialog.lblDataMode]", None))
        self.lblControlMode.setText(QCoreApplication.translate("AlgorithmWorkspaceCreateDialog", u"[AlgorithmWorkspaceCreateDialog.lblControlMode]", None))
        self.lblNote.setText(QCoreApplication.translate("AlgorithmWorkspaceCreateDialog", u"[AlgorithmWorkspaceCreateDialog.lblNote]", None))
        self.btnCreate.setText(QCoreApplication.translate("AlgorithmWorkspaceCreateDialog", u"[AlgorithmWorkspaceCreateDialog.btnCreate]", None))
        self.btnCancel.setText(QCoreApplication.translate("AlgorithmWorkspaceCreateDialog", u"[AlgorithmWorkspaceCreateDialog.btnCancel]", None))
    # retranslateUi

