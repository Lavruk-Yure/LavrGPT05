# core/orders_page.py
# -*- coding: utf-8 -*-
"""Головна сторінка ордерів і broker positions LGE.

Модуль показує cTrader/IB позиції, virtual legs, reconciliation evidence та
операції Open/Close/SL/TP через shared RuntimeEngine. Ручна ширина колонок
таблиці позицій зберігається як Session UI-state і відновлюється при новому
запуску. UI не обходить RuntimeEngine та не підміняє broker/runtime істину.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import UTC, datetime

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMessageBox,
    QSizePolicy,
    QTreeWidgetItem,
    QWidget,
)

from core import ctrader_symbols as ctr_symbols
from core.lang_manager import LangManager
from core.table_column_widths import TableColumnWidthPersistence
from core.ui_translator import UITranslator
from engine.broker_order_identity import (
    ORDER_CONTROL_MODE_AUTO,
    ORDER_CONTROL_MODE_MANUAL,
    ORDER_CONTROL_MODE_SEMI,
    ORDER_CONTROL_MODES,
    get_broker_order_control_mode,
)
from engine.ib_fx_external_exposure import (
    IB_FX_EXTERNAL_EXPOSURE_STALE,
    IBFxExternalExposureExecutionBlockedError,
)
from engine.ib_order_errors import (
    IBVirtualLegCloseConfirmationPendingError,
)
from engine.runtime_constants import (
    IB_BROKER_POSITION_KIND_VIRTUAL_FX,
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_LEG_STATUS_PARTIALLY_CLOSED,
    IB_PROTECTION_STATUS_BLOCKED,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_PROTECTION_STATUS_NONE,
    IB_PROTECTION_STATUS_PARTIAL,
    IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS,
    IB_POSITION_GROUP_MODE_NET_ONLY,
    IB_RECONCILIATION_STATUS_BLOCKED,
    IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING,
    IB_RECONCILIATION_STATUS_RECONCILED,
    IB_RECONCILIATION_STATUS_RECONCILED_MANUAL,
    IB_RECONCILIATION_STATUS_UNRECONCILED,
)
from ui.ui_orders_page import Ui_OrdersPage

logger = logging.getLogger(__name__)


COL_ID = 0
COL_SYMBOL = 1
COL_TYPE = 2
COL_SIDE = 3
COL_VOLUME = 4
COL_ENTRY = 5
COL_CURRENT = 6
COL_SL = 7
COL_TP = 8
COL_PNL = 9
COL_RECONCILIATION = 10
COL_SOURCE = 11
COL_OPENED = 12
COLUMN_COUNT = 13

POSITION_TREE_COLUMN_WIDTHS = {
    COL_ID: 105,
    COL_SYMBOL: 60,
    COL_TYPE: 95,
    COL_SIDE: 68,
    COL_VOLUME: 58,
    COL_ENTRY: 82,
    COL_CURRENT: 82,
    COL_SL: 54,
    COL_TP: 54,
    COL_PNL: 78,
    COL_RECONCILIATION: 94,
    COL_SOURCE: 65,
    COL_OPENED: 90,
}

ROLE_ROW_KIND = int(Qt.ItemDataRole.UserRole)
ROLE_BROKER_POSITION_ID = ROLE_ROW_KIND + 1
ROLE_POSITION_UID = ROLE_ROW_KIND + 2
ROLE_TRADE_UID = ROLE_ROW_KIND + 3
ROLE_GROUP_MODE = ROLE_ROW_KIND + 4
ROLE_BROKER_POSITION_KIND = ROLE_ROW_KIND + 5
ROLE_RECONCILIATION_STATUS = ROLE_ROW_KIND + 6
ROLE_LEG_STATUS = ROLE_ROW_KIND + 7
ROLE_OPERATIONS_ENABLED = ROLE_ROW_KIND + 8
ROLE_RAW_SL = ROLE_ROW_KIND + 9
ROLE_RAW_TP = ROLE_ROW_KIND + 10
ROLE_STABLE_KEY = ROLE_ROW_KIND + 11
ROLE_SYMBOL = ROLE_ROW_KIND + 12
ROLE_SIDE = ROLE_ROW_KIND + 13
ROLE_VOLUME = ROLE_ROW_KIND + 14
ROLE_ORDER_ORIGIN = ROLE_ROW_KIND + 15
ROLE_PNL_VALUE = ROLE_ROW_KIND + 16
ROLE_PNL_APPROXIMATE = ROLE_ROW_KIND + 17
ROLE_PNL_CURRENCY = ROLE_ROW_KIND + 18
ROLE_TOOLTIP_MESSAGES = ROLE_ROW_KIND + 19
ROLE_TOOLTIP_ALL_COLUMNS = ROLE_ROW_KIND + 20
ROLE_EXTERNAL_EXPOSURE_STATUS = ROLE_ROW_KIND + 21
ROLE_EXTERNAL_PROTECTIVE_ORDERS = ROLE_ROW_KIND + 22
ROLE_ACCOUNT_ID = ROLE_ROW_KIND + 23

ROW_KIND_POSITION = "POSITION"
ROW_KIND_GROUP = "GROUP"
ROW_KIND_LEG = "LEG"
ROW_KIND_BROKER_RESIDUAL = "BROKER_RESIDUAL"

ORDER_ORIGIN_BROKER = "BROKER"


class OrdersPage(QWidget):
    """
    Сторінка ручної торгівлі.
    """

    close_requested = Signal()

    def __init__(
        self,
        lang_mgr: LangManager,
        parent: QWidget | None = None,
    ) -> None:
        """
        Ініціалізувати OrdersPage.
        """
        super().__init__(parent)

        self._lang_mgr = lang_mgr

        self._runtime_engine = None
        self._last_ib_position_group_snapshot = None

        self.ui = Ui_OrdersPage()
        self.ui.setupUi(self)

        self._translator = UITranslator(self._lang_mgr)

        self._register_i18n_keys()
        self._translator.apply(self)

        self._init_ui()
        self._table_column_width_persistence = TableColumnWidthPersistence(
            self.ui.tblOpenPositions,
            "orders_page.open_positions",
            tuple(
                POSITION_TREE_COLUMN_WIDTHS[column]
                for column in range(COLUMN_COUNT)
            ),
        )
        self._connect_signals()

    def _register_i18n_keys(self) -> None:
        """
        Зареєструвати LANG-ключі OrdersPage.
        """
        self._lang_mgr.tr("OrdersPage.header", "Manual trading orders")
        self._lang_mgr.tr("OrdersPage.lblSymbol", "Trading symbol")
        self._lang_mgr.tr("OrdersPage.lblSide", "Trade direction")
        self._lang_mgr.tr("OrdersPage.lblLots", "Trading lot size")
        self._lang_mgr.tr("OrdersPage.lblStopLoss", "Stop Loss")
        self._lang_mgr.tr("OrdersPage.lblTakeProfit", "Take Profit")
        self._lang_mgr.tr("OrdersPage.lblComment", "Comment")

        self._lang_mgr.tr("OrdersPage.btnPlaceOrder", "Open")
        self._lang_mgr.tr("OrdersPage.btnClosePosition", "Close position")
        self._lang_mgr.tr("OrdersPage.btnRefreshPositions", "Refresh")
        self._lang_mgr.tr(
            "OrdersPage.btnModifySlTp",
            "Modify SL/TP",
        )
        self._lang_mgr.tr(
            "OrdersPage.btnResolveReconciliation",
            "Resolve reconciliation",
        )
        self._lang_mgr.tr("CommonConfirmDialog.btnYes", "Yes")
        self._lang_mgr.tr("CommonConfirmDialog.btnNo", "No")
        self._lang_mgr.tr("OrdersPage.btnExitOrders", "Exit")

        self._lang_mgr.tr(
            "OrdersPage.titleExternalExposureBlocked",
            "External IB FX exposure",
        )
        self._lang_mgr.tr(
            "OrdersPage.msgExternalExposureOrderBlocked",
            "LGE EXCLUSIVE blocked a new LGE order before Trade persistence "
            "and before the broker request. Account: {account_id}; symbol: "
            "{symbol}; external exposure: {side} {volume}; evidence: "
            "{evidence}. Select the external exposure row and click "
            "Resolve reconciliation to see the exact TWS order identifiers. "
            "Resolve the external position and its protection, then press "
            "Refresh. Go to Monitoring to inspect the WSP and its journal.",
        )
        self._lang_mgr.tr(
            "OrdersPage.statusExternalExposureResolution",
            "LGE EXCLUSIVE: resolve external IB FX exposure for account "
            "{account_id}, symbol {symbol}; then press Refresh.",
        )
        self._lang_mgr.tr(
            "OrdersPage.titleExternalExposureDetails",
            "External IB FX exposure details",
        )
        self._lang_mgr.tr(
            "OrdersPage.msgExternalExposureDetailsIntro",
            "Account: {account_id}\nSymbol: {symbol}\nExternal exposure: "
            "{side} {volume}\nEvidence: {evidence}",
        )
        self._lang_mgr.tr(
            "OrdersPage.msgExternalExposureOrdersHeader",
            "Current foreign-client protective orders received from IB:",
        )
        self._lang_mgr.tr(
            "OrdersPage.msgExternalExposureOrderLine",
            "{order_type} {action} {quantity} @ {price}; orderId={order_id}; "
            "permId={perm_id}; parentId={parent_id}; clientId={client_id}; "
            "OCA={oca_group}; status={status}; TIF={tif}",
        )
        self._lang_mgr.tr(
            "OrdersPage.msgExternalExposureNoCurrentOrders",
            "No exact protective-order rows are available in the current IB "
            "snapshot. Do not cancel an order by guess; verify the position "
            "and orders in TWS or an IB statement.",
        )
        self._lang_mgr.tr(
            "OrdersPage.msgExternalExposureResolutionSteps",
            "These broker orders are read-only in LGE. Find them in TWS "
            "Orders by symbol, order type, price, permId, parentId, clientId "
            "and OCA. IB can report orderId=0 for another client; in that "
            "case use permId/clientId/parentId/OCA. LGE does not invent TWS "
            "row numbers such as 6.1/6.2. If the external position still "
            "exists, close or resolve the position and its protection. If no "
            "position exists, cancel only the matching orphaned protection. "
            "Then press Refresh. To inspect the WSP and its journal, go to "
            "Monitoring.",
        )
        self._lang_mgr.tr(
            "OrdersPage.statusExternalExposureSelected",
            "External IB exposure {symbol}: {side} {volume}; evidence "
            "{evidence}. Press Resolve reconciliation to view the exact TWS "
            "order identifiers.",
        )
        self._lang_mgr.tr("OrdersPage.titleClosePosition", "Close position")
        self._lang_mgr.tr(
            "OrdersPage.msgClosePositionNotImplemented",
            "Close position is not implemented yet.",
        )
        self._lang_mgr.tr(
            "OrdersPage.msgConfirmClosePosition",
            "Close selected position {position_id}?",
        )
        self._lang_mgr.tr(
            "OrdersPage.statusPositionClosed",
            "Position closed. broker_position_id={position_id}",
        )
        self._lang_mgr.tr(
            "OrdersPage.statusPositionCloseSent",
            "Close sent, but position is still visible. "
            "broker_position_id={position_id}",
        )
        self._lang_mgr.tr(
            "OrdersPage.statusPositionCloseFailed",
            "Close position failed: {error}",
        )

        self._lang_mgr.tr(
            "OrdersPage.titleModifySlTp",
            "Modify SL/TP",
        )
        self._lang_mgr.tr(
            "OrdersPage.msgSelectPositionForModify",
            "Select a position to modify SL/TP.",
        )
        self._lang_mgr.tr(
            "OrdersPage.statusUpdated",
            "Updated",
        )
        self._lang_mgr.tr(
            "OrdersPage.statusSlTpModifyFailed",
            "Modify SL/TP failed: {error}",
        )

        self._lang_mgr.tr(
            "OrdersPage.msgSelectPosition",
            "Select a position to close.",
        )
        self._lang_mgr.tr(
            "OrdersPage.titleResolveReconciliation",
            "Resolve IB reconciliation",
        )
        self._lang_mgr.tr(
            "OrdersPage.msgSelectCloseEvidenceMissingLeg",
            "Select one LGE LEG with Close confirmation missing.",
        )
        self._lang_mgr.tr(
            "OrdersPage.msgResolveCloseEvidenceFacts",
            "Symbol: {symbol}\n"
            "LGE LEG: {side} {volume}\n"
            "Broker position: absent / 0\n"
            "Active SL/TP: absent\n"
            "Close execution: not found\n"
            "Current state: {status}\n\n"
            "Proceed to the final confirmation?",
        )
        self._lang_mgr.tr(
            "OrdersPage.msgResolveCloseEvidenceFinal",
            "This action does not close a broker position and does not send "
            "any order to IB.\n\n"
            "It only confirms that the broker position was already closed "
            "while exact execution evidence is unavailable.\n\n"
            "Confirm manual recovery for {symbol} {side} {volume}?",
        )
        self._lang_mgr.tr(
            "OrdersPage.statusCloseEvidenceResolved",
            "Manual IB reconciliation completed. No broker order was sent. "
            "position_uid={position_uid}",
        )
        self._lang_mgr.tr(
            "OrdersPage.statusCloseEvidenceResolveFailed",
            "Manual IB reconciliation failed: {error}",
        )

        self._lang_mgr.tr("OrdersPage.grpOpenPositions", "Trading positions")
        self._lang_mgr.tr("OrdersPage.lblPositionFilter", "Filter")
        self._lang_mgr.tr("OrdersPage.filterManual", "Manual")
        self._lang_mgr.tr("OrdersPage.filterSemi", "Semi-Auto")
        self._lang_mgr.tr("OrdersPage.filterAuto", "Auto")
        self._lang_mgr.tr("OrdersPage.filterBroker", "External at broker")
        self._lang_mgr.tr("OrdersPage.statusReady", "Ready")

        self._lang_mgr.tr("OrdersPage.titleRuntime", "Runtime")
        self._lang_mgr.tr("OrdersPage.titleManualOrder", "Manual order")

        self._lang_mgr.tr(
            "OrdersPage.msgRuntimeNotInitialized",
            "RuntimeEngine is not initialized.",
        )
        self._lang_mgr.tr(
            "OrdersPage.msgSlTpNumeric",
            "Stop Loss / Take Profit must be numeric.",
        )

        self._lang_mgr.tr(
            "OrdersPage.statusOrderOpened",
            "Order opened. position_uid={position_uid}",
        )
        self._lang_mgr.tr(
            "OrdersPage.statusOrderSentPositionNotFound",
            "Order sent. Runtime position was not found yet.",
        )
        self._lang_mgr.tr(
            "OrdersPage.statusPositionsRefreshed",
            "Trading positions refreshed: {count}",
        )
        self._lang_mgr.tr(
            "OrdersPage.statusPartialProtectionWarning",
            "WARNING: {details}",
        )
        self._lang_mgr.tr(
            "OrdersPage.statusAdditionalWarnings",
            "and {count} more",
        )
        self._lang_mgr.tr(
            "OrdersPage.statusProtectionMixed",
            "{leg} mixed {quantity}/{volume}",
        )
        self._lang_mgr.tr(
            "OrdersPage.statusRefreshFailed",
            "Refresh positions failed: {error}",
        )

        self._lang_mgr.tr("OrdersPage.colPositionId", "ID")
        self._lang_mgr.tr("OrdersPage.colSymbol", "Pair")
        self._lang_mgr.tr("OrdersPage.colType", "Type")
        self._lang_mgr.tr("OrdersPage.colSide", "Direction")
        self._lang_mgr.tr("OrdersPage.colVolume", "Volume")
        self._lang_mgr.tr("OrdersPage.colEntry", "Entry price")
        self._lang_mgr.tr("OrdersPage.colCurrent", "Current price")
        self._lang_mgr.tr("OrdersPage.colSL", "SL")
        self._lang_mgr.tr("OrdersPage.colTP", "TP")
        self._lang_mgr.tr("OrdersPage.colPnl", "PnL")
        self._lang_mgr.tr(
            "OrdersPage.colReconciliation",
            "Reconciliation",
        )
        self._lang_mgr.tr("OrdersPage.colSource", "Source")
        self._lang_mgr.tr("OrdersPage.colOpened", "Time")

        self._lang_mgr.tr("OrdersPage.typeBrokerPosition", "Broker position")
        self._lang_mgr.tr("OrdersPage.typeIbNet", "IB NET")
        self._lang_mgr.tr("OrdersPage.typeVirtualFx", "Virtual FX")
        self._lang_mgr.tr("OrdersPage.typeNetOnly", "NET ONLY")
        self._lang_mgr.tr("OrdersPage.typeVirtualLeg", "LGE LEG")
        self._lang_mgr.tr(
            "OrdersPage.typeBrokerResidual",
            "External IB exposure",
        )
        self._lang_mgr.tr("OrdersPage.valueMultiple", "MULTI")
        self._lang_mgr.tr(
            "OrdersPage.tooltipMultipleProtection",
            "Protection is defined separately for each virtual leg.",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipCalculatedLegPnl",
            "Calculated virtual-leg PnL in the quote currency, not IB reqPnLSingle.",
        )
        self._lang_mgr.tr(
            "OrdersPage.msgSelectVirtualLeg",
            "Select a specific virtual leg.",
        )
        self._lang_mgr.tr(
            "OrdersPage.msgLegOperationsDisabled",
            "Virtual-leg operations are disabled for this row.",
        )
        self._lang_mgr.tr(
            "OrdersPage.msgConfirmModifyLeg",
            "Modify virtual leg {position_uid}: {side} {volume}, "
            "SL={stop_loss}, TP={take_profit}?",
        )
        self._lang_mgr.tr(
            "OrdersPage.msgConfirmCloseLeg",
            "Close virtual leg {position_uid}: {side} {volume}, "
            "SL={stop_loss}, TP={take_profit}?",
        )
        self._lang_mgr.tr(
            "OrdersPage.statusPositionGroupsRefreshed",
            "IB position groups refreshed: {groups}; open legs: {legs}",
        )
        self._lang_mgr.tr(
            "OrdersPage.statusReconciliationWarning",
            "IB reconciliation warning: {details}",
        )
        self._lang_mgr.tr(
            "OrdersPage.statusUnmappedProtection",
            "unmapped protection: {ids}",
        )
        self._lang_mgr.tr(
            "OrdersPage.reconciliationReconciled",
            "Reconciled",
        )
        self._lang_mgr.tr(
            "OrdersPage.reconciliationReconciledManual",
            "Reconciled manually",
        )
        self._lang_mgr.tr(
            "OrdersPage.reconciliationUnreconciled",
            "Unreconciled",
        )
        self._lang_mgr.tr(
            "OrdersPage.reconciliationBlocked",
            "Blocked",
        )
        self._lang_mgr.tr(
            "OrdersPage.reconciliationCloseEvidenceMissing",
            "Close confirmation missing",
        )
        self._lang_mgr.tr(
            "OrdersPage.statusSelectedLegOperationsDisabled",
            "Selected virtual leg cannot be modified or closed: {status}",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipLegPositionUid",
            "Position UID: {value}",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipLegTradeUid",
            "Trade UID: {value}",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipLegStatus",
            "Leg status: {value}",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipProtectionStatus",
            "Protection status: {value}",
        )
        self._lang_mgr.tr(
            "OrdersPage.legStatusOpen",
            "Open",
        )
        self._lang_mgr.tr(
            "OrdersPage.legStatusPartiallyClosed",
            "Partially closed",
        )
        self._lang_mgr.tr(
            "OrdersPage.legStatusClosed",
            "Closed",
        )
        self._lang_mgr.tr(
            "OrdersPage.protectionStatusNone",
            "None",
        )
        self._lang_mgr.tr(
            "OrdersPage.protectionStatusPartial",
            "Partial",
        )
        self._lang_mgr.tr(
            "OrdersPage.protectionStatusComplete",
            "Complete",
        )
        self._lang_mgr.tr(
            "OrdersPage.protectionStatusBlocked",
            "Blocked",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipParentExecutionOutsideHistory",
            "Parent MARKET execution is outside current IB history; "
            "persisted reconciled entry was retained",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipParentExecutionMissing",
            "Parent MARKET execution was not found",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipCloseEvidenceMissing",
            "Persisted protective orders are not active and no matching "
            "close execution was found",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipUnmappedProtectiveOrder",
            "Unmapped protective order exists for virtual-leg group",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipExternalProtectionWithoutObservation",
            "External TWS protective orders are active, but external "
            "exposure cannot be derived because the IB CASH Forex "
            "position observation is absent.",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipBrokerNetWithoutVirtualLegs",
            "Broker net position has no LGE virtual legs",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipAtLeastOneLegUnreconciled",
            "At least one virtual leg is not reconciled",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipBrokerNetSnapshotAmbiguous",
            "IB broker net position snapshot is ambiguous",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipBrokerNetMismatch",
            "Signed sum of open virtual legs differs from IB net position: "
            "legs={legs}, broker={broker}, position={position}",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipVirtualFxOffsetStable",
            "IB CASH Forex Virtual FX observation offset remained stable "
            "across the exact LGE operation",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipVirtualFxOffsetChanged",
            "IB CASH Forex Virtual FX observation offset changed "
            "unexpectedly: expected_offset={expected_offset}, "
            "actual_offset={actual_offset}, executions={executions}, "
            "virtual_fx={virtual_fx}, position={position}",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipVirtualFxReconciledByExecutions",
            "IB CASH Forex position row is a Virtual FX observation; "
            "LGE leg state was reconciled by exact order executions",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipVirtualFxCurrentExposure",
            "IB CASH Forex Virtual FX observation follows current open LGE "
            "exposure; older CLOSED-leg executions were excluded",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipVirtualFxZeroReset",
            "IB CASH Forex Virtual FX observation is zero/reset; LGE leg "
            "state was reconciled by exact order identity and persisted "
            "evidence",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipBrokerResidual",
            "IB CASH Forex broker net differs from exact OPEN LGE legs; "
            "the difference is represented as a read-only broker residual: "
            "residual={residual}, managed={managed}, broker={broker}, "
            "position={position}",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipExternalExecutionResidual",
            "IB CASH Forex external exposure is represented from exact "
            "non-LGE executions, not from Virtual FX minus "
            "managed-leg arithmetic: external={external}, "
            "virtual_fx_minus_managed={virtual_fx_minus_managed}, "
            "managed={managed}, virtual_fx={virtual_fx}, "
            "position={position}",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipPersistedExternalExecutionResidual",
            "IB CASH Forex external exposure is retained from persisted "
            "exact evidence because the current execution snapshot no "
            "longer contains that non-LGE execution: external={external}, "
            "virtual_fx_minus_managed={virtual_fx_minus_managed}, "
            "managed={managed}, virtual_fx={virtual_fx}, "
            "position={position}",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipVirtualFxQuantityMismatch",
            "IB Virtual FX quantity differs from recognized LGE executions: "
            "cumulative_executions={cumulative_executions}, "
            "current_exposure_executions={current_exposure_executions}, "
            "virtual_fx={virtual_fx}, position={position}",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipGroupShowsBrokerNetAndResidual",
            "The group row shows the current IB broker net. Exact LGE legs "
            "and the read-only broker residual are shown as separate child "
            "rows.",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipVirtualFxDerivedFromLegs",
            "IB CASH Forex position row is a Virtual FX observation; "
            "displayed side and volume are derived from reconciled open "
            "LGE legs.",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipVirtualFxAbsentDerivedFromLegs",
            "IB CASH Forex position row is absent; displayed side and volume "
            "are derived from reconciled open LGE legs.",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipVirtualFxBrokerFieldsHidden",
            "Broker entry price, PnL and opened time are hidden because the "
            "Virtual FX observation is not terminal position truth.",
        )
        self._lang_mgr.tr(
            "OrdersPage.tooltipBrokerResidualReadOnly",
            "Read-only broker exposure outside exact LGE virtual legs. "
            "Modify and Close are disabled for this row. "
            "broker_net={broker_net}; managed_open_legs={managed_open_legs}; "
            "broker_residual={broker_residual}.",
        )

    def apply_translation(self) -> None:
        """Reapply widget and dynamic table translations."""
        self._translator.apply(self)
        self._apply_table_header_translations()
        self._retranslate_current_ib_reconciliation_values()
        self._retranslate_current_ib_tooltips()
        self._refresh_ib_status_for_current_selection()

    def _apply_table_header_translations(self) -> None:
        """Translate the dynamic QTreeWidget column headers."""
        self.ui.tblOpenPositions.setHeaderLabels(
            [
                self._lang_mgr.tr("OrdersPage.colPositionId", "ID"),
                self._lang_mgr.tr("OrdersPage.colSymbol", "Pair"),
                self._lang_mgr.tr("OrdersPage.colType", "Type"),
                self._lang_mgr.tr("OrdersPage.colSide", "Direction"),
                self._lang_mgr.tr("OrdersPage.colVolume", "Volume"),
                self._lang_mgr.tr("OrdersPage.colEntry", "Entry price"),
                self._lang_mgr.tr("OrdersPage.colCurrent", "Current price"),
                self._lang_mgr.tr("OrdersPage.colSL", "SL"),
                self._lang_mgr.tr("OrdersPage.colTP", "TP"),
                self._lang_mgr.tr("OrdersPage.colPnl", "PnL"),
                self._lang_mgr.tr(
                    "OrdersPage.colReconciliation",
                    "Reconciliation",
                ),
                self._lang_mgr.tr("OrdersPage.colSource", "Source"),
                self._lang_mgr.tr("OrdersPage.colOpened", "Time"),
            ]
        )

    def _init_ui(self) -> None:
        """Initialize manual-order controls and the position tree."""
        self.ui.cmbSymbol.clear()
        self.ui.cmbSymbol.addItems(ctr_symbols.list_enabled_symbols())
        self.ui.cmbSymbol.setCurrentText("EURUSD")

        self.ui.cmbSide.clear()
        self.ui.cmbSide.addItem("BUY", "BUY")
        self.ui.cmbSide.addItem("SELL", "SELL")

        self.ui.spinLots.setDecimals(2)
        self.ui.spinLots.setMinimum(0.01)
        self.ui.spinLots.setMaximum(100.00)
        self.ui.spinLots.setSingleStep(0.01)
        self.ui.spinLots.setValue(0.01)
        self.ui.spinLots.setMinimumHeight(26)

        self.ui.editComment.setText("LGE manual UI order")

        self.ui.chkFilterManual.setChecked(True)
        self.ui.chkFilterSemi.setChecked(True)
        self.ui.chkFilterAuto.setChecked(True)
        self.ui.chkFilterBroker.setChecked(True)

        tree = self.ui.tblOpenPositions
        tree.setColumnCount(COLUMN_COUNT)
        self._apply_table_header_translations()

        header = tree.header()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(36)

        for column_index, width in POSITION_TREE_COLUMN_WIDTHS.items():
            header.setSectionResizeMode(
                column_index,
                QHeaderView.ResizeMode.Interactive,
            )
            tree.setColumnWidth(column_index, width)

        tree.setRootIsDecorated(True)
        tree.setItemsExpandable(True)
        tree.setExpandsOnDoubleClick(True)
        tree.setUniformRowHeights(True)
        tree.setAllColumnsShowFocus(True)
        tree.setIndentation(18)
        tree.setWordWrap(False)
        tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        tree.installEventFilter(self)
        tree.viewport().installEventFilter(self)
        tree.clear()

        self.ui.btnModifySlTp.setEnabled(False)
        self.ui.btnResolveReconciliation.setEnabled(False)
        self.ui.btnClosePosition.setEnabled(False)

        self.ui.lblOrdersStatus.setMinimumWidth(0)
        self.ui.lblOrdersStatus.setWordWrap(False)
        self.ui.lblOrdersStatus.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self.ui.statusSpacer.changeSize(
            0,
            0,
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Minimum,
        )
        self.ui.statusLayout.setStretch(0, 1)
        self.ui.statusLayout.setStretch(1, 0)
        self.ui.statusLayout.setStretch(2, 0)
        self.ui.statusLayout.invalidate()
        self.ui.lblOrdersStatus.setText(
            self._lang_mgr.tr("OrdersPage.statusReady", "Ready")
        )

        self.ui.lblPnlSummary.setMinimumWidth(130)
        self.ui.lblPnlSummary.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.ui.lblPnlSummary.setStyleSheet("font-weight: 600;")
        self._set_pnl_summary(None)

    def _connect_signals(self) -> None:
        """
        Підключити сигнали.
        """
        self.ui.btnPlaceOrder.clicked.connect(self._on_place_order_clicked)
        self.ui.btnClosePosition.clicked.connect(self._on_close_position_clicked)
        self.ui.btnRefreshPositions.clicked.connect(self._on_refresh_clicked)
        self.ui.btnModifySlTp.clicked.connect(self._on_modify_sl_tp_clicked)
        self.ui.btnResolveReconciliation.clicked.connect(
            self._on_resolve_reconciliation_clicked
        )
        self.ui.btnExitOrders.clicked.connect(self._on_exit_clicked)

        self.ui.tblOpenPositions.itemSelectionChanged.connect(
            self._on_position_selection_changed
        )
        self.ui.tblOpenPositions.currentItemChanged.connect(
            self._on_position_current_item_changed
        )

        for checkbox in (
            self.ui.chkFilterManual,
            self.ui.chkFilterSemi,
            self.ui.chkFilterAuto,
            self.ui.chkFilterBroker,
        ):
            checkbox.toggled.connect(self._on_position_filter_changed)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Clear the position selection by Escape or an empty-tree click."""
        tree = self.ui.tblOpenPositions

        if (
            watched is tree
            and isinstance(event, QKeyEvent)
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape
        ):
            self._clear_position_selection()
            return True

        if (
            watched is tree.viewport()
            and isinstance(event, QMouseEvent)
            and event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
            and tree.itemAt(event.position().toPoint()) is None
        ):
            tree.setFocus(Qt.FocusReason.MouseFocusReason)
            self._clear_position_selection()
            return True

        return super().eventFilter(watched, event)

    def _clear_position_selection(self) -> None:
        """Clear the current position row and reset selection-driven controls."""
        tree = self.ui.tblOpenPositions
        tree.clearSelection()
        tree.setCurrentItem(None)
        self._on_position_selection_changed()

    def _on_position_current_item_changed(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        """Prevent a read-only row from retaining the current-row highlight."""
        if current is None or self._tree_item_selection_allowed(current):
            return

        self._clear_position_selection()

    def _on_place_order_clicked(self) -> None:
        """
        Відкрити manual MARKET order через RuntimeEngine.
        """
        if self._runtime_engine is None:
            QMessageBox.warning(
                self,
                self._lang_mgr.tr("OrdersPage.titleRuntime", "Runtime"),
                self._lang_mgr.tr(
                    "OrdersPage.msgRuntimeNotInitialized",
                    "RuntimeEngine is not initialized.",
                ),
            )
            return

        symbol_name = self.ui.cmbSymbol.currentText().strip().upper()
        side = str(self.ui.cmbSide.currentData() or "").strip().upper()

        if not side:
            side = self.ui.cmbSide.currentText().strip().upper()

        lots = float(self.ui.spinLots.value())

        try:
            stop_loss = self._read_optional_float(
                self.ui.editStopLoss.text(),
            )
            take_profit = self._read_optional_float(
                self.ui.editTakeProfit.text(),
            )
        except ValueError:
            QMessageBox.warning(
                self,
                self._lang_mgr.tr(
                    "OrdersPage.titleManualOrder",
                    "Manual order",
                ),
                self._lang_mgr.tr(
                    "OrdersPage.msgSlTpNumeric",
                    "Stop Loss / Take Profit must be numeric.",
                ),
            )
            return

        comment = self.ui.editComment.text().strip()

        try:
            result = self._runtime_engine.place_manual_market_order(
                symbol_name=symbol_name,
                side=side,
                lots=lots,
                stop_loss=stop_loss,
                take_profit=take_profit,
                comment=comment,
                control_mode=ORDER_CONTROL_MODE_MANUAL,
            )
        except IBFxExternalExposureExecutionBlockedError as exc:
            logger.warning("Manual MARKET order blocked by LGE EXCLUSIVE.")
            exposure = exc.matching_exposure
            account_id = (
                exposure.account_id if exposure is not None else "—"
            )
            blocked_symbol = (
                exposure.symbol_name if exposure is not None else symbol_name
            )
            side_text = exposure.side if exposure is not None else "—"
            volume_text = (
                f"{exposure.volume:g}" if exposure is not None else "—"
            )
            evidence_text = self._format_external_exposure_evidence_status(
                exposure.evidence_status
                if exposure is not None
                else exc.reason_code
            )
            message = self._lang_mgr.tr(
                "OrdersPage.msgExternalExposureOrderBlocked",
                "LGE EXCLUSIVE blocked a new LGE order before Trade "
                "persistence and before the broker request. Account: "
                "{account_id}; symbol: {symbol}; external exposure: "
                "{side} {volume}; evidence: {evidence}. Select the "
                "external exposure row and click Resolve reconciliation to "
                "see the exact TWS order identifiers. Resolve the external "
                "position and its protection, then press Refresh. Go to "
                "Monitoring to inspect the WSP and its journal.",
            ).format(
                account_id=account_id,
                symbol=blocked_symbol,
                side=side_text,
                volume=volume_text,
                evidence=evidence_text,
            )
            QMessageBox.warning(
                self,
                self._lang_mgr.tr(
                    "OrdersPage.titleExternalExposureBlocked",
                    "External IB FX exposure",
                ),
                message,
            )
            self.prepare_external_exposure_resolution(
                account_id=account_id,
                symbol_name=blocked_symbol,
            )
            return
        except Exception as exc:  # noqa
            logger.exception("Manual MARKET order failed.")
            QMessageBox.warning(
                self,
                self._lang_mgr.tr(
                    "OrdersPage.titleManualOrder",
                    "Manual order",
                ),
                str(exc),
            )
            return

        position_uid = result.get("position_uid", "")

        if position_uid:
            text = self._lang_mgr.tr(
                "OrdersPage.statusOrderOpened",
                "Order opened. position_uid={position_uid}",
            ).format(position_uid=position_uid)
            self.ui.lblOrdersStatus.setText(text)
        else:
            self.ui.lblOrdersStatus.setText(
                self._lang_mgr.tr(
                    "OrdersPage.statusOrderSentPositionNotFound",
                    "Order sent. Runtime position was not found yet.",
                )
            )

        self._on_refresh_clicked()

    def activate_page(self) -> bool:
        """Refresh positions when OrdersPage becomes the active page."""
        return self.refresh_positions()

    def prepare_external_exposure_resolution(
        self,
        *,
        account_id: str,
        symbol_name: str,
        refresh: bool = True,
    ) -> bool:
        """Focus the read-only external row and explain recovery."""
        symbol = str(symbol_name or "").strip().upper()
        account = str(account_id or "").strip() or "—"
        self.ui.chkFilterBroker.setChecked(True)
        if symbol:
            index = self.ui.cmbSymbol.findText(
                symbol,
                Qt.MatchFlag.MatchFixedString,
            )
            if index >= 0:
                self.ui.cmbSymbol.setCurrentIndex(index)

        refreshed = True
        if refresh:
            refreshed = self.refresh_positions()
            if refreshed:
                self._select_external_exposure_row(
                    account_id=account_id,
                    symbol_name=symbol,
                )

        status = self._lang_mgr.tr(
            "OrdersPage.statusExternalExposureResolution",
            "LGE EXCLUSIVE: resolve external IB FX exposure for account "
            "{account_id}, symbol {symbol}; then press Refresh.",
        ).format(account_id=account, symbol=symbol or "—")
        self._set_orders_status(status, warning=True)
        self.ui.lblOrdersStatus.setToolTip(status)
        return refreshed

    def refresh_positions(self) -> bool:
        """Refresh positions through the current RuntimeEngine."""
        return self._on_refresh_clicked()

    def _on_refresh_clicked(self) -> bool:
        """Handle the Refresh button for positions and IB groups."""
        if self._runtime_engine is None:
            self._set_pnl_summary(None)
            self._set_orders_status(
                self._lang_mgr.tr(
                    "OrdersPage.msgRuntimeNotInitialized",
                    "RuntimeEngine is not initialized.",
                ),
                warning=True,
            )
            return False

        stable_key = self._get_selected_stable_key()

        try:
            broker = self._get_active_broker_code()

            if broker == "IB" and hasattr(
                self._runtime_engine,
                "get_active_broker_position_groups",
            ):
                recover_pending_opens = getattr(
                    self._runtime_engine,
                    "recover_pending_ib_manual_market_order_opens",
                    None,
                )

                if callable(recover_pending_opens):
                    recover_pending_opens()

                recover_pending = getattr(
                    self._runtime_engine,
                    "recover_pending_runtime_position_leg_closes",
                    None,
                )

                if callable(recover_pending):
                    recover_pending()

                sync_groups = getattr(
                    self._runtime_engine,
                    "sync_active_broker_position_groups",
                    None,
                )

                if callable(sync_groups):
                    snapshot = sync_groups()
                else:
                    snapshot = (
                        self._runtime_engine.get_active_broker_position_groups()
                    )
                filter_state, warning_text = self._apply_ib_position_group_snapshot(
                    snapshot,
                    stable_key=stable_key,
                )

                visible_group_count = filter_state["visible_top_level"]
                open_leg_count = filter_state["visible_legs"]

                if warning_text:
                    self._set_orders_status(warning_text, warning=True)
                else:
                    text = self._lang_mgr.tr(
                        "OrdersPage.statusPositionGroupsRefreshed",
                        "IB position groups refreshed: {groups}; " "open legs: {legs}",
                    ).format(
                        groups=visible_group_count,
                        legs=open_leg_count,
                    )
                    self._set_orders_status(text)

                return True

            positions = self._runtime_engine.get_active_broker_positions()
            self._last_ib_position_group_snapshot = None
            self._refresh_positions_table(positions)
            filter_state = self._apply_position_filters()
            self._restore_tree_selection(stable_key)

            warning_text = self._build_partial_sl_tp_warning(positions)

            if warning_text:
                self._set_orders_status(warning_text, warning=True)
            else:
                text = self._lang_mgr.tr(
                    "OrdersPage.statusPositionsRefreshed",
                    "Positions refreshed: {count}",
                ).format(count=filter_state["visible_top_level"])
                self._set_orders_status(text)

            return True
        except Exception as exc:  # noqa
            logger.exception("Refresh positions failed.")
            self._set_pnl_summary(None)
            text = self._lang_mgr.tr(
                "OrdersPage.statusRefreshFailed",
                "Refresh positions failed: {error}",
            ).format(error=str(exc))
            self._set_orders_status(text, warning=True)
            return False

    def _apply_ib_position_group_snapshot(
        self,
        snapshot,
        *,
        stable_key: str,
    ) -> tuple[dict[str, int], str]:
        """Render one already captured IB group snapshot."""
        self._last_ib_position_group_snapshot = snapshot
        self._refresh_ib_position_groups_tree(snapshot)
        filter_state = self._apply_position_filters()
        self._restore_tree_selection(stable_key)
        warning_text = self._build_group_reconciliation_warning(snapshot)
        return filter_state, warning_text

    def _current_selected_position_item(self) -> QTreeWidgetItem | None:
        """Return the selected tree item, not a stale Qt current item."""
        selected_items = self.ui.tblOpenPositions.selectedItems()

        if not selected_items:
            return None

        return selected_items[0]

    def _on_position_selection_changed(self) -> None:
        """Synchronize controls and operation buttons with selected row."""
        item = self._current_selected_position_item()

        if item is not None and not self._tree_item_selection_allowed(item):
            self._clear_position_selection()
            return

        if item is None:
            self.ui.btnModifySlTp.setEnabled(False)
            self.ui.btnResolveReconciliation.setEnabled(False)
            self.ui.btnClosePosition.setEnabled(False)
            self.ui.editStopLoss.clear()
            self.ui.editTakeProfit.clear()
            self._restore_ib_refresh_status_after_selection()
            return

        symbol_name = str(item.data(COL_ID, ROLE_SYMBOL) or "").strip().upper()
        side = str(item.data(COL_ID, ROLE_SIDE) or "").strip().upper()

        if symbol_name:
            symbol_index = self.ui.cmbSymbol.findText(
                symbol_name,
                Qt.MatchFlag.MatchFixedString,
            )

            if symbol_index >= 0:
                self.ui.cmbSymbol.setCurrentIndex(symbol_index)

        if side:
            side_index = self.ui.cmbSide.findData(side)

            if side_index >= 0:
                self.ui.cmbSide.setCurrentIndex(side_index)

        stop_loss = item.data(COL_ID, ROLE_RAW_SL)
        take_profit = item.data(COL_ID, ROLE_RAW_TP)
        self.ui.editStopLoss.setText(self._format_decimal_for_table(stop_loss))
        self.ui.editTakeProfit.setText(self._format_decimal_for_table(take_profit))

        enabled = bool(item.data(COL_ID, ROLE_OPERATIONS_ENABLED))
        row_kind = str(item.data(COL_ID, ROLE_ROW_KIND) or "")
        reconciliation_status = str(
            item.data(COL_ID, ROLE_RECONCILIATION_STATUS) or ""
        ).strip().upper()
        recovery_enabled = (
            (
                row_kind == ROW_KIND_LEG
                and reconciliation_status
                == IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING
            )
            or self._is_external_exposure_resolution_item(item)
        )
        self.ui.btnModifySlTp.setEnabled(enabled)
        self.ui.btnResolveReconciliation.setEnabled(recovery_enabled)
        self.ui.btnClosePosition.setEnabled(enabled)

        if row_kind == ROW_KIND_LEG and not enabled:
            self._set_orders_status(
                self._disabled_leg_operations_text(item),
                warning=True,
            )
            return

        self._refresh_ib_status_for_current_selection()

    def _restore_ib_refresh_status_after_selection(self) -> None:
        """Restore the current IB snapshot status after a row transition."""
        if self._last_ib_position_group_snapshot is None:
            return

        self._retranslate_current_ib_status()

    def _refresh_ib_status_for_current_selection(self) -> None:
        """Show selected-row reconciliation or the overall IB warning."""
        if self._last_ib_position_group_snapshot is None:
            return

        item = self._current_selected_position_item()

        if item is None:
            self._retranslate_current_ib_status()
            return

        row_kind = str(item.data(COL_ID, ROLE_ROW_KIND) or "")
        operations_enabled = bool(item.data(COL_ID, ROLE_OPERATIONS_ENABLED))

        if row_kind == ROW_KIND_LEG and not operations_enabled:
            self._set_orders_status(
                self._disabled_leg_operations_text(item),
                warning=True,
            )
            return

        if self._is_external_exposure_resolution_item(item):
            exposure_status = str(
                item.data(COL_ID, ROLE_EXTERNAL_EXPOSURE_STATUS) or "—"
            ).strip()
            text = self._lang_mgr.tr(
                "OrdersPage.statusExternalExposureSelected",
                "External IB exposure {symbol}: {side} {volume}; evidence "
                "{evidence}. Press Resolve reconciliation to view the exact "
                "TWS order identifiers.",
            ).format(
                symbol=str(item.data(COL_ID, ROLE_SYMBOL) or "—"),
                side=str(item.data(COL_ID, ROLE_SIDE) or "—"),
                volume=self._format_ib_units(item.data(COL_ID, ROLE_VOLUME)),
                evidence=self._format_external_exposure_evidence_status(
                    exposure_status
                ),
            )
            self._set_orders_status(text, warning=True)
            return

        status = str(
            item.data(COL_ID, ROLE_RECONCILIATION_STATUS) or ""
        ).strip()

        if not status:
            self._retranslate_current_ib_status()
            return

        status_text = self._format_ib_reconciliation_status(status)
        symbol = str(item.data(COL_ID, ROLE_SYMBOL) or "").strip().upper()
        text = f"{symbol}: {status_text}" if symbol else status_text
        self._set_orders_status(
            text,
            warning=status != IB_RECONCILIATION_STATUS_RECONCILED,
        )

    def _on_modify_sl_tp_clicked(self) -> None:
        """Modify SL/TP for a broker row or one exact IB virtual leg."""
        if self._runtime_engine is None:
            QMessageBox.warning(
                self,
                self._lang_mgr.tr("OrdersPage.titleRuntime", "Runtime"),
                self._lang_mgr.tr(
                    "OrdersPage.msgRuntimeNotInitialized",
                    "RuntimeEngine is not initialized.",
                ),
            )
            return

        item = self._current_selected_position_item()

        if item is None:
            self._show_modify_selection_warning()
            return

        row_kind = str(item.data(COL_ID, ROLE_ROW_KIND) or "")
        group_mode = str(item.data(COL_ID, ROLE_GROUP_MODE) or "")
        operations_enabled = bool(item.data(COL_ID, ROLE_OPERATIONS_ENABLED))

        if row_kind == ROW_KIND_GROUP and (
            group_mode == IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS
        ):
            self._show_select_virtual_leg_warning()
            return

        if not operations_enabled:
            self._show_leg_operations_disabled_warning()
            return

        try:
            stop_loss = self._read_optional_float(
                self.ui.editStopLoss.text(),
            )
            take_profit = self._read_optional_float(
                self.ui.editTakeProfit.text(),
            )
        except ValueError:
            QMessageBox.warning(
                self,
                self._lang_mgr.tr(
                    "OrdersPage.titleModifySlTp",
                    "Modify SL/TP",
                ),
                self._lang_mgr.tr(
                    "OrdersPage.msgSlTpNumeric",
                    "Stop Loss / Take Profit must be numeric.",
                ),
            )
            return

        stable_key = self._get_selected_stable_key()
        modify_result = None

        try:
            if row_kind == ROW_KIND_LEG:
                position_uid = str(item.data(COL_ID, ROLE_POSITION_UID) or "").strip()

                if not position_uid:
                    raise RuntimeError("Selected IB virtual leg position_uid is empty")

                confirmed = self._ask_localized_yes_no(
                    title=self._lang_mgr.tr(
                        "OrdersPage.titleModifySlTp",
                        "Modify SL/TP",
                    ),
                    text=self._lang_mgr.tr(
                        "OrdersPage.msgConfirmModifyLeg",
                        "Modify virtual leg {position_uid}: {side} "
                        "{volume}, SL={stop_loss}, TP={take_profit}?",
                    ).format(
                        position_uid=self._short_identity(position_uid),
                        side=str(item.data(COL_ID, ROLE_SIDE) or ""),
                        volume=self._format_ib_units(item.data(COL_ID, ROLE_VOLUME)),
                        stop_loss=self._format_optional_confirmation_price(stop_loss),
                        take_profit=(
                            self._format_optional_confirmation_price(take_profit)
                        ),
                    ),
                )

                if not confirmed:
                    return

                modify_result = self._runtime_engine.modify_runtime_position_leg_sl_tp(
                    position_uid=position_uid,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )
            else:
                position_id = str(
                    item.data(COL_ID, ROLE_BROKER_POSITION_ID) or ""
                ).strip()

                if not position_id:
                    self._show_modify_selection_warning()
                    return

                self._runtime_engine.modify_active_broker_position_sl_tp(
                    broker_position_id=position_id,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )
        except Exception as exc:  # noqa
            logger.exception("Modify position SL/TP failed.")
            text = self._lang_mgr.tr(
                "OrdersPage.statusSlTpModifyFailed",
                "Modify SL/TP failed: {error}",
            ).format(error=str(exc))
            self._set_orders_status(text, warning=True)
            QMessageBox.warning(
                self,
                self._lang_mgr.tr(
                    "OrdersPage.titleModifySlTp",
                    "Modify SL/TP",
                ),
                text,
            )
            return

        if row_kind == ROW_KIND_LEG and isinstance(modify_result, dict):
            position_group_snapshot = modify_result.get("position_group_snapshot")

            if position_group_snapshot is not None:
                _, warning_text = self._apply_ib_position_group_snapshot(
                    position_group_snapshot,
                    stable_key=stable_key,
                )

                if warning_text:
                    self._set_orders_status(warning_text, warning=True)
                else:
                    self._set_orders_status(
                        self._lang_mgr.tr(
                            "OrdersPage.statusUpdated",
                            "Updated",
                        )
                    )
                return

        if self._on_refresh_clicked():
            self._set_orders_status(
                self._lang_mgr.tr(
                    "OrdersPage.statusUpdated",
                    "Updated",
                )
            )

    def _build_localized_yes_no_message_box(
        self,
        *,
        title: str,
        text: str,
    ) -> QMessageBox:
        """Build one application-modal Yes/No box with LGE translations."""
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle(title)
        dialog.setText(text)
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)

        yes_button = dialog.button(QMessageBox.StandardButton.Yes)
        if yes_button is not None:
            yes_button.setText(
                self._lang_mgr.tr("CommonConfirmDialog.btnYes", "Yes")
            )

        no_button = dialog.button(QMessageBox.StandardButton.No)
        if no_button is not None:
            no_button.setText(
                self._lang_mgr.tr("CommonConfirmDialog.btnNo", "No")
            )

        return dialog

    def _ask_localized_yes_no(self, *, title: str, text: str) -> bool:
        """Show one localized Yes/No confirmation and return True for Yes."""
        dialog = self._build_localized_yes_no_message_box(
            title=title,
            text=text,
        )
        result = dialog.exec()
        return result == int(QMessageBox.StandardButton.Yes)

    def _on_resolve_reconciliation_clicked(self) -> None:
        """Resolve one CLOSE_EVIDENCE_MISSING leg without broker trade."""
        if self._runtime_engine is None:
            QMessageBox.warning(
                self,
                self._lang_mgr.tr("OrdersPage.titleRuntime", "Runtime"),
                self._lang_mgr.tr(
                    "OrdersPage.msgRuntimeNotInitialized",
                    "RuntimeEngine is not initialized.",
                ),
            )
            return

        item = self._current_selected_position_item()

        if item is not None and self._is_external_exposure_resolution_item(item):
            self._show_external_exposure_details(item)
            return

        if item is None or not self._is_close_evidence_recovery_item(item):
            QMessageBox.warning(
                self,
                self._lang_mgr.tr(
                    "OrdersPage.titleResolveReconciliation",
                    "Resolve IB reconciliation",
                ),
                self._lang_mgr.tr(
                    "OrdersPage.msgSelectCloseEvidenceMissingLeg",
                    "Select one LGE LEG with Close confirmation missing.",
                ),
            )
            return

        position_uid = str(
            item.data(COL_ID, ROLE_POSITION_UID) or ""
        ).strip()
        symbol = str(item.data(COL_ID, ROLE_SYMBOL) or "").strip().upper()
        side = str(item.data(COL_ID, ROLE_SIDE) or "").strip().upper()
        volume = self._format_ib_units(item.data(COL_ID, ROLE_VOLUME))
        status = self._format_ib_reconciliation_status(
            str(item.data(COL_ID, ROLE_RECONCILIATION_STATUS) or "")
        )
        title = self._lang_mgr.tr(
            "OrdersPage.titleResolveReconciliation",
            "Resolve IB reconciliation",
        )
        facts = self._lang_mgr.tr(
            "OrdersPage.msgResolveCloseEvidenceFacts",
            "Symbol: {symbol}\n"
            "LGE LEG: {side} {volume}\n"
            "Broker position: absent / 0\n"
            "Active SL/TP: absent\n"
            "Close execution: not found\n"
            "Current state: {status}\n\n"
            "Proceed to the final confirmation?",
        ).format(
            symbol=symbol,
            side=side,
            volume=volume,
            status=status,
        )
        if not self._ask_localized_yes_no(title=title, text=facts):
            return

        final_text = self._lang_mgr.tr(
            "OrdersPage.msgResolveCloseEvidenceFinal",
            "This action does not close a broker position and does not send "
            "any order to IB.\n\n"
            "It only confirms that the broker position was already closed "
            "while exact execution evidence is unavailable.\n\n"
            "Confirm manual recovery for {symbol} {side} {volume}?",
        ).format(
            symbol=symbol,
            side=side,
            volume=volume,
        )
        if not self._ask_localized_yes_no(title=title, text=final_text):
            return

        self.ui.btnResolveReconciliation.setEnabled(False)

        try:
            result = self._runtime_engine.resolve_ib_close_evidence_missing(
                position_uid=position_uid,
            )
        except Exception as exc:  # noqa
            logger.exception("Manual IB reconciliation failed.")
            text = self._lang_mgr.tr(
                "OrdersPage.statusCloseEvidenceResolveFailed",
                "Manual IB reconciliation failed: {error}",
            ).format(error=str(exc))
            self._set_orders_status(text, warning=True)
            QMessageBox.warning(self, title, text)
            self._on_position_selection_changed()
            return

        self._on_refresh_clicked()
        text = self._lang_mgr.tr(
            "OrdersPage.statusCloseEvidenceResolved",
            "Manual IB reconciliation completed. No broker order was sent. "
            "position_uid={position_uid}",
        ).format(
            position_uid=self._short_identity(
                result.get("position_uid") or position_uid
            )
        )
        self._set_orders_status(text)

    def _show_external_exposure_details(
        self,
        item: QTreeWidgetItem,
    ) -> None:
        """Show exact read-only IB order evidence for one external row."""
        account_id = str(item.data(COL_ID, ROLE_ACCOUNT_ID) or "—").strip()
        symbol = str(item.data(COL_ID, ROLE_SYMBOL) or "—").strip().upper()
        side = str(item.data(COL_ID, ROLE_SIDE) or "—").strip().upper()
        volume = self._format_ib_units(item.data(COL_ID, ROLE_VOLUME))
        evidence = self._format_external_exposure_evidence_status(
            item.data(COL_ID, ROLE_EXTERNAL_EXPOSURE_STATUS)
        )
        orders = self._external_protective_orders_from_item(item)

        intro = self._lang_mgr.tr(
            "OrdersPage.msgExternalExposureDetailsIntro",
            "Account: {account_id}\nSymbol: {symbol}\nExternal exposure: "
            "{side} {volume}\nEvidence: {evidence}",
        ).format(
            account_id=account_id,
            symbol=symbol,
            side=side,
            volume=volume,
            evidence=evidence,
        )
        sections = [intro]

        if orders:
            sections.append(
                self._lang_mgr.tr(
                    "OrdersPage.msgExternalExposureOrdersHeader",
                    "Current foreign-client protective orders received from IB:",
                )
            )
            sections.extend(
                self._format_external_protective_order_line(order)
                for order in orders
            )
        else:
            sections.append(
                self._lang_mgr.tr(
                    "OrdersPage.msgExternalExposureNoCurrentOrders",
                    "No exact protective-order rows are available in the "
                    "current IB snapshot. Do not cancel an order by guess; "
                    "verify the position and orders in TWS or an IB statement.",
                )
            )

        sections.append(
            self._lang_mgr.tr(
                "OrdersPage.msgExternalExposureResolutionSteps",
                "These broker orders are read-only in LGE. Find them in TWS "
                "Orders by symbol, order type, price, permId, parentId, "
                "clientId and OCA. IB can report orderId=0 for another "
                "client; in that case use permId/clientId/parentId/OCA. LGE "
                "does not invent TWS row numbers such as 6.1/6.2. If the "
                "external position still exists, close or resolve the "
                "position and its protection. If no position exists, cancel "
                "only the matching orphaned protection. Then press Refresh. "
                "To inspect the WSP and its journal, go to Monitoring.",
            )
        )
        QMessageBox.information(
            self,
            self._lang_mgr.tr(
                "OrdersPage.titleExternalExposureDetails",
                "External IB FX exposure details",
            ),
            "\n\n".join(sections),
        )

    @staticmethod
    def _is_external_exposure_resolution_item(
        item: QTreeWidgetItem,
    ) -> bool:
        """Return whether a row exposes read-only external-IB recovery."""
        row_kind = str(item.data(COL_ID, ROLE_ROW_KIND) or "")

        if row_kind == ROW_KIND_BROKER_RESIDUAL:
            return True

        if row_kind != ROW_KIND_GROUP:
            return False

        group_mode = str(item.data(COL_ID, ROLE_GROUP_MODE) or "")
        broker_position_kind = str(
            item.data(COL_ID, ROLE_BROKER_POSITION_KIND) or ""
        )
        reconciliation_status = str(
            item.data(COL_ID, ROLE_RECONCILIATION_STATUS) or ""
        ).strip().upper()
        volume = OrdersPage._finite_number(
            item.data(COL_ID, ROLE_VOLUME)
        )

        return (
            group_mode == IB_POSITION_GROUP_MODE_NET_ONLY
            and broker_position_kind == IB_BROKER_POSITION_KIND_VIRTUAL_FX
            and reconciliation_status
            in {
                IB_RECONCILIATION_STATUS_UNRECONCILED,
                IB_RECONCILIATION_STATUS_BLOCKED,
            }
            and volume is not None
            and abs(volume) > 0.0
        )

    @staticmethod
    def _is_close_evidence_recovery_item(
        item: QTreeWidgetItem,
    ) -> bool:
        """Return whether a tree row is eligible for manual recovery."""
        return (
            str(item.data(COL_ID, ROLE_ROW_KIND) or "") == ROW_KIND_LEG
            and str(
                item.data(COL_ID, ROLE_RECONCILIATION_STATUS) or ""
            ).strip().upper()
            == IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING
            and bool(str(item.data(COL_ID, ROLE_POSITION_UID) or "").strip())
        )

    def _on_exit_clicked(self) -> None:
        """
        Закрити сторінку ордерів і повернутися на Monitoring.
        """
        self.close_requested.emit()

    def _on_close_position_clicked(self) -> None:
        """Close a broker position or one exact IB virtual leg."""
        if self._runtime_engine is None:
            self._set_orders_status(
                self._lang_mgr.tr(
                    "OrdersPage.msgRuntimeNotInitialized",
                    "RuntimeEngine is not initialized.",
                ),
                warning=True,
            )
            return

        item = self._current_selected_position_item()

        if item is None:
            self._show_close_selection_warning()
            return

        row_kind = str(item.data(COL_ID, ROLE_ROW_KIND) or "")
        group_mode = str(item.data(COL_ID, ROLE_GROUP_MODE) or "")
        operations_enabled = bool(item.data(COL_ID, ROLE_OPERATIONS_ENABLED))

        if row_kind == ROW_KIND_GROUP and (
            group_mode == IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS
        ):
            self._show_select_virtual_leg_warning()
            return

        if not operations_enabled:
            self._show_leg_operations_disabled_warning()
            return

        try:
            if row_kind == ROW_KIND_LEG:
                position_uid = str(item.data(COL_ID, ROLE_POSITION_UID) or "").strip()

                if not position_uid:
                    raise RuntimeError("Selected IB virtual leg position_uid is empty")

                answer = QMessageBox.question(
                    self,
                    self._lang_mgr.tr(
                        "OrdersPage.titleClosePosition",
                        "Close position",
                    ),
                    self._lang_mgr.tr(
                        "OrdersPage.msgConfirmCloseLeg",
                        "Close virtual leg {position_uid}: {side} "
                        "{volume}, SL={stop_loss}, TP={take_profit}?",
                    ).format(
                        position_uid=self._short_identity(position_uid),
                        side=str(item.data(COL_ID, ROLE_SIDE) or ""),
                        volume=self._format_ib_units(item.data(COL_ID, ROLE_VOLUME)),
                        stop_loss=(
                            self._format_optional_confirmation_price(
                                item.data(COL_ID, ROLE_RAW_SL)
                            )
                        ),
                        take_profit=(
                            self._format_optional_confirmation_price(
                                item.data(COL_ID, ROLE_RAW_TP)
                            )
                        ),
                    ),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )

                if answer != QMessageBox.StandardButton.Yes:
                    return

                result = self._runtime_engine.close_runtime_position_leg(
                    position_uid=position_uid,
                )
                display_identity = self._short_identity(position_uid)
            else:
                position_id = str(
                    item.data(COL_ID, ROLE_BROKER_POSITION_ID) or ""
                ).strip()

                if not position_id:
                    self._show_close_selection_warning()
                    return

                display_identity = self._format_position_id_for_table(position_id)
                answer = QMessageBox.question(
                    self,
                    self._lang_mgr.tr(
                        "OrdersPage.titleClosePosition",
                        "Close position",
                    ),
                    self._lang_mgr.tr(
                        "OrdersPage.msgConfirmClosePosition",
                        "Close selected position {position_id}?",
                    ).format(position_id=display_identity),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )

                if answer != QMessageBox.StandardButton.Yes:
                    return

                result = self._runtime_engine.close_active_broker_position(
                    broker_position_id=position_id,
                )
        except IBVirtualLegCloseConfirmationPendingError as exc:
            logger.warning(
                "IB virtual-leg Close confirmation is pending | "
                "position_uid=%s | close_order_id=%s | details=%s",
                exc.position_uid,
                exc.close_order_id,
                exc.details,
            )
            text = self._lang_mgr.tr(
                "OrdersPage.statusCloseConfirmationPending",
                "Close confirmation is delayed. Do not repeat Close. "
                "LGE will recover the saved broker order during Refresh. "
                "close_order_id={order_id}",
            ).format(order_id=exc.close_order_id)
            self.ui.btnModifySlTp.setEnabled(False)
            self.ui.btnClosePosition.setEnabled(False)
            QMessageBox.warning(
                self,
                self._lang_mgr.tr(
                    "OrdersPage.titleClosePosition",
                    "Close position",
                ),
                text,
            )
            refresh_ok = self._on_refresh_clicked()

            if refresh_ok and not self._tree_contains_position_uid(exc.position_uid):
                resolved_text = self._lang_mgr.tr(
                    "OrdersPage.statusCloseRecoveredAfterDelay",
                    "Position closed after delayed broker confirmation. "
                    "close_order_id={order_id}",
                ).format(order_id=exc.close_order_id)
                self._set_orders_status(resolved_text)
            else:
                self._set_orders_status(text, warning=True)

            return
        except Exception as exc:  # noqa
            logger.exception("Close position failed.")
            text = self._lang_mgr.tr(
                "OrdersPage.statusPositionCloseFailed",
                "Close position failed: {error}",
            ).format(error=str(exc))
            self._set_orders_status(text, warning=True)
            QMessageBox.warning(
                self,
                self._lang_mgr.tr(
                    "OrdersPage.titleClosePosition",
                    "Close position",
                ),
                str(exc),
            )
            return

        if result.get("closed") or row_kind == ROW_KIND_LEG:
            text = self._lang_mgr.tr(
                "OrdersPage.statusPositionClosed",
                "Position closed. broker_position_id={position_id}",
            ).format(position_id=display_identity)
        else:
            text = self._lang_mgr.tr(
                "OrdersPage.statusPositionCloseSent",
                "Close sent, but position is still visible. "
                "broker_position_id={position_id}",
            ).format(position_id=display_identity)

        self._set_orders_status(text)
        self._on_refresh_clicked()

    def set_runtime_engine(
        self,
        runtime_engine,
    ) -> None:
        """
        Встановити shared RuntimeEngine для OrdersPage.

        OrdersPage не створює RuntimeEngine самостійно
        і не звертається напряму до broker adapter.
        """
        self._runtime_engine = runtime_engine

    @staticmethod
    def _read_optional_float(
        text: str,
    ) -> float | None:
        """
        Прочитати необов'язкове float-поле.

        Порожній рядок означає None.
        """
        value = str(text).strip().replace(",", ".")

        if not value:
            return None

        return float(value)

    def _tree_contains_position_uid(self, position_uid: str) -> bool:
        """Return whether an exact virtual leg remains visible in the tree."""
        target = str(position_uid or "").strip()

        if not target:
            return False

        tree = self.ui.tblOpenPositions

        for top_index in range(tree.topLevelItemCount()):
            top_item = tree.topLevelItem(top_index)

            if str(top_item.data(COL_ID, ROLE_POSITION_UID) or "").strip() == target:
                return True

            for child_index in range(top_item.childCount()):
                child = top_item.child(child_index)

                if str(child.data(COL_ID, ROLE_POSITION_UID) or "").strip() == target:
                    return True

        return False

    def _get_selected_position_id(self) -> str:
        """Return broker_position_id from the selected tree item."""
        item = self._current_selected_position_item()

        if item is None:
            return ""

        return str(item.data(COL_ID, ROLE_BROKER_POSITION_ID) or "").strip()

    def _get_active_broker_code(self) -> str:
        """Return the active RuntimeEngine broker code when available."""
        getter = getattr(self._runtime_engine, "get_active_broker", None)

        if not callable(getter):
            return ""

        return str(getter() or "").strip().upper()

    def _get_selected_stable_key(self) -> str:
        """Return stable selection identity before a tree refresh."""
        item = self._current_selected_position_item()

        if item is None:
            return ""

        return str(item.data(COL_ID, ROLE_STABLE_KEY) or "").strip()

    def _select_external_exposure_row(
        self,
        *,
        account_id: str,
        symbol_name: str,
    ) -> bool:
        """Select one visible external row by exact account and symbol."""
        tree = self.ui.tblOpenPositions
        account = str(account_id or "").strip()
        symbol = str(symbol_name or "").strip().upper()

        for top_index in range(tree.topLevelItemCount()):
            top_item = tree.topLevelItem(top_index)

            for item in self._walk_tree_items(top_item):
                if (
                    str(item.data(COL_ID, ROLE_ROW_KIND) or "")
                    != ROW_KIND_BROKER_RESIDUAL
                ):
                    continue
                if (
                    str(item.data(COL_ID, ROLE_ACCOUNT_ID) or "").strip()
                    != account
                ):
                    continue
                if (
                    str(item.data(COL_ID, ROLE_SYMBOL) or "").strip().upper()
                    != symbol
                ):
                    continue
                if self._tree_item_is_effectively_hidden(item):
                    continue
                if not self._tree_item_selection_allowed(item):
                    continue

                parent = item.parent()
                if parent is not None:
                    parent.setExpanded(True)

                tree.clearSelection()
                tree.setCurrentItem(item)
                item.setSelected(True)
                tree.scrollToItem(item)
                self._on_position_selection_changed()
                return True

        return False

    def _restore_tree_selection(self, stable_key: str) -> None:
        """Restore selection by stable key, never by visible row index."""
        tree = self.ui.tblOpenPositions
        key = str(stable_key or "").strip()

        if not key:
            tree.clearSelection()
            tree.setCurrentItem(None)
            self._on_position_selection_changed()
            return

        for top_index in range(tree.topLevelItemCount()):
            top_item = tree.topLevelItem(top_index)

            for item in self._walk_tree_items(top_item):
                item_key = str(item.data(COL_ID, ROLE_STABLE_KEY) or "").strip()

                if item_key != key:
                    continue

                if self._tree_item_is_effectively_hidden(item):
                    continue

                if not self._tree_item_selection_allowed(item):
                    continue

                parent = item.parent()

                if parent is not None:
                    parent.setExpanded(True)

                tree.setCurrentItem(item)
                item.setSelected(True)
                tree.scrollToItem(item)
                self._on_position_selection_changed()
                return

        tree.clearSelection()
        tree.setCurrentItem(None)
        self._on_position_selection_changed()

    @classmethod
    def _walk_tree_items(cls, item):
        """Yield one tree item and all descendants."""
        yield item

        for child_index in range(item.childCount()):
            yield from cls._walk_tree_items(item.child(child_index))

    def _on_position_filter_changed(self, _checked: bool) -> None:
        """Apply local source filters without requesting another broker snapshot."""
        self._apply_position_filters()

    def _apply_position_filters(self) -> dict[str, int]:
        """Hide rows by order origin and recalculate visible PnL."""
        enabled = {
            ORDER_CONTROL_MODE_MANUAL: self.ui.chkFilterManual.isChecked(),
            ORDER_CONTROL_MODE_SEMI: self.ui.chkFilterSemi.isChecked(),
            ORDER_CONTROL_MODE_AUTO: self.ui.chkFilterAuto.isChecked(),
            ORDER_ORIGIN_BROKER: self.ui.chkFilterBroker.isChecked(),
        }
        tree = self.ui.tblOpenPositions
        visible_top_level = 0
        visible_legs = 0
        pnl_totals: dict[str, float] = {}
        approximate_currencies: set[str] = set()

        for top_index in range(tree.topLevelItemCount()):
            top_item = tree.topLevelItem(top_index)
            row_kind = str(top_item.data(COL_ID, ROLE_ROW_KIND) or "").strip()
            group_mode = str(top_item.data(COL_ID, ROLE_GROUP_MODE) or "").strip()

            if (
                row_kind == ROW_KIND_GROUP
                and group_mode == IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS
                and top_item.childCount() > 0
            ):
                any_child_visible = False

                for child_index in range(top_item.childCount()):
                    child = top_item.child(child_index)
                    origin = self._tree_item_order_origin(child)
                    child_visible = bool(enabled.get(origin, False))
                    child.setHidden(not child_visible)

                    if not child_visible:
                        continue

                    any_child_visible = True
                    child_kind = str(
                        child.data(COL_ID, ROLE_ROW_KIND) or ""
                    ).strip()

                    if child_kind == ROW_KIND_LEG:
                        visible_legs += 1

                    self._accumulate_item_pnl(
                        child,
                        totals=pnl_totals,
                        approximate_currencies=approximate_currencies,
                    )

                top_item.setHidden(not any_child_visible)

                if any_child_visible:
                    visible_top_level += 1

                continue

            origin = self._tree_item_order_origin(top_item)
            item_visible = bool(enabled.get(origin, False))
            top_item.setHidden(not item_visible)

            if not item_visible:
                continue

            visible_top_level += 1
            self._accumulate_item_pnl(
                top_item,
                totals=pnl_totals,
                approximate_currencies=approximate_currencies,
            )

        current_item = tree.currentItem()

        if current_item is not None and self._tree_item_is_effectively_hidden(
            current_item
        ):
            tree.clearSelection()
            tree.setCurrentItem(None)
            self._on_position_selection_changed()

        self._set_pnl_summary_totals(
            pnl_totals,
            approximate_currencies=approximate_currencies,
        )
        return {
            "visible_top_level": visible_top_level,
            "visible_legs": visible_legs,
        }

    def _accumulate_item_pnl(
        self,
        item: QTreeWidgetItem,
        *,
        totals: dict[str, float],
        approximate_currencies: set[str],
    ) -> None:
        """Accumulate one visible row without mixing PnL currencies."""
        group_mode = str(item.data(COL_ID, ROLE_GROUP_MODE) or "")
        broker_position_kind = str(
            item.data(COL_ID, ROLE_BROKER_POSITION_KIND) or ""
        )
        reconciliation_status = str(
            item.data(COL_ID, ROLE_RECONCILIATION_STATUS) or ""
        )
        blocked_virtual_fx_observation = (
            group_mode == IB_POSITION_GROUP_MODE_NET_ONLY
            and broker_position_kind == IB_BROKER_POSITION_KIND_VIRTUAL_FX
            and reconciliation_status == IB_RECONCILIATION_STATUS_BLOCKED
        )

        if blocked_virtual_fx_observation:
            return

        value = self._finite_number(item.data(COL_ID, ROLE_PNL_VALUE))

        if value is None:
            return

        currency = self._normalize_currency(
            item.data(COL_ID, ROLE_PNL_CURRENCY)
        )
        totals[currency] = totals.get(currency, 0.0) + value

        if bool(item.data(COL_ID, ROLE_PNL_APPROXIMATE)):
            approximate_currencies.add(currency)

    @staticmethod
    def _tree_item_is_effectively_hidden(item: QTreeWidgetItem) -> bool:
        """Return whether an item or one of its ancestors is hidden."""
        current = item

        while current is not None:
            if current.isHidden():
                return True

            current = current.parent()

        return False

    @staticmethod
    def _tree_item_order_origin(item: QTreeWidgetItem) -> str:
        """Return one canonical filter origin for a tree row."""
        origin = str(item.data(COL_ID, ROLE_ORDER_ORIGIN) or "").strip().upper()

        if origin in ORDER_CONTROL_MODES:
            return origin

        return ORDER_ORIGIN_BROKER

    @staticmethod
    def _normalize_lge_order_origin(source: object) -> str:
        """Normalize persisted LGE source values for source filtering."""
        source_norm = str(source or "").strip().upper()

        if source_norm.startswith("LGE_"):
            source_norm = source_norm[4:]

        if source_norm in ORDER_CONTROL_MODES:
            return source_norm

        # Historical virtual legs were LGE-owned before source markers existed.
        return ORDER_CONTROL_MODE_MANUAL

    @classmethod
    def _flat_position_order_origin(cls, position) -> str:
        """Classify a flat broker position by broker metadata."""
        payload = getattr(position, "raw_payload", None)

        if not isinstance(payload, dict):
            payload = {}

        candidates = (
            payload.get("order_control_mode"),
            payload.get("source"),
            getattr(position, "source", None),
        )

        for candidate in candidates:
            mode = str(candidate or "").strip().upper()

            if mode.startswith("LGE_"):
                mode = mode[4:]

            if mode in ORDER_CONTROL_MODES:
                return mode

        broker_comment = payload.get("broker_comment") or payload.get("comment") or ""
        mode = get_broker_order_control_mode(broker_comment)

        if mode in ORDER_CONTROL_MODES:
            return mode

        label = str(payload.get("label") or "").strip().upper()

        if label.startswith("LGE_"):
            label_mode = label[4:]

            if label_mode in ORDER_CONTROL_MODES:
                return label_mode

        return ORDER_ORIGIN_BROKER

    def _show_modify_selection_warning(self) -> None:
        QMessageBox.warning(
            self,
            self._lang_mgr.tr(
                "OrdersPage.titleModifySlTp",
                "Modify SL/TP",
            ),
            self._lang_mgr.tr(
                "OrdersPage.msgSelectPositionForModify",
                "Select a position to modify SL/TP.",
            ),
        )

    def _show_close_selection_warning(self) -> None:
        QMessageBox.warning(
            self,
            self._lang_mgr.tr(
                "OrdersPage.titleClosePosition",
                "Close position",
            ),
            self._lang_mgr.tr(
                "OrdersPage.msgSelectPosition",
                "Select a position to close.",
            ),
        )

    def _show_select_virtual_leg_warning(self) -> None:
        QMessageBox.warning(
            self,
            self._lang_mgr.tr(
                "OrdersPage.titleRuntime",
                "Runtime",
            ),
            self._lang_mgr.tr(
                "OrdersPage.msgSelectVirtualLeg",
                "Select a specific virtual leg.",
            ),
        )

    def _show_leg_operations_disabled_warning(self) -> None:
        item = self._current_selected_position_item()
        text = (
            self._disabled_leg_operations_text(item)
            if item is not None
            else self._lang_mgr.tr(
                "OrdersPage.msgLegOperationsDisabled",
                "Virtual-leg operations are disabled for this row.",
            )
        )
        self._set_orders_status(text, warning=True)
        QMessageBox.warning(
            self,
            self._lang_mgr.tr(
                "OrdersPage.titleRuntime",
                "Runtime",
            ),
            text,
        )

    def _disabled_leg_operations_text(
        self,
        item: QTreeWidgetItem,
    ) -> str:
        """Return a localized reason for a read-only virtual-leg row."""
        status = self._format_ib_reconciliation_status(
            str(item.data(COL_ID, ROLE_RECONCILIATION_STATUS) or "")
        )
        status_text = status or self._lang_mgr.tr(
            "OrdersPage.reconciliationBlocked",
            "Blocked",
        )
        return self._lang_mgr.tr(
            "OrdersPage.statusSelectedLegOperationsDisabled",
            "Selected virtual leg cannot be modified or closed: {status}",
        ).format(status=status_text)

    def _format_optional_confirmation_price(self, value) -> str:
        """Format an optional protection price for confirmation dialogs."""
        text = self._format_decimal_for_table(value)
        return text or "—"

    @staticmethod
    def _format_text_for_table(
        value,
    ) -> str:
        """
        Підготувати звичайне text value для таблиці.

        None і порожній рядок показуються як порожня клітинка.
        """
        if value is None:
            return ""

        return str(value).strip()

    @staticmethod
    def _format_decimal_for_table(
        value,
        max_decimals: int = 8,
    ) -> str:
        """
        Підготувати number value для таблиці.

        Приклади:
        - 1000.0 -> 1000
        - 0.01000000 -> 0.01
        - 1.42169000 -> 1.42169
        - None -> ""
        """
        if value is None:
            return ""

        text = str(value).strip()

        if not text:
            return ""

        try:
            number = float(text)
        except (TypeError, ValueError):
            return text

        if not math.isfinite(number):
            return ""

        if abs(number) < 0.000000005:
            number = 0.0

        result = f"{number:.{max_decimals}f}"
        result = result.rstrip("0").rstrip(".")

        if result == "-0":
            return "0"

        return result or "0"

    @staticmethod
    def _format_money_for_table(
        value,
    ) -> str:
        """
        Підготувати money/PnL value для таблиці.

        PnL поки показується тільки з broker value.
        Якщо broker value відсутнє — клітинка порожня.
        """
        if value is None:
            return ""

        text = str(value).strip()

        if not text:
            return ""

        try:
            number = float(text)
        except (TypeError, ValueError):
            return text

        if not math.isfinite(number):
            return ""

        if abs(number) < 0.005:
            number = 0.0

        return f"{number:.2f}"

    def _format_position_volume_for_table(
        self,
        position,
    ) -> str:
        """
        Підготувати volume для таблиці broker positions.

        cTrader показує lot volume:
        - 0.01
        - 1
        - 1.5

        IB Forex показує units:
        - 1000 -> 1 000
        - 25000 -> 25 000
        """
        broker = str(getattr(position, "broker", "") or "").strip().upper()
        value = getattr(position, "volume", None)

        if value is None:
            return ""

        text = str(value).strip()

        if not text:
            return ""

        try:
            number = float(text)
        except (TypeError, ValueError):
            return text

        if not math.isfinite(number):
            return ""

        if broker == "IB":
            if number.is_integer():
                return f"{int(number):,}".replace(",", " ")

            return f"{number:,.2f}".replace(",", " ")

        return self._format_decimal_for_table(
            number,
            max_decimals=2,
        )

    def _format_position_pnl_for_table(
        self,
        position,
    ) -> str:
        """Format broker-provided position PnL for the table."""
        return self._format_money_for_table(self._position_pnl_value(position))

    def _format_current_price_for_table(self, position) -> str:
        """Show a dash when cTrader has no real current-price value."""
        broker = str(getattr(position, "broker", "") or "").strip().upper()
        value = getattr(position, "current_price", None)

        if broker == "CTRADER":
            number = self._finite_number(value)

            if number is None or abs(number) < 0.000000005:
                return "—"

        return self._format_decimal_for_table(value)

    @classmethod
    def _position_pnl_value(cls, position) -> float | None:
        """Return a trustworthy broker PnL value or None."""
        broker = str(getattr(position, "broker", "") or "").strip().upper()
        raw_payload = getattr(position, "raw_payload", None) or {}

        if broker == "IB" and "unrealized_pnl" not in raw_payload:
            return None

        return cls._finite_number(getattr(position, "unrealized_pnl", None))

    @classmethod
    def _calculate_flat_positions_total_pnl(
        cls,
        positions: list,
    ) -> float | None:
        """Sum broker PnL once for flat position rows."""
        values = [
            value
            for position in positions
            if (value := cls._position_pnl_value(position)) is not None
        ]

        if not values:
            return None

        return sum(values)

    @staticmethod
    def _finite_number(value) -> float | None:
        """Convert one value to a finite float."""
        if value is None:
            return None

        try:
            number = float(value)
        except (TypeError, ValueError):
            return None

        if not math.isfinite(number):
            return None

        return number

    def _set_pnl_summary(
        self,
        value: float | None,
        *,
        approximate: bool = False,
        currency: str = "",
    ) -> None:
        """Update the PnL summary for zero or one currency."""
        totals: dict[str, float] = {}
        approximate_currencies: set[str] = set()

        if value is not None:
            currency_norm = self._normalize_currency(currency)
            totals[currency_norm] = value

            if approximate:
                approximate_currencies.add(currency_norm)

        self._set_pnl_summary_totals(
            totals,
            approximate_currencies=approximate_currencies,
        )

    def _set_pnl_summary_totals(
        self,
        totals: dict[str, float],
        *,
        approximate_currencies: set[str],
    ) -> None:
        """Render separate PnL totals per currency."""
        parts: list[str] = []

        for currency in sorted(
            totals,
            key=lambda currency_code: (not currency_code, currency_code),
        ):
            value = self._finite_number(totals.get(currency))

            if value is None:
                continue

            text = self._format_money_for_table(value)

            if not text:
                continue

            marker = "≈ " if currency in approximate_currencies else ""
            suffix = f" {currency}" if currency else ""
            parts.append(f"{marker}{text}{suffix}")

        if not parts:
            self.ui.lblPnlSummary.setText("Σ PnL: —")
            self.ui.lblPnlSummary.setToolTip(
                "No trustworthy PnL value is available."
            )
            return

        self.ui.lblPnlSummary.setText(f"Σ PnL: {'; '.join(parts)}")
        self.ui.lblPnlSummary.setToolTip(
            "PnL totals are grouped by currency; approximate virtual-leg "
            "values are calculated from entry and current prices."
        )

    @staticmethod
    def _normalize_currency(value) -> str:
        """Return one canonical upper-case currency code."""
        text = str(value or "").strip().upper()

        if not text:
            return ""

        return "".join(character for character in text if character.isalnum())

    @classmethod
    def _position_pnl_currency(cls, position) -> str:
        """Return broker-declared PnL currency for a flat position."""
        raw_payload = getattr(position, "raw_payload", None) or {}
        return cls._normalize_currency(
            raw_payload.get("pnl_currency")
            or getattr(position, "currency", "")
        )

    @classmethod
    def _ib_virtual_leg_pnl_currency(cls, group) -> str:
        """Return the quote currency used by price-difference PnL."""
        currency = cls._normalize_currency(
            getattr(group, "pnl_currency", "")
            or getattr(group, "currency", "")
        )

        if currency:
            return currency

        compact_symbol = "".join(
            character
            for character in str(group.symbol_name or "").upper()
            if character.isalpha()
        )

        if len(compact_symbol) >= 6:
            return compact_symbol[-3:]

        return ""

    @classmethod
    def _ib_virtual_leg_current_price(cls, group, side: str) -> float | None:
        """Return side-aware bid/ask price for one virtual leg."""
        price_method = getattr(group, "current_price_for_side", None)

        if callable(price_method):
            return cls._finite_number(price_method(side))

        side_value = str(side or "").strip().upper()

        if side_value == "BUY":
            bid_price = cls._finite_number(getattr(group, "bid_price", None))

            if bid_price is not None:
                return bid_price

        if side_value == "SELL":
            ask_price = cls._finite_number(getattr(group, "ask_price", None))

            if ask_price is not None:
                return ask_price

        return cls._finite_number(getattr(group, "current_price", None))

    def _format_pnl_with_currency(
        self,
        value: float | None,
        *,
        currency: str = "",
        approximate: bool = False,
    ) -> str:
        """Format one PnL value with marker and currency."""
        text = self._format_money_for_table(value)

        if not text:
            return ""

        marker = "≈ " if approximate else ""
        currency_norm = self._normalize_currency(currency)
        suffix = f" {currency_norm}" if currency_norm else ""
        return f"{marker}{text}{suffix}"

    def _set_orders_status(
        self,
        text: str,
        warning: bool = False,
    ) -> None:
        """
        Встановити status text для OrdersPage.
        """
        if warning:
            self.ui.lblOrdersStatus.setStyleSheet("color: #ff5555; font-weight: 600;")
        else:
            self.ui.lblOrdersStatus.setStyleSheet("")

        self.ui.lblOrdersStatus.setToolTip(text)
        self.ui.lblOrdersStatus.setText(text)

    @staticmethod
    def _get_sl_tp_payload(
        position,
    ) -> dict:
        """
        Прочитати службові SL/TP flags з raw_payload.
        """
        raw_payload = getattr(position, "raw_payload", None) or {}
        payload = raw_payload.get("sl_tp_orders") or {}

        if isinstance(payload, dict):
            return payload

        return {}

    def _is_sl_tp_partial(
        self,
        position,
        field_name: str,
    ) -> bool:
        """
        Перевірити, чи SL/TP покриває позицію частково.
        """
        payload = self._get_sl_tp_payload(position)

        return bool(payload.get(f"{field_name}_partial"))

    def _format_sl_tp_value_for_table(
        self,
        position,
        field_name: str,
    ) -> str:
        """
        Підготувати SL/TP для таблиці.

        Якщо coverage частковий — додаємо помітну позначку ***.
        """
        value = getattr(position, field_name, None)
        text = self._format_decimal_for_table(value)

        if self._is_sl_tp_partial(position, field_name):
            if text:
                return f"{text} ***"

            return "***"

        return text

    @staticmethod
    def _format_units_for_warning(
        value,
    ) -> str:
        """
        Підготувати IB quantity для warning text.
        """
        try:
            number = float(value)
        except (TypeError, ValueError):
            return ""

        if not math.isfinite(number):
            return ""

        if number.is_integer():
            return f"{int(number):,}".replace(",", " ")

        return f"{number:,.2f}".replace(",", " ")

    def _build_partial_sl_tp_warning(
        self,
        positions: list,
    ) -> str:
        """
        Побудувати warning по частковому IB SL/TP coverage.
        """
        warnings: list[str] = []

        for position in positions:
            broker = str(getattr(position, "broker", "") or "").strip().upper()

            if broker != "IB":
                continue

            payload = self._get_sl_tp_payload(position)
            parts: list[str] = []

            if payload.get("stop_loss_partial"):
                stop_loss_price = self._format_decimal_for_table(
                    getattr(position, "stop_loss", None),
                )
                stop_loss_qty = self._format_units_for_warning(
                    payload.get("stop_loss_quantity"),
                )
                position_volume = self._format_units_for_warning(
                    payload.get("stop_loss_position_volume")
                    or getattr(position, "volume", None),
                )

                if payload.get("stop_loss_ambiguous"):
                    parts.append(
                        self._lang_mgr.tr(
                            "OrdersPage.statusProtectionMixed",
                            "{leg} mixed {quantity}/{volume}",
                        ).format(
                            leg="SL",
                            quantity=stop_loss_qty,
                            volume=position_volume,
                        )
                    )
                else:
                    parts.append(
                        f"SL {stop_loss_price} {stop_loss_qty}/{position_volume}"
                    )

            if payload.get("take_profit_partial"):
                take_profit_price = self._format_decimal_for_table(
                    getattr(position, "take_profit", None),
                )
                take_profit_qty = self._format_units_for_warning(
                    payload.get("take_profit_quantity"),
                )
                position_volume = self._format_units_for_warning(
                    payload.get("take_profit_position_volume")
                    or getattr(position, "volume", None),
                )

                if payload.get("take_profit_ambiguous"):
                    parts.append(
                        self._lang_mgr.tr(
                            "OrdersPage.statusProtectionMixed",
                            "{leg} mixed {quantity}/{volume}",
                        ).format(
                            leg="TP",
                            quantity=take_profit_qty,
                            volume=position_volume,
                        )
                    )
                else:
                    parts.append(
                        f"TP {take_profit_price} "
                        f"{take_profit_qty}/{position_volume}"
                    )

            if not parts:
                continue

            volume_text = self._format_position_volume_for_table(position)
            warnings.append(
                f"IB {position.symbol_name} {position.side} "
                f"{volume_text}: {', '.join(parts)}"
            )

        if not warnings:
            return ""

        if len(warnings) == 1:
            details = warnings[0]
        else:
            additional = self._lang_mgr.tr(
                "OrdersPage.statusAdditionalWarnings",
                "and {count} more",
            ).format(count=len(warnings) - 1)
            details = f"{warnings[0]}; {additional}"

        return self._lang_mgr.tr(
            "OrdersPage.statusPartialProtectionWarning",
            "WARNING: {details}",
        ).format(details=details)

    def _refresh_positions_table(
        self,
        positions: list,
    ) -> None:
        """Render flat broker positions as top-level tree rows."""
        tree = self.ui.tblOpenPositions
        tree.clear()

        for position in positions:
            position_id = str(position.position_id)
            broker = str(position.broker or "").strip().upper()
            operations_enabled = broker == "CTRADER"
            raw_sl = getattr(position, "stop_loss", None)
            raw_tp = getattr(position, "take_profit", None)
            order_origin = self._flat_position_order_origin(position)
            pnl_value = self._position_pnl_value(position)
            values = [
                self._format_position_id_for_table(position_id),
                self._format_text_for_table(position.symbol_name),
                self._lang_mgr.tr(
                    "OrdersPage.typeBrokerPosition",
                    "Broker position",
                ),
                self._format_text_for_table(position.side),
                self._format_position_volume_for_table(position),
                self._format_decimal_for_table(position.entry_price),
                self._format_current_price_for_table(position),
                self._format_sl_tp_value_for_table(position, "stop_loss"),
                self._format_sl_tp_value_for_table(position, "take_profit"),
                self._format_position_pnl_for_table(position),
                "—" if broker == "CTRADER" else "",
                order_origin,
                self._format_opened_time(position.opened_utc),
            ]
            item = QTreeWidgetItem(values)
            metadata = {
                ROLE_ROW_KIND: ROW_KIND_POSITION,
                ROLE_BROKER_POSITION_ID: position_id,
                ROLE_POSITION_UID: "",
                ROLE_TRADE_UID: "",
                ROLE_GROUP_MODE: "",
                ROLE_BROKER_POSITION_KIND: "",
                ROLE_RECONCILIATION_STATUS: "",
                ROLE_LEG_STATUS: "",
                ROLE_OPERATIONS_ENABLED: operations_enabled,
                ROLE_RAW_SL: raw_sl,
                ROLE_RAW_TP: raw_tp,
                ROLE_STABLE_KEY: self._flat_position_stable_key(position),
                ROLE_SYMBOL: str(position.symbol_name),
                ROLE_SIDE: str(position.side),
                ROLE_VOLUME: getattr(position, "volume", None),
                ROLE_ORDER_ORIGIN: order_origin,
                ROLE_PNL_VALUE: pnl_value,
                ROLE_PNL_APPROXIMATE: False,
                ROLE_PNL_CURRENCY: self._position_pnl_currency(position),
            }
            self._apply_tree_item_metadata(item, metadata)
            self._apply_tree_item_alignment(item)
            self._apply_tree_item_selectability(
                item,
                operations_enabled,
            )
            self._apply_flat_position_tooltips(item, position)

            if self._is_sl_tp_partial(position, "stop_loss"):
                item.setForeground(COL_SL, QColor("#ff5555"))

            if self._is_sl_tp_partial(position, "take_profit"):
                item.setForeground(COL_TP, QColor("#ff5555"))

            tree.addTopLevelItem(item)

    def _refresh_ib_position_groups_tree(self, snapshot) -> int:
        """Render active IB groups and return the visible group count."""
        tree = self.ui.tblOpenPositions
        tree.clear()
        visible_group_count = 0

        for group in snapshot.groups:
            open_legs = list(group.open_legs)

            if not self._should_show_ib_position_group(group, open_legs):
                continue

            group_item = self._build_ib_group_item(group)
            tree.addTopLevelItem(group_item)
            visible_group_count += 1

            for leg in open_legs:
                group_item.addChild(self._build_ib_leg_item(group, leg))

            if group.broker_residual_present:
                group_item.addChild(
                    self._build_ib_broker_residual_item(group)
                )

            if open_legs or group.broker_residual_present:
                group_item.setExpanded(True)

        return visible_group_count

    @staticmethod
    def _should_show_ib_position_group(group, open_legs: list) -> bool:
        """Return whether a group belongs in the active positions tree."""
        closed_virtual_fx_observation = (
            group.broker_position_kind == IB_BROKER_POSITION_KIND_VIRTUAL_FX
            and group.group_mode == IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS
            and group.reconciliation_status == IB_RECONCILIATION_STATUS_RECONCILED
            and not open_legs
        )

        if closed_virtual_fx_observation:
            broker_volume = abs(float(group.broker_volume or 0.0))
            return (
                group.broker_position_present and broker_volume > 0.0
            ) or group.broker_residual_present

        return group.broker_position_present or bool(open_legs)

    def _build_ib_group_item(self, group) -> QTreeWidgetItem:
        """Build one top-level IB broker group row."""
        stop_loss, stop_loss_text = self._group_protection_value(
            group,
            "stop_loss",
        )
        take_profit, take_profit_text = self._group_protection_value(
            group,
            "take_profit",
        )
        group_type = self._format_ib_group_type(group)
        broker_entry_price = group.broker_entry_price
        broker_unrealized_pnl = group.unrealized_pnl
        broker_opened_utc = group.opened_utc
        blocked_virtual_fx_observation = (
            group.group_mode == IB_POSITION_GROUP_MODE_NET_ONLY
            and group.broker_position_kind == IB_BROKER_POSITION_KIND_VIRTUAL_FX
            and group.reconciliation_status == IB_RECONCILIATION_STATUS_BLOCKED
        )
        virtual_fx_group = (
            group.broker_position_kind
            == IB_BROKER_POSITION_KIND_VIRTUAL_FX
            and group.group_mode
            == IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS
        )
        broker_only_fallback = (
            group.group_mode == IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS
            and not group.open_legs
            and group.broker_position_present
            and abs(float(group.broker_volume or 0.0)) > 0.0
        )
        order_origin = (
            ORDER_ORIGIN_BROKER
            if group.group_mode == IB_POSITION_GROUP_MODE_NET_ONLY
            or broker_only_fallback
            else ""
        )

        if virtual_fx_group:
            broker_entry_price = None
            broker_unrealized_pnl = None
            broker_opened_utc = ""

        if blocked_virtual_fx_observation:
            broker_unrealized_pnl = None

        values = [
            self._format_position_id_for_table(group.broker_position_id),
            group.symbol_name,
            group_type,
            group.display_side,
            self._format_ib_units(group.display_volume),
            self._format_decimal_for_table(broker_entry_price),
            self._format_decimal_for_table(group.current_price),
            stop_loss_text,
            take_profit_text,
            self._format_money_for_table(broker_unrealized_pnl),
            self._format_ib_reconciliation_status(
                group.reconciliation_status,
            ),
            order_origin or "IB",
            self._format_opened_time(broker_opened_utc),
        ]
        item = QTreeWidgetItem(values)
        group_pnl_value = (
            self._finite_number(broker_unrealized_pnl)
            if group.group_mode == IB_POSITION_GROUP_MODE_NET_ONLY
            else None
        )
        metadata = {
            ROLE_ROW_KIND: ROW_KIND_GROUP,
            ROLE_BROKER_POSITION_ID: group.broker_position_id,
            ROLE_POSITION_UID: "",
            ROLE_TRADE_UID: "",
            ROLE_GROUP_MODE: group.group_mode,
            ROLE_BROKER_POSITION_KIND: group.broker_position_kind,
            ROLE_RECONCILIATION_STATUS: group.reconciliation_status,
            ROLE_LEG_STATUS: "",
            ROLE_OPERATIONS_ENABLED: False,
            ROLE_RAW_SL: stop_loss,
            ROLE_RAW_TP: take_profit,
            ROLE_STABLE_KEY: f"GROUP:{group.broker_position_id}",
            ROLE_SYMBOL: group.symbol_name,
            ROLE_SIDE: group.display_side,
            ROLE_VOLUME: group.display_volume,
            ROLE_ORDER_ORIGIN: order_origin,
            ROLE_PNL_VALUE: group_pnl_value,
            ROLE_PNL_APPROXIMATE: False,
            ROLE_PNL_CURRENCY: self._normalize_currency(
                getattr(group, "pnl_currency", "")
            ),
            ROLE_ACCOUNT_ID: group.account_id,
            ROLE_EXTERNAL_EXPOSURE_STATUS: (
                "CONFIRMED"
                if (
                    group.group_mode == IB_POSITION_GROUP_MODE_NET_ONLY
                    and group.broker_position_kind
                    == IB_BROKER_POSITION_KIND_VIRTUAL_FX
                    and group.broker_position_present
                    and abs(float(group.broker_volume or 0.0)) > 0.0
                    and group.reconciliation_status
                    != IB_RECONCILIATION_STATUS_RECONCILED
                )
                else ""
            ),
            ROLE_EXTERNAL_PROTECTIVE_ORDERS: tuple(
                dict(order)
                for order in (
                    getattr(group, "broker_residual_protective_orders", ())
                    or ()
                )
            ),
        }
        self._apply_tree_item_metadata(item, metadata)
        self._apply_tree_item_alignment(item)
        self._apply_tree_item_selectability(item, True)
        self._apply_reconciliation_style(
            item,
            group.reconciliation_status,
        )

        messages = list(group.reconciliation_messages)

        if virtual_fx_group:
            if group.broker_residual_present:
                messages.append(
                    "The group row shows the current IB broker net. Exact "
                    "LGE legs and the read-only broker residual are shown "
                    "as separate child rows."
                )
            elif group.broker_position_present:
                messages.append(
                    "IB CASH Forex position row is a Virtual FX "
                    "observation; displayed side and volume are derived "
                    "from reconciled open LGE legs."
                )
            else:
                messages.append(
                    "IB CASH Forex position row is absent; displayed side "
                    "and volume are derived from reconciled open LGE legs."
                )

            messages.append(
                "Broker entry price, PnL and opened time are hidden because "
                "the Virtual FX observation is not terminal position truth."
            )

        if group.group_mode == IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS:
            messages.append(
                "Protection is defined separately for each virtual leg."
            )

        self._set_ib_item_tooltip(
            item,
            messages,
            all_columns=True,
        )
        return item

    def _build_ib_leg_item(self, group, leg) -> QTreeWidgetItem:
        """Build one child row for an active LGE virtual leg."""
        current_price = self._ib_virtual_leg_current_price(
            group,
            leg.side,
        )
        pnl_value = self.calculate_virtual_leg_pnl(
            side=leg.side,
            volume=leg.volume,
            entry_price=leg.entry_price,
            current_price=current_price,
        )
        pnl_currency = self._ib_virtual_leg_pnl_currency(group)
        pnl_text = self._format_pnl_with_currency(
            pnl_value,
            currency=pnl_currency,
            approximate=True,
        )

        order_origin = self._normalize_lge_order_origin(leg.source)
        operations_enabled = (
            group.leg_operations_enabled
            and leg.leg_status == IB_LEG_STATUS_OPEN
            and leg.reconciliation_status == IB_RECONCILIATION_STATUS_RECONCILED
        )
        selection_enabled = (
            operations_enabled
            or leg.reconciliation_status
            == IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING
        )
        values = [
            self._short_identity(leg.position_uid),
            leg.symbol_name,
            self._lang_mgr.tr(
                "OrdersPage.typeVirtualLeg",
                "LGE LEG",
            ),
            leg.side,
            self._format_ib_units(leg.volume),
            self._format_decimal_for_table(leg.entry_price),
            self._format_decimal_for_table(current_price),
            self._format_decimal_for_table(leg.stop_loss),
            self._format_decimal_for_table(leg.take_profit),
            pnl_text,
            self._format_ib_reconciliation_status(
                leg.reconciliation_status,
            ),
            order_origin,
            self._format_opened_time(leg.opened_utc),
        ]
        item = QTreeWidgetItem(values)
        metadata = {
            ROLE_ROW_KIND: ROW_KIND_LEG,
            ROLE_BROKER_POSITION_ID: leg.broker_position_id,
            ROLE_POSITION_UID: leg.position_uid,
            ROLE_TRADE_UID: leg.trade_uid,
            ROLE_GROUP_MODE: group.group_mode,
            ROLE_BROKER_POSITION_KIND: group.broker_position_kind,
            ROLE_RECONCILIATION_STATUS: leg.reconciliation_status,
            ROLE_LEG_STATUS: leg.leg_status,
            ROLE_OPERATIONS_ENABLED: operations_enabled,
            ROLE_RAW_SL: leg.stop_loss,
            ROLE_RAW_TP: leg.take_profit,
            ROLE_STABLE_KEY: f"LEG:{leg.position_uid}",
            ROLE_SYMBOL: leg.symbol_name,
            ROLE_SIDE: leg.side,
            ROLE_VOLUME: leg.volume,
            ROLE_ORDER_ORIGIN: order_origin,
            ROLE_PNL_VALUE: pnl_value,
            ROLE_PNL_APPROXIMATE: pnl_value is not None,
            ROLE_PNL_CURRENCY: pnl_currency,
        }
        self._apply_tree_item_metadata(item, metadata)
        self._apply_tree_item_alignment(item)
        self._apply_tree_item_selectability(
            item,
            selection_enabled,
        )
        self._apply_reconciliation_style(
            item,
            leg.reconciliation_status,
        )

        tooltip_parts = [
            f"position_uid={leg.position_uid}",
            f"trade_uid={leg.trade_uid}",
            f"leg_status={leg.leg_status}",
            f"protection_status={leg.protection_status}",
        ]
        tooltip_parts.extend(leg.reconciliation_messages)
        self._set_ib_item_tooltip(
            item,
            tooltip_parts,
            all_columns=False,
        )
        return item

    def _build_ib_broker_residual_item(self, group) -> QTreeWidgetItem:
        """Build one read-only child row for external broker exposure."""
        side = group.broker_residual_side
        volume = group.broker_residual_volume
        current_price = self._ib_virtual_leg_current_price(group, side)
        exposure_status = str(
            getattr(group, "broker_residual_evidence_status", "") or ""
        ).strip().upper()
        reconciliation_text = self._format_ib_reconciliation_status(
            group.reconciliation_status,
        )
        protective_orders = tuple(
            dict(order)
            for order in (
                getattr(group, "broker_residual_protective_orders", ()) or ()
            )
        )
        stop_loss = self._single_external_order_price(
            protective_orders,
            order_type_prefix="STP",
        )
        take_profit = self._single_external_order_price(
            protective_orders,
            order_type_prefix="LMT",
        )
        stop_loss_text = self._external_order_price_text(
            protective_orders,
            order_type_prefix="STP",
        )
        take_profit_text = self._external_order_price_text(
            protective_orders,
            order_type_prefix="LMT",
        )

        if exposure_status == IB_FX_EXTERNAL_EXPOSURE_STALE:
            reconciliation_text = self._lang_mgr.tr(
                "OrdersPage.externalExposureNeedsConfirmation",
                "Needs confirmation",
            )

        values = [
            "BROKER",
            group.symbol_name,
            self._lang_mgr.tr(
                "OrdersPage.typeBrokerResidual",
                "External IB exposure",
            ),
            side,
            self._format_ib_units(volume),
            "",
            self._format_decimal_for_table(current_price),
            stop_loss_text,
            take_profit_text,
            "",
            reconciliation_text,
            ORDER_ORIGIN_BROKER,
            "",
        ]
        item = QTreeWidgetItem(values)
        metadata = {
            ROLE_ROW_KIND: ROW_KIND_BROKER_RESIDUAL,
            ROLE_BROKER_POSITION_ID: group.broker_position_id,
            ROLE_POSITION_UID: "",
            ROLE_TRADE_UID: "",
            ROLE_GROUP_MODE: group.group_mode,
            ROLE_BROKER_POSITION_KIND: group.broker_position_kind,
            ROLE_RECONCILIATION_STATUS: group.reconciliation_status,
            ROLE_LEG_STATUS: "",
            ROLE_OPERATIONS_ENABLED: False,
            ROLE_RAW_SL: stop_loss,
            ROLE_RAW_TP: take_profit,
            ROLE_STABLE_KEY: f"RESIDUAL:{group.broker_position_id}",
            ROLE_SYMBOL: group.symbol_name,
            ROLE_SIDE: side,
            ROLE_VOLUME: volume,
            ROLE_ORDER_ORIGIN: ORDER_ORIGIN_BROKER,
            ROLE_PNL_VALUE: None,
            ROLE_PNL_APPROXIMATE: False,
            ROLE_PNL_CURRENCY: "",
            ROLE_EXTERNAL_EXPOSURE_STATUS: exposure_status,
            ROLE_EXTERNAL_PROTECTIVE_ORDERS: protective_orders,
            ROLE_ACCOUNT_ID: group.account_id,
        }
        self._apply_tree_item_metadata(item, metadata)
        self._apply_tree_item_alignment(item)
        self._apply_tree_item_selectability(item, True)
        self._apply_reconciliation_style(
            item,
            group.reconciliation_status,
        )

        if exposure_status == IB_FX_EXTERNAL_EXPOSURE_STALE:
            stale_color = QColor("#ffb347")

            for column in (
                COL_TYPE,
                COL_VOLUME,
                COL_RECONCILIATION,
            ):
                item.setForeground(column, stale_color)

        tooltip = (
            "Read-only broker exposure outside exact LGE virtual legs. "
            "Modify and Close are disabled for this row. "
            f"broker_net={group.broker_signed_volume}; "
            f"managed_open_legs={group.signed_open_leg_volume}; "
            f"broker_residual={group.broker_residual_signed_volume}."
        )
        tooltip_messages = [tooltip]

        if exposure_status == IB_FX_EXTERNAL_EXPOSURE_STALE:
            tooltip_messages.append(
                self._lang_mgr.tr(
                    "OrdersPage.tooltipExternalExposureNeedsConfirmation",
                    "The external IB FX exposure is retained from the "
                    "persistent ledger because the current Virtual FX "
                    "position observation is absent. Broker confirmation "
                    "is required before automated Paper or Live execution "
                    "for this account and symbol.",
                )
            )

        self._set_ib_item_tooltip(
            item,
            tooltip_messages,
            all_columns=True,
        )
        return item

    def _format_external_exposure_evidence_status(
        self,
        value: object,
    ) -> str:
        """Translate the external-exposure evidence state for the user."""
        status = str(value or "").strip().upper()
        mapping = {
            "CONFIRMED": (
                "AlgorithmWorkspaceSafety.evidenceConfirmed",
                "Confirmed",
            ),
            "STALE": (
                "AlgorithmWorkspaceSafety.evidenceStale",
                "Needs broker confirmation",
            ),
            "CLEARED": (
                "AlgorithmWorkspaceSafety.evidenceCleared",
                "Cleared",
            ),
            "EVIDENCE_UNAVAILABLE": (
                "AlgorithmWorkspaceSafety.evidenceUnavailable",
                "Evidence unavailable",
            ),
        }
        key_fallback = mapping.get(status)
        if key_fallback is None:
            return status or "—"
        return self._lang_mgr.tr(*key_fallback)

    @staticmethod
    def _external_protective_orders_from_item(
        item: QTreeWidgetItem,
    ) -> tuple[dict[str, object], ...]:
        """Return normalized current foreign-client order evidence."""
        stored = item.data(COL_ID, ROLE_EXTERNAL_PROTECTIVE_ORDERS)

        if not isinstance(stored, (list, tuple)):
            return ()

        return tuple(dict(order) for order in stored if isinstance(order, dict))

    @staticmethod
    def _external_order_prices(
        orders,
        *,
        order_type_prefix: str,
    ) -> tuple[float, ...]:
        prefix = str(order_type_prefix or "").strip().upper()
        values: list[float] = []

        for order in orders:
            order_type = str(order.get("order_type") or "").strip().upper()
            if not order_type.startswith(prefix):
                continue
            try:
                price = float(order.get("price") or 0.0)
            except (TypeError, ValueError):
                continue
            if price <= 0.0:
                continue
            if not any(abs(price - existing) <= 0.000000001 for existing in values):
                values.append(price)

        return tuple(values)

    @classmethod
    def _single_external_order_price(
        cls,
        orders,
        *,
        order_type_prefix: str,
    ) -> float | None:
        prices = cls._external_order_prices(
            orders,
            order_type_prefix=order_type_prefix,
        )
        return prices[0] if len(prices) == 1 else None

    def _external_order_price_text(
        self,
        orders,
        *,
        order_type_prefix: str,
    ) -> str:
        prices = self._external_order_prices(
            orders,
            order_type_prefix=order_type_prefix,
        )
        if not prices:
            return ""
        if len(prices) > 1:
            return "MULTI"
        return self._format_decimal_for_table(prices[0])

    def _format_external_protective_order_line(self, order) -> str:
        """Format one current TWS protective order with stable identifiers."""
        price = self._format_decimal_for_table(order.get("price")) or "—"
        quantity = self._format_ib_units(order.get("quantity"))
        return self._lang_mgr.tr(
            "OrdersPage.msgExternalExposureOrderLine",
            "{order_type} {action} {quantity} @ {price}; orderId={order_id}; "
            "permId={perm_id}; parentId={parent_id}; clientId={client_id}; "
            "OCA={oca_group}; status={status}; TIF={tif}",
        ).format(
            order_type=str(order.get("order_type") or "—"),
            action=str(order.get("action") or "—"),
            quantity=quantity,
            price=price,
            order_id=order.get("order_id") or 0,
            perm_id=order.get("perm_id") or 0,
            parent_id=order.get("parent_id") or 0,
            client_id=order.get("client_id") or 0,
            oca_group=str(order.get("oca_group") or "—"),
            status=str(order.get("status") or "—"),
            tif=str(order.get("tif") or "—"),
        )

    def _external_protective_orders_tooltip(
        self,
        item: QTreeWidgetItem,
    ) -> str:
        orders = self._external_protective_orders_from_item(item)
        if not orders:
            return self._lang_mgr.tr(
                "OrdersPage.msgExternalExposureNoCurrentOrders",
                "No exact protective-order rows are available in the current "
                "IB snapshot. Do not cancel an order by guess; verify the "
                "position and orders in TWS or an IB statement.",
            )

        header = self._lang_mgr.tr(
            "OrdersPage.msgExternalExposureOrdersHeader",
            "Current foreign-client protective orders received from IB:",
        )
        lines = [header]
        lines.extend(
            self._format_external_protective_order_line(order)
            for order in orders
        )
        return "\n".join(lines)

    @staticmethod
    def _flat_position_stable_key(position) -> str:
        """Build the stable key required for flat broker positions."""
        broker = str(getattr(position, "broker", "") or "").strip().upper()
        position_id = str(getattr(position, "position_id", "") or "").strip()
        prefix = "CTRADER" if broker == "CTRADER" else "POSITION"
        return f"{prefix}:{position_id}"

    @staticmethod
    def _apply_tree_item_metadata(
        item: QTreeWidgetItem,
        metadata: dict[int, object],
    ) -> None:
        """Store stable row identity in Qt roles on the ID column."""
        for role, value in metadata.items():
            item.setData(COL_ID, role, value)

    @staticmethod
    def _apply_tree_item_selectability(
        item: QTreeWidgetItem,
        selectable: bool,
    ) -> None:
        """Allow selection only for rows that expose a safe UI action."""
        flags = item.flags()

        if selectable:
            flags |= Qt.ItemFlag.ItemIsSelectable
        else:
            flags &= ~Qt.ItemFlag.ItemIsSelectable

        item.setFlags(flags)

    @staticmethod
    def _tree_item_selection_allowed(item: QTreeWidgetItem) -> bool:
        """Return whether Qt may keep this row selected or current."""
        return bool(item.flags() & Qt.ItemFlag.ItemIsSelectable)

    @staticmethod
    def _apply_tree_item_alignment(item: QTreeWidgetItem) -> None:
        """Apply consistent alignment to all columns of a tree row."""
        numeric_columns = {
            COL_VOLUME,
            COL_ENTRY,
            COL_CURRENT,
            COL_SL,
            COL_TP,
            COL_PNL,
        }

        for column_index in range(COLUMN_COUNT):
            if column_index in numeric_columns:
                alignment = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            else:
                alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

            item.setTextAlignment(column_index, alignment)

    def _apply_flat_position_tooltips(
        self,
        item: QTreeWidgetItem,
        position,
    ) -> None:
        """Keep full flat-position values available without widening UI."""
        broker = str(getattr(position, "broker", "") or "").strip().upper()
        reconciliation = "—" if broker == "CTRADER" else ""
        raw_values = [
            position.position_id,
            position.symbol_name,
            position.broker,
            position.side,
            position.volume,
            position.entry_price,
            self._format_current_price_for_table(position),
            position.stop_loss,
            position.take_profit,
            position.unrealized_pnl,
            reconciliation,
            position.broker,
            position.opened_utc,
        ]

        for column_index, value in enumerate(raw_values):
            item.setToolTip(
                column_index,
                "" if value is None else str(value),
            )

    def _set_ib_item_tooltip(
        self,
        item: QTreeWidgetItem,
        messages,
        *,
        all_columns: bool,
    ) -> None:
        """Store canonical IB diagnostics and render the active language."""
        raw_messages = tuple(
            str(message or "").strip()
            for message in messages
            if str(message or "").strip()
        )
        item.setData(COL_ID, ROLE_TOOLTIP_MESSAGES, raw_messages)
        item.setData(
            COL_ID,
            ROLE_TOOLTIP_ALL_COLUMNS,
            bool(all_columns),
        )
        self._apply_stored_ib_item_tooltip(item)

    def _apply_stored_ib_item_tooltip(
        self,
        item: QTreeWidgetItem,
    ) -> None:
        """Render one stored IB tooltip without changing broker state."""
        stored = item.data(COL_ID, ROLE_TOOLTIP_MESSAGES)

        if isinstance(stored, str):
            messages = [stored]
        elif isinstance(stored, (list, tuple)):
            messages = list(stored)
        else:
            messages = []

        localized = [
            self._localize_ib_reconciliation_message(message)
            for message in messages
        ]
        if str(item.data(COL_ID, ROLE_ROW_KIND) or "") == (
            ROW_KIND_BROKER_RESIDUAL
        ):
            evidence_text = self._external_protective_orders_tooltip(item)
            if evidence_text:
                localized.append(evidence_text)

        tooltip = "\n".join(message for message in localized if message)
        all_columns = bool(
            item.data(COL_ID, ROLE_TOOLTIP_ALL_COLUMNS)
        )

        if all_columns:
            for column_index in range(COLUMN_COUNT):
                item.setToolTip(column_index, tooltip)
        else:
            item.setToolTip(COL_ID, tooltip)

        if str(item.data(COL_ID, ROLE_ROW_KIND) or "") == ROW_KIND_LEG:
            item.setToolTip(
                COL_PNL,
                self._lang_mgr.tr(
                    "OrdersPage.tooltipCalculatedLegPnl",
                    "Calculated virtual-leg PnL in the quote currency, "
                    "not IB reqPnLSingle.",
                ),
            )

    def _retranslate_current_ib_tooltips(self) -> None:
        """Retranslate current IB diagnostics without a broker refresh."""
        tree = self.ui.tblOpenPositions

        for top_index in range(tree.topLevelItemCount()):
            top_item = tree.topLevelItem(top_index)

            for item in self._walk_tree_items(top_item):
                if item.data(COL_ID, ROLE_TOOLTIP_MESSAGES) is None:
                    continue

                self._apply_stored_ib_item_tooltip(item)

    def _localize_ib_reconciliation_message(self, message) -> str:
        """Translate one canonical Runtime diagnostic at the UI boundary."""
        text = str(message or "").strip()

        if not text or text.startswith("BROKER_RESIDUAL: signed_volume="):
            return ""

        if text.startswith("position_uid="):
            return self._lang_mgr.tr(
                "OrdersPage.tooltipLegPositionUid",
                "Position UID: {value}",
            ).format(value=text.removeprefix("position_uid="))

        if text.startswith("trade_uid="):
            return self._lang_mgr.tr(
                "OrdersPage.tooltipLegTradeUid",
                "Trade UID: {value}",
            ).format(value=text.removeprefix("trade_uid="))

        if text.startswith("leg_status="):
            value = self._format_ib_leg_status(
                text.removeprefix("leg_status=")
            )
            return self._lang_mgr.tr(
                "OrdersPage.tooltipLegStatus",
                "Leg status: {value}",
            ).format(value=value)

        if text.startswith("protection_status="):
            value = self._format_ib_protection_status(
                text.removeprefix("protection_status=")
            )
            return self._lang_mgr.tr(
                "OrdersPage.tooltipProtectionStatus",
                "Protection status: {value}",
            ).format(value=value)

        close_prefix = "CLOSE_EVIDENCE_MISSING: "

        if text.startswith(close_prefix):
            text = text.removeprefix(close_prefix)

        close_evidence_message = (
            "Persisted protective orders are not active and no matching "
            "close execution was found"
        )

        if text.casefold() == close_evidence_message.casefold():
            return self._lang_mgr.tr(
                "OrdersPage.tooltipCloseEvidenceMissing",
                close_evidence_message,
            )

        exact_messages = {
            "Parent MARKET execution is outside current IB history; "
            "persisted reconciled entry was retained": (
                "OrdersPage.tooltipParentExecutionOutsideHistory",
                "Parent MARKET execution is outside current IB history; "
                "persisted reconciled entry was retained",
            ),
            "Parent MARKET execution was not found": (
                "OrdersPage.tooltipParentExecutionMissing",
                "Parent MARKET execution was not found",
            ),
            "Unmapped protective order exists for virtual-leg group": (
                "OrdersPage.tooltipUnmappedProtectiveOrder",
                "Unmapped protective order exists for virtual-leg group",
            ),
            "External TWS protective orders are active, but external "
            "exposure cannot be derived because the IB CASH Forex "
            "position observation is absent.": (
                "OrdersPage.tooltipExternalProtectionWithoutObservation",
                "External TWS protective orders are active, but external "
                "exposure cannot be derived because the IB CASH Forex "
                "position observation is absent.",
            ),
            "Persisted external IB FX exposure is retained because the "
            "current IB CASH Forex position observation is absent; broker "
            "confirmation is required.": (
                "OrdersPage.tooltipExternalExposureRetained",
                "Persisted external IB FX exposure is retained because the "
                "current IB CASH Forex position observation is absent; "
                "broker confirmation is required.",
            ),
            "Foreign-client protective orders still support the persisted "
            "external IB FX exposure, but the current position observation "
            "is absent.": (
                "OrdersPage.tooltipExternalExposureProtectedWithoutObservation",
                "Foreign-client protective orders still support the "
                "persisted external IB FX exposure, but the current position "
                "observation is absent.",
            ),
            "Current IB CASH Forex exposure without exact LGE virtual "
            "legs is represented as read-only external exposure.": (
                "OrdersPage.tooltipCurrentExternalExposure",
                "Current IB CASH Forex exposure without exact LGE virtual "
                "legs is represented as read-only external exposure.",
            ),
            "External IB FX exposure was inferred from active foreign-client "
            "protective orders while the current position observation is "
            "absent; the orders may be orphaned, so broker confirmation is "
            "required.": (
                "OrdersPage.tooltipExternalExposureProtectiveEvidence",
                "External IB FX exposure was inferred from active "
                "foreign-client protective orders while the current "
                "position observation is absent; the orders may be "
                "orphaned, so broker confirmation is required.",
            ),
            "Broker net position has no LGE virtual legs": (
                "OrdersPage.tooltipBrokerNetWithoutVirtualLegs",
                "Broker net position has no LGE virtual legs",
            ),
            "At least one virtual leg is not reconciled": (
                "OrdersPage.tooltipAtLeastOneLegUnreconciled",
                "At least one virtual leg is not reconciled",
            ),
            "IB broker net position snapshot is ambiguous": (
                "OrdersPage.tooltipBrokerNetSnapshotAmbiguous",
                "IB broker net position snapshot is ambiguous",
            ),
            "IB CASH Forex Virtual FX observation offset remained stable "
            "across the exact LGE operation": (
                "OrdersPage.tooltipVirtualFxOffsetStable",
                "IB CASH Forex Virtual FX observation offset remained stable "
                "across the exact LGE operation",
            ),
            "IB CASH Forex position row is a Virtual FX observation; "
            "LGE leg state was reconciled by exact order executions": (
                "OrdersPage.tooltipVirtualFxReconciledByExecutions",
                "IB CASH Forex position row is a Virtual FX observation; "
                "LGE leg state was reconciled by exact order executions",
            ),
            "IB CASH Forex Virtual FX observation follows current open LGE "
            "exposure; older CLOSED-leg executions were excluded": (
                "OrdersPage.tooltipVirtualFxCurrentExposure",
                "IB CASH Forex Virtual FX observation follows current open "
                "LGE exposure; older CLOSED-leg executions were excluded",
            ),
            "IB CASH Forex Virtual FX observation is zero/reset; LGE leg "
            "state was reconciled by exact order identity and persisted "
            "evidence": (
                "OrdersPage.tooltipVirtualFxZeroReset",
                "IB CASH Forex Virtual FX observation is zero/reset; LGE "
                "leg state was reconciled by exact order identity and "
                "persisted evidence",
            ),
            "The group row shows the current IB broker net. Exact LGE legs "
            "and the read-only broker residual are shown as separate child "
            "rows.": (
                "OrdersPage.tooltipGroupShowsBrokerNetAndResidual",
                "The group row shows the current IB broker net. Exact LGE "
                "legs and the read-only broker residual are shown as "
                "separate child rows.",
            ),
            "IB CASH Forex position row is a Virtual FX observation; "
            "displayed side and volume are derived from reconciled open "
            "LGE legs.": (
                "OrdersPage.tooltipVirtualFxDerivedFromLegs",
                "IB CASH Forex position row is a Virtual FX observation; "
                "displayed side and volume are derived from reconciled open "
                "LGE legs.",
            ),
            "IB CASH Forex position row is absent; displayed side and volume "
            "are derived from reconciled open LGE legs.": (
                "OrdersPage.tooltipVirtualFxAbsentDerivedFromLegs",
                "IB CASH Forex position row is absent; displayed side and "
                "volume are derived from reconciled open LGE legs.",
            ),
            "Broker entry price, PnL and opened time are hidden because the "
            "Virtual FX observation is not terminal position truth.": (
                "OrdersPage.tooltipVirtualFxBrokerFieldsHidden",
                "Broker entry price, PnL and opened time are hidden because "
                "the Virtual FX observation is not terminal position truth.",
            ),
            "Protection is defined separately for each virtual leg.": (
                "OrdersPage.tooltipMultipleProtection",
                "Protection is defined separately for each virtual leg.",
            ),
        }
        exact = exact_messages.get(text)

        if exact is not None:
            key, fallback = exact
            return self._lang_mgr.tr(key, fallback)

        patterns = (
            (
                re.compile(
                    r"^Signed sum of open virtual legs differs from IB net "
                    r"position: legs=(?P<legs>[^,]+), "
                    r"broker=(?P<broker>[^,]+), "
                    r"position=(?P<position>.+)$"
                ),
                "OrdersPage.tooltipBrokerNetMismatch",
                "Signed sum of open virtual legs differs from IB net "
                "position: legs={legs}, broker={broker}, "
                "position={position}",
            ),
            (
                re.compile(
                    r"^IB CASH Forex Virtual FX observation offset changed "
                    r"unexpectedly: expected_offset=(?P<expected_offset>[^,]+), "
                    r"actual_offset=(?P<actual_offset>[^,]+), "
                    r"executions=(?P<executions>[^,]+), "
                    r"virtual_fx=(?P<virtual_fx>[^,]+), "
                    r"position=(?P<position>.+)$"
                ),
                "OrdersPage.tooltipVirtualFxOffsetChanged",
                "IB CASH Forex Virtual FX observation offset changed "
                "unexpectedly: expected_offset={expected_offset}, "
                "actual_offset={actual_offset}, executions={executions}, "
                "virtual_fx={virtual_fx}, position={position}",
            ),
            (
                re.compile(
                    r"^IB CASH Forex broker net differs from exact OPEN LGE "
                    r"legs; the difference is represented as a read-only "
                    r"broker residual: residual=(?P<residual>[^,]+), "
                    r"managed=(?P<managed>[^,]+), "
                    r"broker=(?P<broker>[^,]+), "
                    r"position=(?P<position>.+)$"
                ),
                "OrdersPage.tooltipBrokerResidual",
                "IB CASH Forex broker net differs from exact OPEN LGE legs; "
                "the difference is represented as a read-only broker "
                "residual: residual={residual}, managed={managed}, "
                "broker={broker}, position={position}",
            ),
            (
                re.compile(
                    r"^IB CASH Forex external exposure is represented from "
                    r"exact non-LGE executions, not from Virtual FX "
                    r"minus managed-leg arithmetic: "
                    r"external=(?P<external>[^,]+), "
                    r"virtual_fx_minus_managed="
                    r"(?P<virtual_fx_minus_managed>[^,]+), "
                    r"managed=(?P<managed>[^,]+), "
                    r"virtual_fx=(?P<virtual_fx>[^,]+), "
                    r"position=(?P<position>.+)$"
                ),
                "OrdersPage.tooltipExternalExecutionResidual",
                "IB CASH Forex external exposure is represented from exact "
                "non-LGE executions, not from Virtual FX minus "
                "managed-leg arithmetic: external={external}, "
                "virtual_fx_minus_managed={virtual_fx_minus_managed}, "
                "managed={managed}, virtual_fx={virtual_fx}, "
                "position={position}",
            ),
            (
                re.compile(
                    r"^IB CASH Forex external exposure is retained from "
                    r"persisted exact evidence because the current execution "
                    r"snapshot no longer contains that non-LGE execution: "
                    r"external=(?P<external>[^,]+), "
                    r"virtual_fx_minus_managed="
                    r"(?P<virtual_fx_minus_managed>[^,]+), "
                    r"managed=(?P<managed>[^,]+), "
                    r"virtual_fx=(?P<virtual_fx>[^,]+), "
                    r"position=(?P<position>.+)$"
                ),
                "OrdersPage.tooltipPersistedExternalExecutionResidual",
                "IB CASH Forex external exposure is retained from persisted "
                "exact evidence because the current execution snapshot no "
                "longer contains that non-LGE execution: external={external}, "
                "virtual_fx_minus_managed={virtual_fx_minus_managed}, "
                "managed={managed}, virtual_fx={virtual_fx}, "
                "position={position}",
            ),
            (
                re.compile(
                    r"^IB Virtual FX quantity differs from recognized LGE "
                    r"executions: "
                    r"cumulative_executions=(?P<cumulative_executions>[^,]+), "
                    r"current_exposure_executions="
                    r"(?P<current_exposure_executions>[^,]+), "
                    r"virtual_fx=(?P<virtual_fx>[^,]+), "
                    r"position=(?P<position>.+)$"
                ),
                "OrdersPage.tooltipVirtualFxQuantityMismatch",
                "IB Virtual FX quantity differs from recognized LGE "
                "executions: cumulative_executions="
                "{cumulative_executions}, current_exposure_executions="
                "{current_exposure_executions}, virtual_fx={virtual_fx}, "
                "position={position}",
            ),
            (
                re.compile(
                    r"^Read-only broker exposure outside exact LGE virtual "
                    r"legs\. Modify and Close are disabled for this row\. "
                    r"broker_net=(?P<broker_net>[^;]+); "
                    r"managed_open_legs=(?P<managed_open_legs>[^;]+); "
                    r"broker_residual=(?P<broker_residual>.+)\.$"
                ),
                "OrdersPage.tooltipBrokerResidualReadOnly",
                "Read-only broker exposure outside exact LGE virtual legs. "
                "Modify and Close are disabled for this row. "
                "broker_net={broker_net}; "
                "managed_open_legs={managed_open_legs}; "
                "broker_residual={broker_residual}.",
            ),
        )

        for pattern, key, fallback in patterns:
            match = pattern.fullmatch(text)

            if match is not None:
                return self._lang_mgr.tr(key, fallback).format(
                    **match.groupdict()
                )

        return text

    def _format_ib_leg_status(self, status: str) -> str:
        """Return a localized user-facing virtual-leg lifecycle status."""
        status_value = str(status or "").strip().upper()
        translations = {
            IB_LEG_STATUS_OPEN: (
                "OrdersPage.legStatusOpen",
                "Open",
            ),
            IB_LEG_STATUS_PARTIALLY_CLOSED: (
                "OrdersPage.legStatusPartiallyClosed",
                "Partially closed",
            ),
            IB_LEG_STATUS_CLOSED: (
                "OrdersPage.legStatusClosed",
                "Closed",
            ),
        }
        translation = translations.get(status_value)

        if translation is None:
            return str(status or "")

        key, fallback = translation
        return self._lang_mgr.tr(key, fallback)

    def _format_ib_protection_status(self, status: str) -> str:
        """Return a localized user-facing virtual-leg protection status."""
        status_value = str(status or "").strip().upper()
        translations = {
            IB_PROTECTION_STATUS_NONE: (
                "OrdersPage.protectionStatusNone",
                "None",
            ),
            IB_PROTECTION_STATUS_PARTIAL: (
                "OrdersPage.protectionStatusPartial",
                "Partial",
            ),
            IB_PROTECTION_STATUS_COMPLETE: (
                "OrdersPage.protectionStatusComplete",
                "Complete",
            ),
            IB_PROTECTION_STATUS_BLOCKED: (
                "OrdersPage.protectionStatusBlocked",
                "Blocked",
            ),
        }
        translation = translations.get(status_value)

        if translation is None:
            return str(status or "")

        key, fallback = translation
        return self._lang_mgr.tr(key, fallback)

    def _format_ib_reconciliation_status(self, status: str) -> str:
        """Return a localized user-facing IB reconciliation status."""
        status_value = str(status or "").strip().upper()
        status_keys = {
            IB_RECONCILIATION_STATUS_RECONCILED: (
                "OrdersPage.reconciliationReconciled",
                "Reconciled",
            ),
            IB_RECONCILIATION_STATUS_RECONCILED_MANUAL: (
                "OrdersPage.reconciliationReconciledManual",
                "Reconciled manually",
            ),
            IB_RECONCILIATION_STATUS_UNRECONCILED: (
                "OrdersPage.reconciliationUnreconciled",
                "Unreconciled",
            ),
            IB_RECONCILIATION_STATUS_BLOCKED: (
                "OrdersPage.reconciliationBlocked",
                "Blocked",
            ),
            IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING: (
                "OrdersPage.reconciliationCloseEvidenceMissing",
                "Close confirmation missing",
            ),
        }
        translation = status_keys.get(status_value)

        if translation is None:
            return str(status or "")

        key, fallback = translation
        return self._lang_mgr.tr(key, fallback)

    def _retranslate_current_ib_reconciliation_values(self) -> None:
        """Retranslate rendered IB status cells without broker access."""
        tree = self.ui.tblOpenPositions

        for top_index in range(tree.topLevelItemCount()):
            top_item = tree.topLevelItem(top_index)
            items = [top_item]
            items.extend(
                top_item.child(child_index)
                for child_index in range(top_item.childCount())
            )

            for item in items:
                status = str(
                    item.data(COL_ID, ROLE_RECONCILIATION_STATUS) or ""
                ).strip()

                if status:
                    item.setText(
                        COL_RECONCILIATION,
                        self._format_ib_reconciliation_status(status),
                    )

    def _retranslate_current_ib_status(self) -> None:
        """Retranslate the current IB refresh status without a new request."""
        snapshot = self._last_ib_position_group_snapshot

        if snapshot is None:
            return

        warning_text = self._build_group_reconciliation_warning(snapshot)

        if warning_text:
            self._set_orders_status(warning_text, warning=True)
            return

        filter_state = self._apply_position_filters()
        text = self._lang_mgr.tr(
            "OrdersPage.statusPositionGroupsRefreshed",
            "IB position groups refreshed: {groups}; open legs: {legs}",
        ).format(
            groups=filter_state["visible_top_level"],
            legs=filter_state["visible_legs"],
        )
        self._set_orders_status(text)

    @staticmethod
    def _apply_reconciliation_style(
        item: QTreeWidgetItem,
        status: str,
    ) -> None:
        """Show warning and blocked reconciliation states explicitly."""
        if status in {
            IB_RECONCILIATION_STATUS_BLOCKED,
            IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING,
        }:
            color = QColor("#ff5555")
        elif status == IB_RECONCILIATION_STATUS_UNRECONCILED:
            color = QColor("#f2c14e")
        else:
            return

        item.setForeground(COL_RECONCILIATION, color)

    def _format_ib_group_type(self, group) -> str:
        """Return user-facing IB group type."""
        if group.group_mode == IB_POSITION_GROUP_MODE_NET_ONLY:
            return self._lang_mgr.tr(
                "OrdersPage.typeNetOnly",
                "NET ONLY",
            )

        if group.broker_position_kind == IB_BROKER_POSITION_KIND_VIRTUAL_FX:
            return self._lang_mgr.tr(
                "OrdersPage.typeVirtualFx",
                "Virtual FX",
            )

        return self._lang_mgr.tr("OrdersPage.typeIbNet", "IB NET")

    def _group_protection_value(
        self,
        group,
        field_name: str,
    ) -> tuple[float | None, str]:
        """Format NET_ONLY protection or summarize leg-level protection."""
        if group.group_mode == IB_POSITION_GROUP_MODE_NET_ONLY:
            value = getattr(group, field_name, None)
            return value, self._format_decimal_for_table(value)

        values = {
            float(value)
            for value in (getattr(leg, field_name, None) for leg in group.open_legs)
            if value is not None
        }

        if not values:
            return None, ""

        if len(values) == 1:
            value = next(iter(values))
            return value, self._format_decimal_for_table(value)

        return (
            None,
            self._lang_mgr.tr("OrdersPage.valueMultiple", "MULTI"),
        )

    def _build_group_reconciliation_warning(self, snapshot) -> str:
        """Build a compact status while preserving full details in tooltips."""
        details: list[str] = []

        if snapshot.unmapped_protective_order_ids:
            ids = ", ".join(
                str(order_id) for order_id in snapshot.unmapped_protective_order_ids
            )
            details.append(
                self._lang_mgr.tr(
                    "OrdersPage.statusUnmappedProtection",
                    "unmapped protection: {ids}",
                ).format(ids=ids)
            )

        for group in snapshot.groups:
            if (
                group.group_mode == IB_POSITION_GROUP_MODE_NET_ONLY
                and group.reconciliation_status == IB_RECONCILIATION_STATUS_UNRECONCILED
            ):
                continue

            if group.reconciliation_status not in {
                IB_RECONCILIATION_STATUS_BLOCKED,
                IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING,
                IB_RECONCILIATION_STATUS_UNRECONCILED,
            }:
                continue

            status_text = self._format_ib_reconciliation_status(
                group.reconciliation_status,
            )
            details.append(f"{group.symbol_name}={status_text}")

        if not details:
            return ""

        return self._lang_mgr.tr(
            "OrdersPage.statusReconciliationWarning",
            "IB reconciliation warning: {details}",
        ).format(details="; ".join(details))

    @staticmethod
    def calculate_virtual_leg_pnl(
        side: str,
        volume,
        entry_price,
        current_price,
    ) -> float | None:
        """Calculate approximate virtual-leg PnL from group current price."""
        if entry_price is None or current_price is None:
            return None

        try:
            volume_value = float(volume)
            entry_value = float(entry_price)
            current_value = float(current_price)
        except (TypeError, ValueError):
            return None

        if not all(
            math.isfinite(value) for value in (volume_value, entry_value, current_value)
        ):
            return None

        side_value = str(side or "").strip().upper()

        if side_value == "BUY":
            return (current_value - entry_value) * volume_value

        if side_value == "SELL":
            return (entry_value - current_value) * volume_value

        return None

    @staticmethod
    def _format_ib_units(value) -> str:
        """Format IB quantity as units with grouped thousands."""
        if value is None:
            return ""

        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value).strip()

        if not math.isfinite(number):
            return ""

        if number.is_integer():
            return f"{int(number):,}".replace(",", " ")

        return f"{number:,.2f}".replace(",", " ")

    @staticmethod
    def _short_identity(value: str, length: int = 8) -> str:
        """Return a compact identity while preserving the full role value."""
        text = str(value or "").strip()

        if len(text) <= length:
            return text

        return text[:length]

    @staticmethod
    def _format_position_id_for_table(
        position_id: str,
    ) -> str:
        """
        Стиснути broker position id для таблиці.

        Для IB внутрішній id має вигляд:
        IB:DUM513747:EURUSD

        У таблиці показуємо тільки account id:
        DUM513747

        Повний id лишається в Qt.UserRole для close-position логіки.
        """
        text = str(position_id or "").strip()

        if text.startswith("IB:"):
            parts = text.split(":")

            if len(parts) >= 2 and parts[1]:
                return parts[1]

        return text

    @staticmethod
    def _format_opened_time(
        value,
    ) -> str:
        """
        Стиснути broker open timestamp для таблиці.

        Для таблиці показуємо короткий формат:
        - 07-09 12:08

        Повний timestamp лишається у tooltip.
        """
        text = str(value or "").strip()

        if not text:
            return ""

        if (
            len(text) >= 14
            and text[:8].isdigit()
            and text[8] == " "
            and text[9:11].isdigit()
            and text[11] == ":"
            and text[12:14].isdigit()
        ):
            return f"{text[4:6]}-{text[6:8]} {text[9:14]}"

        if text.isdigit():
            raw_timestamp = int(text)
            timestamp_seconds = raw_timestamp

            if raw_timestamp > 10_000_000_000:
                timestamp_seconds = raw_timestamp / 1000

            try:
                return datetime.fromtimestamp(
                    timestamp_seconds,
                    UTC,
                ).strftime("%m-%d %H:%M")
            except Exception:  # noqa
                return text

        normalized = text.replace("Z", "+00:00")

        try:
            parsed = datetime.fromisoformat(normalized)

            return parsed.strftime("%m-%d %H:%M")
        except ValueError:
            pass

        if "T" in text:
            compact = text.replace("T", " ")

            if len(compact) >= 16 and compact[:4].isdigit():
                return compact[5:16]

            return compact[:16]

        return text
