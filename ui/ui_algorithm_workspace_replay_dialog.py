# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'algorithm_workspace_replay_dialog.ui'
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
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDateTimeEdit,
    QDialog, QDoubleSpinBox, QFormLayout, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSizePolicy, QSpacerItem, QVBoxLayout,
    QWidget)

class Ui_AlgorithmWorkspaceReplayDialog(object):
    def setupUi(self, AlgorithmWorkspaceReplayDialog):
        if not AlgorithmWorkspaceReplayDialog.objectName():
            AlgorithmWorkspaceReplayDialog.setObjectName(u"AlgorithmWorkspaceReplayDialog")
        AlgorithmWorkspaceReplayDialog.resize(620, 610)
        AlgorithmWorkspaceReplayDialog.setMinimumSize(QSize(560, 560))
        self.verticalLayout = QVBoxLayout(AlgorithmWorkspaceReplayDialog)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.lblWorkspace = QLabel(AlgorithmWorkspaceReplayDialog)
        self.lblWorkspace.setObjectName(u"lblWorkspace")
        self.lblWorkspace.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblWorkspace)

        self.grpSource = QGroupBox(AlgorithmWorkspaceReplayDialog)
        self.grpSource.setObjectName(u"grpSource")
        self.formLayoutSource = QFormLayout(self.grpSource)
        self.formLayoutSource.setObjectName(u"formLayoutSource")
        self.lblSourceType = QLabel(self.grpSource)
        self.lblSourceType.setObjectName(u"lblSourceType")

        self.formLayoutSource.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblSourceType)

        self.cmbSourceType = QComboBox(self.grpSource)
        self.cmbSourceType.setObjectName(u"cmbSourceType")

        self.formLayoutSource.setWidget(0, QFormLayout.ItemRole.FieldRole, self.cmbSourceType)

        self.lblSourceName = QLabel(self.grpSource)
        self.lblSourceName.setObjectName(u"lblSourceName")

        self.formLayoutSource.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblSourceName)

        self.edtSourceName = QLineEdit(self.grpSource)
        self.edtSourceName.setObjectName(u"edtSourceName")

        self.formLayoutSource.setWidget(1, QFormLayout.ItemRole.FieldRole, self.edtSourceName)

        self.lblFilePath = QLabel(self.grpSource)
        self.lblFilePath.setObjectName(u"lblFilePath")

        self.formLayoutSource.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblFilePath)

        self.horizontalLayoutFile = QHBoxLayout()
        self.horizontalLayoutFile.setObjectName(u"horizontalLayoutFile")
        self.edtFilePath = QLineEdit(self.grpSource)
        self.edtFilePath.setObjectName(u"edtFilePath")

        self.horizontalLayoutFile.addWidget(self.edtFilePath)

        self.btnBrowse = QPushButton(self.grpSource)
        self.btnBrowse.setObjectName(u"btnBrowse")

        self.horizontalLayoutFile.addWidget(self.btnBrowse)


        self.formLayoutSource.setLayout(2, QFormLayout.ItemRole.FieldRole, self.horizontalLayoutFile)


        self.verticalLayout.addWidget(self.grpSource)

        self.grpRange = QGroupBox(AlgorithmWorkspaceReplayDialog)
        self.grpRange.setObjectName(u"grpRange")
        self.gridLayoutRange = QGridLayout(self.grpRange)
        self.gridLayoutRange.setObjectName(u"gridLayoutRange")
        self.chkStartEnabled = QCheckBox(self.grpRange)
        self.chkStartEnabled.setObjectName(u"chkStartEnabled")

        self.gridLayoutRange.addWidget(self.chkStartEnabled, 0, 0, 1, 1)

        self.dtStartUtc = QDateTimeEdit(self.grpRange)
        self.dtStartUtc.setObjectName(u"dtStartUtc")
        self.dtStartUtc.setCalendarPopup(True)

        self.gridLayoutRange.addWidget(self.dtStartUtc, 0, 1, 1, 1)

        self.chkEndEnabled = QCheckBox(self.grpRange)
        self.chkEndEnabled.setObjectName(u"chkEndEnabled")

        self.gridLayoutRange.addWidget(self.chkEndEnabled, 1, 0, 1, 1)

        self.dtEndUtc = QDateTimeEdit(self.grpRange)
        self.dtEndUtc.setObjectName(u"dtEndUtc")
        self.dtEndUtc.setCalendarPopup(True)

        self.gridLayoutRange.addWidget(self.dtEndUtc, 1, 1, 1, 1)

        self.lblSourceTimezone = QLabel(self.grpRange)
        self.lblSourceTimezone.setObjectName(u"lblSourceTimezone")

        self.gridLayoutRange.addWidget(self.lblSourceTimezone, 2, 0, 1, 1)

        self.cmbSourceTimezone = QComboBox(self.grpRange)
        self.cmbSourceTimezone.setObjectName(u"cmbSourceTimezone")
        self.cmbSourceTimezone.setEditable(True)

        self.gridLayoutRange.addWidget(self.cmbSourceTimezone, 2, 1, 1, 1)


        self.verticalLayout.addWidget(self.grpRange)

        self.grpCsv = QGroupBox(AlgorithmWorkspaceReplayDialog)
        self.grpCsv.setObjectName(u"grpCsv")
        self.formLayoutCsv = QFormLayout(self.grpCsv)
        self.formLayoutCsv.setObjectName(u"formLayoutCsv")
        self.lblSourceTimeframe = QLabel(self.grpCsv)
        self.lblSourceTimeframe.setObjectName(u"lblSourceTimeframe")

        self.formLayoutCsv.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblSourceTimeframe)

        self.cmbSourceTimeframe = QComboBox(self.grpCsv)
        self.cmbSourceTimeframe.setObjectName(u"cmbSourceTimeframe")

        self.formLayoutCsv.setWidget(0, QFormLayout.ItemRole.FieldRole, self.cmbSourceTimeframe)

        self.lblDelimiter = QLabel(self.grpCsv)
        self.lblDelimiter.setObjectName(u"lblDelimiter")

        self.formLayoutCsv.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblDelimiter)

        self.cmbDelimiter = QComboBox(self.grpCsv)
        self.cmbDelimiter.setObjectName(u"cmbDelimiter")

        self.formLayoutCsv.setWidget(1, QFormLayout.ItemRole.FieldRole, self.cmbDelimiter)

        self.lblDecimalSeparator = QLabel(self.grpCsv)
        self.lblDecimalSeparator.setObjectName(u"lblDecimalSeparator")

        self.formLayoutCsv.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblDecimalSeparator)

        self.cmbDecimalSeparator = QComboBox(self.grpCsv)
        self.cmbDecimalSeparator.setObjectName(u"cmbDecimalSeparator")

        self.formLayoutCsv.setWidget(2, QFormLayout.ItemRole.FieldRole, self.cmbDecimalSeparator)

        self.lblSpread = QLabel(self.grpCsv)
        self.lblSpread.setObjectName(u"lblSpread")

        self.formLayoutCsv.setWidget(3, QFormLayout.ItemRole.LabelRole, self.lblSpread)

        self.spnSpread = QDoubleSpinBox(self.grpCsv)
        self.spnSpread.setObjectName(u"spnSpread")
        self.spnSpread.setKeyboardTracking(False)
        self.spnSpread.setDecimals(8)
        self.spnSpread.setMaximum(1000000.000000000000000)
        self.spnSpread.setSingleStep(0.000010000000000)

        self.formLayoutCsv.setWidget(3, QFormLayout.ItemRole.FieldRole, self.spnSpread)


        self.verticalLayout.addWidget(self.grpCsv)

        self.grpAccount = QGroupBox(AlgorithmWorkspaceReplayDialog)
        self.grpAccount.setObjectName(u"grpAccount")
        self.formLayoutAccount = QFormLayout(self.grpAccount)
        self.formLayoutAccount.setObjectName(u"formLayoutAccount")
        self.lblInitialBalance = QLabel(self.grpAccount)
        self.lblInitialBalance.setObjectName(u"lblInitialBalance")

        self.formLayoutAccount.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblInitialBalance)

        self.spnInitialBalance = QDoubleSpinBox(self.grpAccount)
        self.spnInitialBalance.setObjectName(u"spnInitialBalance")
        self.spnInitialBalance.setKeyboardTracking(False)
        self.spnInitialBalance.setDecimals(2)
        self.spnInitialBalance.setMinimum(100.000000000000000)
        self.spnInitialBalance.setMaximum(100000.000000000000000)
        self.spnInitialBalance.setSingleStep(100.000000000000000)
        self.spnInitialBalance.setValue(1000.000000000000000)

        self.formLayoutAccount.setWidget(0, QFormLayout.ItemRole.FieldRole, self.spnInitialBalance)

        self.lblAccountNote = QLabel(self.grpAccount)
        self.lblAccountNote.setObjectName(u"lblAccountNote")
        self.lblAccountNote.setWordWrap(True)

        self.formLayoutAccount.setWidget(1, QFormLayout.ItemRole.SpanningRole, self.lblAccountNote)


        self.verticalLayout.addWidget(self.grpAccount)

        self.lblNote = QLabel(AlgorithmWorkspaceReplayDialog)
        self.lblNote.setObjectName(u"lblNote")
        self.lblNote.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblNote)

        self.verticalSpacer = QSpacerItem(20, 16, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout.addItem(self.verticalSpacer)

        self.horizontalLayoutButtons = QHBoxLayout()
        self.horizontalLayoutButtons.setObjectName(u"horizontalLayoutButtons")
        self.horizontalSpacerButtons = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutButtons.addItem(self.horizontalSpacerButtons)

        self.btnSave = QPushButton(AlgorithmWorkspaceReplayDialog)
        self.btnSave.setObjectName(u"btnSave")

        self.horizontalLayoutButtons.addWidget(self.btnSave)

        self.btnCancel = QPushButton(AlgorithmWorkspaceReplayDialog)
        self.btnCancel.setObjectName(u"btnCancel")

        self.horizontalLayoutButtons.addWidget(self.btnCancel)


        self.verticalLayout.addLayout(self.horizontalLayoutButtons)


        self.retranslateUi(AlgorithmWorkspaceReplayDialog)

        self.btnSave.setDefault(True)


        QMetaObject.connectSlotsByName(AlgorithmWorkspaceReplayDialog)
    # setupUi

    def retranslateUi(self, AlgorithmWorkspaceReplayDialog):
        AlgorithmWorkspaceReplayDialog.setWindowTitle(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.windowTitle]", None))
        self.lblWorkspace.setText(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.workspace]", None))
        self.grpSource.setTitle(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.grpSource]", None))
        self.lblSourceType.setText(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.lblSourceType]", None))
        self.lblSourceName.setText(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.lblSourceName]", None))
        self.lblFilePath.setText(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.lblFilePath]", None))
        self.btnBrowse.setText(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.btnBrowse]", None))
        self.grpRange.setTitle(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.grpRange]", None))
        self.chkStartEnabled.setText(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.chkStartEnabled]", None))
        self.dtStartUtc.setDisplayFormat(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"yyyy-MM-dd HH:mm:ss", None))
        self.chkEndEnabled.setText(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.chkEndEnabled]", None))
        self.dtEndUtc.setDisplayFormat(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"yyyy-MM-dd HH:mm:ss", None))
        self.lblSourceTimezone.setText(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.lblSourceTimezone]", None))
        self.grpCsv.setTitle(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.grpCsv]", None))
        self.lblSourceTimeframe.setText(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.lblSourceTimeframe]", None))
        self.lblDelimiter.setText(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.lblDelimiter]", None))
        self.lblDecimalSeparator.setText(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.lblDecimalSeparator]", None))
        self.lblSpread.setText(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.lblSpread]", None))
        self.grpAccount.setTitle(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.grpAccount]", None))
        self.lblInitialBalance.setText(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.lblInitialBalance]", None))
        self.lblAccountNote.setText(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.accountNote]", None))
        self.lblNote.setText(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.note]", None))
        self.btnSave.setText(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.btnSave]", None))
        self.btnCancel.setText(QCoreApplication.translate("AlgorithmWorkspaceReplayDialog", u"[AlgorithmWorkspaceReplayDialog.btnCancel]", None))
    # retranslateUi

