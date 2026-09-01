# ib_position_group.py
"""
Чиста Runtime-модель IB broker net position groups.

RoadMap90:
- звичайна broker position лишається фінансовою правдою IB;
- IB CASH Forex row позначається як Virtual FX observation;
- LGE virtual legs є логічною декомпозицією всередині group;
- broker-only/manual positions не отримують вигаданих virtual legs;
- модуль не залежить від Qt, SQLite або IB API objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from engine.broker_position import (
    POSITION_SIDE_BUY,
    POSITION_SIDE_SELL,
    POSITION_SIDE_UNKNOWN,
)
from engine.ib_fx_external_exposure import (
    IB_FX_EXTERNAL_EXPOSURE_STALE,
)
from engine.ib_virtual_position_leg import (
    IBVirtualPositionLeg,
    IBVirtualPositionLegReconciliationSnapshot,
)
from engine.runtime_constants import (
    IB_BROKER_POSITION_KIND_NET,
    IB_BROKER_POSITION_KIND_VIRTUAL_FX,
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_LEG_STATUS_PARTIALLY_CLOSED,
    IB_OPEN_ORDER_TERMINAL_STATUSES,
    IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS,
    IB_POSITION_GROUP_MODE_NET_ONLY,
    IB_POSITION_QUANTITY_ABS_TOLERANCE,
    IB_PROTECTIVE_ORDER_TYPES,
    IB_RECONCILIATION_STATUS_BLOCKED,
    IB_RECONCILIATION_STATUS_RECONCILED,
    IB_RECONCILIATION_STATUS_UNRECONCILED,
)


@dataclass(slots=True)
class IBPositionGroup:
    """
    Одна IB broker net position із нулем або кількома LGE virtual legs.
    """

    broker_position_id: str
    account_id: str
    symbol_name: str
    broker_position_present: bool
    broker_side: str
    broker_volume: float
    broker_signed_volume: float
    broker_entry_price: float | None
    broker_position_kind: str = IB_BROKER_POSITION_KIND_NET
    broker_residual_signed_volume: float = 0.0
    broker_residual_evidence_status: str = ""
    broker_residual_protective_orders: tuple[dict[str, Any], ...] = field(
        default_factory=tuple
    )
    currency: str = ""
    pnl_currency: str = ""
    current_price: float | None = None
    bid_price: float | None = None
    ask_price: float | None = None
    quote_timestamp: str = ""
    quote_market_data_type: int | None = None
    unrealized_pnl: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    opened_utc: str = ""
    group_mode: str = IB_POSITION_GROUP_MODE_NET_ONLY
    reconciliation_status: str = IB_RECONCILIATION_STATUS_UNRECONCILED
    reconciliation_messages: tuple[str, ...] = field(default_factory=tuple)
    legs: list[IBVirtualPositionLeg] = field(default_factory=list)

    @property
    def open_legs(self) -> list[IBVirtualPositionLeg]:
        """
        Повернути active logical legs цієї group.
        """
        return [
            leg
            for leg in self.legs
            if leg.leg_status in {IB_LEG_STATUS_OPEN, IB_LEG_STATUS_PARTIALLY_CLOSED}
        ]

    @property
    def closed_legs(self) -> list[IBVirtualPositionLeg]:
        """
        Повернути закриті logical legs цієї group.
        """
        return [leg for leg in self.legs if leg.leg_status == IB_LEG_STATUS_CLOSED]

    @property
    def signed_open_leg_volume(self) -> float:
        """
        Повернути signed sum активних LGE legs.
        """
        return sum(leg.signed_volume for leg in self.open_legs)

    @property
    def display_uses_reconciled_legs(self) -> bool:
        """
        Позначити LGE Virtual FX group, яку UI показує через OPEN legs.

        IB CASH Forex position row є лише Virtual FX observation. Після
        restart або зміни trading day вона може зникнути чи описувати не
        logical net відкритих LGE legs. Коли broker row відсутня, UI все
        одно показує persisted OPEN legs, але reconciliation warning і
        заборона операцій залишаються чинними.
        """
        virtual_fx_open_legs = (
            self.broker_position_kind == IB_BROKER_POSITION_KIND_VIRTUAL_FX
            and self.group_mode == IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS
            and bool(self.open_legs)
            and not self.broker_residual_present
        )

        if not virtual_fx_open_legs:
            return False

        return (
            self.reconciliation_status == IB_RECONCILIATION_STATUS_RECONCILED
            or not self.broker_position_present
        )

    @property
    def broker_residual_present(self) -> bool:
        """Return whether broker net contains read-only external exposure."""
        residual = abs(self.broker_residual_signed_volume)
        return residual > IB_POSITION_QUANTITY_ABS_TOLERANCE

    @property
    def broker_residual_confirmation_required(self) -> bool:
        """Return whether the external exposure lacks a current observation."""
        return (
            self.broker_residual_present
            and self.broker_residual_evidence_status == IB_FX_EXTERNAL_EXPOSURE_STALE
        )

    @property
    def broker_residual_side(self) -> str:
        """Return the direction of the read-only broker residual."""
        if self.broker_residual_signed_volume > 0.0:
            return POSITION_SIDE_BUY

        if self.broker_residual_signed_volume < 0.0:
            return POSITION_SIDE_SELL

        return POSITION_SIDE_UNKNOWN

    @property
    def broker_residual_volume(self) -> float:
        """Return absolute read-only broker residual volume."""
        return abs(self.broker_residual_signed_volume)

    @property
    def display_signed_volume(self) -> float:
        """Повернути broker net або safe persisted logical net для UI."""
        persisted_virtual_fx_net = (
            self.broker_position_kind == IB_BROKER_POSITION_KIND_VIRTUAL_FX
            and self.group_mode == IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS
            and not self.broker_position_present
        )

        if persisted_virtual_fx_net:
            return self.signed_open_leg_volume + self.broker_residual_signed_volume

        if self.display_uses_reconciled_legs:
            return self.signed_open_leg_volume

        return self.broker_signed_volume

    @property
    def display_side(self) -> str:
        """Повернути напрямок, який UI може показати без припущень."""
        signed_volume = self.display_signed_volume

        if signed_volume > 0.0:
            return POSITION_SIDE_BUY

        if signed_volume < 0.0:
            return POSITION_SIDE_SELL

        return POSITION_SIDE_UNKNOWN

    @property
    def display_volume(self) -> float:
        """Повернути абсолютний broker або reconciled logical net."""
        return abs(self.display_signed_volume)

    def current_price_for_side(self, side: str) -> float | None:
        """Return executable close-side price for one logical leg."""
        side_value = str(side or "").strip().upper()

        if side_value == POSITION_SIDE_BUY and self.bid_price is not None:
            return self.bid_price

        if side_value == POSITION_SIDE_SELL and self.ask_price is not None:
            return self.ask_price

        return self.current_price

    @property
    def leg_operations_enabled(self) -> bool:
        """Allow exact operations for any individually reconciled OPEN leg."""
        return self.group_mode == IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS and any(
            leg.leg_status == IB_LEG_STATUS_OPEN
            and leg.reconciliation_status == IB_RECONCILIATION_STATUS_RECONCILED
            for leg in self.legs
        )

    @property
    def broker_quantity_is_terminal_truth(self) -> bool:
        """
        Позначити, чи broker quantity є strict net-position truth.

        Для IB CASH Forex TWS/API position row є Virtual FX observation.
        Він корисний для аудиту, але не замінює LGE execution ledger.
        """
        return self.broker_position_kind != IB_BROKER_POSITION_KIND_VIRTUAL_FX

    def to_dict(self) -> dict[str, Any]:
        """
        Перетворити group DTO у стабільний Runtime dict.
        """
        quantity_is_terminal_truth = self.broker_quantity_is_terminal_truth

        return {
            "broker_position_id": self.broker_position_id,
            "account_id": self.account_id,
            "symbol_name": self.symbol_name,
            "broker_position_present": self.broker_position_present,
            "broker_side": self.broker_side,
            "broker_volume": self.broker_volume,
            "broker_signed_volume": self.broker_signed_volume,
            "broker_entry_price": self.broker_entry_price,
            "broker_position_kind": self.broker_position_kind,
            "broker_residual_signed_volume": self.broker_residual_signed_volume,
            "broker_residual_evidence_status": (self.broker_residual_evidence_status),
            "broker_residual_confirmation_required": (
                self.broker_residual_confirmation_required
            ),
            "broker_residual_protective_orders": [
                dict(order) for order in self.broker_residual_protective_orders
            ],
            "broker_residual_present": self.broker_residual_present,
            "broker_residual_side": self.broker_residual_side,
            "broker_residual_volume": self.broker_residual_volume,
            "broker_quantity_is_terminal_truth": quantity_is_terminal_truth,
            "currency": self.currency,
            "pnl_currency": self.pnl_currency,
            "current_price": self.current_price,
            "bid_price": self.bid_price,
            "ask_price": self.ask_price,
            "quote_timestamp": self.quote_timestamp,
            "quote_market_data_type": self.quote_market_data_type,
            "unrealized_pnl": self.unrealized_pnl,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "opened_utc": self.opened_utc,
            "group_mode": self.group_mode,
            "reconciliation_status": self.reconciliation_status,
            "reconciliation_messages": list(self.reconciliation_messages),
            "open_leg_count": len(self.open_legs),
            "closed_leg_count": len(self.closed_legs),
            "signed_open_leg_volume": self.signed_open_leg_volume,
            "display_uses_reconciled_legs": self.display_uses_reconciled_legs,
            "display_signed_volume": self.display_signed_volume,
            "display_side": self.display_side,
            "display_volume": self.display_volume,
            "leg_operations_enabled": self.leg_operations_enabled,
            "legs": [leg.to_dict() for leg in self.legs],
        }


@dataclass(slots=True)
class IBPositionGroupSnapshot:
    """
    Read-only Runtime snapshot IB position groups.
    """

    captured_utc: str
    complete: bool
    groups: list[IBPositionGroup]
    unmapped_protective_order_ids: list[int]

    def to_dict(self) -> dict[str, Any]:
        """
        Перетворити snapshot у стабільний Runtime dict.
        """
        return {
            "captured_utc": self.captured_utc,
            "complete": self.complete,
            "groups": [group.to_dict() for group in self.groups],
            "unmapped_protective_order_ids": list(self.unmapped_protective_order_ids),
        }


def build_ib_position_group_snapshot(
    reconciliation_snapshot: IBVirtualPositionLegReconciliationSnapshot,
    evidence_snapshot: dict[str, Any],
) -> IBPositionGroupSnapshot:
    """
    Побудувати broker-net groups із reconciled legs та IB positions.

    Position row без LGE legs лишається NET_ONLY. Group із persisted legs,
    але без поточного broker position row, не зникає: вона показується з
    broker_position_present=False та reconciliation status із reconciler.
    """
    if not reconciliation_snapshot.complete:
        raise RuntimeError("IB virtual-leg reconciliation is incomplete")

    evidence_complete = evidence_snapshot.get("complete")
    if not isinstance(evidence_complete, bool) or not evidence_complete:
        raise RuntimeError("IB virtual-leg evidence is incomplete")

    position_rows = [
        row
        for row in evidence_snapshot.get("positions") or []
        if not _position_row_is_explicitly_flat(row)
    ]
    legs_by_group = _group_legs(reconciliation_snapshot.legs)
    positions_by_group = _group_positions(position_rows)
    external_exposures = {
        broker_position_id: exposure
        for broker_position_id, exposure in (
            reconciliation_snapshot.group_external_exposures.items()
        )
        if exposure.is_active
    }
    ordered_ids = _ordered_group_ids(
        legs=reconciliation_snapshot.legs,
        position_rows=position_rows,
    )

    for broker_position_id in external_exposures:
        if broker_position_id not in ordered_ids:
            ordered_ids.append(broker_position_id)

    groups: list[IBPositionGroup] = []

    for broker_position_id in ordered_ids:
        persisted_legs = list(legs_by_group.get(broker_position_id, []))
        position_rows = positions_by_group.get(broker_position_id, [])

        if (
            reconciliation_snapshot.group_cash_fx_managed_observation_only.get(
                broker_position_id,
                False,
            )
            and broker_position_id not in external_exposures
        ):
            continue

        group_mode = _active_group_mode(
            legs=persisted_legs,
            position_rows=position_rows,
        )

        if broker_position_id in external_exposures:
            group_mode = IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS

        active_group_legs = (
            persisted_legs
            if group_mode == IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS
            else []
        )
        status, messages = _group_reconciliation_state(
            broker_position_id=broker_position_id,
            group_mode=group_mode,
            persisted_legs=persisted_legs,
            position_rows=position_rows,
            reconciliation_snapshot=reconciliation_snapshot,
        )
        broker_state = _build_broker_state(position_rows)
        account_id, symbol_name = _group_identity(
            broker_position_id=broker_position_id,
            legs=persisted_legs,
            position_rows=position_rows,
        )
        broker_position_kind = _broker_position_kind(
            broker_position_id=broker_position_id,
            account_id=account_id,
            symbol_name=symbol_name,
            persisted_legs=persisted_legs,
            evidence_snapshot=evidence_snapshot,
        )

        if broker_position_id in external_exposures:
            broker_position_kind = IB_BROKER_POSITION_KIND_VIRTUAL_FX
        broker_residual_signed_volume = 0.0
        broker_residual_evidence_status = ""
        broker_residual_protective_orders: tuple[dict[str, Any], ...] = ()

        if group_mode == IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS:
            residual_volumes = (
                reconciliation_snapshot.group_broker_residual_signed_volumes
            )
            broker_residual_signed_volume = residual_volumes.get(
                broker_position_id,
                0.0,
            )
            broker_residual_evidence_status = (
                reconciliation_snapshot.group_broker_residual_evidence_statuses.get(
                    broker_position_id, ""
                )
            )
            broker_residual_protective_orders = _external_protective_order_details(
                evidence_snapshot=evidence_snapshot,
                broker_position_id=broker_position_id,
                account_id=account_id,
                symbol_name=symbol_name,
            )

        groups.append(
            IBPositionGroup(
                broker_position_id=broker_position_id,
                account_id=account_id,
                symbol_name=symbol_name,
                broker_position_present=bool(position_rows),
                broker_side=broker_state["side"],
                broker_volume=broker_state["volume"],
                broker_signed_volume=broker_state["signed_volume"],
                broker_entry_price=broker_state["entry_price"],
                broker_position_kind=broker_position_kind,
                broker_residual_signed_volume=broker_residual_signed_volume,
                broker_residual_evidence_status=(broker_residual_evidence_status),
                broker_residual_protective_orders=(broker_residual_protective_orders),
                currency=broker_state["currency"],
                pnl_currency=broker_state["pnl_currency"],
                current_price=broker_state["current_price"],
                unrealized_pnl=broker_state["unrealized_pnl"],
                stop_loss=broker_state["stop_loss"],
                take_profit=broker_state["take_profit"],
                opened_utc=broker_state["opened_utc"],
                group_mode=group_mode,
                reconciliation_status=status,
                reconciliation_messages=messages,
                legs=active_group_legs,
            )
        )

    return IBPositionGroupSnapshot(
        captured_utc=reconciliation_snapshot.captured_utc,
        complete=True,
        groups=groups,
        unmapped_protective_order_ids=list(
            reconciliation_snapshot.unmapped_protective_order_ids
        ),
    )


def _external_protective_order_details(
    *,
    evidence_snapshot: dict[str, Any],
    broker_position_id: str,
    account_id: str,
    symbol_name: str,
) -> tuple[dict[str, Any], ...]:
    """Return current foreign-client SL/TP rows that prove the residual.

    The rows are read-only evidence. They are deliberately not persisted as
    broker truth because TWS can replace, cancel or renumber them between
    snapshots. ``perm_id`` remains the preferred stable identifier when the
    API reports ``order_id=0`` for a foreign client.
    """
    current_client_id = _optional_int(evidence_snapshot.get("current_client_id"))
    details: list[dict[str, Any]] = []

    for source_row in evidence_snapshot.get("open_orders") or []:
        row = dict(source_row)
        status = str(row.get("status") or "").strip().upper()

        if status in IB_OPEN_ORDER_TERMINAL_STATUSES:
            continue

        order_type = str(row.get("order_type") or "").strip().upper()

        if order_type not in IB_PROTECTIVE_ORDER_TYPES:
            continue

        if not _row_matches_group(
            row=row,
            broker_position_id=broker_position_id,
            account_id=account_id,
            symbol_name=symbol_name,
        ):
            continue

        same_client_id = row.get("same_client_id")
        row_client_id = _optional_int(row.get("client_id"))

        if isinstance(same_client_id, bool):
            if same_client_id:
                continue
        elif (
            current_client_id is not None
            and row_client_id is not None
            and row_client_id == current_client_id
        ):
            continue

        quantity = _safe_float(row.get("total_quantity", row.get("quantity")))

        if quantity <= IB_POSITION_QUANTITY_ABS_TOLERANCE:
            continue

        lmt_price = _safe_float(row.get("lmt_price"))
        aux_price = _safe_float(row.get("aux_price"))
        price = aux_price if order_type.startswith("STP") else lmt_price

        details.append(
            {
                "order_id": _optional_int(row.get("order_id")) or 0,
                "perm_id": _optional_int(row.get("perm_id")) or 0,
                "parent_id": _optional_int(row.get("parent_id")) or 0,
                "client_id": row_client_id if row_client_id is not None else 0,
                "oca_group": str(row.get("oca_group") or "").strip(),
                "action": str(row.get("action") or "").strip().upper(),
                "order_type": order_type,
                "quantity": quantity,
                "price": price if price > 0.0 else None,
                "lmt_price": lmt_price if lmt_price > 0.0 else None,
                "aux_price": aux_price if aux_price > 0.0 else None,
                "status": str(row.get("status") or "").strip(),
                "tif": str(row.get("tif") or "").strip(),
            }
        )

    details.sort(
        key=lambda item: (
            int(item.get("parent_id") or 0),
            str(item.get("oca_group") or ""),
            str(item.get("order_type") or ""),
            int(item.get("perm_id") or 0),
            int(item.get("order_id") or 0),
        )
    )
    return tuple(details)


def _broker_position_kind(
    broker_position_id: str,
    account_id: str,
    symbol_name: str,
    persisted_legs: list[IBVirtualPositionLeg],
    evidence_snapshot: dict[str, Any],
) -> str:
    """
    Визначити strict broker net або IB Virtual FX observation.

    Поточний IB CASH evidence може зникнути після reset Virtual FX row.
    Наявність persisted IB virtual legs зберігає тип групи між сесіями.
    """
    evidence_rows = (
        list(evidence_snapshot.get("positions") or [])
        + list(evidence_snapshot.get("open_orders") or [])
        + list(evidence_snapshot.get("completed_orders") or [])
        + list(evidence_snapshot.get("executions") or [])
    )

    for row in evidence_rows:
        if not _row_matches_group(
            row=row,
            broker_position_id=broker_position_id,
            account_id=account_id,
            symbol_name=symbol_name,
        ):
            continue

        if str(row.get("sec_type") or "").strip().upper() == "CASH":
            return IB_BROKER_POSITION_KIND_VIRTUAL_FX

    if persisted_legs:
        return IB_BROKER_POSITION_KIND_VIRTUAL_FX

    return IB_BROKER_POSITION_KIND_NET


def _row_matches_group(
    row: dict[str, Any],
    broker_position_id: str,
    account_id: str,
    symbol_name: str,
) -> bool:
    """
    Перевірити account + contract identity одного evidence row.
    """
    row_position_id = str(row.get("broker_position_id") or "").strip()

    if row_position_id:
        return row_position_id == broker_position_id

    row_account = str(row.get("account_id") or row.get("account") or "").strip()
    row_symbol = _symbol_name_from_row(row)
    return row_account == account_id and row_symbol == symbol_name


def _symbol_name_from_row(row: dict[str, Any]) -> str:
    """
    Побудувати canonical symbol із scalar evidence row.
    """
    symbol_name = str(row.get("symbol_name") or "").strip().upper()

    if symbol_name:
        return symbol_name

    symbol = str(row.get("symbol") or "").strip().upper()
    currency = str(row.get("currency") or "").strip().upper()
    return f"{symbol}{currency}" if symbol and currency else symbol


def _active_group_mode(
    legs: list[IBVirtualPositionLeg],
    position_rows: list[dict[str, Any]],
) -> str:
    """Визначити режим поточної активної broker exposure."""
    has_open_legs = any(
        leg.leg_status in {IB_LEG_STATUS_OPEN, IB_LEG_STATUS_PARTIALLY_CLOSED}
        for leg in legs
    )

    if has_open_legs:
        return IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS

    if position_rows:
        return IB_POSITION_GROUP_MODE_NET_ONLY

    if legs:
        return IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS

    return IB_POSITION_GROUP_MODE_NET_ONLY


def _group_legs(
    legs: Iterable[IBVirtualPositionLeg],
) -> dict[str, list[IBVirtualPositionLeg]]:
    """
    Згрупувати legs за broker position id зі стабільним порядком.
    """
    result: dict[str, list[IBVirtualPositionLeg]] = {}

    for leg in legs:
        result.setdefault(leg.broker_position_id, []).append(leg)

    return result


def _position_row_is_explicitly_flat(row: dict[str, Any]) -> bool:
    """Return whether IB explicitly reported a zero broker position."""
    signed_quantity = _optional_float(row.get("signed_quantity", row.get("position")))
    return signed_quantity is not None and abs(signed_quantity) <= 1e-12


def _group_positions(
    position_rows: Iterable[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    Згрупувати scalar IB position evidence rows.
    """
    result: dict[str, list[dict[str, Any]]] = {}

    for row in position_rows:
        broker_position_id = str(row.get("broker_position_id") or "").strip()

        if broker_position_id:
            result.setdefault(broker_position_id, []).append(row)

    return result


def _ordered_group_ids(
    legs: Iterable[IBVirtualPositionLeg],
    position_rows: Iterable[dict[str, Any]],
) -> list[str]:
    """
    Повернути LGE groups першими, потім broker-only groups.
    """
    result: list[str] = []

    for leg in legs:
        if leg.broker_position_id not in result:
            result.append(leg.broker_position_id)

    for row in position_rows:
        broker_position_id = str(row.get("broker_position_id") or "").strip()

        if broker_position_id and broker_position_id not in result:
            result.append(broker_position_id)

    return result


def _group_reconciliation_state(
    broker_position_id: str,
    group_mode: str,
    persisted_legs: list[IBVirtualPositionLeg],
    position_rows: list[dict[str, Any]],
    reconciliation_snapshot: IBVirtualPositionLegReconciliationSnapshot,
) -> tuple[str, tuple[str, ...]]:
    """
    Визначити reconciliation state без реконструкції broker-only legs.
    """
    reconciliation_status = reconciliation_snapshot.group_statuses.get(
        broker_position_id,
        IB_RECONCILIATION_STATUS_UNRECONCILED,
    )
    reconciliation_messages = reconciliation_snapshot.group_messages.get(
        broker_position_id,
        (),
    )

    if group_mode == IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS:
        return reconciliation_status, reconciliation_messages

    if persisted_legs and reconciliation_status == IB_RECONCILIATION_STATUS_BLOCKED:
        return reconciliation_status, reconciliation_messages

    if len(position_rows) > 1:
        return (
            IB_RECONCILIATION_STATUS_BLOCKED,
            ("IB broker net position snapshot is ambiguous",),
        )

    return (
        IB_RECONCILIATION_STATUS_UNRECONCILED,
        ("Broker net position has no LGE virtual legs",),
    )


def _build_broker_state(
    position_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Нормалізувати broker-net fields без припущень при ambiguity.
    """
    if len(position_rows) != 1:
        return {
            "side": POSITION_SIDE_UNKNOWN,
            "volume": 0.0,
            "signed_volume": 0.0,
            "entry_price": None,
            "currency": "",
            "pnl_currency": "",
            "current_price": None,
            "unrealized_pnl": None,
            "stop_loss": None,
            "take_profit": None,
            "opened_utc": "",
        }

    row = position_rows[0]
    signed_volume = _safe_float(row.get("signed_quantity", row.get("position")))

    if signed_volume > 0.0:
        side = POSITION_SIDE_BUY
    elif signed_volume < 0.0:
        side = POSITION_SIDE_SELL
    else:
        side = POSITION_SIDE_UNKNOWN

    return {
        "side": side,
        "volume": abs(signed_volume),
        "signed_volume": signed_volume,
        "entry_price": _optional_float(row.get("average_cost", row.get("avg_cost"))),
        "currency": str(row.get("currency") or "").strip().upper(),
        "pnl_currency": str(row.get("pnl_currency") or "").strip().upper(),
        "current_price": _optional_float(row.get("current_price")),
        "unrealized_pnl": _optional_float(row.get("unrealized_pnl")),
        "stop_loss": _optional_float(row.get("stop_loss")),
        "take_profit": _optional_float(row.get("take_profit")),
        "opened_utc": str(row.get("opened_utc") or "").strip(),
    }


def _group_identity(
    broker_position_id: str,
    legs: list[IBVirtualPositionLeg],
    position_rows: list[dict[str, Any]],
) -> tuple[str, str]:
    """
    Визначити account і symbol із leg, broker row або position id.
    """
    if legs:
        return legs[0].account_id, legs[0].symbol_name

    if position_rows:
        row = position_rows[0]
        return (
            str(row.get("account_id") or row.get("account") or "").strip(),
            str(row.get("symbol_name") or "").strip().upper(),
        )

    parts = broker_position_id.split(":", 2)

    if len(parts) == 3:
        return parts[1], parts[2].upper()

    return "", ""


def _optional_int(value: object) -> int | None:
    """Safely normalize an optional scalar integer."""
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float, str, bytes, bytearray)):
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return None

    return None


def _safe_float(value: object) -> float:
    """
    Безпечно нормалізувати scalar number.
    """
    if isinstance(value, bool) or value is None:
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return 0.0

    return 0.0


def _optional_float(value: object) -> float | None:
    """
    Безпечно нормалізувати optional scalar number.
    """
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        text = value.strip()

        if not text:
            return None

        try:
            return float(text)
        except ValueError:
            return None

    return None
