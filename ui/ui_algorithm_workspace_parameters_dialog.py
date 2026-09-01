# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'algorithm_workspace_parameters_dialog.ui'
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
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class Ui_AlgorithmWorkspaceParametersDialog(object):
    def setupUi(self, AlgorithmWorkspaceParametersDialog):
        if not AlgorithmWorkspaceParametersDialog.objectName():
            AlgorithmWorkspaceParametersDialog.setObjectName(
                "AlgorithmWorkspaceParametersDialog"
            )
        AlgorithmWorkspaceParametersDialog.resize(1040, 790)
        AlgorithmWorkspaceParametersDialog.setMinimumSize(QSize(900, 650))
        AlgorithmWorkspaceParametersDialog.setModal(True)
        self.verticalLayout = QVBoxLayout(AlgorithmWorkspaceParametersDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.lblWorkspace = QLabel(AlgorithmWorkspaceParametersDialog)
        self.lblWorkspace.setObjectName("lblWorkspace")
        sizePolicy = QSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.lblWorkspace.sizePolicy().hasHeightForWidth())
        self.lblWorkspace.setSizePolicy(sizePolicy)
        self.lblWorkspace.setMaximumSize(QSize(16777215, 70))
        self.lblWorkspace.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblWorkspace)

        self.lblContext = QLabel(AlgorithmWorkspaceParametersDialog)
        self.lblContext.setObjectName("lblContext")
        sizePolicy.setHeightForWidth(self.lblContext.sizePolicy().hasHeightForWidth())
        self.lblContext.setSizePolicy(sizePolicy)
        self.lblContext.setMaximumSize(QSize(16777215, 70))
        self.lblContext.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblContext)

        self.splitParameters = QSplitter(AlgorithmWorkspaceParametersDialog)
        self.splitParameters.setObjectName("splitParameters")
        sizePolicy1 = QSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(
            self.splitParameters.sizePolicy().hasHeightForWidth()
        )
        self.splitParameters.setSizePolicy(sizePolicy1)
        self.splitParameters.setOrientation(Qt.Orientation.Horizontal)
        self.treeParameters = QTreeWidget(self.splitParameters)
        self.treeParameters.setObjectName("treeParameters")
        self.treeParameters.setMinimumSize(QSize(360, 0))
        self.treeParameters.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.treeParameters.setAlternatingRowColors(True)
        self.treeParameters.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerItem
        )
        self.treeParameters.setRootIsDecorated(True)
        self.treeParameters.setUniformRowHeights(True)
        self.treeParameters.setColumnCount(2)
        self.splitParameters.addWidget(self.treeParameters)
        self.pnlEditor = QWidget(self.splitParameters)
        self.pnlEditor.setObjectName("pnlEditor")
        sizePolicy2 = QSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored
        )
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.pnlEditor.sizePolicy().hasHeightForWidth())
        self.pnlEditor.setSizePolicy(sizePolicy2)
        self.verticalLayoutEditor = QVBoxLayout(self.pnlEditor)
        self.verticalLayoutEditor.setObjectName("verticalLayoutEditor")
        self.verticalLayoutEditor.setContentsMargins(10, 0, 0, 0)
        self.lblParameterTitle = QLabel(self.pnlEditor)
        self.lblParameterTitle.setObjectName("lblParameterTitle")
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        self.lblParameterTitle.setFont(font)
        self.lblParameterTitle.setWordWrap(True)

        self.verticalLayoutEditor.addWidget(self.lblParameterTitle)

        self.lblParameterDescription = QLabel(self.pnlEditor)
        self.lblParameterDescription.setObjectName("lblParameterDescription")
        self.lblParameterDescription.setWordWrap(True)

        self.verticalLayoutEditor.addWidget(self.lblParameterDescription)

        self.grpValueEditor = QGroupBox(self.pnlEditor)
        self.grpValueEditor.setObjectName("grpValueEditor")
        self.verticalLayoutValueEditor = QVBoxLayout(self.grpValueEditor)
        self.verticalLayoutValueEditor.setObjectName("verticalLayoutValueEditor")
        self.stackValueEditor = QStackedWidget(self.grpValueEditor)
        self.stackValueEditor.setObjectName("stackValueEditor")
        self.pageNoSelection = QWidget()
        self.pageNoSelection.setObjectName("pageNoSelection")
        self.verticalLayoutNoSelection = QVBoxLayout(self.pageNoSelection)
        self.verticalLayoutNoSelection.setObjectName("verticalLayoutNoSelection")
        self.lblNoSelection = QLabel(self.pageNoSelection)
        self.lblNoSelection.setObjectName("lblNoSelection")
        self.lblNoSelection.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lblNoSelection.setWordWrap(True)

        self.verticalLayoutNoSelection.addWidget(self.lblNoSelection)

        self.stackValueEditor.addWidget(self.pageNoSelection)
        self.pageFloat = QWidget()
        self.pageFloat.setObjectName("pageFloat")
        self.verticalLayoutFloat = QVBoxLayout(self.pageFloat)
        self.verticalLayoutFloat.setObjectName("verticalLayoutFloat")
        self.spnFloatValue = QDoubleSpinBox(self.pageFloat)
        self.spnFloatValue.setObjectName("spnFloatValue")
        self.spnFloatValue.setKeyboardTracking(False)
        self.spnFloatValue.setDecimals(6)
        self.spnFloatValue.setMinimum(-1000000000000.000000000000000)
        self.spnFloatValue.setMaximum(1000000000000.000000000000000)

        self.verticalLayoutFloat.addWidget(self.spnFloatValue)

        self.stackValueEditor.addWidget(self.pageFloat)
        self.pageInteger = QWidget()
        self.pageInteger.setObjectName("pageInteger")
        self.verticalLayoutInteger = QVBoxLayout(self.pageInteger)
        self.verticalLayoutInteger.setObjectName("verticalLayoutInteger")
        self.spnIntegerValue = QSpinBox(self.pageInteger)
        self.spnIntegerValue.setObjectName("spnIntegerValue")
        self.spnIntegerValue.setKeyboardTracking(False)
        self.spnIntegerValue.setMinimum(-2147483647)
        self.spnIntegerValue.setMaximum(2147483647)

        self.verticalLayoutInteger.addWidget(self.spnIntegerValue)

        self.stackValueEditor.addWidget(self.pageInteger)
        self.pageBoolean = QWidget()
        self.pageBoolean.setObjectName("pageBoolean")
        self.verticalLayoutBoolean = QVBoxLayout(self.pageBoolean)
        self.verticalLayoutBoolean.setObjectName("verticalLayoutBoolean")
        self.cmbBooleanValue = QComboBox(self.pageBoolean)
        self.cmbBooleanValue.setObjectName("cmbBooleanValue")

        self.verticalLayoutBoolean.addWidget(self.cmbBooleanValue)

        self.stackValueEditor.addWidget(self.pageBoolean)
        self.pageChoice = QWidget()
        self.pageChoice.setObjectName("pageChoice")
        self.verticalLayoutChoice = QVBoxLayout(self.pageChoice)
        self.verticalLayoutChoice.setObjectName("verticalLayoutChoice")
        self.cmbChoiceValue = QComboBox(self.pageChoice)
        self.cmbChoiceValue.setObjectName("cmbChoiceValue")

        self.verticalLayoutChoice.addWidget(self.cmbChoiceValue)

        self.stackValueEditor.addWidget(self.pageChoice)

        self.verticalLayoutValueEditor.addWidget(self.stackValueEditor)

        self.verticalLayoutEditor.addWidget(self.grpValueEditor)

        self.grpParameterDetails = QGroupBox(self.pnlEditor)
        self.grpParameterDetails.setObjectName("grpParameterDetails")
        self.formLayoutDetails = QFormLayout(self.grpParameterDetails)
        self.formLayoutDetails.setObjectName("formLayoutDetails")
        self.formLayoutDetails.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignTop
            | Qt.AlignmentFlag.AlignTrailing
        )
        self.lblStatusCaption = QLabel(self.grpParameterDetails)
        self.lblStatusCaption.setObjectName("lblStatusCaption")

        self.formLayoutDetails.setWidget(
            0, QFormLayout.ItemRole.LabelRole, self.lblStatusCaption
        )

        self.lblStatusValue = QLabel(self.grpParameterDetails)
        self.lblStatusValue.setObjectName("lblStatusValue")
        self.lblStatusValue.setWordWrap(True)

        self.formLayoutDetails.setWidget(
            0, QFormLayout.ItemRole.FieldRole, self.lblStatusValue
        )

        self.lblFeatureCaption = QLabel(self.grpParameterDetails)
        self.lblFeatureCaption.setObjectName("lblFeatureCaption")

        self.formLayoutDetails.setWidget(
            1, QFormLayout.ItemRole.LabelRole, self.lblFeatureCaption
        )

        self.lblFeatureValue = QLabel(self.grpParameterDetails)
        self.lblFeatureValue.setObjectName("lblFeatureValue")
        self.lblFeatureValue.setWordWrap(True)

        self.formLayoutDetails.setWidget(
            1, QFormLayout.ItemRole.FieldRole, self.lblFeatureValue
        )

        self.lblConstraintsCaption = QLabel(self.grpParameterDetails)
        self.lblConstraintsCaption.setObjectName("lblConstraintsCaption")

        self.formLayoutDetails.setWidget(
            2, QFormLayout.ItemRole.LabelRole, self.lblConstraintsCaption
        )

        self.lblConstraintsValue = QLabel(self.grpParameterDetails)
        self.lblConstraintsValue.setObjectName("lblConstraintsValue")
        self.lblConstraintsValue.setWordWrap(True)

        self.formLayoutDetails.setWidget(
            2, QFormLayout.ItemRole.FieldRole, self.lblConstraintsValue
        )

        self.verticalLayoutEditor.addWidget(self.grpParameterDetails)

        self.verticalSpacerEditor = QSpacerItem(
            20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        )

        self.verticalLayoutEditor.addItem(self.verticalSpacerEditor)

        self.splitParameters.addWidget(self.pnlEditor)

        self.verticalLayout.addWidget(self.splitParameters)

        self.lblNote = QLabel(AlgorithmWorkspaceParametersDialog)
        self.lblNote.setObjectName("lblNote")
        sizePolicy.setHeightForWidth(self.lblNote.sizePolicy().hasHeightForWidth())
        self.lblNote.setSizePolicy(sizePolicy)
        self.lblNote.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblNote)

        self.horizontalLayoutButtons = QHBoxLayout()
        self.horizontalLayoutButtons.setObjectName("horizontalLayoutButtons")
        self.btnIndicatorProfiles = QPushButton(AlgorithmWorkspaceParametersDialog)
        self.btnIndicatorProfiles.setObjectName("btnIndicatorProfiles")

        self.horizontalLayoutButtons.addWidget(self.btnIndicatorProfiles)

        self.btnReplaySettings = QPushButton(AlgorithmWorkspaceParametersDialog)
        self.btnReplaySettings.setObjectName("btnReplaySettings")
        self.btnReplaySettings.setVisible(False)

        self.horizontalLayoutButtons.addWidget(self.btnReplaySettings)

        self.horizontalSpacerButtons = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayoutButtons.addItem(self.horizontalSpacerButtons)

        self.btnSave = QPushButton(AlgorithmWorkspaceParametersDialog)
        self.btnSave.setObjectName("btnSave")

        self.horizontalLayoutButtons.addWidget(self.btnSave)

        self.btnClose = QPushButton(AlgorithmWorkspaceParametersDialog)
        self.btnClose.setObjectName("btnClose")

        self.horizontalLayoutButtons.addWidget(self.btnClose)

        self.verticalLayout.addLayout(self.horizontalLayoutButtons)

        self.retranslateUi(AlgorithmWorkspaceParametersDialog)

        self.btnSave.setDefault(True)

        QMetaObject.connectSlotsByName(AlgorithmWorkspaceParametersDialog)

    # setupUi

    def retranslateUi(self, AlgorithmWorkspaceParametersDialog):
        AlgorithmWorkspaceParametersDialog.setWindowTitle(
            QCoreApplication.translate(
                "AlgorithmWorkspaceParametersDialog",
                "[AlgorithmWorkspaceParametersDialog.windowTitle]",
                None,
            )
        )
        self.lblWorkspace.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceParametersDialog",
                "[AlgorithmWorkspaceParametersDialog.workspace]",
                None,
            )
        )
        self.lblContext.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceParametersDialog",
                "[AlgorithmWorkspaceParametersDialog.context]",
                None,
            )
        )
        ___qtreewidgetitem = self.treeParameters.headerItem()
        ___qtreewidgetitem.setText(
            1,
            QCoreApplication.translate(
                "AlgorithmWorkspaceParametersDialog",
                "[AlgorithmWorkspaceParametersDialog.columnValue]",
                None,
            ),
        )
        ___qtreewidgetitem.setText(
            0,
            QCoreApplication.translate(
                "AlgorithmWorkspaceParametersDialog",
                "[AlgorithmWorkspaceParametersDialog.columnParameter]",
                None,
            ),
        )
        self.lblParameterTitle.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceParametersDialog",
                "[AlgorithmWorkspaceParametersDialog.selectParameterTitle]",
                None,
            )
        )
        self.lblParameterDescription.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceParametersDialog",
                "[AlgorithmWorkspaceParametersDialog.selectParameterDescription]",
                None,
            )
        )
        self.grpValueEditor.setTitle(
            QCoreApplication.translate(
                "AlgorithmWorkspaceParametersDialog",
                "[AlgorithmWorkspaceParametersDialog.grpValueEditor]",
                None,
            )
        )
        self.lblNoSelection.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceParametersDialog",
                "[AlgorithmWorkspaceParametersDialog.noSelection]",
                None,
            )
        )
        self.grpParameterDetails.setTitle(
            QCoreApplication.translate(
                "AlgorithmWorkspaceParametersDialog",
                "[AlgorithmWorkspaceParametersDialog.grpParameterDetails]",
                None,
            )
        )
        self.lblStatusCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceParametersDialog",
                "[AlgorithmWorkspaceParametersDialog.lblStatus]",
                None,
            )
        )
        self.lblStatusValue.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceParametersDialog", "\u2014", None
            )
        )
        self.lblFeatureCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceParametersDialog",
                "[AlgorithmWorkspaceParametersDialog.lblFeature]",
                None,
            )
        )
        self.lblFeatureValue.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceParametersDialog", "\u2014", None
            )
        )
        self.lblConstraintsCaption.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceParametersDialog",
                "[AlgorithmWorkspaceParametersDialog.lblConstraints]",
                None,
            )
        )
        self.lblConstraintsValue.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceParametersDialog", "\u2014", None
            )
        )
        self.lblNote.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceParametersDialog",
                "[AlgorithmWorkspaceParametersDialog.note]",
                None,
            )
        )
        self.btnIndicatorProfiles.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceParametersDialog",
                "[AlgorithmWorkspaceParametersDialog.btnIndicatorProfiles]",
                None,
            )
        )
        self.btnReplaySettings.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceParametersDialog",
                "[AlgorithmWorkspaceParametersDialog.btnReplaySettings]",
                None,
            )
        )
        self.btnSave.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceParametersDialog",
                "[AlgorithmWorkspaceParametersDialog.btnSave]",
                None,
            )
        )
        self.btnClose.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceParametersDialog",
                "[AlgorithmWorkspaceParametersDialog.btnClose]",
                None,
            )
        )

    # retranslateUi
