# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'algorithm_workspace_history_download_dialog.ui'
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
    QDateEdit,
    QDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)


class Ui_AlgorithmWorkspaceHistoryDownloadDialog(object):
    def setupUi(self, AlgorithmWorkspaceHistoryDownloadDialog):
        if not AlgorithmWorkspaceHistoryDownloadDialog.objectName():
            AlgorithmWorkspaceHistoryDownloadDialog.setObjectName(
                "AlgorithmWorkspaceHistoryDownloadDialog"
            )
        AlgorithmWorkspaceHistoryDownloadDialog.resize(650, 520)
        AlgorithmWorkspaceHistoryDownloadDialog.setMinimumSize(QSize(590, 480))
        self.verticalLayout = QVBoxLayout(AlgorithmWorkspaceHistoryDownloadDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.lblWorkspace = QLabel(AlgorithmWorkspaceHistoryDownloadDialog)
        self.lblWorkspace.setObjectName("lblWorkspace")
        self.lblWorkspace.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblWorkspace)

        self.grpBinding = QGroupBox(AlgorithmWorkspaceHistoryDownloadDialog)
        self.grpBinding.setObjectName("grpBinding")
        self.gridLayoutBinding = QGridLayout(self.grpBinding)
        self.gridLayoutBinding.setObjectName("gridLayoutBinding")
        self.lblBrokerCaption = QLabel(self.grpBinding)
        self.lblBrokerCaption.setObjectName("lblBrokerCaption")

        self.gridLayoutBinding.addWidget(self.lblBrokerCaption, 0, 0, 1, 1)

        self.lblBroker = QLabel(self.grpBinding)
        self.lblBroker.setObjectName("lblBroker")

        self.gridLayoutBinding.addWidget(self.lblBroker, 0, 1, 1, 1)

        self.lblAccountCaption = QLabel(self.grpBinding)
        self.lblAccountCaption.setObjectName("lblAccountCaption")

        self.gridLayoutBinding.addWidget(self.lblAccountCaption, 0, 2, 1, 1)

        self.lblAccount = QLabel(self.grpBinding)
        self.lblAccount.setObjectName("lblAccount")

        self.gridLayoutBinding.addWidget(self.lblAccount, 0, 3, 1, 1)

        self.lblSymbolCaption = QLabel(self.grpBinding)
        self.lblSymbolCaption.setObjectName("lblSymbolCaption")

        self.gridLayoutBinding.addWidget(self.lblSymbolCaption, 1, 0, 1, 1)

        self.lblSymbol = QLabel(self.grpBinding)
        self.lblSymbol.setObjectName("lblSymbol")

        self.gridLayoutBinding.addWidget(self.lblSymbol, 1, 1, 1, 1)

        self.lblTimeframeCaption = QLabel(self.grpBinding)
        self.lblTimeframeCaption.setObjectName("lblTimeframeCaption")

        self.gridLayoutBinding.addWidget(self.lblTimeframeCaption, 1, 2, 1, 1)

        self.lblTimeframe = QLabel(self.grpBinding)
        self.lblTimeframe.setObjectName("lblTimeframe")

        self.gridLayoutBinding.addWidget(self.lblTimeframe, 1, 3, 1, 1)

        self.verticalLayout.addWidget(self.grpBinding)

        self.grpRange = QGroupBox(AlgorithmWorkspaceHistoryDownloadDialog)
        self.grpRange.setObjectName("grpRange")
        self.gridLayoutRange = QGridLayout(self.grpRange)
        self.gridLayoutRange.setObjectName("gridLayoutRange")
        self.lblStartDate = QLabel(self.grpRange)
        self.lblStartDate.setObjectName("lblStartDate")

        self.gridLayoutRange.addWidget(self.lblStartDate, 0, 0, 1, 1)

        self.dtStartDate = QDateEdit(self.grpRange)
        self.dtStartDate.setObjectName("dtStartDate")
        self.dtStartDate.setCalendarPopup(True)

        self.gridLayoutRange.addWidget(self.dtStartDate, 0, 1, 1, 1)

        self.lblEndDate = QLabel(self.grpRange)
        self.lblEndDate.setObjectName("lblEndDate")

        self.gridLayoutRange.addWidget(self.lblEndDate, 1, 0, 1, 1)

        self.dtEndDate = QDateEdit(self.grpRange)
        self.dtEndDate.setObjectName("dtEndDate")
        self.dtEndDate.setCalendarPopup(True)

        self.gridLayoutRange.addWidget(self.dtEndDate, 1, 1, 1, 1)

        self.lblTimezone = QLabel(self.grpRange)
        self.lblTimezone.setObjectName("lblTimezone")

        self.gridLayoutRange.addWidget(self.lblTimezone, 2, 0, 1, 1)

        self.cmbTimezone = QComboBox(self.grpRange)
        self.cmbTimezone.setObjectName("cmbTimezone")
        self.cmbTimezone.setEditable(True)

        self.gridLayoutRange.addWidget(self.cmbTimezone, 2, 1, 1, 1)

        self.verticalLayout.addWidget(self.grpRange)

        self.grpDestination = QGroupBox(AlgorithmWorkspaceHistoryDownloadDialog)
        self.grpDestination.setObjectName("grpDestination")
        self.formLayoutDestination = QFormLayout(self.grpDestination)
        self.formLayoutDestination.setObjectName("formLayoutDestination")
        self.lblPlannedFile = QLabel(self.grpDestination)
        self.lblPlannedFile.setObjectName("lblPlannedFile")

        self.formLayoutDestination.setWidget(
            0, QFormLayout.ItemRole.LabelRole, self.lblPlannedFile
        )

        self.edtPlannedFile = QLineEdit(self.grpDestination)
        self.edtPlannedFile.setObjectName("edtPlannedFile")
        self.edtPlannedFile.setReadOnly(True)

        self.formLayoutDestination.setWidget(
            0, QFormLayout.ItemRole.FieldRole, self.edtPlannedFile
        )

        self.lblDestinationFolder = QLabel(self.grpDestination)
        self.lblDestinationFolder.setObjectName("lblDestinationFolder")

        self.formLayoutDestination.setWidget(
            1, QFormLayout.ItemRole.LabelRole, self.lblDestinationFolder
        )

        self.edtDestinationFolder = QLineEdit(self.grpDestination)
        self.edtDestinationFolder.setObjectName("edtDestinationFolder")
        self.edtDestinationFolder.setReadOnly(True)

        self.formLayoutDestination.setWidget(
            1, QFormLayout.ItemRole.FieldRole, self.edtDestinationFolder
        )

        self.verticalLayout.addWidget(self.grpDestination)

        self.grpProgress = QGroupBox(AlgorithmWorkspaceHistoryDownloadDialog)
        self.grpProgress.setObjectName("grpProgress")
        self.verticalLayoutProgress = QVBoxLayout(self.grpProgress)
        self.verticalLayoutProgress.setObjectName("verticalLayoutProgress")
        self.progressDownload = QProgressBar(self.grpProgress)
        self.progressDownload.setObjectName("progressDownload")
        self.progressDownload.setValue(0)
        self.progressDownload.setTextVisible(False)

        self.verticalLayoutProgress.addWidget(self.progressDownload)

        self.lblStatus = QLabel(self.grpProgress)
        self.lblStatus.setObjectName("lblStatus")
        self.lblStatus.setWordWrap(True)

        self.verticalLayoutProgress.addWidget(self.lblStatus)

        self.verticalLayout.addWidget(self.grpProgress)

        self.lblNote = QLabel(AlgorithmWorkspaceHistoryDownloadDialog)
        self.lblNote.setObjectName("lblNote")
        self.lblNote.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblNote)

        self.verticalSpacer = QSpacerItem(
            20, 16, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        )

        self.verticalLayout.addItem(self.verticalSpacer)

        self.horizontalLayoutButtons = QHBoxLayout()
        self.horizontalLayoutButtons.setObjectName("horizontalLayoutButtons")
        self.horizontalSpacerButtons = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayoutButtons.addItem(self.horizontalSpacerButtons)

        self.btnDownload = QPushButton(AlgorithmWorkspaceHistoryDownloadDialog)
        self.btnDownload.setObjectName("btnDownload")

        self.horizontalLayoutButtons.addWidget(self.btnDownload)

        self.btnUseForReplay = QPushButton(AlgorithmWorkspaceHistoryDownloadDialog)
        self.btnUseForReplay.setObjectName("btnUseForReplay")
        self.btnUseForReplay.setEnabled(False)

        self.horizontalLayoutButtons.addWidget(self.btnUseForReplay)

        self.btnClose = QPushButton(AlgorithmWorkspaceHistoryDownloadDialog)
        self.btnClose.setObjectName("btnClose")

        self.horizontalLayoutButtons.addWidget(self.btnClose)

        self.verticalLayout.addLayout(self.horizontalLayoutButtons)

        self.retranslateUi(AlgorithmWorkspaceHistoryDownloadDialog)

        self.btnDownload.setDefault(True)

        QMetaObject.connectSlotsByName(AlgorithmWorkspaceHistoryDownloadDialog)

    # setupUi

    def retranslateUi(self, AlgorithmWorkspaceHistoryDownloadDialog):
        AlgorithmWorkspaceHistoryDownloadDialog.setWindowTitle(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog",
                "[AlgorithmWorkspaceHistoryDownloadDialog.windowTitle]",
                None,
            )
        )
        self.lblWorkspace.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog",
                "[AlgorithmWorkspaceHistoryDownloadDialog.workspace]",
                None,
            )
        )
        self.grpBinding.setTitle(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog",
                "[AlgorithmWorkspaceHistoryDownloadDialog.grpBinding]",
                None,
            )
        )
        self.lblBrokerCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog",
                "[AlgorithmWorkspaceHistoryDownloadDialog.lblBroker]",
                None,
            )
        )
        self.lblBroker.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog", "\u2014", None
            )
        )
        self.lblAccountCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog",
                "[AlgorithmWorkspaceHistoryDownloadDialog.lblAccount]",
                None,
            )
        )
        self.lblAccount.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog", "\u2014", None
            )
        )
        self.lblSymbolCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog",
                "[AlgorithmWorkspaceHistoryDownloadDialog.lblSymbol]",
                None,
            )
        )
        self.lblSymbol.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog", "\u2014", None
            )
        )
        self.lblTimeframeCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog",
                "[AlgorithmWorkspaceHistoryDownloadDialog.lblTimeframe]",
                None,
            )
        )
        self.lblTimeframe.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog", "\u2014", None
            )
        )
        self.grpRange.setTitle(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog",
                "[AlgorithmWorkspaceHistoryDownloadDialog.grpRange]",
                None,
            )
        )
        self.lblStartDate.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog",
                "[AlgorithmWorkspaceHistoryDownloadDialog.lblStartDate]",
                None,
            )
        )
        self.dtStartDate.setDisplayFormat(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog", "yyyy-MM-dd", None
            )
        )
        self.lblEndDate.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog",
                "[AlgorithmWorkspaceHistoryDownloadDialog.lblEndDate]",
                None,
            )
        )
        self.dtEndDate.setDisplayFormat(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog", "yyyy-MM-dd", None
            )
        )
        self.lblTimezone.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog",
                "[AlgorithmWorkspaceHistoryDownloadDialog.lblTimezone]",
                None,
            )
        )
        self.grpDestination.setTitle(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog",
                "[AlgorithmWorkspaceHistoryDownloadDialog.grpDestination]",
                None,
            )
        )
        self.lblPlannedFile.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog",
                "[AlgorithmWorkspaceHistoryDownloadDialog.lblPlannedFile]",
                None,
            )
        )
        self.lblDestinationFolder.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog",
                "[AlgorithmWorkspaceHistoryDownloadDialog.lblDestinationFolder]",
                None,
            )
        )
        self.grpProgress.setTitle(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog",
                "[AlgorithmWorkspaceHistoryDownloadDialog.grpProgress]",
                None,
            )
        )
        self.lblStatus.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog",
                "[AlgorithmWorkspaceHistoryDownloadDialog.statusReady]",
                None,
            )
        )
        self.lblNote.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog",
                "[AlgorithmWorkspaceHistoryDownloadDialog.note]",
                None,
            )
        )
        self.btnDownload.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog",
                "[AlgorithmWorkspaceHistoryDownloadDialog.btnDownload]",
                None,
            )
        )
        self.btnUseForReplay.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog",
                "[AlgorithmWorkspaceHistoryDownloadDialog.btnUseForReplay]",
                None,
            )
        )
        self.btnClose.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceHistoryDownloadDialog",
                "[AlgorithmWorkspaceHistoryDownloadDialog.btnClose]",
                None,
            )
        )

    # retranslateUi
