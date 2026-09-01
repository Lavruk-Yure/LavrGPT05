# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'algorithm_workspace_area.ui'
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
    QHBoxLayout,
    QLabel,
    QMdiArea,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
import resources_rc


class Ui_AlgorithmWorkspaceArea(object):
    def setupUi(self, AlgorithmWorkspaceArea):
        if not AlgorithmWorkspaceArea.objectName():
            AlgorithmWorkspaceArea.setObjectName("AlgorithmWorkspaceArea")
        AlgorithmWorkspaceArea.resize(1180, 720)
        self.verticalLayout = QVBoxLayout(AlgorithmWorkspaceArea)
        self.verticalLayout.setSpacing(6)
        self.verticalLayout.setObjectName("verticalLayout")
        self.verticalLayout.setContentsMargins(12, 8, 12, 8)
        self.horizontalLayoutToolbar = QHBoxLayout()
        self.horizontalLayoutToolbar.setObjectName("horizontalLayoutToolbar")
        self.lblTitle = QLabel(AlgorithmWorkspaceArea)
        self.lblTitle.setObjectName("lblTitle")
        self.lblTitle.setStyleSheet('font: 700 15pt "Segoe UI";\n' "color: #ffffff;")

        self.horizontalLayoutToolbar.addWidget(self.lblTitle)

        self.horizontalSpacerToolbar = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayoutToolbar.addItem(self.horizontalSpacerToolbar)

        self.btnNew = QPushButton(AlgorithmWorkspaceArea)
        self.btnNew.setObjectName("btnNew")
        self.btnNew.setMinimumSize(QSize(0, 2))
        self.btnNew.setMaximumSize(QSize(16777215, 26))
        self.btnNew.setStyleSheet(
            "QPushButton {\n"
            "    min-height: 0px;\n"
            "    max-height: 24px;\n"
            "    padding: 0px 10px;\n"
            '    font: 9pt "Segoe UI";\n'
            "}"
        )

        self.horizontalLayoutToolbar.addWidget(self.btnNew)

        self.btnCascade = QPushButton(AlgorithmWorkspaceArea)
        self.btnCascade.setObjectName("btnCascade")
        self.btnCascade.setMinimumSize(QSize(0, 2))
        self.btnCascade.setMaximumSize(QSize(16777215, 26))
        self.btnCascade.setStyleSheet(
            "QPushButton {\n"
            "    min-height: 0px;\n"
            "    max-height: 24px;\n"
            "    padding: 0px 10px;\n"
            '    font: 9pt "Segoe UI";\n'
            "}"
        )

        self.horizontalLayoutToolbar.addWidget(self.btnCascade)

        self.btnTile = QPushButton(AlgorithmWorkspaceArea)
        self.btnTile.setObjectName("btnTile")
        self.btnTile.setMinimumSize(QSize(0, 2))
        self.btnTile.setMaximumSize(QSize(16777215, 26))
        self.btnTile.setStyleSheet(
            "QPushButton {\n"
            "    min-height: 0px;\n"
            "    max-height: 24px;\n"
            "    padding: 0px 10px;\n"
            '    font: 9pt "Segoe UI";\n'
            "}"
        )

        self.horizontalLayoutToolbar.addWidget(self.btnTile)

        self.btnWorkspaceLock = QToolButton(AlgorithmWorkspaceArea)
        self.btnWorkspaceLock.setObjectName("btnWorkspaceLock")
        self.btnWorkspaceLock.setMinimumSize(QSize(30, 2))
        self.btnWorkspaceLock.setMaximumSize(QSize(30, 26))
        self.btnWorkspaceLock.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btnWorkspaceLock.setStyleSheet(
            "QToolButton#btnWorkspaceLock {\n"
            "    background-color: #d7edf1;\n"
            "    border: 1px solid #6ca6b2;\n"
            "    border-radius: 5px;\n"
            "    min-height: 0px;\n"
            "    max-height: 24px;\n"
            "    padding: 0px;\n"
            "}\n"
            "QToolButton#btnWorkspaceLock:hover {\n"
            "    background-color: #ffffff;\n"
            "    border-color: #9bd3dc;\n"
            "}\n"
            "QToolButton#btnWorkspaceLock:pressed {\n"
            "    background-color: #c4e1e6;\n"
            "    border-color: #4f8e9b;\n"
            "}\n"
            "QToolButton#btnWorkspaceLock:checked {\n"
            "    background-color: #f2c14e;\n"
            "    border-color: #d49b00;\n"
            "}\n"
            "QToolButton#btnWorkspaceLock:checked:hover {\n"
            "    background-color: #ffd66a;\n"
            "    border-color: #d49b00;\n"
            "}"
        )
        icon = QIcon()
        icon.addFile(
            ":/icons/lock_open.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off
        )
        self.btnWorkspaceLock.setIcon(icon)
        self.btnWorkspaceLock.setIconSize(QSize(18, 18))
        self.btnWorkspaceLock.setCheckable(True)
        self.btnWorkspaceLock.setAutoRaise(False)

        self.horizontalLayoutToolbar.addWidget(self.btnWorkspaceLock)

        self.verticalLayout.addLayout(self.horizontalLayoutToolbar)

        self.stackWorkspaceState = QStackedWidget(AlgorithmWorkspaceArea)
        self.stackWorkspaceState.setObjectName("stackWorkspaceState")
        self.pageEmpty = QWidget()
        self.pageEmpty.setObjectName("pageEmpty")
        self.verticalLayoutEmpty = QVBoxLayout(self.pageEmpty)
        self.verticalLayoutEmpty.setObjectName("verticalLayoutEmpty")
        self.verticalSpacerEmptyTop = QSpacerItem(
            20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        )

        self.verticalLayoutEmpty.addItem(self.verticalSpacerEmptyTop)

        self.lblEmpty = QLabel(self.pageEmpty)
        self.lblEmpty.setObjectName("lblEmpty")
        self.lblEmpty.setStyleSheet("color: #a7cbd2;\n" 'font: 600 12pt "Segoe UI";')
        self.lblEmpty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.verticalLayoutEmpty.addWidget(self.lblEmpty)

        self.verticalSpacerEmptyBottom = QSpacerItem(
            20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        )

        self.verticalLayoutEmpty.addItem(self.verticalSpacerEmptyBottom)

        self.stackWorkspaceState.addWidget(self.pageEmpty)
        self.pageMdi = QWidget()
        self.pageMdi.setObjectName("pageMdi")
        self.verticalLayoutMdi = QVBoxLayout(self.pageMdi)
        self.verticalLayoutMdi.setObjectName("verticalLayoutMdi")
        self.verticalLayoutMdi.setContentsMargins(0, 0, 0, 0)
        self.mdiWorkspaces = QMdiArea(self.pageMdi)
        self.mdiWorkspaces.setObjectName("mdiWorkspaces")
        self.mdiWorkspaces.setStyleSheet(
            "QMdiArea#mdiWorkspaces {\n"
            "    background-color: #132c35;\n"
            "    border: 1px solid #315965;\n"
            "    border-radius: 6px;\n"
            "}"
        )
        self.mdiWorkspaces.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.mdiWorkspaces.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.mdiWorkspaces.setActivationOrder(
            QMdiArea.WindowOrder.ActivationHistoryOrder
        )
        self.mdiWorkspaces.setViewMode(QMdiArea.ViewMode.SubWindowView)
        self.mdiWorkspaces.setDocumentMode(True)

        self.verticalLayoutMdi.addWidget(self.mdiWorkspaces)

        self.stackWorkspaceState.addWidget(self.pageMdi)

        self.verticalLayout.addWidget(self.stackWorkspaceState)

        self.retranslateUi(AlgorithmWorkspaceArea)

        self.stackWorkspaceState.setCurrentIndex(0)

        QMetaObject.connectSlotsByName(AlgorithmWorkspaceArea)

    # setupUi

    def retranslateUi(self, AlgorithmWorkspaceArea):
        self.lblTitle.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceArea", "[AlgorithmWorkspaceArea.lblTitle]", None
            )
        )
        self.btnNew.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceArea", "[AlgorithmWorkspaceArea.btnNew]", None
            )
        )
        self.btnCascade.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceArea", "[AlgorithmWorkspaceArea.btnCascade]", None
            )
        )
        self.btnTile.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceArea", "[AlgorithmWorkspaceArea.btnTile]", None
            )
        )
        self.lblEmpty.setText(
            QCoreApplication.translate(
                "AlgorithmWorkspaceArea", "[AlgorithmWorkspaceArea.lblEmpty]", None
            )
        )
        pass

    # retranslateUi
