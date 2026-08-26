# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'algorithm_workspace_history_download_dialog.ui'
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
from PySide6.QtWidgets import (QApplication, QComboBox, QDateEdit, QDialog,
    QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QProgressBar, QPushButton,
    QSizePolicy, QSpacerItem, QVBoxLayout, QWidget)

class Ui_AlgorithmWorkspaceHistoryDownloadDialog(object):
    def setupUi(self, AlgorithmWorkspaceHistoryDownloadDialog):
        if not AlgorithmWorkspaceHistoryDownloadDialog.objectName():
            AlgorithmWorkspaceHistoryDownloadDialog.setObjectName(u"AlgorithmWorkspaceHistoryDownloadDialog")
        AlgorithmWorkspaceHistoryDownloadDialog.resize(650, 520)
        AlgorithmWorkspaceHistoryDownloadDialog.setMinimumSize(QSize(590, 480))
        self.verticalLayout = QVBoxLayout(AlgorithmWorkspaceHistoryDownloadDialog)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.lblWorkspace = QLabel(AlgorithmWorkspaceHistoryDownloadDialog)
        self.lblWorkspace.setObjectName(u"lblWorkspace")
        self.lblWorkspace.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblWorkspace)

        self.grpBinding = QGroupBox(AlgorithmWorkspaceHistoryDownloadDialog)
        self.grpBinding.setObjectName(u"grpBinding")
        self.gridLayoutBinding = QGridLayout(self.grpBinding)
        self.gridLayoutBinding.setObjectName(u"gridLayoutBinding")
        self.lblBrokerCaption = QLabel(self.grpBinding)
        self.lblBrokerCaption.setObjectName(u"lblBrokerCaption")

        self.gridLayoutBinding.addWidget(self.lblBrokerCaption, 0, 0, 1, 1)

        self.lblBroker = QLabel(self.grpBinding)
        self.lblBroker.setObjectName(u"lblBroker")

        self.gridLayoutBinding.addWidget(self.lblBroker, 0, 1, 1, 1)

        self.lblAccountCaption = QLabel(self.grpBinding)
        self.lblAccountCaption.setObjectName(u"lblAccountCaption")

        self.gridLayoutBinding.addWidget(self.lblAccountCaption, 0, 2, 1, 1)

        self.lblAccount = QLabel(self.grpBinding)
        self.lblAccount.setObjectName(u"lblAccount")

        self.gridLayoutBinding.addWidget(self.lblAccount, 0, 3, 1, 1)

        self.lblSymbolCaption = QLabel(self.grpBinding)
        self.lblSymbolCaption.setObjectName(u"lblSymbolCaption")

        self.gridLayoutBinding.addWidget(self.lblSymbolCaption, 1, 0, 1, 1)

        self.lblSymbol = QLabel(self.grpBinding)
        self.lblSymbol.setObjectName(u"lblSymbol")

        self.gridLayoutBinding.addWidget(self.lblSymbol, 1, 1, 1, 1)

        self.lblTimeframeCaption = QLabel(self.grpBinding)
        self.lblTimeframeCaption.setObjectName(u"lblTimeframeCaption")

        self.gridLayoutBinding.addWidget(self.lblTimeframeCaption, 1, 2, 1, 1)

        self.lblTimeframe = QLabel(self.grpBinding)
        self.lblTimeframe.setObjectName(u"lblTimeframe")

        self.gridLayoutBinding.addWidget(self.lblTimeframe, 1, 3, 1, 1)


        self.verticalLayout.addWidget(self.grpBinding)

        self.grpRange = QGroupBox(AlgorithmWorkspaceHistoryDownloadDialog)
        self.grpRange.setObjectName(u"grpRange")
        self.gridLayoutRange = QGridLayout(self.grpRange)
        self.gridLayoutRange.setObjectName(u"gridLayoutRange")
        self.lblStartDate = QLabel(self.grpRange)
        self.lblStartDate.setObjectName(u"lblStartDate")

        self.gridLayoutRange.addWidget(self.lblStartDate, 0, 0, 1, 1)

        self.dtStartDate = QDateEdit(self.grpRange)
        self.dtStartDate.setObjectName(u"dtStartDate")
        self.dtStartDate.setCalendarPopup(True)

        self.gridLayoutRange.addWidget(self.dtStartDate, 0, 1, 1, 1)

        self.lblEndDate = QLabel(self.grpRange)
        self.lblEndDate.setObjectName(u"lblEndDate")

        self.gridLayoutRange.addWidget(self.lblEndDate, 1, 0, 1, 1)

        self.dtEndDate = QDateEdit(self.grpRange)
        self.dtEndDate.setObjectName(u"dtEndDate")
        self.dtEndDate.setCalendarPopup(True)

        self.gridLayoutRange.addWidget(self.dtEndDate, 1, 1, 1, 1)

        self.lblTimezone = QLabel(self.grpRange)
        self.lblTimezone.setObjectName(u"lblTimezone")

        self.gridLayoutRange.addWidget(self.lblTimezone, 2, 0, 1, 1)

        self.cmbTimezone = QComboBox(self.grpRange)
        self.cmbTimezone.setObjectName(u"cmbTimezone")
        self.cmbTimezone.setEditable(True)

        self.gridLayoutRange.addWidget(self.cmbTimezone, 2, 1, 1, 1)


        self.verticalLayout.addWidget(self.grpRange)

        self.grpDestination = QGroupBox(AlgorithmWorkspaceHistoryDownloadDialog)
        self.grpDestination.setObjectName(u"grpDestination")
        self.formLayoutDestination = QFormLayout(self.grpDestination)
        self.formLayoutDestination.setObjectName(u"formLayoutDestination")
        self.lblPlannedFile = QLabel(self.grpDestination)
        self.lblPlannedFile.setObjectName(u"lblPlannedFile")

        self.formLayoutDestination.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblPlannedFile)

        self.edtPlannedFile = QLineEdit(self.grpDestination)
        self.edtPlannedFile.setObjectName(u"edtPlannedFile")
        self.edtPlannedFile.setReadOnly(True)

        self.formLayoutDestination.setWidget(0, QFormLayout.ItemRole.FieldRole, self.edtPlannedFile)

        self.lblDestinationFolder = QLabel(self.grpDestination)
        self.lblDestinationFolder.setObjectName(u"lblDestinationFolder")

        self.formLayoutDestination.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblDestinationFolder)

        self.edtDestinationFolder = QLineEdit(self.grpDestination)
        self.edtDestinationFolder.setObjectName(u"edtDestinationFolder")
        self.edtDestinationFolder.setReadOnly(True)

        self.formLayoutDestination.setWidget(1, QFormLayout.ItemRole.FieldRole, self.edtDestinationFolder)


        self.verticalLayout.addWidget(self.grpDestination)

        self.grpProgress = QGroupBox(AlgorithmWorkspaceHistoryDownloadDialog)
        self.grpProgress.setObjectName(u"grpProgress")
        self.verticalLayoutProgress = QVBoxLayout(self.grpProgress)
        self.verticalLayoutProgress.setObjectName(u"verticalLayoutProgress")
        self.progressDownload = QProgressBar(self.grpProgress)
        self.progressDownload.setObjectName(u"progressDownload")
        self.progressDownload.setValue(0)
        self.progressDownload.setTextVisible(False)

        self.verticalLayoutProgress.addWidget(self.progressDownload)

        self.lblStatus = QLabel(self.grpProgress)
        self.lblStatus.setObjectName(u"lblStatus")
        self.lblStatus.setWordWrap(True)

        self.verticalLayoutProgress.addWidget(self.lblStatus)


        self.verticalLayout.addWidget(self.grpProgress)

        self.lblNote = QLabel(AlgorithmWorkspaceHistoryDownloadDialog)
        self.lblNote.setObjectName(u"lblNote")
        self.lblNote.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblNote)

        self.verticalSpacer = QSpacerItem(20, 16, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout.addItem(self.verticalSpacer)

        self.horizontalLayoutButtons = QHBoxLayout()
        self.horizontalLayoutButtons.setObjectName(u"horizontalLayoutButtons")
        self.horizontalSpacerButtons = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutButtons.addItem(self.horizontalSpacerButtons)

        self.btnDownload = QPushButton(AlgorithmWorkspaceHistoryDownloadDialog)
        self.btnDownload.setObjectName(u"btnDownload")

        self.horizontalLayoutButtons.addWidget(self.btnDownload)

        self.btnUseForReplay = QPushButton(AlgorithmWorkspaceHistoryDownloadDialog)
        self.btnUseForReplay.setObjectName(u"btnUseForReplay")
        self.btnUseForReplay.setEnabled(False)

        self.horizontalLayoutButtons.addWidget(self.btnUseForReplay)

        self.btnClose = QPushButton(AlgorithmWorkspaceHistoryDownloadDialog)
        self.btnClose.setObjectName(u"btnClose")

        self.horizontalLayoutButtons.addWidget(self.btnClose)


        self.verticalLayout.addLayout(self.horizontalLayoutButtons)


        self.retranslateUi(AlgorithmWorkspaceHistoryDownloadDialog)

        self.btnDownload.setDefault(True)


        QMetaObject.connectSlotsByName(AlgorithmWorkspaceHistoryDownloadDialog)
    # setupUi

    def retranslateUi(self, AlgorithmWorkspaceHistoryDownloadDialog):
        AlgorithmWorkspaceHistoryDownloadDialog.setWindowTitle(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"[AlgorithmWorkspaceHistoryDownloadDialog.windowTitle]", None))
        self.lblWorkspace.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"[AlgorithmWorkspaceHistoryDownloadDialog.workspace]", None))
        self.grpBinding.setTitle(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"[AlgorithmWorkspaceHistoryDownloadDialog.grpBinding]", None))
        self.lblBrokerCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"[AlgorithmWorkspaceHistoryDownloadDialog.lblBroker]", None))
        self.lblBroker.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"\u2014", None))
        self.lblAccountCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"[AlgorithmWorkspaceHistoryDownloadDialog.lblAccount]", None))
        self.lblAccount.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"\u2014", None))
        self.lblSymbolCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"[AlgorithmWorkspaceHistoryDownloadDialog.lblSymbol]", None))
        self.lblSymbol.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"\u2014", None))
        self.lblTimeframeCaption.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"[AlgorithmWorkspaceHistoryDownloadDialog.lblTimeframe]", None))
        self.lblTimeframe.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"\u2014", None))
        self.grpRange.setTitle(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"[AlgorithmWorkspaceHistoryDownloadDialog.grpRange]", None))
        self.lblStartDate.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"[AlgorithmWorkspaceHistoryDownloadDialog.lblStartDate]", None))
        self.dtStartDate.setDisplayFormat(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"yyyy-MM-dd", None))
        self.lblEndDate.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"[AlgorithmWorkspaceHistoryDownloadDialog.lblEndDate]", None))
        self.dtEndDate.setDisplayFormat(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"yyyy-MM-dd", None))
        self.lblTimezone.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"[AlgorithmWorkspaceHistoryDownloadDialog.lblTimezone]", None))
        self.grpDestination.setTitle(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"[AlgorithmWorkspaceHistoryDownloadDialog.grpDestination]", None))
        self.lblPlannedFile.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"[AlgorithmWorkspaceHistoryDownloadDialog.lblPlannedFile]", None))
        self.lblDestinationFolder.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"[AlgorithmWorkspaceHistoryDownloadDialog.lblDestinationFolder]", None))
        self.grpProgress.setTitle(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"[AlgorithmWorkspaceHistoryDownloadDialog.grpProgress]", None))
        self.lblStatus.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"[AlgorithmWorkspaceHistoryDownloadDialog.statusReady]", None))
        self.lblNote.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"[AlgorithmWorkspaceHistoryDownloadDialog.note]", None))
        self.btnDownload.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"[AlgorithmWorkspaceHistoryDownloadDialog.btnDownload]", None))
        self.btnUseForReplay.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"[AlgorithmWorkspaceHistoryDownloadDialog.btnUseForReplay]", None))
        self.btnClose.setText(QCoreApplication.translate("AlgorithmWorkspaceHistoryDownloadDialog", u"[AlgorithmWorkspaceHistoryDownloadDialog.btnClose]", None))
    # retranslateUi

