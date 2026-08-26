# ib_virtual_position_leg.py
"""
Чиста Runtime-модель IB virtual position legs.

RoadMap90:
- без Qt;
- без SQLite;
- без IB API objects;
- broker net position залишається фінансовою правдою IB;
- virtual leg описує логічний LGE-вхід усередині broker net position.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from typing import Any, Iterable

from engine.broker_position import POSITION_SIDE_BUY, POSITION_SIDE_SELL
from engine.ib_fx_external_exposure import (
    IB_FX_EXTERNAL_EXPOSURE_CONFIRMED,
    IB_FX_EXTERNAL_EXPOSURE_STALE,
    IBFxExternalExposure,
)
from engine.runtime_constants import (
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_LEG_STATUS_PARTIALLY_CLOSED,
    IB_OPEN_ORDER_TERMINAL_STATUSES,
    IB_POSITION_QUANTITY_ABS_TOLERANCE,
    IB_PROTECTION_STATUS_BLOCKED,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_PROTECTION_STATUS_NONE,
    IB_PROTECTION_STATUS_PARTIAL,
    IB_PROTECTIVE_ORDER_TYPES,
    IB_RECONCILIATION_STATUS_BLOCKED,
    IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING,
    IB_RECONCILIATION_STATUS_RECONCILED,
    IB_RECONCILIATION_STATUS_UNRECONCILED,
    IB_SL_TP_COVERAGE_REL_TOLERANCE,
    IB_STOP_ORDER_TYPES,
    IB_TAKE_PROFIT_ORDER_TYPES,
)

IB_BROKER_RESIDUAL_MESSAGE_PREFIX = "BROKER_RESIDUAL: signed_volume="
IB_EXTERNAL_PROTECTION_WITHOUT_OBSERVATION_MESSAGE = (
    "External TWS protective orders are active, but external exposure "
    "cannot be derived because the IB CASH Forex position observation "
    "is absent."
)
IB_EXTERNAL_EXPOSURE_STALE_MESSAGE = (
    "Persisted external IB FX exposure is retained because the current "
    "IB CASH Forex position observation is absent; broker confirmation "
    "is required."
)
IB_EXTERNAL_EXPOSURE_STALE_PROTECTED_MESSAGE = (
    "Foreign-client protective orders still support the persisted external "
    "IB FX exposure, but the current position observation is absent."
)
IB_EXTERNAL_EXPOSURE_CURRENT_MESSAGE = (
    "Current IB CASH Forex exposure without exact LGE virtual legs is "
    "represented as read-only external exposure."
)
IB_EXTERNAL_EXPOSURE_PROTECTIVE_EVIDENCE_MESSAGE = (
    "External IB FX exposure was inferred from active foreign-client "
    "protective orders while the current position observation is absent; "
    "the orders may be orphaned, so broker confirmation is required."
)


@dataclass(slots=True)
class IBVirtualPositionLeg:
    """
    Логічна LGE-leg усередині однієї IB broker net position.

    Об'єкт не стверджує, що IB має окрему hedge position для цієї leg.
    """

    position_uid: str
    trade_uid: str
    broker_position_id: str
    account_id: str
    symbol_name: str
    side: str
    volume: float
    entry_price: float | None
    opened_utc: str
    source: str

    parent_order_id: int | None = None
    stop_loss_order_id: int | None = None
    take_profit_order_id: int | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    oca_group: str = ""
    close_order_ids: tuple[int, ...] = field(default_factory=tuple)
    parent_order_perm_id: int | None = None
    stop_loss_order_perm_id: int | None = None
    take_profit_order_perm_id: int | None = None

    leg_status: str = IB_LEG_STATUS_OPEN
    protection_status: str = IB_PROTECTION_STATUS_NONE
    reconciliation_status: str = IB_RECONCILIATION_STATUS_UNRECONCILED
    reconciliation_messages: tuple[str, ...] = field(default_factory=tuple)

    @property
    def signed_volume(self) -> float:
        """
        Повернути signed volume цієї leg.
        """
        if self.side == POSITION_SIDE_BUY:
            return float(self.volume)

        if self.side == POSITION_SIDE_SELL:
            return -float(self.volume)

        return 0.0

    @property
    def protective_action(self) -> str:
        """
        Повернути протилежну action для protective orders.
        """
        if self.side == POSITION_SIDE_BUY:
            return "SELL"

        if self.side == POSITION_SIDE_SELL:
            return "BUY"

        return ""

    def to_dict(self) -> dict[str, Any]:
        """
        Перетворити DTO у стабільний Runtime dict.
        """
        return {
            "position_uid": self.position_uid,
            "trade_uid": self.trade_uid,
            "broker_position_id": self.broker_position_id,
            "account_id": self.account_id,
            "symbol_name": self.symbol_name,
            "side": self.side,
            "volume": self.volume,
            "entry_price": self.entry_price,
            "opened_utc": self.opened_utc,
            "source": self.source,
            "parent_order_id": self.parent_order_id,
            "stop_loss_order_id": self.stop_loss_order_id,
            "take_profit_order_id": self.take_profit_order_id,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "oca_group": self.oca_group,
            "close_order_ids": list(self.close_order_ids),
            "parent_order_perm_id": self.parent_order_perm_id,
            "stop_loss_order_perm_id": self.stop_loss_order_perm_id,
            "take_profit_order_perm_id": self.take_profit_order_perm_id,
            "leg_status": self.leg_status,
            "protection_status": self.protection_status,
            "reconciliation_status": self.reconciliation_status,
            "reconciliation_messages": list(self.reconciliation_messages),
        }


@dataclass(slots=True)
class IBVirtualPositionLegReconciliationSnapshot:
    """
    Результат чистого reconciliation без broker operations.
    """

    captured_utc: str
    complete: bool
    legs: list[IBVirtualPositionLeg]
    group_statuses: dict[str, str]
    group_messages: dict[str, tuple[str, ...]]
    unmapped_protective_order_ids: list[int]
    group_broker_residual_signed_volumes: dict[str, float] = field(default_factory=dict)
    group_broker_residual_evidence_statuses: dict[str, str] = field(
        default_factory=dict
    )
    group_external_exposures: dict[str, IBFxExternalExposure] = field(
        default_factory=dict
    )
    group_cash_fx_managed_observation_only: dict[str, bool] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        """
        Перетворити reconciliation snapshot у dict.
        """
        return {
            "captured_utc": self.captured_utc,
            "complete": self.complete,
            "legs": [leg.to_dict() for leg in self.legs],
            "group_statuses": dict(self.group_statuses),
            "group_messages": {
                key: list(value) for key, value in self.group_messages.items()
            },
            "group_broker_residual_signed_volumes": dict(
                self.group_broker_residual_signed_volumes
            ),
            "group_broker_residual_evidence_statuses": dict(
                self.group_broker_residual_evidence_statuses
            ),
            "group_external_exposures": {
                key: {
                    "broker_position_id": exposure.broker_position_id,
                    "account_id": exposure.account_id,
                    "symbol_name": exposure.symbol_name,
                    "signed_volume": exposure.signed_volume,
                    "evidence_status": exposure.evidence_status,
                    "last_confirmed_utc": exposure.last_confirmed_utc,
                    "last_observed_utc": exposure.last_observed_utc,
                    "updated_utc": exposure.updated_utc,
                }
                for key, exposure in self.group_external_exposures.items()
            },
            "group_cash_fx_managed_observation_only": dict(
                self.group_cash_fx_managed_observation_only
            ),
            "unmapped_protective_order_ids": list(self.unmapped_protective_order_ids),
        }


def build_ib_virtual_position_legs_from_repository_seeds(
    seeds: Iterable[dict[str, Any]],
) -> list[IBVirtualPositionLeg]:
    """
    Побудувати unreconciled DTO з read-only RuntimeRepository seeds.

    Broker snapshot price/side/volume навмисно не переносяться в leg,
    бо після IB netting вони описують net position, а не окремий вхід.
    """
    result: list[IBVirtualPositionLeg] = []

    for seed in seeds:
        result.append(
            IBVirtualPositionLeg(
                position_uid=str(seed.get("position_uid") or "").strip(),
                trade_uid=str(seed.get("trade_uid") or "").strip(),
                broker_position_id=str(seed.get("broker_position_id") or "").strip(),
                account_id=str(seed.get("account_id") or "").strip(),
                symbol_name=str(seed.get("symbol_name") or "").strip().upper(),
                side=str(seed.get("logical_side") or "").strip().upper(),
                volume=_safe_float(seed.get("logical_volume")),
                entry_price=_optional_float(seed.get("persisted_entry_price")),
                opened_utc=str(seed.get("persisted_opened_utc") or "").strip(),
                source=str(seed.get("trade_source") or "").strip().upper(),
                parent_order_id=(
                    _optional_int(seed.get("persisted_parent_order_id"))
                    or _optional_int(seed.get("parent_order_id"))
                ),
                stop_loss_order_id=_optional_int(
                    seed.get("persisted_stop_loss_order_id")
                ),
                take_profit_order_id=_optional_int(
                    seed.get("persisted_take_profit_order_id")
                ),
                stop_loss=_optional_float(seed.get("persisted_stop_loss")),
                take_profit=_optional_float(seed.get("persisted_take_profit")),
                oca_group=str(seed.get("persisted_oca_group") or "").strip(),
                close_order_ids=_optional_int_tuple(
                    seed.get("persisted_close_order_ids")
                ),
                parent_order_perm_id=_optional_int(
                    seed.get("persisted_parent_perm_id")
                ),
                stop_loss_order_perm_id=_optional_int(
                    seed.get("persisted_stop_loss_perm_id")
                ),
                take_profit_order_perm_id=_optional_int(
                    seed.get("persisted_take_profit_perm_id")
                ),
                leg_status=str(seed.get("persisted_leg_status") or IB_LEG_STATUS_OPEN)
                .strip()
                .upper(),
                protection_status=str(
                    seed.get("persisted_protection_status") or IB_PROTECTION_STATUS_NONE
                )
                .strip()
                .upper(),
                reconciliation_status=str(
                    seed.get("persisted_reconciliation_status")
                    or IB_RECONCILIATION_STATUS_UNRECONCILED
                )
                .strip()
                .upper(),
                reconciliation_messages=_persisted_reconciliation_messages(
                    seed.get("persisted_reconciliation_messages_json")
                ),
            )
        )

    return result


def _persisted_reconciliation_messages(value: object) -> tuple[str, ...]:
    """Return persisted reconciliation messages from one repository seed."""
    if value is None:
        return ()

    try:
        payload = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return ()

    if not isinstance(payload, list):
        return ()

    return tuple(message for item in payload if (message := str(item or "").strip()))


def build_confirmed_ib_virtual_position_leg_after_open(
    *,
    position_uid: str,
    trade_uid: str,
    broker_position_id: str,
    account_id: str,
    symbol_name: str,
    side: str,
    volume: float,
    source: str,
    broker_result: dict[str, Any],
    evidence_snapshot: dict[str, Any],
) -> IBVirtualPositionLeg:
    """
    Build one confirmed LGE-owned leg immediately after IB Open.

    CASH Forex Virtual FX quantity is deliberately not used here. The broker
    effect was already proven by the before/after position delta in
    RuntimeEngine. This function proves the exact parent execution and exact
    active child order identities from one complete IB evidence snapshot.
    """
    _validate_complete_evidence_snapshot(evidence_snapshot)

    position_uid_clean = str(position_uid or "").strip()
    trade_uid_clean = str(trade_uid or "").strip()
    broker_position_id_clean = str(broker_position_id or "").strip()
    account_id_clean = str(account_id or "").strip()
    symbol_name_clean = str(symbol_name or "").strip().upper()
    side_clean = str(side or "").strip().upper()
    source_clean = str(source or "").strip().upper()
    volume_value = abs(float(volume))

    if not all(
        (
            position_uid_clean,
            trade_uid_clean,
            broker_position_id_clean,
            account_id_clean,
            symbol_name_clean,
            source_clean,
        )
    ):
        raise RuntimeError("New IB virtual-leg identity is incomplete")

    if side_clean not in {POSITION_SIDE_BUY, POSITION_SIDE_SELL}:
        raise RuntimeError("New IB virtual-leg side is invalid")

    if volume_value <= 0.0:
        raise RuntimeError("New IB virtual-leg volume is not positive")

    broker_status = str(broker_result.get("status") or "").strip().upper()

    if broker_status != "FILLED":
        raise RuntimeError("New IB virtual-leg parent order is not FILLED")

    broker_filled = abs(_safe_float(broker_result.get("filled")))
    broker_remaining = abs(_safe_float(broker_result.get("remaining")))

    if not _quantities_equal(broker_filled, volume_value):
        raise RuntimeError("New IB virtual-leg broker filled quantity differs")

    if not _quantities_equal(broker_remaining, 0.0):
        raise RuntimeError("New IB virtual-leg broker remaining quantity is not zero")

    parent_order_id = _optional_int(
        broker_result.get("parent_order_id")
        or broker_result.get("broker_order_id")
        or broker_result.get("order_id")
    )

    if parent_order_id is None:
        raise RuntimeError("New IB virtual-leg parent order id is missing")

    matching_executions = [
        row
        for row in evidence_snapshot.get("executions") or []
        if _optional_int(row.get("order_id")) == parent_order_id
        and str(row.get("account") or "").strip() == account_id_clean
        and _symbol_name_from_row(row) == symbol_name_clean
        and _execution_side(row.get("side")) == side_clean
    ]

    if not matching_executions:
        raise RuntimeError("New IB virtual-leg parent execution was not found")

    executed_volume = sum(
        abs(_safe_float(row.get("shares"))) for row in matching_executions
    )

    if not _quantities_equal(executed_volume, volume_value):
        raise RuntimeError("New IB virtual-leg parent execution quantity differs")

    entry_numerator = sum(
        abs(_safe_float(row.get("shares"))) * _safe_float(row.get("price"))
        for row in matching_executions
    )
    entry_price = entry_numerator / executed_volume

    if entry_price <= 0.0:
        raise RuntimeError("New IB virtual-leg execution price is not positive")

    broker_avg_fill_price = _optional_float(broker_result.get("avg_fill_price"))

    if broker_avg_fill_price is not None and not math.isclose(
        entry_price,
        broker_avg_fill_price,
        rel_tol=IB_SL_TP_COVERAGE_REL_TOLERANCE,
        abs_tol=IB_POSITION_QUANTITY_ABS_TOLERANCE,
    ):
        raise RuntimeError("New IB virtual-leg average fill price differs")

    opened_utc = next(
        (
            str(row.get("time") or "").strip()
            for row in reversed(matching_executions)
            if str(row.get("time") or "").strip()
        ),
        str(evidence_snapshot.get("captured_utc") or "").strip(),
    )
    stop_loss_order_id = _optional_int(broker_result.get("stop_loss_order_id"))
    take_profit_order_id = _optional_int(broker_result.get("take_profit_order_id"))
    stop_loss = _optional_float(broker_result.get("stop_loss"))
    take_profit = _optional_float(broker_result.get("take_profit"))

    expected_child_ids = {
        order_id
        for order_id in (stop_loss_order_id, take_profit_order_id)
        if order_id is not None
    }
    reported_child_ids = {
        order_id
        for value in broker_result.get("child_order_ids") or []
        if (order_id := _optional_int(value)) is not None
    }

    if reported_child_ids != expected_child_ids:
        raise RuntimeError("New IB virtual-leg child order ids differ")

    if (stop_loss is None) != (stop_loss_order_id is None):
        raise RuntimeError("New IB virtual-leg Stop Loss identity is incomplete")

    if (take_profit is None) != (take_profit_order_id is None):
        raise RuntimeError("New IB virtual-leg Take Profit identity is incomplete")

    open_orders = list(evidence_snapshot.get("open_orders") or [])
    current_client_id = _optional_int(evidence_snapshot.get("current_client_id"))
    broker_client_id = _optional_int(broker_result.get("current_client_id"))

    if (
        current_client_id is None
        or broker_client_id is None
        or current_client_id != broker_client_id
    ):
        raise RuntimeError("New IB virtual-leg current client id differs")

    protective_action = (
        POSITION_SIDE_SELL if side_clean == POSITION_SIDE_BUY else POSITION_SIDE_BUY
    )
    identity_leg = IBVirtualPositionLeg(
        position_uid=position_uid_clean,
        trade_uid=trade_uid_clean,
        broker_position_id=broker_position_id_clean,
        account_id=account_id_clean,
        symbol_name=symbol_name_clean,
        side=side_clean,
        volume=volume_value,
        entry_price=entry_price,
        opened_utc=opened_utc,
        source=source_clean,
    )
    parent_perm_ids = {
        perm_id
        for row in matching_executions
        if (perm_id := _optional_int(row.get("perm_id"))) is not None
    }

    if len(parent_perm_ids) > 1:
        raise RuntimeError("New IB virtual-leg parent permId is ambiguous")

    parent_order_perm_id = next(iter(parent_perm_ids), None)
    mapped_rows: list[dict[str, Any]] = []

    for order_id, order_types, expected_price in (
        (stop_loss_order_id, IB_STOP_ORDER_TYPES, stop_loss),
        (
            take_profit_order_id,
            IB_TAKE_PROFIT_ORDER_TYPES,
            take_profit,
        ),
    ):
        if order_id is None:
            continue

        candidates = [
            row
            for row in open_orders
            if _open_order_row_is_active(row) and _order_id(row) == order_id
        ]

        if len(candidates) != 1:
            raise RuntimeError(
                "New IB virtual-leg active child order was not found " "uniquely"
            )

        row = candidates[0]

        if _optional_int(row.get("parent_id")) != parent_order_id:
            raise RuntimeError("New IB virtual-leg child parent id differs")

        if not _order_matches_leg_contract(row, identity_leg):
            raise RuntimeError("New IB virtual-leg child contract differs")

        row_action = str(row.get("action") or "").strip().upper()

        if row_action != protective_action:
            raise RuntimeError("New IB virtual-leg protective action differs")

        if not _quantities_equal(
            _safe_float(row.get("total_quantity")),
            volume_value,
        ):
            raise RuntimeError("New IB virtual-leg protective quantity differs")

        if _normalize_order_type(row.get("order_type")) not in order_types:
            raise RuntimeError("New IB virtual-leg protective order type differs")

        if current_client_id is None or not bool(row.get("same_client_id")):
            raise RuntimeError("New IB virtual-leg protective ownership is unknown")

        row_client_id = _optional_int(row.get("client_id"))

        if row_client_id != current_client_id:
            raise RuntimeError("New IB virtual-leg protective client id differs")

        actual_price = (
            _stop_price(row) if order_id == stop_loss_order_id else _limit_price(row)
        )

        if (
            expected_price is None
            or actual_price is None
            or not math.isclose(
                actual_price,
                expected_price,
                rel_tol=IB_SL_TP_COVERAGE_REL_TOLERANCE,
                abs_tol=IB_POSITION_QUANTITY_ABS_TOLERANCE,
            )
        ):
            raise RuntimeError("New IB virtual-leg protective price differs")

        mapped_rows.append(row)

    oca_groups = {
        str(row.get("oca_group") or "").strip()
        for row in mapped_rows
        if str(row.get("oca_group") or "").strip()
    }

    if len(oca_groups) > 1:
        raise RuntimeError("New IB virtual-leg protective OCA groups differ")

    stop_loss_order_perm_id = next(
        (
            _optional_int(row.get("perm_id"))
            for row in mapped_rows
            if _order_id(row) == stop_loss_order_id
        ),
        None,
    )
    take_profit_order_perm_id = next(
        (
            _optional_int(row.get("perm_id"))
            for row in mapped_rows
            if _order_id(row) == take_profit_order_id
        ),
        None,
    )

    if stop_loss_order_id is not None and take_profit_order_id is not None:
        protection_status = IB_PROTECTION_STATUS_COMPLETE
    elif stop_loss_order_id is not None or take_profit_order_id is not None:
        protection_status = IB_PROTECTION_STATUS_PARTIAL
    else:
        protection_status = IB_PROTECTION_STATUS_NONE

    return IBVirtualPositionLeg(
        position_uid=position_uid_clean,
        trade_uid=trade_uid_clean,
        broker_position_id=broker_position_id_clean,
        account_id=account_id_clean,
        symbol_name=symbol_name_clean,
        side=side_clean,
        volume=volume_value,
        entry_price=entry_price,
        opened_utc=opened_utc,
        source=source_clean,
        parent_order_id=parent_order_id,
        stop_loss_order_id=stop_loss_order_id,
        take_profit_order_id=take_profit_order_id,
        stop_loss=stop_loss,
        take_profit=take_profit,
        oca_group=next(iter(oca_groups), ""),
        parent_order_perm_id=parent_order_perm_id,
        stop_loss_order_perm_id=stop_loss_order_perm_id,
        take_profit_order_perm_id=take_profit_order_perm_id,
        leg_status=IB_LEG_STATUS_OPEN,
        protection_status=protection_status,
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
        reconciliation_messages=("Confirmed immediately after LGE-owned IB Open",),
    )


def reconcile_ib_virtual_position_legs(
    legs: Iterable[IBVirtualPositionLeg],
    evidence_snapshot: dict[str, Any],
    cash_fx_virtual_observation_offsets: dict[str, float] | None = None,
    persisted_external_exposures: dict[str, IBFxExternalExposure] | None = None,
) -> IBVirtualPositionLegReconciliationSnapshot:
    """
    Зіставити Runtime legs із IB executions, net positions та open orders.

    На цьому етапі protective order можна прив'язати лише сильним доказом:
    збереженим child order id або точним parentOrderId. Fallback за symbol,
    side, price чи volume тут навмисно відсутній.
    """
    _validate_complete_evidence_snapshot(evidence_snapshot)

    source_legs = [replace(leg) for leg in legs]
    positions = list(evidence_snapshot.get("positions") or [])
    executions = list(evidence_snapshot.get("executions") or [])
    open_orders = list(evidence_snapshot.get("open_orders") or [])
    completed_orders = list(evidence_snapshot.get("completed_orders") or [])
    current_client_id = _optional_int(evidence_snapshot.get("current_client_id"))

    positions_by_id = _build_positions_by_id(positions)
    cash_fx_group_ids = _cash_fx_group_ids(
        legs=source_legs,
        positions=positions,
        open_orders=open_orders,
        completed_orders=completed_orders,
        executions=executions,
    )
    reconciled_legs: list[IBVirtualPositionLeg] = []
    consumed_protective_order_ids: set[int] = set()

    for leg in source_legs:
        reconciled_leg, consumed_ids = _reconcile_single_leg(
            leg=leg,
            executions=executions,
            open_orders=open_orders,
            completed_orders=completed_orders,
            current_client_id=current_client_id,
        )
        reconciled_legs.append(reconciled_leg)
        consumed_protective_order_ids.update(consumed_ids)

    group_statuses: dict[str, str] = {}
    group_messages: dict[str, tuple[str, ...]] = {}
    group_broker_residual_signed_volumes: dict[str, float] = {}
    group_broker_residual_evidence_statuses: dict[str, str] = {}
    group_external_exposures: dict[str, IBFxExternalExposure] = {}
    group_cash_fx_managed_observation_only: dict[str, bool] = {}
    persisted_exposures = dict(persisted_external_exposures or {})
    captured_utc = str(evidence_snapshot.get("captured_utc") or "").strip()
    protective_candidates = _external_protective_exposure_candidates(
        open_orders=open_orders,
        current_client_id=current_client_id,
    )

    for broker_position_id in _ordered_group_ids(reconciled_legs):
        group_legs = [
            leg
            for leg in reconciled_legs
            if leg.broker_position_id == broker_position_id
        ]
        position_rows = positions_by_id.get(broker_position_id, [])
        status, messages, broker_residual_signed_volume = _reconcile_group_quantity(
            broker_position_id=broker_position_id,
            legs=group_legs,
            position_rows=position_rows,
            executions=executions,
            cash_fx=broker_position_id in cash_fx_group_ids,
            cash_fx_virtual_observation_offset=(
                None
                if cash_fx_virtual_observation_offsets is None
                else cash_fx_virtual_observation_offsets.get(broker_position_id)
            ),
        )

        residual_evidence_status = ""
        external_protection_present = _group_has_external_protective_orders(
            broker_position_id=broker_position_id,
            open_orders=open_orders,
            current_client_id=current_client_id,
        )

        if broker_position_id in cash_fx_group_ids and position_rows:
            residual_evidence_status = IB_FX_EXTERNAL_EXPOSURE_CONFIRMED
        elif broker_position_id in cash_fx_group_ids and not position_rows:
            persisted_exposure = persisted_exposures.get(broker_position_id)
            protective_only_cleared = bool(
                persisted_exposure is not None
                and persisted_exposure.is_active
                and not persisted_exposure.last_confirmed_utc
                and broker_position_id not in protective_candidates
            )

            if protective_only_cleared:
                broker_residual_signed_volume = 0.0
                residual_evidence_status = IB_FX_EXTERNAL_EXPOSURE_CONFIRMED
            else:
                persisted_signed_volume = (
                    persisted_exposure.signed_volume
                    if (persisted_exposure is not None and persisted_exposure.is_active)
                    else _cash_fx_persisted_residual_signed_volume(group_legs)
                )

                if persisted_signed_volume is not None:
                    broker_residual_signed_volume = persisted_signed_volume
                    residual_evidence_status = IB_FX_EXTERNAL_EXPOSURE_STALE
                    messages = _merge_messages(
                        messages,
                        (IB_EXTERNAL_EXPOSURE_STALE_MESSAGE,),
                    )

                    if external_protection_present:
                        messages = _merge_messages(
                            messages,
                            (IB_EXTERNAL_EXPOSURE_STALE_PROTECTED_MESSAGE,),
                        )
                elif external_protection_present:
                    messages = _merge_messages(
                        messages,
                        (IB_EXTERNAL_PROTECTION_WITHOUT_OBSERVATION_MESSAGE,),
                    )

        group_legs, exposure_recovered = (
            _recover_unprotected_open_leg_from_broker_exposure(
                legs=group_legs,
                position_rows=position_rows,
                executions=executions,
                group_status=status,
                broker_residual_signed_volume=broker_residual_signed_volume,
            )
        )

        if exposure_recovered:
            recovered_by_uid = {leg.position_uid: leg for leg in group_legs}
            reconciled_legs = [
                (
                    recovered_by_uid.get(leg.position_uid, leg)
                    if leg.broker_position_id == broker_position_id
                    else leg
                )
                for leg in reconciled_legs
            ]

        blocked_leg_messages = tuple(
            message
            for leg in group_legs
            if leg.reconciliation_status == IB_RECONCILIATION_STATUS_BLOCKED
            for message in leg.reconciliation_messages
        )
        close_evidence_missing_messages = tuple(
            message
            for leg in group_legs
            if leg.reconciliation_status
            == IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING
            for message in leg.reconciliation_messages
        )

        if blocked_leg_messages:
            status = IB_RECONCILIATION_STATUS_BLOCKED
            messages = _merge_messages(messages, blocked_leg_messages)
            reconciled_legs = [
                (
                    _block_leg(leg, messages)
                    if leg.broker_position_id == broker_position_id
                    else leg
                )
                for leg in reconciled_legs
            ]
        elif close_evidence_missing_messages:
            status = IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING
            messages = _merge_messages(
                messages,
                close_evidence_missing_messages,
            )
        elif status == IB_RECONCILIATION_STATUS_BLOCKED:
            reconciled_legs = [
                (
                    _block_leg(leg, messages)
                    if leg.broker_position_id == broker_position_id
                    else leg
                )
                for leg in reconciled_legs
            ]
        elif any(
            leg.reconciliation_status != IB_RECONCILIATION_STATUS_RECONCILED
            for leg in group_legs
        ):
            status = IB_RECONCILIATION_STATUS_UNRECONCILED
            messages = _merge_messages(
                messages,
                ("At least one virtual leg is not reconciled",),
            )

        if status == IB_RECONCILIATION_STATUS_RECONCILED:
            reconciled_legs = [
                (
                    _replace_broker_residual_message(
                        leg,
                        broker_residual_signed_volume,
                    )
                    if leg.broker_position_id == broker_position_id
                    else leg
                )
                for leg in reconciled_legs
            ]

        group_cash_fx_managed_observation_only[broker_position_id] = (
            broker_position_id in cash_fx_group_ids
            and status == IB_RECONCILIATION_STATUS_RECONCILED
            and abs(broker_residual_signed_volume)
            <= IB_POSITION_QUANTITY_ABS_TOLERANCE
            and _cash_fx_position_observation_is_managed_close_flow(
                legs=group_legs,
                position_rows=position_rows,
                executions=executions,
            )
        )
        group_statuses[broker_position_id] = status
        group_messages[broker_position_id] = messages
        group_broker_residual_signed_volumes[broker_position_id] = (
            broker_residual_signed_volume
        )
        group_broker_residual_evidence_statuses[broker_position_id] = (
            residual_evidence_status
        )

    # Build one explicit external-exposure record per IB CASH group.
    # This includes current broker-only positions, persisted ledger rows,
    # and guarded evidence inferred from foreign-client protective orders.
    group_legs_by_id: dict[str, list[IBVirtualPositionLeg]] = {}

    for leg in reconciled_legs:
        group_legs_by_id.setdefault(leg.broker_position_id, []).append(leg)

    current_cash_rows: dict[str, list[dict[str, Any]]] = {}

    for row in positions:
        identity = _ib_cash_group_identity_from_row(row)

        if identity is None:
            continue

        broker_position_id, _, _ = identity
        current_cash_rows.setdefault(broker_position_id, []).append(row)

    def register_external_exposure(
        *,
        exposure_broker_position_id: str,
        exposure_account_id: str,
        exposure_symbol_name: str,
        exposure_signed_volume: float,
        exposure_evidence_status: str,
        allow_zero: bool = False,
    ) -> None:
        if (
            not allow_zero
            and abs(exposure_signed_volume) <= IB_POSITION_QUANTITY_ABS_TOLERANCE
        ):
            return

        prior_exposure = persisted_exposures.get(exposure_broker_position_id)
        last_confirmed_utc = (
            captured_utc
            if exposure_evidence_status == IB_FX_EXTERNAL_EXPOSURE_CONFIRMED
            else (
                prior_exposure.last_confirmed_utc if prior_exposure is not None else ""
            )
        )
        group_external_exposures[exposure_broker_position_id] = IBFxExternalExposure(
            broker_position_id=exposure_broker_position_id,
            account_id=exposure_account_id,
            symbol_name=exposure_symbol_name,
            signed_volume=exposure_signed_volume,
            evidence_status=exposure_evidence_status,
            last_confirmed_utc=last_confirmed_utc,
            last_observed_utc=captured_utc,
            updated_utc=captured_utc,
        )

    for (
        broker_position_id,
        evidence_status,
    ) in group_broker_residual_evidence_statuses.items():
        signed_volume = group_broker_residual_signed_volumes.get(
            broker_position_id,
            0.0,
        )

        if abs(signed_volume) <= IB_POSITION_QUANTITY_ABS_TOLERANCE:
            continue

        group_legs = group_legs_by_id.get(broker_position_id, [])
        current_rows = current_cash_rows.get(broker_position_id, [])
        persisted = persisted_exposures.get(broker_position_id)

        if group_legs:
            account_id = group_legs[0].account_id
            symbol_name = group_legs[0].symbol_name
        elif len(current_rows) == 1:
            identity = _ib_cash_group_identity_from_row(current_rows[0])

            if identity is None:
                continue

            _, account_id, symbol_name = identity
        elif persisted is not None:
            account_id = persisted.account_id
            symbol_name = persisted.symbol_name
        else:
            candidate = protective_candidates.get(broker_position_id)

            if candidate is None:
                continue

            account_id, symbol_name, _ = candidate

        register_external_exposure(
            exposure_broker_position_id=broker_position_id,
            exposure_account_id=account_id,
            exposure_symbol_name=symbol_name,
            exposure_signed_volume=signed_volume,
            exposure_evidence_status=evidence_status,
        )

    # A current CASH position without exact LGE legs is entirely external.
    for broker_position_id, rows in current_cash_rows.items():
        if broker_position_id in group_statuses or len(rows) != 1:
            continue

        identity = _ib_cash_group_identity_from_row(rows[0])

        if identity is None:
            continue

        _, account_id, symbol_name = identity
        signed_volume = _safe_float(
            rows[0].get("signed_quantity", rows[0].get("position"))
        )

        group_statuses[broker_position_id] = IB_RECONCILIATION_STATUS_RECONCILED
        group_messages[broker_position_id] = (
            (IB_EXTERNAL_EXPOSURE_CURRENT_MESSAGE,)
            if abs(signed_volume) > IB_POSITION_QUANTITY_ABS_TOLERANCE
            else ()
        )
        group_broker_residual_signed_volumes[broker_position_id] = signed_volume
        group_broker_residual_evidence_statuses[broker_position_id] = (
            IB_FX_EXTERNAL_EXPOSURE_CONFIRMED
        )
        group_cash_fx_managed_observation_only[broker_position_id] = False
        register_external_exposure(
            exposure_broker_position_id=broker_position_id,
            exposure_account_id=account_id,
            exposure_symbol_name=symbol_name,
            exposure_signed_volume=signed_volume,
            exposure_evidence_status=IB_FX_EXTERNAL_EXPOSURE_CONFIRMED,
            allow_zero=True,
        )

    # Preserve ledger-only exposure when the transient Virtual FX row vanishes.
    for broker_position_id, persisted in persisted_exposures.items():
        if not persisted.is_active:
            continue

        if broker_position_id in current_cash_rows:
            continue

        if (
            group_broker_residual_evidence_statuses.get(broker_position_id)
            == IB_FX_EXTERNAL_EXPOSURE_CONFIRMED
        ):
            continue

        if broker_position_id not in group_external_exposures:
            protective_only = not persisted.last_confirmed_utc
            active_protection = broker_position_id in protective_candidates

            if protective_only and not active_protection:
                group_broker_residual_signed_volumes[broker_position_id] = 0.0
                group_broker_residual_evidence_statuses[broker_position_id] = (
                    IB_FX_EXTERNAL_EXPOSURE_CONFIRMED
                )
                register_external_exposure(
                    exposure_broker_position_id=broker_position_id,
                    exposure_account_id=persisted.account_id,
                    exposure_symbol_name=persisted.symbol_name,
                    exposure_signed_volume=0.0,
                    exposure_evidence_status=IB_FX_EXTERNAL_EXPOSURE_CONFIRMED,
                    allow_zero=True,
                )
                continue

            group_statuses.setdefault(
                broker_position_id,
                IB_RECONCILIATION_STATUS_RECONCILED,
            )
            group_messages[broker_position_id] = _merge_messages(
                group_messages.get(broker_position_id, ()),
                (IB_EXTERNAL_EXPOSURE_STALE_MESSAGE,),
            )
            group_broker_residual_signed_volumes[broker_position_id] = (
                persisted.signed_volume
            )
            group_broker_residual_evidence_statuses[broker_position_id] = (
                IB_FX_EXTERNAL_EXPOSURE_STALE
            )
            register_external_exposure(
                exposure_broker_position_id=broker_position_id,
                exposure_account_id=persisted.account_id,
                exposure_symbol_name=persisted.symbol_name,
                exposure_signed_volume=persisted.signed_volume,
                exposure_evidence_status=IB_FX_EXTERNAL_EXPOSURE_STALE,
            )

    # Foreign-client protection is useful current evidence, but not proof that
    # the underlying position still exists. Show it explicitly and fail closed.
    for broker_position_id, candidate in protective_candidates.items():
        if broker_position_id in current_cash_rows:
            continue

        if broker_position_id in group_external_exposures:
            continue

        account_id, symbol_name, signed_volume = candidate
        group_statuses.setdefault(
            broker_position_id,
            IB_RECONCILIATION_STATUS_RECONCILED,
        )
        existing_messages = tuple(
            message
            for message in group_messages.get(broker_position_id, ())
            if message != IB_EXTERNAL_PROTECTION_WITHOUT_OBSERVATION_MESSAGE
        )
        group_messages[broker_position_id] = _merge_messages(
            existing_messages,
            (IB_EXTERNAL_EXPOSURE_PROTECTIVE_EVIDENCE_MESSAGE,),
        )
        group_broker_residual_signed_volumes[broker_position_id] = signed_volume
        group_broker_residual_evidence_statuses[broker_position_id] = (
            IB_FX_EXTERNAL_EXPOSURE_STALE
        )
        register_external_exposure(
            exposure_broker_position_id=broker_position_id,
            exposure_account_id=account_id,
            exposure_symbol_name=symbol_name,
            exposure_signed_volume=signed_volume,
            exposure_evidence_status=IB_FX_EXTERNAL_EXPOSURE_STALE,
        )

    unmapped_order_ids = _find_unmapped_protective_order_ids(
        legs=reconciled_legs,
        open_orders=open_orders,
        consumed_order_ids=consumed_protective_order_ids,
        current_client_id=current_client_id,
    )

    if unmapped_order_ids:
        affected_groups = _groups_for_unmapped_orders(
            legs=reconciled_legs,
            open_orders=open_orders,
            order_ids=unmapped_order_ids,
        )

        for broker_position_id in affected_groups:
            message = "Unmapped protective order exists for virtual-leg group"
            group_statuses[broker_position_id] = IB_RECONCILIATION_STATUS_BLOCKED
            if not group_broker_residual_evidence_statuses.get(broker_position_id):
                group_broker_residual_signed_volumes[broker_position_id] = 0.0
            group_messages[broker_position_id] = _merge_messages(
                group_messages.get(broker_position_id, ()),
                (message,),
            )
            reconciled_legs = [
                (
                    _block_leg(leg, (message,))
                    if leg.broker_position_id == broker_position_id
                    else leg
                )
                for leg in reconciled_legs
            ]

    return IBVirtualPositionLegReconciliationSnapshot(
        captured_utc=str(evidence_snapshot.get("captured_utc") or ""),
        complete=True,
        legs=reconciled_legs,
        group_statuses=group_statuses,
        group_messages=group_messages,
        unmapped_protective_order_ids=unmapped_order_ids,
        group_broker_residual_signed_volumes=group_broker_residual_signed_volumes,
        group_broker_residual_evidence_statuses=(
            group_broker_residual_evidence_statuses
        ),
        group_external_exposures=group_external_exposures,
        group_cash_fx_managed_observation_only=(
            group_cash_fx_managed_observation_only
        ),
    )


def _cash_fx_position_observation_is_managed_close_flow(
    *,
    legs: list[IBVirtualPositionLeg],
    position_rows: list[dict[str, Any]],
    executions: list[dict[str, Any]],
) -> bool:
    """Return whether a non-zero CASH row is only an LGE close-flow trace.

    After all logical legs are CLOSED, IB Virtual FX can still show the
    current-session SELL/BUY close flow instead of zero.  It is not an active
    external position when the exact current execution quantity is fully
    explained by persisted LGE order identity.
    """
    if not legs or len(position_rows) != 1:
        return False

    if any(leg.leg_status != IB_LEG_STATUS_CLOSED for leg in legs):
        return False

    external_execution_present, _ = _cash_fx_external_execution_summary(
        legs,
        executions,
    )
    if external_execution_present:
        return False

    broker_signed_quantity = _safe_float(
        position_rows[0].get(
            "signed_quantity",
            position_rows[0].get("position"),
        )
    )
    managed_execution_signed_quantity = sum(
        _signed_execution_quantity(row)
        for row in executions
        if _execution_matches_group(row, legs)
        and _cash_fx_execution_is_known_lge(row, legs)
    )
    return _quantities_equal(
        broker_signed_quantity,
        managed_execution_signed_quantity,
    )


def _recover_unprotected_open_leg_from_broker_exposure(
    *,
    legs: list[IBVirtualPositionLeg],
    position_rows: list[dict[str, Any]],
    executions: list[dict[str, Any]],
    group_status: str,
    broker_residual_signed_volume: float,
) -> tuple[list[IBVirtualPositionLeg], bool]:
    """
    Recover one OPEN leg when exact broker exposure proves it remains open.

    Missing persisted SL/TP orders alone do not prove that the position was
    closed. Recovery is allowed only for one ambiguous OPEN leg and only when
    the current broker net, after subtracting every other reconciled OPEN leg,
    equals that leg exactly. Ambiguous multi-leg and residual cases stay
    blocked by the existing reconciliation rules.
    """
    if group_status != IB_RECONCILIATION_STATUS_RECONCILED:
        return legs, False

    if abs(broker_residual_signed_volume) > IB_POSITION_QUANTITY_ABS_TOLERANCE:
        return legs, False

    if len(position_rows) != 1:
        return legs, False

    if _cash_fx_has_external_execution_evidence(legs, executions):
        return legs, False

    candidates = [
        leg
        for leg in legs
        if leg.leg_status == IB_LEG_STATUS_OPEN
        and leg.reconciliation_status == IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING
    ]

    if len(candidates) != 1:
        return legs, False

    candidate = candidates[0]
    other_open_legs = [
        leg
        for leg in legs
        if leg.position_uid != candidate.position_uid
        and leg.leg_status == IB_LEG_STATUS_OPEN
    ]

    if any(
        leg.reconciliation_status != IB_RECONCILIATION_STATUS_RECONCILED
        for leg in other_open_legs
    ):
        return legs, False

    broker_signed_quantity = _safe_float(
        position_rows[0].get(
            "signed_quantity",
            position_rows[0].get("position"),
        )
    )
    other_signed_quantity = sum(leg.signed_volume for leg in other_open_legs)
    supported_candidate_quantity = broker_signed_quantity - other_signed_quantity

    if not _quantities_equal(
        supported_candidate_quantity,
        candidate.signed_volume,
    ):
        return legs, False

    recovered_messages = tuple(
        message
        for message in candidate.reconciliation_messages
        if not message.startswith("CLOSE_EVIDENCE_MISSING:")
    )
    recovered_candidate = replace(
        candidate,
        stop_loss_order_id=None,
        take_profit_order_id=None,
        stop_loss=None,
        take_profit=None,
        oca_group="",
        protection_status=IB_PROTECTION_STATUS_NONE,
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
        reconciliation_messages=recovered_messages,
    )
    recovered_legs = [
        recovered_candidate if leg.position_uid == candidate.position_uid else leg
        for leg in legs
    ]
    return recovered_legs, True


def _reconcile_single_leg(
    leg: IBVirtualPositionLeg,
    executions: list[dict[str, Any]],
    open_orders: list[dict[str, Any]],
    completed_orders: list[dict[str, Any]],
    current_client_id: int | None,
) -> tuple[IBVirtualPositionLeg, set[int]]:
    """
    Reconcile одну leg за exact parent/child order identity.
    """
    messages = tuple(
        message
        for message in leg.reconciliation_messages
        if message.startswith(IB_BROKER_RESIDUAL_MESSAGE_PREFIX)
    )
    status = IB_RECONCILIATION_STATUS_RECONCILED

    if not _is_valid_leg_identity(leg):
        return _block_leg(leg, ("Invalid virtual-leg identity",)), set()

    matching_executions = [
        row for row in executions if _execution_matches_leg(row, leg)
    ]

    if not matching_executions:
        if _has_persisted_parent_execution_evidence(leg):
            messages = _merge_messages(
                messages,
                (
                    "Parent MARKET execution is outside current IB history; "
                    "persisted reconciled entry was retained",
                ),
            )
        else:
            status = IB_RECONCILIATION_STATUS_UNRECONCILED
            messages = _merge_messages(
                messages,
                ("Parent MARKET execution was not found",),
            )
        entry_price = leg.entry_price
        opened_utc = leg.opened_utc
    else:
        execution_volume = sum(
            _safe_float(row.get("shares")) for row in matching_executions
        )

        if not _quantities_equal(execution_volume, leg.volume):
            return (
                _block_leg(
                    leg,
                    ("Parent execution quantity differs from leg volume",),
                ),
                set(),
            )

        entry_price = _weighted_execution_price(matching_executions)
        opened_utc = _earliest_execution_time(matching_executions)

    explicit_close = _map_explicit_close_fill(
        leg=leg,
        executions=executions,
    )
    completed_fill = _map_completed_protective_fill(
        leg=leg,
        completed_orders=completed_orders,
        executions=executions,
        current_client_id=current_client_id,
    )

    if not completed_fill["closed"] and not completed_fill["blocked"]:
        execution_only_fill = _map_execution_only_protective_fill(
            leg=leg,
            executions=executions,
        )

        if execution_only_fill["closed"] or execution_only_fill["blocked"]:
            completed_fill = execution_only_fill

    protection = _map_leg_protection(
        leg=leg,
        open_orders=open_orders,
        current_client_id=current_client_id,
    )

    if explicit_close["blocked"]:
        status = IB_RECONCILIATION_STATUS_BLOCKED
        messages = _merge_messages(
            messages,
            explicit_close["messages"],
        )

    if completed_fill["blocked"]:
        status = IB_RECONCILIATION_STATUS_BLOCKED
        messages = _merge_messages(
            messages,
            completed_fill["messages"],
        )

    if protection["blocked"]:
        status = IB_RECONCILIATION_STATUS_BLOCKED
        messages = _merge_messages(messages, protection["messages"])

    if (
        not completed_fill["closed"]
        and not explicit_close["closed"]
        and leg.leg_status in {IB_LEG_STATUS_OPEN, IB_LEG_STATUS_PARTIALLY_CLOSED}
        and _leg_has_persisted_protection_identity(leg)
        and not protection["consumed_order_ids"]
    ):
        if (
            status != IB_RECONCILIATION_STATUS_BLOCKED
            and _has_persisted_parent_execution_evidence(leg)
        ):
            status = IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING
        else:
            status = IB_RECONCILIATION_STATUS_BLOCKED
        messages = _merge_messages(
            messages,
            (
                "CLOSE_EVIDENCE_MISSING: persisted protective orders are "
                "not active and no matching close execution was found",
            ),
        )

    leg_status = leg.leg_status
    stop_loss_order_id = protection["stop_loss_order_id"]
    take_profit_order_id = protection["take_profit_order_id"]
    stop_loss = protection["stop_loss"]
    take_profit = protection["take_profit"]
    oca_group = protection["oca_group"]
    protection_status = protection["protection_status"]

    if explicit_close["closed"]:
        leg_status = IB_LEG_STATUS_CLOSED
        protection_status = IB_PROTECTION_STATUS_NONE

        if protection["consumed_order_ids"]:
            status = IB_RECONCILIATION_STATUS_BLOCKED
            messages = _merge_messages(
                messages,
                ("Explicitly closed virtual leg still has active protection",),
            )

    if completed_fill["closed"]:
        leg_status = IB_LEG_STATUS_CLOSED
        protection_status = IB_PROTECTION_STATUS_NONE

        if protection["consumed_order_ids"]:
            status = IB_RECONCILIATION_STATUS_BLOCKED
            messages = _merge_messages(
                messages,
                ("Closed virtual leg still has active protective orders",),
            )

        if completed_fill["order_role"] == "STOP_LOSS":
            stop_loss_order_id = completed_fill["order_id"]
            stop_loss = completed_fill["price"]
        elif completed_fill["order_role"] == "TAKE_PROFIT":
            take_profit_order_id = completed_fill["order_id"]
            take_profit = completed_fill["price"]

        oca_group = completed_fill["oca_group"] or oca_group

    reconciled_leg = replace(
        leg,
        entry_price=entry_price,
        opened_utc=opened_utc,
        stop_loss_order_id=stop_loss_order_id,
        take_profit_order_id=take_profit_order_id,
        stop_loss=stop_loss,
        take_profit=take_profit,
        oca_group=oca_group,
        leg_status=leg_status,
        protection_status=protection_status,
        reconciliation_status=status,
        reconciliation_messages=messages,
    )

    return reconciled_leg, set(protection["consumed_order_ids"])


def _map_explicit_close_fill(
    leg: IBVirtualPositionLeg,
    executions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Prove one explicit LGE MARKET close by persisted close order id."""
    if not leg.close_order_ids:
        return {"closed": False, "blocked": False, "messages": ()}

    matching_rows = [
        row
        for row in executions
        if _optional_int(row.get("order_id")) in leg.close_order_ids
        and _execution_matches_group(row, [leg])
    ]

    if not matching_rows:
        if leg.leg_status == IB_LEG_STATUS_CLOSED:
            return {"closed": True, "blocked": False, "messages": ()}
        return {
            "closed": False,
            "blocked": True,
            "messages": ("Persisted close execution was not found",),
        }

    expected_side = leg.protective_action
    actual_sides = {_execution_side(row.get("side")) for row in matching_rows}

    if actual_sides != {expected_side}:
        return {
            "closed": False,
            "blocked": True,
            "messages": ("Explicit close execution action differs from leg",),
        }

    quantity = sum(_safe_float(row.get("shares")) for row in matching_rows)

    if not _quantities_equal(quantity, leg.volume):
        return {
            "closed": False,
            "blocked": True,
            "messages": ("Explicit close execution quantity differs from leg",),
        }

    return {"closed": True, "blocked": False, "messages": ()}


def _map_completed_protective_fill(
    leg: IBVirtualPositionLeg,
    completed_orders: list[dict[str, Any]],
    executions: list[dict[str, Any]],
    current_client_id: int | None,
) -> dict[str, Any]:
    """
    Довести full broker-triggered Close конкретної virtual leg.

    Completed order сам по собі недостатній. Потрібні exact parent/child
    identity та matching execution на повний volume цієї leg. Поле
    completed-order total_quantity є лише допоміжним: після завершення
    TWS може повернути 0, тому закриття доводиться execution quantity.
    """
    if leg.leg_status == IB_LEG_STATUS_CLOSED:
        return _empty_completed_fill_result()

    candidates = [
        row
        for row in completed_orders
        if _normalize_order_type(row.get("order_type")) in IB_PROTECTIVE_ORDER_TYPES
        and _order_has_strong_leg_identity(row, leg)
    ]

    if not candidates:
        return _empty_completed_fill_result()

    messages: tuple[str, ...] = ()
    valid_rows: list[dict[str, Any]] = []

    for row in candidates:
        if not _order_matches_leg_contract(row, leg):
            messages = _merge_messages(
                messages,
                ("Completed protective order contract differs from leg",),
            )
            continue

        if not _order_is_owned_by_current_client(row, current_client_id):
            messages = _merge_messages(
                messages,
                ("Completed protective order belongs to a different " "IB clientId",),
            )
            continue

        if _normalize_order_action(row.get("action")) != leg.protective_action:
            messages = _merge_messages(
                messages,
                ("Completed protective order action differs from leg",),
            )
            continue

        valid_rows.append(row)

    if messages:
        return {
            **_empty_completed_fill_result(),
            "blocked": True,
            "messages": messages,
        }

    filled_rows: list[tuple[dict[str, Any], float, int]] = []
    partial_fill_detected = False

    for row in valid_rows:
        order_type = _normalize_order_type(row.get("order_type"))

        if order_type in IB_STOP_ORDER_TYPES:
            order_id = leg.stop_loss_order_id
        elif order_type in IB_TAKE_PROFIT_ORDER_TYPES:
            order_id = leg.take_profit_order_id
        else:
            order_id = None

        if order_id is None:
            continue

        execution_volume = sum(
            _safe_float(execution.get("shares"))
            for execution in executions
            if _protective_execution_matches_order(
                execution=execution,
                completed_order=row,
                leg=leg,
            )
        )

        if execution_volume <= IB_POSITION_QUANTITY_ABS_TOLERANCE:
            continue

        reported_quantity = _safe_float(row.get("total_quantity", row.get("quantity")))

        if (
            reported_quantity > IB_POSITION_QUANTITY_ABS_TOLERANCE
            and not _quantities_equal(reported_quantity, leg.volume)
        ):
            return {
                **_empty_completed_fill_result(),
                "blocked": True,
                "messages": (
                    "Executed protective order quantity metadata " "differs from leg",
                ),
            }

        if _quantities_equal(execution_volume, leg.volume):
            filled_rows.append((row, execution_volume, order_id))
        else:
            partial_fill_detected = True

    if partial_fill_detected:
        return {
            **_empty_completed_fill_result(),
            "blocked": True,
            "messages": ("Partial protective execution cannot be represented safely",),
        }

    if len(filled_rows) > 1:
        return {
            **_empty_completed_fill_result(),
            "blocked": True,
            "messages": ("Multiple completed protective fills match one virtual leg",),
        }

    if not filled_rows:
        filled_status_rows = [
            row for row in valid_rows if _completed_order_is_filled(row)
        ]

        if filled_status_rows:
            return {
                **_empty_completed_fill_result(),
                "blocked": True,
                "messages": ("Completed protective fill lacks matching execution",),
            }

        return _empty_completed_fill_result()

    row, _, persisted_order_id = filled_rows[0]
    order_type = _normalize_order_type(row.get("order_type"))

    if order_type in IB_STOP_ORDER_TYPES:
        order_role = "STOP_LOSS"
        price = _stop_price(row)
    else:
        order_role = "TAKE_PROFIT"
        price = _limit_price(row)

    return {
        "closed": True,
        "blocked": False,
        "messages": (),
        "order_id": persisted_order_id,
        "order_role": order_role,
        "price": price,
        "oca_group": str(row.get("oca_group") or "").strip(),
    }


def _map_execution_only_protective_fill(
    leg: IBVirtualPositionLeg,
    executions: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Довести broker-triggered Close без completed-order callback.

    IB може не повернути completedOrder для захисного ордера попередньої
    сесії, але reqExecutions все ще повертає exact child orderId. У такому
    випадку persisted STOP_LOSS / TAKE_PROFIT order ids разом із account,
    symbol, action і full execution quantity є достатнім strong evidence.
    """
    if leg.leg_status == IB_LEG_STATUS_CLOSED:
        return _empty_completed_fill_result()

    stop_loss_order_id = leg.stop_loss_order_id
    take_profit_order_id = leg.take_profit_order_id

    if stop_loss_order_id is not None and stop_loss_order_id == take_profit_order_id:
        return {
            **_empty_completed_fill_result(),
            "blocked": True,
            "messages": ("Persisted SL/TP order identities are ambiguous",),
        }

    role_by_order_id: dict[int, str] = {}

    if stop_loss_order_id is not None:
        role_by_order_id[stop_loss_order_id] = "STOP_LOSS"

    if take_profit_order_id is not None:
        role_by_order_id[take_profit_order_id] = "TAKE_PROFIT"

    if not role_by_order_id:
        return _empty_completed_fill_result()

    candidate_rows: list[tuple[dict[str, Any], int]] = []

    for row in executions:
        matched_order_ids = [
            order_id
            for order_id, perm_id in (
                (stop_loss_order_id, leg.stop_loss_order_perm_id),
                (take_profit_order_id, leg.take_profit_order_perm_id),
            )
            if order_id is not None
            and _row_matches_order_identity(
                row=row,
                order_id=order_id,
                perm_id=perm_id,
            )
        ]

        if len(matched_order_ids) > 1:
            return {
                **_empty_completed_fill_result(),
                "blocked": True,
                "messages": (
                    "Protective execution identity matches multiple children",
                ),
            }

        if matched_order_ids:
            candidate_rows.append((row, matched_order_ids[0]))

    if not candidate_rows:
        return _empty_completed_fill_result()

    messages: tuple[str, ...] = ()
    valid_rows_by_order_id: dict[int, list[dict[str, Any]]] = {}

    for row, order_id in candidate_rows:
        if str(row.get("account") or "").strip() != leg.account_id:
            messages = _merge_messages(
                messages,
                ("Protective execution account differs from leg",),
            )
            continue

        if _symbol_name_from_row(row) != leg.symbol_name:
            messages = _merge_messages(
                messages,
                ("Protective execution contract differs from leg",),
            )
            continue

        if _execution_side(row.get("side")) != leg.protective_action:
            messages = _merge_messages(
                messages,
                ("Protective execution action differs from leg",),
            )
            continue

        if _safe_float(row.get("shares")) <= IB_POSITION_QUANTITY_ABS_TOLERANCE:
            messages = _merge_messages(
                messages,
                ("Protective execution quantity is not positive",),
            )
            continue

        valid_rows_by_order_id.setdefault(order_id, []).append(row)

    if messages:
        return {
            **_empty_completed_fill_result(),
            "blocked": True,
            "messages": messages,
        }

    full_fills: list[tuple[int, list[dict[str, Any]]]] = []
    partial_fill_detected = False

    for order_id, rows in valid_rows_by_order_id.items():
        execution_volume = sum(_safe_float(row.get("shares")) for row in rows)

        if _quantities_equal(execution_volume, leg.volume):
            full_fills.append((order_id, rows))
        elif execution_volume > IB_POSITION_QUANTITY_ABS_TOLERANCE:
            partial_fill_detected = True

    if partial_fill_detected:
        return {
            **_empty_completed_fill_result(),
            "blocked": True,
            "messages": ("Partial protective execution cannot be represented safely",),
        }

    if len(full_fills) > 1:
        return {
            **_empty_completed_fill_result(),
            "blocked": True,
            "messages": ("Multiple protective executions match one virtual leg",),
        }

    if not full_fills:
        return _empty_completed_fill_result()

    order_id, execution_rows = full_fills[0]
    order_role = role_by_order_id[order_id]

    if order_role == "STOP_LOSS":
        price = leg.stop_loss
    else:
        price = leg.take_profit

    if price is None:
        price = _weighted_execution_price(execution_rows)

    return {
        "closed": True,
        "blocked": False,
        "messages": (),
        "order_id": order_id,
        "order_role": order_role,
        "price": price,
        "oca_group": leg.oca_group,
    }


def _empty_completed_fill_result() -> dict[str, Any]:
    """
    Повернути порожній result completed protective fill mapping.
    """
    return {
        "closed": False,
        "blocked": False,
        "messages": (),
        "order_id": None,
        "order_role": "",
        "price": None,
        "oca_group": "",
    }


def _protective_execution_matches_order(
    execution: dict[str, Any],
    completed_order: dict[str, Any],
    leg: IBVirtualPositionLeg,
) -> bool:
    """
    Перевірити execution конкретного completed protective order.
    """
    order_type = _normalize_order_type(completed_order.get("order_type"))

    if order_type in IB_STOP_ORDER_TYPES:
        persisted_order_id = leg.stop_loss_order_id
        persisted_perm_id = leg.stop_loss_order_perm_id
    elif order_type in IB_TAKE_PROFIT_ORDER_TYPES:
        persisted_order_id = leg.take_profit_order_id
        persisted_perm_id = leg.take_profit_order_perm_id
    else:
        return False

    if not _row_matches_order_identity(
        row=execution,
        order_id=persisted_order_id,
        perm_id=persisted_perm_id,
    ):
        return False

    if str(execution.get("account") or "").strip() != leg.account_id:
        return False

    if _symbol_name_from_row(execution) != leg.symbol_name:
        return False

    execution_action = _execution_side(execution.get("side"))
    return execution_action == leg.protective_action


def _completed_order_is_filled(row: dict[str, Any]) -> bool:
    """
    Перевірити broker status completed order без припущень по регістру.
    """
    statuses = {
        str(row.get("status") or "").strip().upper(),
        str(row.get("completed_status") or "").strip().upper(),
    }

    return "FILLED" in statuses or _safe_float(row.get("filled")) > 0.0


def _map_leg_protection(
    leg: IBVirtualPositionLeg,
    open_orders: list[dict[str, Any]],
    current_client_id: int | None,
) -> dict[str, Any]:
    """
    Знайти protection лише за persisted child ids або parentOrderId.
    """
    candidates = [
        row
        for row in open_orders
        if _open_order_row_is_active(row) and _order_has_strong_leg_identity(row, leg)
    ]

    if not candidates:
        return {
            "blocked": False,
            "messages": (),
            "protection_status": IB_PROTECTION_STATUS_NONE,
            "stop_loss_order_id": leg.stop_loss_order_id,
            "take_profit_order_id": leg.take_profit_order_id,
            "stop_loss": leg.stop_loss,
            "take_profit": leg.take_profit,
            "oca_group": leg.oca_group,
            "consumed_order_ids": [],
        }

    messages: tuple[str, ...] = ()
    valid_rows: list[dict[str, Any]] = []

    for row in candidates:
        if not _order_matches_leg_contract(row, leg):
            messages = _merge_messages(
                messages,
                ("Protective order contract differs from virtual leg",),
            )
            continue

        if not _order_is_owned_by_current_client(row, current_client_id):
            messages = _merge_messages(
                messages,
                ("Protective order belongs to a different IB clientId",),
            )
            continue

        if _normalize_order_action(row.get("action")) != leg.protective_action:
            messages = _merge_messages(
                messages,
                ("Protective order action differs from virtual leg",),
            )
            continue

        quantity = _safe_float(row.get("total_quantity", row.get("quantity")))

        if not _quantities_equal(quantity, leg.volume):
            messages = _merge_messages(
                messages,
                ("Protective order quantity differs from leg volume",),
            )
            continue

        valid_rows.append(row)

    if messages:
        return {
            "blocked": True,
            "messages": messages,
            "protection_status": IB_PROTECTION_STATUS_BLOCKED,
            "stop_loss_order_id": leg.stop_loss_order_id,
            "take_profit_order_id": leg.take_profit_order_id,
            "stop_loss": leg.stop_loss,
            "take_profit": leg.take_profit,
            "oca_group": leg.oca_group,
            "consumed_order_ids": [
                order_id
                for order_id in (_order_id(row) for row in candidates)
                if order_id is not None
            ],
        }

    stop_rows = [
        row
        for row in valid_rows
        if _normalize_order_type(row.get("order_type")) in IB_STOP_ORDER_TYPES
    ]
    take_profit_rows = [
        row
        for row in valid_rows
        if _normalize_order_type(row.get("order_type")) in IB_TAKE_PROFIT_ORDER_TYPES
    ]
    unknown_rows = [
        row
        for row in valid_rows
        if _normalize_order_type(row.get("order_type")) not in IB_PROTECTIVE_ORDER_TYPES
    ]

    if len(stop_rows) > 1 or len(take_profit_rows) > 1 or unknown_rows:
        return {
            "blocked": True,
            "messages": ("Protective order mapping is ambiguous",),
            "protection_status": IB_PROTECTION_STATUS_BLOCKED,
            "stop_loss_order_id": leg.stop_loss_order_id,
            "take_profit_order_id": leg.take_profit_order_id,
            "stop_loss": leg.stop_loss,
            "take_profit": leg.take_profit,
            "oca_group": leg.oca_group,
            "consumed_order_ids": [
                order_id
                for order_id in (_order_id(row) for row in candidates)
                if order_id is not None
            ],
        }

    stop_row = stop_rows[0] if stop_rows else None
    take_profit_row = take_profit_rows[0] if take_profit_rows else None

    if stop_row is not None and take_profit_row is not None:
        protection_status = IB_PROTECTION_STATUS_COMPLETE
    elif stop_row is not None or take_profit_row is not None:
        protection_status = IB_PROTECTION_STATUS_PARTIAL
    else:
        protection_status = IB_PROTECTION_STATUS_NONE

    oca_groups = {
        str(row.get("oca_group") or "").strip()
        for row in valid_rows
        if str(row.get("oca_group") or "").strip()
    }

    if len(oca_groups) > 1:
        return {
            "blocked": True,
            "messages": ("Protective pair has different OCA groups",),
            "protection_status": IB_PROTECTION_STATUS_BLOCKED,
            "stop_loss_order_id": leg.stop_loss_order_id,
            "take_profit_order_id": leg.take_profit_order_id,
            "stop_loss": leg.stop_loss,
            "take_profit": leg.take_profit,
            "oca_group": leg.oca_group,
            "consumed_order_ids": [
                order_id
                for order_id in (_order_id(row) for row in valid_rows)
                if order_id is not None
            ],
        }

    return {
        "blocked": False,
        "messages": (),
        "protection_status": protection_status,
        "stop_loss_order_id": _order_id(stop_row),
        "take_profit_order_id": _order_id(take_profit_row),
        "stop_loss": _stop_price(stop_row),
        "take_profit": _limit_price(take_profit_row),
        "oca_group": next(iter(oca_groups), leg.oca_group),
        "consumed_order_ids": [
            order_id
            for order_id in (_order_id(row) for row in valid_rows)
            if order_id is not None
        ],
    }


def _has_persisted_parent_execution_evidence(
    leg: IBVirtualPositionLeg,
) -> bool:
    """
    Дозволити reuse раніше reconciled parent execution identity.
    """
    return (
        leg.parent_order_id is not None
        and leg.entry_price is not None
        and math.isfinite(float(leg.entry_price))
        and float(leg.entry_price) > 0.0
        and bool(str(leg.opened_utc or "").strip())
        and leg.reconciliation_status == IB_RECONCILIATION_STATUS_RECONCILED
    )


def _leg_has_persisted_protection_identity(
    leg: IBVirtualPositionLeg,
) -> bool:
    """
    Перевірити, чи persistence очікує хоча б один protective child.
    """
    return leg.stop_loss_order_id is not None or leg.take_profit_order_id is not None


def _cash_fx_group_ids(
    legs: list[IBVirtualPositionLeg],
    positions: list[dict[str, Any]],
    open_orders: list[dict[str, Any]],
    completed_orders: list[dict[str, Any]],
    executions: list[dict[str, Any]],
) -> set[str]:
    """
    Визначити LGE groups, підтверджені як IB CASH Forex.
    """
    evidence_rows = positions + open_orders + completed_orders + executions
    result: set[str] = set()

    for leg in legs:
        if any(
            str(row.get("sec_type") or "").strip().upper() == "CASH"
            and _row_matches_leg_group(row, leg)
            for row in evidence_rows
        ):
            result.add(leg.broker_position_id)

    return result


def _row_matches_leg_group(
    row: dict[str, Any],
    leg: IBVirtualPositionLeg,
) -> bool:
    """
    Перевірити account + symbol identity evidence row до leg group.
    """
    broker_position_id = str(row.get("broker_position_id") or "").strip()

    if broker_position_id:
        return broker_position_id == leg.broker_position_id

    account_id = str(row.get("account_id") or row.get("account") or "").strip()
    return (
        account_id == leg.account_id and _symbol_name_from_row(row) == leg.symbol_name
    )


def _execution_matches_group(
    row: dict[str, Any],
    legs: list[IBVirtualPositionLeg],
) -> bool:
    """
    Перевірити, чи execution належить account + symbol leg group.
    """
    if not legs:
        return False

    reference_leg = legs[0]
    return _row_matches_leg_group(row, reference_leg)


def _signed_execution_quantity(row: dict[str, Any]) -> float:
    """
    Повернути signed quantity одного IB execution.
    """
    quantity = _safe_float(row.get("shares"))
    side = _execution_side(row.get("side"))

    if side == POSITION_SIDE_BUY:
        return quantity

    if side == POSITION_SIDE_SELL:
        return -quantity

    return 0.0


def _reconcile_group_quantity(
    broker_position_id: str,
    legs: list[IBVirtualPositionLeg],
    position_rows: list[dict[str, Any]],
    executions: list[dict[str, Any]],
    cash_fx: bool,
    cash_fx_virtual_observation_offset: float | None = None,
) -> tuple[str, tuple[str, ...], float]:
    """
    Перевірити strict broker net або IB CASH Virtual FX observation.
    """
    runtime_signed_quantity = sum(
        leg.signed_volume
        for leg in legs
        if leg.leg_status in {IB_LEG_STATUS_OPEN, IB_LEG_STATUS_PARTIALLY_CLOSED}
    )

    if not position_rows:
        broker_signed_quantity = 0.0
    elif len(position_rows) == 1:
        broker_signed_quantity = _safe_float(
            position_rows[0].get(
                "signed_quantity",
                position_rows[0].get("position"),
            )
        )
    else:
        return (
            IB_RECONCILIATION_STATUS_BLOCKED,
            ("IB broker net position snapshot is ambiguous",),
            0.0,
        )

    if cash_fx:
        return _reconcile_cash_fx_virtual_position(
            broker_position_id=broker_position_id,
            legs=legs,
            executions=executions,
            broker_signed_quantity=broker_signed_quantity,
            expected_observation_offset=cash_fx_virtual_observation_offset,
        )

    if not _quantities_equal(
        runtime_signed_quantity,
        broker_signed_quantity,
    ):
        return (
            IB_RECONCILIATION_STATUS_BLOCKED,
            (
                "Signed sum of open virtual legs differs from IB net position: "
                f"legs={runtime_signed_quantity}, "
                f"broker={broker_signed_quantity}, "
                f"position={broker_position_id}",
            ),
            0.0,
        )

    return IB_RECONCILIATION_STATUS_RECONCILED, (), 0.0


def _cash_fx_all_known_order_ids(
    legs: Iterable[IBVirtualPositionLeg],
) -> set[int]:
    """Return every exact LGE order id known for the CASH group."""
    return {
        order_id
        for leg in legs
        for order_id in (
            leg.parent_order_id,
            leg.stop_loss_order_id,
            leg.take_profit_order_id,
            *leg.close_order_ids,
        )
        if order_id is not None
    }


def _cash_fx_current_exposure_order_ids(
    legs: Iterable[IBVirtualPositionLeg],
) -> set[int]:
    """Return exact order ids relevant to current open CASH exposure."""
    source_legs = list(legs)
    open_legs = [leg for leg in source_legs if leg.leg_status != IB_LEG_STATUS_CLOSED]
    return _cash_fx_all_known_order_ids(open_legs or source_legs)


def _cash_fx_execution_is_known_lge(
    row: dict[str, Any],
    legs: list[IBVirtualPositionLeg],
) -> bool:
    """Match execution to exact persisted LGE order identity."""
    order_id = _optional_int(row.get("order_id"))

    for leg in legs:
        if _execution_matches_leg(row, leg):
            return True

        if _row_matches_order_identity(
            row=row,
            order_id=leg.stop_loss_order_id,
            perm_id=leg.stop_loss_order_perm_id,
        ):
            return True

        if _row_matches_order_identity(
            row=row,
            order_id=leg.take_profit_order_id,
            perm_id=leg.take_profit_order_perm_id,
        ):
            return True

        if order_id is not None and order_id in leg.close_order_ids:
            return True

    return False


def _cash_fx_external_execution_summary(
    legs: list[IBVirtualPositionLeg],
    executions: list[dict[str, Any]],
) -> tuple[bool, float]:
    """Return exact non-LGE execution presence and signed quantity."""
    present = False
    signed_quantity = 0.0

    for row in executions:
        if not _execution_matches_group(row, legs):
            continue

        row_signed_quantity = _signed_execution_quantity(row)

        if abs(row_signed_quantity) <= IB_POSITION_QUANTITY_ABS_TOLERANCE:
            continue

        if _cash_fx_execution_is_known_lge(row, legs):
            continue

        present = True
        signed_quantity += row_signed_quantity

    return present, signed_quantity


def _cash_fx_has_external_execution_evidence(
    legs: list[IBVirtualPositionLeg],
    executions: list[dict[str, Any]],
) -> bool:
    """Return whether current evidence contains non-LGE execution flow."""
    present, _ = _cash_fx_external_execution_summary(legs, executions)
    return present


def _cash_fx_persisted_residual_signed_volume(
    legs: Iterable[IBVirtualPositionLeg],
) -> float | None:
    """Return one consistent legacy persisted residual marker."""
    values: list[float] = []

    for leg in legs:
        for message in leg.reconciliation_messages:
            if not message.startswith(IB_BROKER_RESIDUAL_MESSAGE_PREFIX):
                continue

            raw_value = message.removeprefix(IB_BROKER_RESIDUAL_MESSAGE_PREFIX).strip()

            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue

            if not math.isfinite(value):
                continue

            if abs(value) <= IB_POSITION_QUANTITY_ABS_TOLERANCE:
                continue

            values.append(value)

    if not values:
        return None

    first = values[0]

    if any(not _quantities_equal(value, first) for value in values[1:]):
        return None

    return first


def _broker_residual_message(signed_volume: float) -> str:
    """Build one stable persisted marker for broker-only exposure."""
    return f"{IB_BROKER_RESIDUAL_MESSAGE_PREFIX}{signed_volume}"


def _replace_broker_residual_message(
    leg: IBVirtualPositionLeg,
    signed_volume: float,
) -> IBVirtualPositionLeg:
    """Replace persisted residual marker without duplicating messages."""
    messages = tuple(
        message
        for message in leg.reconciliation_messages
        if not message.startswith(IB_BROKER_RESIDUAL_MESSAGE_PREFIX)
    )

    if abs(signed_volume) > IB_POSITION_QUANTITY_ABS_TOLERANCE:
        messages = _merge_messages(
            messages,
            (_broker_residual_message(signed_volume),),
        )

    return replace(leg, reconciliation_messages=messages)


def _reconcile_cash_fx_virtual_position(
    broker_position_id: str,
    legs: list[IBVirtualPositionLeg],
    executions: list[dict[str, Any]],
    broker_signed_quantity: float,
    expected_observation_offset: float | None = None,
) -> tuple[str, tuple[str, ...], float]:
    """
    Звірити IB Virtual FX row з відомими LGE executions.

    Для CASH Forex position row не є сумою історичних LGE legs. TWS може
    почати Virtual FX tracking заново після нового session/trading day.
    Тому terminal safety базується на exact known order ids та executions.
    """
    group_executions = [
        row for row in executions if _execution_matches_group(row, legs)
    ]
    current_exposure_legs = [
        leg for leg in legs if leg.leg_status != IB_LEG_STATUS_CLOSED
    ] or legs
    cumulative_signed_quantity = sum(
        _signed_execution_quantity(row)
        for row in group_executions
        if _cash_fx_execution_is_known_lge(row, legs)
    )
    current_exposure_signed_quantity = sum(
        _signed_execution_quantity(row)
        for row in group_executions
        if _cash_fx_execution_is_known_lge(row, current_exposure_legs)
    )
    observed_offset = broker_signed_quantity - cumulative_signed_quantity
    runtime_signed_quantity = sum(
        leg.signed_volume
        for leg in legs
        if leg.leg_status in {IB_LEG_STATUS_OPEN, IB_LEG_STATUS_PARTIALLY_CLOSED}
    )
    broker_minus_managed_signed_volume = (
        broker_signed_quantity - runtime_signed_quantity
    )
    external_execution_present, external_execution_signed_volume = (
        _cash_fx_external_execution_summary(legs, group_executions)
    )
    persisted_residual_signed_volume = _cash_fx_persisted_residual_signed_volume(
        legs
    )

    if external_execution_present:
        broker_residual_signed_volume = external_execution_signed_volume
        residual_evidence_source = "exact non-LGE executions"
    else:
        broker_residual_signed_volume = 0.0
        residual_evidence_source = ""

    if expected_observation_offset is not None:
        if _quantities_equal(
            observed_offset,
            expected_observation_offset,
        ):
            if external_execution_present:
                residual_for_display = external_execution_signed_volume
            elif persisted_residual_signed_volume is not None:
                residual_for_display = persisted_residual_signed_volume
            else:
                residual_for_display = 0.0

            return (
                IB_RECONCILIATION_STATUS_RECONCILED,
                (
                    "IB CASH Forex Virtual FX observation offset remained "
                    "stable across the exact LGE operation",
                ),
                residual_for_display,
            )

        return (
            IB_RECONCILIATION_STATUS_BLOCKED,
            (
                "IB CASH Forex Virtual FX observation offset changed "
                "unexpectedly: "
                f"expected_offset={expected_observation_offset}, "
                f"actual_offset={observed_offset}, "
                f"executions={cumulative_signed_quantity}, "
                f"virtual_fx={broker_signed_quantity}, "
                f"position={broker_position_id}",
            ),
            0.0,
        )

    if external_execution_present:
        return (
            IB_RECONCILIATION_STATUS_RECONCILED,
            (
                "IB CASH Forex external exposure is represented from "
                f"{residual_evidence_source}, not from Virtual FX minus "
                "managed-leg arithmetic: "
                f"external={broker_residual_signed_volume}, "
                f"virtual_fx_minus_managed={broker_minus_managed_signed_volume}, "
                f"managed={runtime_signed_quantity}, "
                f"virtual_fx={broker_signed_quantity}, "
                f"position={broker_position_id}",
            ),
            broker_residual_signed_volume,
        )

    if _quantities_equal(
        cumulative_signed_quantity,
        broker_signed_quantity,
    ):
        return (
            IB_RECONCILIATION_STATUS_RECONCILED,
            (
                "IB CASH Forex position row is a Virtual FX observation; "
                "LGE leg state was reconciled by exact order executions",
            ),
            0.0,
        )

    if _quantities_equal(
        current_exposure_signed_quantity,
        broker_signed_quantity,
    ):
        return (
            IB_RECONCILIATION_STATUS_RECONCILED,
            (
                "IB CASH Forex Virtual FX observation follows current open "
                "LGE exposure; older CLOSED-leg executions were excluded",
            ),
            0.0,
        )

    if _quantities_equal(broker_signed_quantity, 0.0):
        return (
            IB_RECONCILIATION_STATUS_RECONCILED,
            (
                "IB CASH Forex Virtual FX observation is zero/reset; "
                "LGE leg state was reconciled by exact order identity "
                "and persisted evidence",
            ),
            0.0,
        )

    if persisted_residual_signed_volume is not None:
        return (
            IB_RECONCILIATION_STATUS_RECONCILED,
            (
                "IB CASH Forex external exposure is retained from persisted "
                "exact evidence because the current execution snapshot no "
                "longer contains that non-LGE execution: "
                f"external={persisted_residual_signed_volume}, "
                f"virtual_fx_minus_managed={broker_minus_managed_signed_volume}, "
                f"managed={runtime_signed_quantity}, "
                f"virtual_fx={broker_signed_quantity}, "
                f"position={broker_position_id}",
            ),
            persisted_residual_signed_volume,
        )

    return (
        IB_RECONCILIATION_STATUS_BLOCKED,
        (
            "IB Virtual FX quantity differs from recognized LGE "
            "executions: "
            f"cumulative_executions={cumulative_signed_quantity}, "
            f"current_exposure_executions="
            f"{current_exposure_signed_quantity}, "
            f"virtual_fx={broker_signed_quantity}, "
            f"position={broker_position_id}",
        ),
        0.0,
    )


def get_ib_cash_fx_virtual_observation_offset(
    legs: Iterable[IBVirtualPositionLeg],
    evidence_snapshot: dict[str, Any],
    broker_position_id: str,
) -> float | None:
    """Return current IB CASH Virtual FX observation baseline offset."""
    source_legs = [leg for leg in legs if leg.broker_position_id == broker_position_id]

    if not source_legs:
        return None

    positions = list(evidence_snapshot.get("positions") or [])
    open_orders = list(evidence_snapshot.get("open_orders") or [])
    completed_orders = list(evidence_snapshot.get("completed_orders") or [])
    executions = list(evidence_snapshot.get("executions") or [])
    cash_group_ids = _cash_fx_group_ids(
        legs=source_legs,
        positions=positions,
        open_orders=open_orders,
        completed_orders=completed_orders,
        executions=executions,
    )

    if broker_position_id not in cash_group_ids:
        return None

    position_rows = _build_positions_by_id(positions).get(
        broker_position_id,
        [],
    )

    if not position_rows:
        broker_signed_quantity = 0.0
    elif len(position_rows) == 1:
        broker_signed_quantity = _safe_float(
            position_rows[0].get(
                "signed_quantity",
                position_rows[0].get("position"),
            )
        )
    else:
        raise RuntimeError("IB CASH Virtual FX position snapshot is ambiguous")

    recognized_signed_quantity = sum(
        _signed_execution_quantity(row)
        for row in executions
        if _execution_matches_group(row, source_legs)
        and _cash_fx_execution_is_known_lge(row, source_legs)
    )
    return broker_signed_quantity - recognized_signed_quantity


def _validate_complete_evidence_snapshot(
    evidence_snapshot: dict[str, Any],
) -> None:
    """
    Заборонити reconciliation з partial broker evidence.
    """
    required_true_fields = (
        "complete",
        "positions_complete",
        "open_orders_complete",
        "completed_orders_complete",
        "executions_complete",
    )

    incomplete_fields = [
        field_name
        for field_name in required_true_fields
        if evidence_snapshot.get(field_name) is not True
    ]

    if incomplete_fields:
        joined = ", ".join(incomplete_fields)
        raise RuntimeError(f"IB virtual-leg evidence is incomplete: {joined}")


def _build_positions_by_id(
    position_rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    Згрупувати broker positions за normalized position id.
    """
    result: dict[str, list[dict[str, Any]]] = {}

    for row in position_rows:
        broker_position_id = str(row.get("broker_position_id") or "").strip()

        if broker_position_id:
            result.setdefault(broker_position_id, []).append(row)

    return result


def _ordered_group_ids(legs: list[IBVirtualPositionLeg]) -> list[str]:
    """
    Повернути group ids зі стабільним порядком.
    """
    result: list[str] = []

    for leg in legs:
        if leg.broker_position_id not in result:
            result.append(leg.broker_position_id)

    return result


def _execution_matches_leg(
    row: dict[str, Any],
    leg: IBVirtualPositionLeg,
) -> bool:
    """Перевірити exact parent execution identity з permId."""
    if leg.parent_order_id is None:
        return False

    if not _row_matches_order_identity(
        row=row,
        order_id=leg.parent_order_id,
        perm_id=_effective_parent_perm_id(leg),
    ):
        return False

    if str(row.get("account") or "").strip() != leg.account_id:
        return False

    if _symbol_name_from_row(row) != leg.symbol_name:
        return False

    return _execution_side(row.get("side")) == leg.side


def _order_has_strong_leg_identity(
    row: dict[str, Any],
    leg: IBVirtualPositionLeg,
) -> bool:
    """Перевірити child identity без довіри до reused orderId."""
    if _row_matches_order_identity(
        row=row,
        order_id=leg.stop_loss_order_id,
        perm_id=leg.stop_loss_order_perm_id,
    ) and _order_oca_identity_matches_leg(row, leg):
        return True

    if _row_matches_order_identity(
        row=row,
        order_id=leg.take_profit_order_id,
        perm_id=leg.take_profit_order_perm_id,
    ) and _order_oca_identity_matches_leg(row, leg):
        return True

    # Коли persisted child ids вже відомі, parentId сам по собі не є
    # достатнім: IB може повторно видати orderId у новій сесії.
    if leg.stop_loss_order_id is not None or leg.take_profit_order_id is not None:
        return False

    parent_id = _optional_int(row.get("parent_id"))

    if leg.parent_order_id is None or parent_id != leg.parent_order_id:
        return False

    persisted_oca_group = str(leg.oca_group or "").strip()

    if not persisted_oca_group:
        return True

    return str(row.get("oca_group") or "").strip() == persisted_oca_group


def _effective_parent_perm_id(leg: IBVirtualPositionLeg) -> int | None:
    """Return stable parent permId, preferring numeric bracket OCA id."""
    numeric_oca_group = _optional_int(leg.oca_group)

    if numeric_oca_group is not None:
        return numeric_oca_group

    return leg.parent_order_perm_id


def _order_oca_identity_matches_leg(
    row: dict[str, Any],
    leg: IBVirtualPositionLeg,
) -> bool:
    """Require persisted OCA identity when the leg already has one."""
    persisted_oca_group = str(leg.oca_group or "").strip()

    if not persisted_oca_group:
        return True

    return str(row.get("oca_group") or "").strip() == persisted_oca_group


def _row_matches_order_identity(
    row: dict[str, Any],
    order_id: int | None,
    perm_id: int | None,
) -> bool:
    """Match one IB order by stable identity without inventing orderId.

    IB can return ``orderId=0`` for historical/cross-session evidence while
    still returning the stable ``permId``.  When a persisted permId exists,
    accept the row only if permId matches and orderId is either the persisted
    value or unavailable/zero.  A different non-zero orderId stays rejected.
    """
    if order_id is None:
        return False

    row_order_id = _optional_int(row.get("order_id"))

    if perm_id is None:
        return row_order_id == order_id

    if _optional_int(row.get("perm_id")) != perm_id:
        return False

    return row_order_id in {None, 0, order_id}


def _order_matches_leg_contract(
    row: dict[str, Any],
    leg: IBVirtualPositionLeg,
) -> bool:
    """
    Перевірити account + contract identity.
    """
    account_id = str(row.get("account_id") or row.get("account") or "").strip()
    broker_position_id = str(row.get("broker_position_id") or "").strip()

    if account_id != leg.account_id:
        return False

    if broker_position_id:
        return broker_position_id == leg.broker_position_id

    return _symbol_name_from_row(row) == leg.symbol_name


def _order_is_owned_by_current_client(
    row: dict[str, Any],
    current_client_id: int | None,
) -> bool:
    """
    Перевірити same-client ownership.
    """
    if row.get("same_client_id") is not None:
        return row.get("same_client_id") is True

    row_client_id = _optional_int(row.get("client_id"))

    if current_client_id is None or row_client_id is None:
        return False

    return row_client_id == current_client_id


def _ib_cash_group_identity_from_row(
    row: dict[str, Any],
) -> tuple[str, str, str] | None:
    """Return canonical IB CASH group identity from one evidence row."""
    if str(row.get("sec_type") or "").strip().upper() != "CASH":
        return None

    account_id = str(row.get("account_id") or row.get("account") or "").strip()
    symbol_name = _symbol_name_from_row(row)
    broker_position_id = str(row.get("broker_position_id") or "").strip()

    if not broker_position_id and account_id and symbol_name:
        broker_position_id = f"IB:{account_id}:{symbol_name}"

    if not broker_position_id or not account_id or not symbol_name:
        return None

    return broker_position_id, account_id, symbol_name


def _external_protective_exposure_candidates(
    *,
    open_orders: list[dict[str, Any]],
    current_client_id: int | None,
) -> dict[str, tuple[str, str, float]]:
    """Infer guarded external exposure from foreign-client protection.

    One bracket contributes its protected quantity once, even when both
    Stop Loss and Take Profit children are active. The result is deliberately
    treated as STALE evidence because protective orders can be orphaned.
    """
    brackets: dict[
        tuple[str, str],
        tuple[str, str, set[str], list[float]],
    ] = {}

    for row in open_orders:
        if not _open_order_row_is_active(row):
            continue

        if (
            _normalize_order_type(row.get("order_type"))
            not in IB_PROTECTIVE_ORDER_TYPES
        ):
            continue

        if _order_is_owned_by_current_client(row, current_client_id):
            continue

        identity = _ib_cash_group_identity_from_row(row)

        if identity is None:
            continue

        broker_position_id, account_id, symbol_name = identity
        action = _normalize_order_action(row.get("action"))

        if action not in {POSITION_SIDE_BUY, POSITION_SIDE_SELL}:
            continue

        quantity = _safe_float(row.get("total_quantity", row.get("quantity")))

        if quantity <= IB_POSITION_QUANTITY_ABS_TOLERANCE:
            continue

        parent_id = _optional_int(row.get("parent_id"))
        oca_group = str(row.get("oca_group") or "").strip()
        perm_id = _optional_int(row.get("perm_id"))
        order_id = _order_id(row)

        if parent_id is not None and parent_id > 0:
            bracket_identity = f"PARENT:{parent_id}"
        elif oca_group:
            bracket_identity = f"OCA:{oca_group}"
        elif perm_id is not None and perm_id > 0:
            bracket_identity = f"PERM:{perm_id}"
        elif order_id is not None and order_id > 0:
            bracket_identity = f"ORDER:{order_id}"
        else:
            continue

        key = broker_position_id, bracket_identity
        existing = brackets.get(key)

        if existing is None:
            brackets[key] = (
                account_id,
                symbol_name,
                {action},
                [quantity],
            )
            continue

        existing_account, existing_symbol, actions, quantities = existing
        actions.add(action)
        quantities.append(quantity)
        brackets[key] = (
            existing_account,
            existing_symbol,
            actions,
            quantities,
        )

    result: dict[str, tuple[str, str, float]] = {}

    for (broker_position_id, _), value in brackets.items():
        account_id, symbol_name, actions, quantities = value

        if len(actions) != 1 or not quantities:
            continue

        reference_quantity = quantities[0]

        if any(
            not _quantities_equal(quantity, reference_quantity)
            for quantity in quantities[1:]
        ):
            continue

        action = next(iter(actions))
        signed_volume = (
            reference_quantity if action == POSITION_SIDE_SELL else -reference_quantity
        )
        previous = result.get(broker_position_id)

        if previous is None:
            result[broker_position_id] = (
                account_id,
                symbol_name,
                signed_volume,
            )
            continue

        previous_account, previous_symbol, previous_volume = previous

        if previous_account != account_id or previous_symbol != symbol_name:
            result.pop(broker_position_id, None)
            continue

        result[broker_position_id] = (
            account_id,
            symbol_name,
            previous_volume + signed_volume,
        )

    return {
        broker_position_id: value
        for broker_position_id, value in result.items()
        if abs(value[2]) > IB_POSITION_QUANTITY_ABS_TOLERANCE
    }


def _group_has_external_protective_orders(
    *,
    broker_position_id: str,
    open_orders: list[dict[str, Any]],
    current_client_id: int | None,
) -> bool:
    """Return whether a CASH group has foreign-client protective orders."""
    group_id = str(broker_position_id or "").strip()

    for row in open_orders:
        if not _open_order_row_is_active(row):
            continue

        if (
            _normalize_order_type(row.get("order_type"))
            not in IB_PROTECTIVE_ORDER_TYPES
        ):
            continue

        row_group_id = str(row.get("broker_position_id") or "").strip()

        if row_group_id != group_id:
            continue

        if not _order_is_owned_by_current_client(row, current_client_id):
            return True

    return False


def _find_unmapped_protective_order_ids(
    legs: list[IBVirtualPositionLeg],
    open_orders: list[dict[str, Any]],
    consumed_order_ids: set[int],
    current_client_id: int | None,
) -> list[int]:
    """
    Знайти STP/LMT orders для leg groups без strong mapping.
    """
    group_ids = {leg.broker_position_id for leg in legs}
    result: list[int] = []

    for row in open_orders:
        if not _open_order_row_is_active(row):
            continue

        order_type = _normalize_order_type(row.get("order_type"))
        order_id = _order_id(row)
        broker_position_id = str(row.get("broker_position_id") or "").strip()

        if order_type not in IB_PROTECTIVE_ORDER_TYPES:
            continue

        if broker_position_id not in group_ids:
            continue

        # Захисні ордери, створені вручну в TWS або іншим clientId,
        # належать broker residual, а не LGE virtual legs. Вони мають
        # лишатися read-only broker evidence і не блокувати керовані legs.
        if not _order_is_owned_by_current_client(row, current_client_id):
            continue

        # IB може віддати manual/open order з API orderId=0. Нуль не є
        # стабільною identity і не повинен потрапляти до unmapped ids.
        if order_id is None or order_id <= 0:
            continue

        if order_id in consumed_order_ids:
            continue

        result.append(order_id)

    return sorted(set(result))


def _groups_for_unmapped_orders(
    legs: list[IBVirtualPositionLeg],
    open_orders: list[dict[str, Any]],
    order_ids: list[int],
) -> set[str]:
    """
    Визначити affected groups для unmapped protective orders.
    """
    valid_group_ids = {leg.broker_position_id for leg in legs}
    affected: set[str] = set()

    for row in open_orders:
        if _order_id(row) not in order_ids:
            continue

        broker_position_id = str(row.get("broker_position_id") or "").strip()

        if broker_position_id in valid_group_ids:
            affected.add(broker_position_id)

    return affected


def _block_leg(
    leg: IBVirtualPositionLeg,
    messages: tuple[str, ...],
) -> IBVirtualPositionLeg:
    """
    Повернути blocked копію leg.
    """
    return replace(
        leg,
        protection_status=(
            IB_PROTECTION_STATUS_BLOCKED
            if leg.protection_status != IB_PROTECTION_STATUS_NONE
            else leg.protection_status
        ),
        reconciliation_status=IB_RECONCILIATION_STATUS_BLOCKED,
        reconciliation_messages=_merge_messages(
            leg.reconciliation_messages,
            messages,
        ),
    )


def _is_valid_leg_identity(leg: IBVirtualPositionLeg) -> bool:
    """
    Перевірити мінімальну identity virtual leg.
    """
    return bool(
        leg.position_uid
        and leg.trade_uid
        and leg.broker_position_id
        and leg.account_id
        and leg.symbol_name
        and leg.side in {POSITION_SIDE_BUY, POSITION_SIDE_SELL}
        and math.isfinite(float(leg.volume))
        and float(leg.volume) > 0.0
    )


def _weighted_execution_price(rows: list[dict[str, Any]]) -> float:
    """
    Розрахувати weighted average execution price.
    """
    total_volume = sum(_safe_float(row.get("shares")) for row in rows)

    if total_volume <= 0.0:
        return 0.0

    total_value = sum(
        _safe_float(row.get("shares")) * _safe_float(row.get("price")) for row in rows
    )
    return total_value / total_volume


def _earliest_execution_time(rows: list[dict[str, Any]]) -> str:
    """
    Повернути earliest non-empty IB execution time.
    """
    times = sorted(
        str(row.get("time") or "").strip()
        for row in rows
        if str(row.get("time") or "").strip()
    )
    return times[0] if times else ""


def _execution_side(value: Any) -> str:
    """
    Нормалізувати IB execution side.
    """
    text = str(value or "").strip().upper()

    if text in {"BOT", "BUY"}:
        return POSITION_SIDE_BUY

    if text in {"SLD", "SELL"}:
        return POSITION_SIDE_SELL

    return ""


def _open_order_row_is_active(row: dict[str, Any]) -> bool:
    """Return whether an IB order row is current broker evidence."""
    status = str(row.get("status") or "").strip().upper()
    return status not in IB_OPEN_ORDER_TERMINAL_STATUSES


def _normalize_order_action(value: Any) -> str:
    """
    Нормалізувати IB order action.
    """
    text = str(value or "").strip().upper()

    if text in {"BOT", "BUY"}:
        return "BUY"

    if text in {"SLD", "SELL"}:
        return "SELL"

    return text


def _normalize_order_type(value: Any) -> str:
    """
    Нормалізувати IB order type.
    """
    return " ".join(str(value or "").strip().upper().split())


def _symbol_name_from_row(row: dict[str, Any]) -> str:
    """
    Побудувати canonical symbol із evidence row.
    """
    symbol_name = str(row.get("symbol_name") or "").strip().upper()

    if symbol_name:
        return symbol_name

    symbol = str(row.get("symbol") or "").strip().upper()
    currency = str(row.get("currency") or "").strip().upper()
    return f"{symbol}{currency}" if symbol and currency else symbol


def _order_id(row: dict[str, Any] | None) -> int | None:
    """
    Повернути normalized order id.
    """
    if row is None:
        return None

    return _optional_int(row.get("order_id"))


def _stop_price(row: dict[str, Any] | None) -> float | None:
    """
    Повернути STP aux price.
    """
    if row is None:
        return None

    return _optional_float(row.get("aux_price"))


def _limit_price(row: dict[str, Any] | None) -> float | None:
    """
    Повернути LMT price.
    """
    if row is None:
        return None

    return _optional_float(row.get("lmt_price"))


def _optional_int(value: Any) -> int | None:
    """
    Безпечно нормалізувати optional int.
    """
    if value is None or value == "":
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_int_tuple(value: Any) -> tuple[int, ...]:
    """Normalize persisted comma-separated or iterable order ids."""
    if value is None or value == "":
        return ()

    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, Iterable):
        items = list(value)
    else:
        items = [value]

    result: list[int] = []

    for item in items:
        order_id = _optional_int(item)
        if order_id is not None and order_id > 0 and order_id not in result:
            result.append(order_id)

    return tuple(result)


def _safe_float(value: Any) -> float:
    """
    Безпечно нормалізувати float.
    """
    try:
        result = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0

    return result if math.isfinite(result) else 0.0


def _optional_float(value: Any) -> float | None:
    """
    Безпечно нормалізувати optional float.
    """
    if value is None or value == "":
        return None

    result = _safe_float(value)
    return result if result > 0.0 else None


def _quantities_equal(left: float, right: float) -> bool:
    """
    Порівняти IB quantities з runtime tolerance.
    """
    return math.isclose(
        float(left),
        float(right),
        rel_tol=IB_SL_TP_COVERAGE_REL_TOLERANCE,
        abs_tol=IB_POSITION_QUANTITY_ABS_TOLERANCE,
    )


def _merge_messages(
    current: tuple[str, ...],
    additions: tuple[str, ...],
) -> tuple[str, ...]:
    """
    Об'єднати повідомлення без дублікатів.
    """
    result = list(current)

    for message in additions:
        if message and message not in result:
            result.append(message)

    return tuple(result)
