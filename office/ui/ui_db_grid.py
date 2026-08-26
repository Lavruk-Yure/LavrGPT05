# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'db_grid.ui'
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
    QCheckBox,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)
import resources_rc


class Ui_DbGridWindow(object):
    def setupUi(self, DbGridWindow):
        if not DbGridWindow.objectName():
            DbGridWindow.setObjectName("DbGridWindow")
        DbGridWindow.resize(1240, 900)
        DbGridWindow.setMinimumSize(QSize(900, 650))
        icon = QIcon()
        icon.addFile(
            ":/office/icons/lgeoffice_gpt_24x24.png",
            QSize(),
            QIcon.Mode.Normal,
            QIcon.State.Off,
        )
        DbGridWindow.setWindowIcon(icon)
        DbGridWindow.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        DbGridWindow.setSizeGripEnabled(True)
        self.verticalLayoutMain = QVBoxLayout(DbGridWindow)
        self.verticalLayoutMain.setObjectName("verticalLayoutMain")
        self.splitterMain = QSplitter(DbGridWindow)
        self.splitterMain.setObjectName("splitterMain")
        self.splitterMain.setOrientation(Qt.Orientation.Horizontal)
        self.splitterMain.setChildrenCollapsible(False)
        self.grpCustomers = QGroupBox(self.splitterMain)
        self.grpCustomers.setObjectName("grpCustomers")
        self.grpCustomers.setMinimumSize(QSize(320, 0))
        self.verticalLayoutCustomers = QVBoxLayout(self.grpCustomers)
        self.verticalLayoutCustomers.setObjectName("verticalLayoutCustomers")
        self.verticalLayoutCustomers.setContentsMargins(-1, 20, -1, -1)
        self.tvCustomers = QTableView(self.grpCustomers)
        self.tvCustomers.setObjectName("tvCustomers")
        self.tvCustomers.setEditTriggers(
            QAbstractItemView.EditTrigger.AnyKeyPressed
            | QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )

        self.verticalLayoutCustomers.addWidget(self.tvCustomers)

        self.layoutCustFilters = QVBoxLayout()
        self.layoutCustFilters.setSpacing(10)
        self.layoutCustFilters.setObjectName("layoutCustFilters")
        self.layoutCustFilters.setContentsMargins(6, 6, 6, 6)
        self.editCustFilterEmail = QLineEdit(self.grpCustomers)
        self.editCustFilterEmail.setObjectName("editCustFilterEmail")
        self.editCustFilterEmail.setClearButtonEnabled(True)

        self.layoutCustFilters.addWidget(self.editCustFilterEmail)

        self.editCustFilterName = QLineEdit(self.grpCustomers)
        self.editCustFilterName.setObjectName("editCustFilterName")
        self.editCustFilterName.setClearButtonEnabled(True)

        self.layoutCustFilters.addWidget(self.editCustFilterName)

        self.comboCustFilterCreated = QComboBox(self.grpCustomers)
        self.comboCustFilterCreated.addItem("")
        self.comboCustFilterCreated.addItem("")
        self.comboCustFilterCreated.addItem("")
        self.comboCustFilterCreated.addItem("")
        self.comboCustFilterCreated.setObjectName("comboCustFilterCreated")

        self.layoutCustFilters.addWidget(self.comboCustFilterCreated)

        self.layoutCustFilterButtons = QHBoxLayout()
        self.layoutCustFilterButtons.setObjectName("layoutCustFilterButtons")
        self.layoutCustFilterButtons.setContentsMargins(6, 6, 6, 6)
        self.horizontalSpacer_3 = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.layoutCustFilterButtons.addItem(self.horizontalSpacer_3)

        self.btnCustFilterAction = QPushButton(self.grpCustomers)
        self.btnCustFilterAction.setObjectName("btnCustFilterAction")

        self.layoutCustFilterButtons.addWidget(self.btnCustFilterAction)

        self.horizontalSpacer_4 = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.layoutCustFilterButtons.addItem(self.horizontalSpacer_4)

        self.layoutCustFilters.addLayout(self.layoutCustFilterButtons)

        self.layoutCustFilters.setStretch(0, 5)
        self.layoutCustFilters.setStretch(1, 5)
        self.layoutCustFilters.setStretch(2, 5)
        self.layoutCustFilters.setStretch(3, 1)

        self.verticalLayoutCustomers.addLayout(self.layoutCustFilters)

        self.layoutCustNav = QHBoxLayout()
        self.layoutCustNav.setObjectName("layoutCustNav")
        self.btnCustFirst = QPushButton(self.grpCustomers)
        self.btnCustFirst.setObjectName("btnCustFirst")

        self.layoutCustNav.addWidget(self.btnCustFirst)

        self.btnCustPrev = QPushButton(self.grpCustomers)
        self.btnCustPrev.setObjectName("btnCustPrev")

        self.layoutCustNav.addWidget(self.btnCustPrev)

        self.btnCustNext = QPushButton(self.grpCustomers)
        self.btnCustNext.setObjectName("btnCustNext")

        self.layoutCustNav.addWidget(self.btnCustNext)

        self.btnCustLast = QPushButton(self.grpCustomers)
        self.btnCustLast.setObjectName("btnCustLast")

        self.layoutCustNav.addWidget(self.btnCustLast)

        self.btnCustAdd = QPushButton(self.grpCustomers)
        self.btnCustAdd.setObjectName("btnCustAdd")
        self.btnCustAdd.setMinimumSize(QSize(0, 0))
        self.btnCustAdd.setMaximumSize(QSize(16777215, 16777215))

        self.layoutCustNav.addWidget(self.btnCustAdd)

        self.btnCustDel = QPushButton(self.grpCustomers)
        self.btnCustDel.setObjectName("btnCustDel")

        self.layoutCustNav.addWidget(self.btnCustDel)

        self.btnCustSave = QPushButton(self.grpCustomers)
        self.btnCustSave.setObjectName("btnCustSave")

        self.layoutCustNav.addWidget(self.btnCustSave)

        self.btnCustCancel = QPushButton(self.grpCustomers)
        self.btnCustCancel.setObjectName("btnCustCancel")

        self.layoutCustNav.addWidget(self.btnCustCancel)

        self.btnCustRefresh = QPushButton(self.grpCustomers)
        self.btnCustRefresh.setObjectName("btnCustRefresh")

        self.layoutCustNav.addWidget(self.btnCustRefresh)

        self.horizontalSpacer_5 = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.layoutCustNav.addItem(self.horizontalSpacer_5)

        self.btnCustOrderRequest = QPushButton(self.grpCustomers)
        self.btnCustOrderRequest.setObjectName("btnCustOrderRequest")

        self.layoutCustNav.addWidget(self.btnCustOrderRequest)

        self.verticalLayoutCustomers.addLayout(self.layoutCustNav)

        self.verticalLayoutCustomers.setStretch(0, 20)
        self.verticalLayoutCustomers.setStretch(1, 4)
        self.verticalLayoutCustomers.setStretch(2, 1)
        self.splitterMain.addWidget(self.grpCustomers)
        self.splitterRight = QSplitter(self.splitterMain)
        self.splitterRight.setObjectName("splitterRight")
        self.splitterRight.setOrientation(Qt.Orientation.Vertical)
        self.splitterRight.setChildrenCollapsible(False)
        self.grpOrders = QGroupBox(self.splitterRight)
        self.grpOrders.setObjectName("grpOrders")
        self.verticalLayoutOrders = QVBoxLayout(self.grpOrders)
        self.verticalLayoutOrders.setObjectName("verticalLayoutOrders")
        self.verticalLayoutOrders.setContentsMargins(-1, 20, -1, -1)
        self.tvOrders = QTableView(self.grpOrders)
        self.tvOrders.setObjectName("tvOrders")

        self.verticalLayoutOrders.addWidget(self.tvOrders)

        self.layoutOrdNav = QHBoxLayout()
        self.layoutOrdNav.setObjectName("layoutOrdNav")
        self.btnOrdFirst = QPushButton(self.grpOrders)
        self.btnOrdFirst.setObjectName("btnOrdFirst")

        self.layoutOrdNav.addWidget(self.btnOrdFirst)

        self.btnOrdPrev = QPushButton(self.grpOrders)
        self.btnOrdPrev.setObjectName("btnOrdPrev")

        self.layoutOrdNav.addWidget(self.btnOrdPrev)

        self.btnOrdNext = QPushButton(self.grpOrders)
        self.btnOrdNext.setObjectName("btnOrdNext")

        self.layoutOrdNav.addWidget(self.btnOrdNext)

        self.btnOrdLast = QPushButton(self.grpOrders)
        self.btnOrdLast.setObjectName("btnOrdLast")

        self.layoutOrdNav.addWidget(self.btnOrdLast)

        self.btnOrdAdd = QPushButton(self.grpOrders)
        self.btnOrdAdd.setObjectName("btnOrdAdd")

        self.layoutOrdNav.addWidget(self.btnOrdAdd)

        self.btnOrdDel = QPushButton(self.grpOrders)
        self.btnOrdDel.setObjectName("btnOrdDel")

        self.layoutOrdNav.addWidget(self.btnOrdDel)

        self.btnOrdSave = QPushButton(self.grpOrders)
        self.btnOrdSave.setObjectName("btnOrdSave")

        self.layoutOrdNav.addWidget(self.btnOrdSave)

        self.btnOrdCancel = QPushButton(self.grpOrders)
        self.btnOrdCancel.setObjectName("btnOrdCancel")

        self.layoutOrdNav.addWidget(self.btnOrdCancel)

        self.btnOrdRefresh = QPushButton(self.grpOrders)
        self.btnOrdRefresh.setObjectName("btnOrdRefresh")

        self.layoutOrdNav.addWidget(self.btnOrdRefresh)

        self.horizontalSpacer_2 = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.layoutOrdNav.addItem(self.horizontalSpacer_2)

        self.btnOrdIssue = QPushButton(self.grpOrders)
        self.btnOrdIssue.setObjectName("btnOrdIssue")

        self.layoutOrdNav.addWidget(self.btnOrdIssue)

        self.verticalLayoutOrders.addLayout(self.layoutOrdNav)

        self.splitterRight.addWidget(self.grpOrders)
        self.splitterPayLic = QSplitter(self.splitterRight)
        self.splitterPayLic.setObjectName("splitterPayLic")
        self.splitterPayLic.setOrientation(Qt.Orientation.Vertical)
        self.splitterPayLic.setChildrenCollapsible(False)
        self.grpPayments = QGroupBox(self.splitterPayLic)
        self.grpPayments.setObjectName("grpPayments")
        self.verticalLayoutPayments = QVBoxLayout(self.grpPayments)
        self.verticalLayoutPayments.setObjectName("verticalLayoutPayments")
        self.verticalLayoutPayments.setContentsMargins(-1, 20, -1, -1)
        self.chkPayUnlinked = QCheckBox(self.grpPayments)
        self.chkPayUnlinked.setObjectName("chkPayUnlinked")

        self.verticalLayoutPayments.addWidget(self.chkPayUnlinked)

        self.tvPayments = QTableView(self.grpPayments)
        self.tvPayments.setObjectName("tvPayments")

        self.verticalLayoutPayments.addWidget(self.tvPayments)

        self.layoutPayNav = QHBoxLayout()
        self.layoutPayNav.setObjectName("layoutPayNav")
        self.btnPayFirst = QPushButton(self.grpPayments)
        self.btnPayFirst.setObjectName("btnPayFirst")

        self.layoutPayNav.addWidget(self.btnPayFirst)

        self.btnPayPrev = QPushButton(self.grpPayments)
        self.btnPayPrev.setObjectName("btnPayPrev")

        self.layoutPayNav.addWidget(self.btnPayPrev)

        self.btnPayNext = QPushButton(self.grpPayments)
        self.btnPayNext.setObjectName("btnPayNext")

        self.layoutPayNav.addWidget(self.btnPayNext)

        self.btnPayLast = QPushButton(self.grpPayments)
        self.btnPayLast.setObjectName("btnPayLast")

        self.layoutPayNav.addWidget(self.btnPayLast)

        self.btnPayAdd = QPushButton(self.grpPayments)
        self.btnPayAdd.setObjectName("btnPayAdd")

        self.layoutPayNav.addWidget(self.btnPayAdd)

        self.btnPayDel = QPushButton(self.grpPayments)
        self.btnPayDel.setObjectName("btnPayDel")

        self.layoutPayNav.addWidget(self.btnPayDel)

        self.btnPaySave = QPushButton(self.grpPayments)
        self.btnPaySave.setObjectName("btnPaySave")

        self.layoutPayNav.addWidget(self.btnPaySave)

        self.btnPayCancel = QPushButton(self.grpPayments)
        self.btnPayCancel.setObjectName("btnPayCancel")

        self.layoutPayNav.addWidget(self.btnPayCancel)

        self.btnPayRefresh = QPushButton(self.grpPayments)
        self.btnPayRefresh.setObjectName("btnPayRefresh")

        self.layoutPayNav.addWidget(self.btnPayRefresh)

        self.horizontalSpacer_6 = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.layoutPayNav.addItem(self.horizontalSpacer_6)

        self.btnPayAddDialog = QPushButton(self.grpPayments)
        self.btnPayAddDialog.setObjectName("btnPayAddDialog")

        self.layoutPayNav.addWidget(self.btnPayAddDialog)

        self.horizontalSpacerPayOffice = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.layoutPayNav.addItem(self.horizontalSpacerPayOffice)

        self.btnPayLinkToOrder = QPushButton(self.grpPayments)
        self.btnPayLinkToOrder.setObjectName("btnPayLinkToOrder")

        self.layoutPayNav.addWidget(self.btnPayLinkToOrder)

        self.verticalLayoutPayments.addLayout(self.layoutPayNav)

        self.splitterPayLic.addWidget(self.grpPayments)
        self.grpLicenses = QGroupBox(self.splitterPayLic)
        self.grpLicenses.setObjectName("grpLicenses")
        self.verticalLayoutLicenses = QVBoxLayout(self.grpLicenses)
        self.verticalLayoutLicenses.setObjectName("verticalLayoutLicenses")
        self.verticalLayoutLicenses.setContentsMargins(-1, 20, -1, -1)
        self.tvLicenses = QTableView(self.grpLicenses)
        self.tvLicenses.setObjectName("tvLicenses")

        self.verticalLayoutLicenses.addWidget(self.tvLicenses)

        self.layoutLicNav = QHBoxLayout()
        self.layoutLicNav.setObjectName("layoutLicNav")
        self.btnLicFirst = QPushButton(self.grpLicenses)
        self.btnLicFirst.setObjectName("btnLicFirst")

        self.layoutLicNav.addWidget(self.btnLicFirst)

        self.btnLicPrev = QPushButton(self.grpLicenses)
        self.btnLicPrev.setObjectName("btnLicPrev")

        self.layoutLicNav.addWidget(self.btnLicPrev)

        self.btnLicNext = QPushButton(self.grpLicenses)
        self.btnLicNext.setObjectName("btnLicNext")

        self.layoutLicNav.addWidget(self.btnLicNext)

        self.btnLicLast = QPushButton(self.grpLicenses)
        self.btnLicLast.setObjectName("btnLicLast")

        self.layoutLicNav.addWidget(self.btnLicLast)

        self.btnLicAdd = QPushButton(self.grpLicenses)
        self.btnLicAdd.setObjectName("btnLicAdd")

        self.layoutLicNav.addWidget(self.btnLicAdd)

        self.btnLicDel = QPushButton(self.grpLicenses)
        self.btnLicDel.setObjectName("btnLicDel")

        self.layoutLicNav.addWidget(self.btnLicDel)

        self.btnLicSave = QPushButton(self.grpLicenses)
        self.btnLicSave.setObjectName("btnLicSave")

        self.layoutLicNav.addWidget(self.btnLicSave)

        self.btnLicCancel = QPushButton(self.grpLicenses)
        self.btnLicCancel.setObjectName("btnLicCancel")

        self.layoutLicNav.addWidget(self.btnLicCancel)

        self.btnLicRefresh = QPushButton(self.grpLicenses)
        self.btnLicRefresh.setObjectName("btnLicRefresh")

        self.layoutLicNav.addWidget(self.btnLicRefresh)

        self.horizontalSpacerLicOffice = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.layoutLicNav.addItem(self.horizontalSpacerLicOffice)

        self.btnLicEmail = QPushButton(self.grpLicenses)
        self.btnLicEmail.setObjectName("btnLicEmail")

        self.layoutLicNav.addWidget(self.btnLicEmail)

        self.verticalLayoutLicenses.addLayout(self.layoutLicNav)

        self.splitterPayLic.addWidget(self.grpLicenses)
        self.splitterRight.addWidget(self.splitterPayLic)
        self.splitterMain.addWidget(self.splitterRight)

        self.verticalLayoutMain.addWidget(self.splitterMain)

        self.layoutBottomButtons = QHBoxLayout()
        self.layoutBottomButtons.setObjectName("layoutBottomButtons")
        self.horizontalSpacer = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.layoutBottomButtons.addItem(self.horizontalSpacer)

        self.btnClose = QPushButton(DbGridWindow)
        self.btnClose.setObjectName("btnClose")

        self.layoutBottomButtons.addWidget(self.btnClose)

        self.verticalLayoutMain.addLayout(self.layoutBottomButtons)

        self.retranslateUi(DbGridWindow)

        QMetaObject.connectSlotsByName(DbGridWindow)

    # setupUi

    def retranslateUi(self, DbGridWindow):
        DbGridWindow.setWindowTitle(
            QCoreApplication.translate("DbGridWindow", "DbGrid", None)
        )
        self.grpCustomers.setTitle(
            QCoreApplication.translate(
                "DbGridWindow", "\u041a\u043b\u0456\u0454\u043d\u0442\u0438", None
            )
        )
        self.editCustFilterEmail.setPlaceholderText(
            QCoreApplication.translate(
                "DbGridWindow",
                "Email \u043c\u0456\u0441\u0442\u0438\u0442\u044c...",
                None,
            )
        )
        self.editCustFilterName.setPlaceholderText(
            QCoreApplication.translate(
                "DbGridWindow",
                "\u041f\u0406\u0411 \u043c\u0456\u0441\u0442\u0438\u0442\u044c...",
                None,
            )
        )
        self.comboCustFilterCreated.setItemText(
            0, QCoreApplication.translate("DbGridWindow", "\u0412\u0441\u0456", None)
        )
        self.comboCustFilterCreated.setItemText(
            1,
            QCoreApplication.translate(
                "DbGridWindow", "7 \u0434\u043d\u0456\u0432", None
            ),
        )
        self.comboCustFilterCreated.setItemText(
            2,
            QCoreApplication.translate(
                "DbGridWindow", "1 \u043c\u0456\u0441\u044f\u0446\u044c", None
            ),
        )
        self.comboCustFilterCreated.setItemText(
            3, QCoreApplication.translate("DbGridWindow", "1 \u0440\u0456\u043a", None)
        )

        # if QT_CONFIG(tooltip)
        self.btnCustFilterAction.setToolTip(
            QCoreApplication.translate(
                "DbGridWindow",
                "\u0417\u0430\u0441\u0442\u043e\u0441\u0443\u0432\u0430\u0442\u0438 \u0444\u0456\u043b\u044c\u0442\u0440",
                None,
            )
        )
        # endif // QT_CONFIG(tooltip)
        self.btnCustFilterAction.setText("")
        # if QT_CONFIG(tooltip)
        self.btnCustOrderRequest.setToolTip(
            QCoreApplication.translate(
                "DbGridWindow",
                "\u0417\u0430\u043c\u043e\u0432\u043b\u0435\u043d\u043d\u044f \u043b\u0456\u0446\u0435\u043d\u0437\u0456\u0457 (\u0441\u0442\u0432\u043e\u0440\u0438\u0442\u0438 \u0437\u0430\u043c\u043e\u0432\u043b\u0435\u043d\u043d\u044f \u0434\u043b\u044f \u0432\u0438\u0431\u0440\u0430\u043d\u043e\u0433\u043e \u043a\u043b\u0456\u0454\u043d\u0442\u0430)",
                None,
            )
        )
        # endif // QT_CONFIG(tooltip)
        self.grpOrders.setTitle(
            QCoreApplication.translate(
                "DbGridWindow",
                "\u0417\u0430\u043c\u043e\u0432\u043b\u0435\u043d\u043d\u044f",
                None,
            )
        )
        self.grpPayments.setTitle(
            QCoreApplication.translate(
                "DbGridWindow", "\u041f\u043b\u0430\u0442\u0435\u0436\u0456", None
            )
        )
        self.chkPayUnlinked.setText(
            QCoreApplication.translate(
                "DbGridWindow",
                "\u041d\u0435 \u043f\u0440\u0438\u0432'\u044f\u0437\u0430\u043d\u0456 \u043f\u043b\u0430\u0442\u0435\u0436\u0456",
                None,
            )
        )
        # if QT_CONFIG(tooltip)
        self.btnPayAddDialog.setToolTip(
            QCoreApplication.translate(
                "DbGridWindow",
                "\u0414\u043e\u0434\u0430\u0442\u0438 \u043f\u043b\u0430\u0442\u0456\u0436 (\u0447\u0435\u0440\u0435\u0437 \u0444\u043e\u0440\u043c\u0443)",
                None,
            )
        )
        # endif // QT_CONFIG(tooltip)
        # if QT_CONFIG(tooltip)
        self.btnPayLinkToOrder.setToolTip(
            QCoreApplication.translate(
                "DbGridWindow",
                "\u041f\u0440\u0438\u0432'\u044f\u0437\u0430\u0442\u0438 \u043f\u043b\u0430\u0442\u0456\u0436 \u0434\u043e \u0437\u0430\u043c\u043e\u0432\u043b\u0435\u043d\u043d\u044f",
                None,
            )
        )
        # endif // QT_CONFIG(tooltip)
        self.btnPayLinkToOrder.setText("")
        self.grpLicenses.setTitle(
            QCoreApplication.translate(
                "DbGridWindow", "\u041b\u0456\u0446\u0435\u043d\u0437\u0456\u0457", None
            )
        )
        # if QT_CONFIG(tooltip)
        self.btnLicEmail.setToolTip(
            QCoreApplication.translate(
                "DbGridWindow",
                "\u041d\u0430\u0434\u0456\u0441\u043b\u0430\u0442\u0438 e-Mail",
                None,
            )
        )
        # endif // QT_CONFIG(tooltip)
        self.btnClose.setText(
            QCoreApplication.translate(
                "DbGridWindow", "\u0417\u0430\u043a\u0440\u0438\u0442\u0438", None
            )
        )

    # retranslateUi
