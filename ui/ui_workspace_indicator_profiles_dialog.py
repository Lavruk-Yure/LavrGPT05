# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'workspace_indicator_profiles_dialog.ui'
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
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
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


class Ui_WorkspaceIndicatorProfilesDialog(object):
    def setupUi(self, WorkspaceIndicatorProfilesDialog):
        if not WorkspaceIndicatorProfilesDialog.objectName():
            WorkspaceIndicatorProfilesDialog.setObjectName(
                "WorkspaceIndicatorProfilesDialog"
            )
        WorkspaceIndicatorProfilesDialog.resize(1100, 720)
        WorkspaceIndicatorProfilesDialog.setMinimumSize(QSize(900, 600))
        WorkspaceIndicatorProfilesDialog.setModal(True)
        self.verticalLayout = QVBoxLayout(WorkspaceIndicatorProfilesDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.lblWorkspace = QLabel(WorkspaceIndicatorProfilesDialog)
        self.lblWorkspace.setObjectName("lblWorkspace")
        self.lblWorkspace.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblWorkspace)

        self.lblCurrentBindings = QLabel(WorkspaceIndicatorProfilesDialog)
        self.lblCurrentBindings.setObjectName("lblCurrentBindings")
        self.lblCurrentBindings.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblCurrentBindings)

        self.splitProfiles = QSplitter(WorkspaceIndicatorProfilesDialog)
        self.splitProfiles.setObjectName("splitProfiles")
        self.splitProfiles.setOrientation(Qt.Orientation.Horizontal)
        self.pnlProfiles = QWidget(self.splitProfiles)
        self.pnlProfiles.setObjectName("pnlProfiles")
        self.verticalLayoutProfiles = QVBoxLayout(self.pnlProfiles)
        self.verticalLayoutProfiles.setObjectName("verticalLayoutProfiles")
        self.verticalLayoutProfiles.setContentsMargins(0, 0, 8, 0)
        self.treeProfiles = QTreeWidget(self.pnlProfiles)
        self.treeProfiles.setObjectName("treeProfiles")
        self.treeProfiles.setMinimumSize(QSize(390, 0))
        self.treeProfiles.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.treeProfiles.setAlternatingRowColors(True)
        self.treeProfiles.setRootIsDecorated(True)
        self.treeProfiles.setUniformRowHeights(True)
        self.treeProfiles.setColumnCount(3)

        self.verticalLayoutProfiles.addWidget(self.treeProfiles)

        self.horizontalLayoutProfileActions = QHBoxLayout()
        self.horizontalLayoutProfileActions.setObjectName(
            "horizontalLayoutProfileActions"
        )
        self.btnNew = QPushButton(self.pnlProfiles)
        self.btnNew.setObjectName("btnNew")

        self.horizontalLayoutProfileActions.addWidget(self.btnNew)

        self.btnDuplicate = QPushButton(self.pnlProfiles)
        self.btnDuplicate.setObjectName("btnDuplicate")

        self.horizontalLayoutProfileActions.addWidget(self.btnDuplicate)

        self.btnArchive = QPushButton(self.pnlProfiles)
        self.btnArchive.setObjectName("btnArchive")

        self.horizontalLayoutProfileActions.addWidget(self.btnArchive)

        self.btnDelete = QPushButton(self.pnlProfiles)
        self.btnDelete.setObjectName("btnDelete")

        self.horizontalLayoutProfileActions.addWidget(self.btnDelete)

        self.verticalLayoutProfiles.addLayout(self.horizontalLayoutProfileActions)

        self.splitProfiles.addWidget(self.pnlProfiles)
        self.pnlEditor = QWidget(self.splitProfiles)
        self.pnlEditor.setObjectName("pnlEditor")
        self.verticalLayoutEditor = QVBoxLayout(self.pnlEditor)
        self.verticalLayoutEditor.setObjectName("verticalLayoutEditor")
        self.verticalLayoutEditor.setContentsMargins(8, 0, 0, 0)
        self.grpProfile = QGroupBox(self.pnlEditor)
        self.grpProfile.setObjectName("grpProfile")
        self.formLayoutProfile = QFormLayout(self.grpProfile)
        self.formLayoutProfile.setObjectName("formLayoutProfile")
        self.lblNameCaption = QLabel(self.grpProfile)
        self.lblNameCaption.setObjectName("lblNameCaption")

        self.formLayoutProfile.setWidget(
            0, QFormLayout.ItemRole.LabelRole, self.lblNameCaption
        )

        self.edtName = QLineEdit(self.grpProfile)
        self.edtName.setObjectName("edtName")

        self.formLayoutProfile.setWidget(
            0, QFormLayout.ItemRole.FieldRole, self.edtName
        )

        self.lblIndicatorCaption = QLabel(self.grpProfile)
        self.lblIndicatorCaption.setObjectName("lblIndicatorCaption")

        self.formLayoutProfile.setWidget(
            1, QFormLayout.ItemRole.LabelRole, self.lblIndicatorCaption
        )

        self.lblIndicatorValue = QLabel(self.grpProfile)
        self.lblIndicatorValue.setObjectName("lblIndicatorValue")

        self.formLayoutProfile.setWidget(
            1, QFormLayout.ItemRole.FieldRole, self.lblIndicatorValue
        )

        self.lblSourceReferenceCaption = QLabel(self.grpProfile)
        self.lblSourceReferenceCaption.setObjectName("lblSourceReferenceCaption")

        self.formLayoutProfile.setWidget(
            2, QFormLayout.ItemRole.LabelRole, self.lblSourceReferenceCaption
        )

        self.lblSourceReferenceValue = QLabel(self.grpProfile)
        self.lblSourceReferenceValue.setObjectName("lblSourceReferenceValue")

        self.formLayoutProfile.setWidget(
            2, QFormLayout.ItemRole.FieldRole, self.lblSourceReferenceValue
        )

        self.lblRevisionCaption = QLabel(self.grpProfile)
        self.lblRevisionCaption.setObjectName("lblRevisionCaption")

        self.formLayoutProfile.setWidget(
            3, QFormLayout.ItemRole.LabelRole, self.lblRevisionCaption
        )

        self.lblRevisionValue = QLabel(self.grpProfile)
        self.lblRevisionValue.setObjectName("lblRevisionValue")

        self.formLayoutProfile.setWidget(
            3, QFormLayout.ItemRole.FieldRole, self.lblRevisionValue
        )

        self.lblProfileStatusCaption = QLabel(self.grpProfile)
        self.lblProfileStatusCaption.setObjectName("lblProfileStatusCaption")

        self.formLayoutProfile.setWidget(
            4, QFormLayout.ItemRole.LabelRole, self.lblProfileStatusCaption
        )

        self.lblProfileStatusValue = QLabel(self.grpProfile)
        self.lblProfileStatusValue.setObjectName("lblProfileStatusValue")
        self.lblProfileStatusValue.setWordWrap(True)

        self.formLayoutProfile.setWidget(
            4, QFormLayout.ItemRole.FieldRole, self.lblProfileStatusValue
        )

        self.verticalLayoutEditor.addWidget(self.grpProfile)

        self.stackIndicator = QStackedWidget(self.pnlEditor)
        self.stackIndicator.setObjectName("stackIndicator")
        self.pageNoSelection = QWidget()
        self.pageNoSelection.setObjectName("pageNoSelection")
        self.verticalLayoutNoSelection = QVBoxLayout(self.pageNoSelection)
        self.verticalLayoutNoSelection.setObjectName("verticalLayoutNoSelection")
        self.lblNoSelection = QLabel(self.pageNoSelection)
        self.lblNoSelection.setObjectName("lblNoSelection")
        self.lblNoSelection.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lblNoSelection.setWordWrap(True)

        self.verticalLayoutNoSelection.addWidget(self.lblNoSelection)

        self.stackIndicator.addWidget(self.pageNoSelection)
        self.pageMacd = QWidget()
        self.pageMacd.setObjectName("pageMacd")
        self.formLayoutMacd = QFormLayout(self.pageMacd)
        self.formLayoutMacd.setObjectName("formLayoutMacd")
        self.lblMacdSource = QLabel(self.pageMacd)
        self.lblMacdSource.setObjectName("lblMacdSource")

        self.formLayoutMacd.setWidget(
            0, QFormLayout.ItemRole.LabelRole, self.lblMacdSource
        )

        self.cmbMacdSource = QComboBox(self.pageMacd)
        self.cmbMacdSource.setObjectName("cmbMacdSource")

        self.formLayoutMacd.setWidget(
            0, QFormLayout.ItemRole.FieldRole, self.cmbMacdSource
        )

        self.lblMacdFast = QLabel(self.pageMacd)
        self.lblMacdFast.setObjectName("lblMacdFast")

        self.formLayoutMacd.setWidget(
            1, QFormLayout.ItemRole.LabelRole, self.lblMacdFast
        )

        self.spnMacdFast = QSpinBox(self.pageMacd)
        self.spnMacdFast.setObjectName("spnMacdFast")
        self.spnMacdFast.setMinimum(1)
        self.spnMacdFast.setMaximum(100000)

        self.formLayoutMacd.setWidget(
            1, QFormLayout.ItemRole.FieldRole, self.spnMacdFast
        )

        self.lblMacdSlow = QLabel(self.pageMacd)
        self.lblMacdSlow.setObjectName("lblMacdSlow")

        self.formLayoutMacd.setWidget(
            2, QFormLayout.ItemRole.LabelRole, self.lblMacdSlow
        )

        self.spnMacdSlow = QSpinBox(self.pageMacd)
        self.spnMacdSlow.setObjectName("spnMacdSlow")
        self.spnMacdSlow.setMinimum(1)
        self.spnMacdSlow.setMaximum(100000)

        self.formLayoutMacd.setWidget(
            2, QFormLayout.ItemRole.FieldRole, self.spnMacdSlow
        )

        self.lblMacdSignal = QLabel(self.pageMacd)
        self.lblMacdSignal.setObjectName("lblMacdSignal")

        self.formLayoutMacd.setWidget(
            3, QFormLayout.ItemRole.LabelRole, self.lblMacdSignal
        )

        self.spnMacdSignal = QSpinBox(self.pageMacd)
        self.spnMacdSignal.setObjectName("spnMacdSignal")
        self.spnMacdSignal.setMinimum(1)
        self.spnMacdSignal.setMaximum(100000)

        self.formLayoutMacd.setWidget(
            3, QFormLayout.ItemRole.FieldRole, self.spnMacdSignal
        )

        self.lblMacdOscillatorMa = QLabel(self.pageMacd)
        self.lblMacdOscillatorMa.setObjectName("lblMacdOscillatorMa")

        self.formLayoutMacd.setWidget(
            4, QFormLayout.ItemRole.LabelRole, self.lblMacdOscillatorMa
        )

        self.cmbMacdOscillatorMa = QComboBox(self.pageMacd)
        self.cmbMacdOscillatorMa.setObjectName("cmbMacdOscillatorMa")

        self.formLayoutMacd.setWidget(
            4, QFormLayout.ItemRole.FieldRole, self.cmbMacdOscillatorMa
        )

        self.lblMacdSignalMa = QLabel(self.pageMacd)
        self.lblMacdSignalMa.setObjectName("lblMacdSignalMa")

        self.formLayoutMacd.setWidget(
            5, QFormLayout.ItemRole.LabelRole, self.lblMacdSignalMa
        )

        self.cmbMacdSignalMa = QComboBox(self.pageMacd)
        self.cmbMacdSignalMa.setObjectName("cmbMacdSignalMa")

        self.formLayoutMacd.setWidget(
            5, QFormLayout.ItemRole.FieldRole, self.cmbMacdSignalMa
        )

        self.lblMacdShift = QLabel(self.pageMacd)
        self.lblMacdShift.setObjectName("lblMacdShift")

        self.formLayoutMacd.setWidget(
            6, QFormLayout.ItemRole.LabelRole, self.lblMacdShift
        )

        self.spnMacdShift = QSpinBox(self.pageMacd)
        self.spnMacdShift.setObjectName("spnMacdShift")
        self.spnMacdShift.setMinimum(0)
        self.spnMacdShift.setMaximum(100000)

        self.formLayoutMacd.setWidget(
            6, QFormLayout.ItemRole.FieldRole, self.spnMacdShift
        )

        self.stackIndicator.addWidget(self.pageMacd)
        self.pageAlligator = QWidget()
        self.pageAlligator.setObjectName("pageAlligator")
        self.formLayoutAlligator = QFormLayout(self.pageAlligator)
        self.formLayoutAlligator.setObjectName("formLayoutAlligator")
        self.lblAlligatorSource = QLabel(self.pageAlligator)
        self.lblAlligatorSource.setObjectName("lblAlligatorSource")

        self.formLayoutAlligator.setWidget(
            0, QFormLayout.ItemRole.LabelRole, self.lblAlligatorSource
        )

        self.cmbAlligatorSource = QComboBox(self.pageAlligator)
        self.cmbAlligatorSource.setObjectName("cmbAlligatorSource")

        self.formLayoutAlligator.setWidget(
            0, QFormLayout.ItemRole.FieldRole, self.cmbAlligatorSource
        )

        self.lblJawPeriod = QLabel(self.pageAlligator)
        self.lblJawPeriod.setObjectName("lblJawPeriod")

        self.formLayoutAlligator.setWidget(
            1, QFormLayout.ItemRole.LabelRole, self.lblJawPeriod
        )

        self.spnJawPeriod = QSpinBox(self.pageAlligator)
        self.spnJawPeriod.setObjectName("spnJawPeriod")
        self.spnJawPeriod.setMinimum(1)
        self.spnJawPeriod.setMaximum(100000)

        self.formLayoutAlligator.setWidget(
            1, QFormLayout.ItemRole.FieldRole, self.spnJawPeriod
        )

        self.lblJawShift = QLabel(self.pageAlligator)
        self.lblJawShift.setObjectName("lblJawShift")

        self.formLayoutAlligator.setWidget(
            2, QFormLayout.ItemRole.LabelRole, self.lblJawShift
        )

        self.spnJawShift = QSpinBox(self.pageAlligator)
        self.spnJawShift.setObjectName("spnJawShift")
        self.spnJawShift.setMinimum(0)
        self.spnJawShift.setMaximum(100000)

        self.formLayoutAlligator.setWidget(
            2, QFormLayout.ItemRole.FieldRole, self.spnJawShift
        )

        self.lblTeethPeriod = QLabel(self.pageAlligator)
        self.lblTeethPeriod.setObjectName("lblTeethPeriod")

        self.formLayoutAlligator.setWidget(
            3, QFormLayout.ItemRole.LabelRole, self.lblTeethPeriod
        )

        self.spnTeethPeriod = QSpinBox(self.pageAlligator)
        self.spnTeethPeriod.setObjectName("spnTeethPeriod")
        self.spnTeethPeriod.setMinimum(1)
        self.spnTeethPeriod.setMaximum(100000)

        self.formLayoutAlligator.setWidget(
            3, QFormLayout.ItemRole.FieldRole, self.spnTeethPeriod
        )

        self.lblTeethShift = QLabel(self.pageAlligator)
        self.lblTeethShift.setObjectName("lblTeethShift")

        self.formLayoutAlligator.setWidget(
            4, QFormLayout.ItemRole.LabelRole, self.lblTeethShift
        )

        self.spnTeethShift = QSpinBox(self.pageAlligator)
        self.spnTeethShift.setObjectName("spnTeethShift")
        self.spnTeethShift.setMinimum(0)
        self.spnTeethShift.setMaximum(100000)

        self.formLayoutAlligator.setWidget(
            4, QFormLayout.ItemRole.FieldRole, self.spnTeethShift
        )

        self.lblLipsPeriod = QLabel(self.pageAlligator)
        self.lblLipsPeriod.setObjectName("lblLipsPeriod")

        self.formLayoutAlligator.setWidget(
            5, QFormLayout.ItemRole.LabelRole, self.lblLipsPeriod
        )

        self.spnLipsPeriod = QSpinBox(self.pageAlligator)
        self.spnLipsPeriod.setObjectName("spnLipsPeriod")
        self.spnLipsPeriod.setMinimum(1)
        self.spnLipsPeriod.setMaximum(100000)

        self.formLayoutAlligator.setWidget(
            5, QFormLayout.ItemRole.FieldRole, self.spnLipsPeriod
        )

        self.lblLipsShift = QLabel(self.pageAlligator)
        self.lblLipsShift.setObjectName("lblLipsShift")

        self.formLayoutAlligator.setWidget(
            6, QFormLayout.ItemRole.LabelRole, self.lblLipsShift
        )

        self.spnLipsShift = QSpinBox(self.pageAlligator)
        self.spnLipsShift.setObjectName("spnLipsShift")
        self.spnLipsShift.setMinimum(0)
        self.spnLipsShift.setMaximum(100000)

        self.formLayoutAlligator.setWidget(
            6, QFormLayout.ItemRole.FieldRole, self.spnLipsShift
        )

        self.lblAlligatorMa = QLabel(self.pageAlligator)
        self.lblAlligatorMa.setObjectName("lblAlligatorMa")

        self.formLayoutAlligator.setWidget(
            7, QFormLayout.ItemRole.LabelRole, self.lblAlligatorMa
        )

        self.cmbAlligatorMa = QComboBox(self.pageAlligator)
        self.cmbAlligatorMa.setObjectName("cmbAlligatorMa")

        self.formLayoutAlligator.setWidget(
            7, QFormLayout.ItemRole.FieldRole, self.cmbAlligatorMa
        )

        self.stackIndicator.addWidget(self.pageAlligator)

        self.verticalLayoutEditor.addWidget(self.stackIndicator)

        self.verticalSpacerEditor = QSpacerItem(
            20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        )

        self.verticalLayoutEditor.addItem(self.verticalSpacerEditor)

        self.splitProfiles.addWidget(self.pnlEditor)

        self.verticalLayout.addWidget(self.splitProfiles)

        self.lblNote = QLabel(WorkspaceIndicatorProfilesDialog)
        self.lblNote.setObjectName("lblNote")
        self.lblNote.setWordWrap(True)

        self.verticalLayout.addWidget(self.lblNote)

        self.horizontalLayoutButtons = QHBoxLayout()
        self.horizontalLayoutButtons.setObjectName("horizontalLayoutButtons")
        self.btnUseForWorkspace = QPushButton(WorkspaceIndicatorProfilesDialog)
        self.btnUseForWorkspace.setObjectName("btnUseForWorkspace")

        self.horizontalLayoutButtons.addWidget(self.btnUseForWorkspace)

        self.horizontalSpacerButtons = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayoutButtons.addItem(self.horizontalSpacerButtons)

        self.btnSave = QPushButton(WorkspaceIndicatorProfilesDialog)
        self.btnSave.setObjectName("btnSave")

        self.horizontalLayoutButtons.addWidget(self.btnSave)

        self.btnClose = QPushButton(WorkspaceIndicatorProfilesDialog)
        self.btnClose.setObjectName("btnClose")

        self.horizontalLayoutButtons.addWidget(self.btnClose)

        self.verticalLayout.addLayout(self.horizontalLayoutButtons)

        self.retranslateUi(WorkspaceIndicatorProfilesDialog)

        QMetaObject.connectSlotsByName(WorkspaceIndicatorProfilesDialog)

    # setupUi

    def retranslateUi(self, WorkspaceIndicatorProfilesDialog):
        WorkspaceIndicatorProfilesDialog.setWindowTitle(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.windowTitle]",
                None,
            )
        )
        self.lblWorkspace.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.workspace]",
                None,
            )
        )
        self.lblCurrentBindings.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.currentBindings]",
                None,
            )
        )
        ___qtreewidgetitem = self.treeProfiles.headerItem()
        ___qtreewidgetitem.setText(
            2,
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.columnStatus]",
                None,
            ),
        )
        ___qtreewidgetitem.setText(
            1,
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.columnRevision]",
                None,
            ),
        )
        ___qtreewidgetitem.setText(
            0,
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.columnProfile]",
                None,
            ),
        )
        self.btnNew.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.btnNew]",
                None,
            )
        )
        self.btnDuplicate.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.btnDuplicate]",
                None,
            )
        )
        self.btnArchive.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.btnArchive]",
                None,
            )
        )
        self.btnDelete.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.btnDelete]",
                None,
            )
        )
        self.grpProfile.setTitle(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.grpProfile]",
                None,
            )
        )
        self.lblNameCaption.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.lblName]",
                None,
            )
        )
        self.lblIndicatorCaption.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.lblIndicator]",
                None,
            )
        )
        self.lblIndicatorValue.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog", "\u2014", None
            )
        )
        self.lblSourceReferenceCaption.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.lblSourceReference]",
                None,
            )
        )
        self.lblSourceReferenceValue.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog", "\u2014", None
            )
        )
        self.lblRevisionCaption.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.lblRevision]",
                None,
            )
        )
        self.lblRevisionValue.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog", "\u2014", None
            )
        )
        self.lblProfileStatusCaption.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.lblStatus]",
                None,
            )
        )
        self.lblProfileStatusValue.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog", "\u2014", None
            )
        )
        self.lblNoSelection.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.noSelection]",
                None,
            )
        )
        self.lblMacdSource.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.lblSource]",
                None,
            )
        )
        self.lblMacdFast.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.lblFastPeriod]",
                None,
            )
        )
        self.lblMacdSlow.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.lblSlowPeriod]",
                None,
            )
        )
        self.lblMacdSignal.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.lblSignalPeriod]",
                None,
            )
        )
        self.lblMacdOscillatorMa.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.lblOscillatorMa]",
                None,
            )
        )
        self.lblMacdSignalMa.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.lblSignalMa]",
                None,
            )
        )
        self.lblMacdShift.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.lblShift]",
                None,
            )
        )
        self.lblAlligatorSource.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.lblSource]",
                None,
            )
        )
        self.lblJawPeriod.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.lblJawPeriod]",
                None,
            )
        )
        self.lblJawShift.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.lblJawShift]",
                None,
            )
        )
        self.lblTeethPeriod.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.lblTeethPeriod]",
                None,
            )
        )
        self.lblTeethShift.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.lblTeethShift]",
                None,
            )
        )
        self.lblLipsPeriod.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.lblLipsPeriod]",
                None,
            )
        )
        self.lblLipsShift.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.lblLipsShift]",
                None,
            )
        )
        self.lblAlligatorMa.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.lblMaType]",
                None,
            )
        )
        self.lblNote.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.note]",
                None,
            )
        )
        self.btnUseForWorkspace.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.btnUseForWorkspace]",
                None,
            )
        )
        self.btnSave.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.btnSave]",
                None,
            )
        )
        self.btnClose.setText(
            QCoreApplication.translate(
                "WorkspaceIndicatorProfilesDialog",
                "[WorkspaceIndicatorProfilesDialog.btnClose]",
                None,
            )
        )

    # retranslateUi
