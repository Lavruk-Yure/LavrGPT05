"""IB mixed managed/residual exposure and missing close evidence check."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_position_group import build_ib_position_group_snapshot  # noqa: E402
from engine.ib_virtual_position_leg import (  # noqa: E402
    IBVirtualPositionLeg,
    build_ib_virtual_position_legs_from_repository_seeds,
    reconcile_ib_virtual_position_legs,
)
from engine.runtime_constants import (  # noqa: E402
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_PROTECTION_STATUS_NONE,
    IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING,
    IB_RECONCILIATION_STATUS_RECONCILED,
)

ACCOUNT_ID = "DUM513747"
EURUSD_ID = f"IB:{ACCOUNT_ID}:EURUSD"
USDZAR_ID = f"IB:{ACCOUNT_ID}:USDZAR"


def build_position(
    broker_position_id: str,
    symbol: str,
    currency: str,
    signed_quantity: float,
) -> dict[str, Any]:
    return {
        "account": ACCOUNT_ID,
        "symbol": symbol,
        "currency": currency,
        "sec_type": "CASH",
        "symbol_name": f"{symbol}{currency}",
        "broker_position_id": broker_position_id,
        "signed_quantity": signed_quantity,
        "position": signed_quantity,
        "avg_cost": 1.13995,
    }


def build_protective_order(
    *,
    broker_position_id: str,
    symbol: str,
    currency: str,
    order_id: int,
    parent_id: int,
    order_type: str,
    price: float,
    oca_group: str,
) -> dict[str, Any]:
    row = {
        "order_id": order_id,
        "parent_id": parent_id,
        "account": ACCOUNT_ID,
        "symbol": symbol,
        "currency": currency,
        "sec_type": "CASH",
        "symbol_name": f"{symbol}{currency}",
        "broker_position_id": broker_position_id,
        "action": "BUY",
        "order_type": order_type,
        "total_quantity": 1000.0,
        "lmt_price": 0.0,
        "aux_price": 0.0,
        "client_id": 1,
        "same_client_id": True,
        "oca_group": oca_group,
        "order_ref": "[LGE:M] LGE manual UI order",
        "status": "Submitted",
    }

    if order_type == "STP":
        row["aux_price"] = price
    else:
        row["lmt_price"] = price

    return row


def build_external_execution() -> dict[str, Any]:
    return {
        "account": ACCOUNT_ID,
        "symbol": "EUR",
        "currency": "USD",
        "sec_type": "CASH",
        "symbol_name": "EURUSD",
        "broker_position_id": EURUSD_ID,
        "side": "BOT",
        "shares": 2000.0,
        "price": 1.13995,
        "time": "20260724 03:26:50 US/Eastern",
        "order_id": None,
        "perm_id": 1379079080,
    }


def build_snapshot(
    *,
    positions: list[dict[str, Any]],
    open_orders: list[dict[str, Any]],
    executions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "broker": "IB",
        "captured_utc": "2026-07-24T10:56:53+00:00",
        "current_client_id": 1,
        "complete": True,
        "positions_complete": True,
        "open_orders_complete": True,
        "completed_orders_complete": True,
        "executions_complete": True,
        "completed_orders_api_only": False,
        "account_ids": [ACCOUNT_ID],
        "positions": positions,
        "open_orders": open_orders,
        "completed_orders": [],
        "executions": executions,
    }


def build_eurusd_leg() -> IBVirtualPositionLeg:
    return IBVirtualPositionLeg(
        position_uid="6b20bcb4-d36a-4962-9847-b6886ca02780",
        trade_uid="a638b247-d045-4815-b3f4-0b9723c4d26f",
        broker_position_id=EURUSD_ID,
        account_id=ACCOUNT_ID,
        symbol_name="EURUSD",
        side="SELL",
        volume=1000.0,
        entry_price=1.1372,
        opened_utc="20260723 09:26:45 US/Eastern",
        source="MANUAL",
        parent_order_id=194,
        stop_loss_order_id=196,
        take_profit_order_id=195,
        stop_loss=1.144,
        take_profit=1.136,
        oca_group="1329483705",
        leg_status=IB_LEG_STATUS_OPEN,
        protection_status=IB_PROTECTION_STATUS_COMPLETE,
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
    )


def build_usdzar_leg() -> IBVirtualPositionLeg:
    return IBVirtualPositionLeg(
        position_uid="f16dac30-63c5-4fda-9fb0-0331d6b56d34",
        trade_uid="a879e4f8-affc-458c-8146-5508bfe68fa4",
        broker_position_id=USDZAR_ID,
        account_id=ACCOUNT_ID,
        symbol_name="USDZAR",
        side="BUY",
        volume=1000.0,
        entry_price=16.64547,
        opened_utc="20260723 09:23:49 US/Eastern",
        source="MANUAL",
        parent_order_id=191,
        stop_loss_order_id=192,
        take_profit_order_id=193,
        stop_loss=16.4,
        take_profit=16.75,
        oca_group="LGE_SLTP_1_192_193",
        leg_status=IB_LEG_STATUS_OPEN,
        protection_status=IB_PROTECTION_STATUS_COMPLETE,
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
    )


def build_usdzar_closed_sell_leg() -> IBVirtualPositionLeg:
    return IBVirtualPositionLeg(
        position_uid="b7da1514-49d0-4aaf-b86d-ffaeab1d5fbf",
        trade_uid="6acce2dc-d3b0-4421-b2f9-72cad6beaa05",
        broker_position_id=USDZAR_ID,
        account_id=ACCOUNT_ID,
        symbol_name="USDZAR",
        side="SELL",
        volume=1000.0,
        entry_price=16.88252,
        opened_utc="20260724 09:24:07 US/Eastern",
        source="MANUAL",
        parent_order_id=197,
        stop_loss_order_id=198,
        take_profit_order_id=199,
        stop_loss=16.852,
        take_profit=16.6,
        oca_group="LGE_SLTP_1_198_199",
        close_order_ids=(201,),
        leg_status=IB_LEG_STATUS_CLOSED,
        protection_status=IB_PROTECTION_STATUS_NONE,
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
    )


def build_usdzar_sell_leg_close_execution() -> dict[str, Any]:
    return {
        "account": ACCOUNT_ID,
        "symbol": "USD",
        "currency": "ZAR",
        "sec_type": "CASH",
        "symbol_name": "USDZAR",
        "broker_position_id": USDZAR_ID,
        "side": "BOT",
        "shares": 1000.0,
        "price": 16.78575,
        "time": "20260728 02:30:30 US/Eastern",
        "order_id": 201,
        "perm_id": 1209512923,
    }


def build_usdzar_external_execution() -> dict[str, Any]:
    return {
        "account": ACCOUNT_ID,
        "symbol": "USD",
        "currency": "ZAR",
        "sec_type": "CASH",
        "symbol_name": "USDZAR",
        "broker_position_id": USDZAR_ID,
        "side": "SLD",
        "shares": 1000.0,
        "price": 16.79,
        "time": "20260728 02:31:00 US/Eastern",
        "order_id": None,
        "perm_id": 1209512999,
    }


def main() -> int:
    eurusd_leg = build_eurusd_leg()
    eurusd_evidence = build_snapshot(
        positions=[build_position(EURUSD_ID, "EUR", "USD", 2000.0)],
        open_orders=[
            build_protective_order(
                broker_position_id=EURUSD_ID,
                symbol="EUR",
                currency="USD",
                order_id=195,
                parent_id=194,
                order_type="LMT",
                price=1.136,
                oca_group="1329483705",
            ),
            build_protective_order(
                broker_position_id=EURUSD_ID,
                symbol="EUR",
                currency="USD",
                order_id=196,
                parent_id=194,
                order_type="STP",
                price=1.144,
                oca_group="1329483705",
            ),
        ],
        executions=[build_external_execution()],
    )
    reconciliation = reconcile_ib_virtual_position_legs(
        [eurusd_leg],
        eurusd_evidence,
    )

    if reconciliation.group_statuses[EURUSD_ID] != (
        IB_RECONCILIATION_STATUS_RECONCILED
    ):
        raise AssertionError("Mixed EURUSD group was not reconciled")

    residual = reconciliation.group_broker_residual_signed_volumes[EURUSD_ID]

    if residual != 2000.0:
        raise AssertionError(f"Unexpected broker residual: {residual}")

    group_snapshot = build_ib_position_group_snapshot(
        reconciliation_snapshot=reconciliation,
        evidence_snapshot=eurusd_evidence,
    )
    group = group_snapshot.groups[0]

    if group.display_side != "BUY" or group.display_volume != 2000.0:
        raise AssertionError("Group row does not show Virtual FX BUY 2 000")

    if group.broker_residual_side != "BUY":
        raise AssertionError("Broker residual side differs")

    if group.broker_residual_volume != 2000.0:
        raise AssertionError("Broker residual volume differs")

    if not group.leg_operations_enabled:
        raise AssertionError("Exact LGE leg operations remained blocked")

    persisted_leg = reconciliation.legs[0]
    restarted_legs = build_ib_virtual_position_legs_from_repository_seeds(
        [
            {
                "position_uid": persisted_leg.position_uid,
                "trade_uid": persisted_leg.trade_uid,
                "broker_position_id": persisted_leg.broker_position_id,
                "account_id": persisted_leg.account_id,
                "symbol_name": persisted_leg.symbol_name,
                "logical_side": persisted_leg.side,
                "logical_volume": persisted_leg.volume,
                "trade_source": persisted_leg.source,
                "parent_order_id": persisted_leg.parent_order_id,
                "persisted_entry_price": persisted_leg.entry_price,
                "persisted_opened_utc": persisted_leg.opened_utc,
                "persisted_parent_order_id": persisted_leg.parent_order_id,
                "persisted_stop_loss_order_id": (persisted_leg.stop_loss_order_id),
                "persisted_take_profit_order_id": (persisted_leg.take_profit_order_id),
                "persisted_stop_loss": persisted_leg.stop_loss,
                "persisted_take_profit": persisted_leg.take_profit,
                "persisted_oca_group": persisted_leg.oca_group,
                "persisted_leg_status": persisted_leg.leg_status,
                "persisted_protection_status": (persisted_leg.protection_status),
                "persisted_reconciliation_status": (
                    persisted_leg.reconciliation_status
                ),
                "persisted_reconciliation_messages_json": json.dumps(
                    list(persisted_leg.reconciliation_messages)
                ),
            }
        ]
    )
    restarted_reconciliation = reconcile_ib_virtual_position_legs(
        restarted_legs,
        build_snapshot(
            positions=[build_position(EURUSD_ID, "EUR", "USD", 2000.0)],
            open_orders=eurusd_evidence["open_orders"],
            executions=[],
        ),
    )

    if restarted_reconciliation.group_statuses[EURUSD_ID] != (
        IB_RECONCILIATION_STATUS_RECONCILED
    ):
        raise AssertionError("Persisted broker residual did not survive restart")

    restarted_residual = restarted_reconciliation.group_broker_residual_signed_volumes[
        EURUSD_ID
    ]

    if restarted_residual != 2000.0:
        raise AssertionError("Restarted broker residual volume differs")

    usdzar_reconciliation = reconcile_ib_virtual_position_legs(
        [build_usdzar_leg()],
        build_snapshot(positions=[], open_orders=[], executions=[]),
    )
    usdzar_leg = usdzar_reconciliation.legs[0]

    if usdzar_leg.reconciliation_status != (
        IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING
    ):
        raise AssertionError("Missing USDZAR close evidence was not classified")

    if usdzar_reconciliation.group_statuses[USDZAR_ID] != (
        IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING
    ):
        raise AssertionError("USDZAR group lost missing-evidence status")

    if usdzar_reconciliation.group_broker_residual_signed_volumes[USDZAR_ID] != 0.0:
        raise AssertionError("Missing broker row created a false residual")

    supported_open_reconciliation = reconcile_ib_virtual_position_legs(
        [build_usdzar_leg(), build_usdzar_closed_sell_leg()],
        build_snapshot(
            positions=[build_position(USDZAR_ID, "USD", "ZAR", 1000.0)],
            open_orders=[],
            executions=[build_usdzar_sell_leg_close_execution()],
        ),
    )
    supported_open_leg = next(
        leg
        for leg in supported_open_reconciliation.legs
        if leg.position_uid == build_usdzar_leg().position_uid
    )

    if supported_open_leg.reconciliation_status != (
        IB_RECONCILIATION_STATUS_RECONCILED
    ):
        raise AssertionError("Exact broker exposure did not recover OPEN leg")

    if supported_open_leg.protection_status != IB_PROTECTION_STATUS_NONE:
        raise AssertionError("Recovered OPEN leg retained protection status")

    if any(
        value is not None
        for value in (
            supported_open_leg.stop_loss_order_id,
            supported_open_leg.take_profit_order_id,
            supported_open_leg.stop_loss,
            supported_open_leg.take_profit,
        )
    ):
        raise AssertionError("Recovered OPEN leg retained stale SL/TP state")

    if supported_open_leg.oca_group:
        raise AssertionError("Recovered OPEN leg retained stale OCA group")

    if supported_open_reconciliation.group_statuses[USDZAR_ID] != (
        IB_RECONCILIATION_STATUS_RECONCILED
    ):
        raise AssertionError("Exact broker exposure did not recover group")

    supported_group_snapshot = build_ib_position_group_snapshot(
        reconciliation_snapshot=supported_open_reconciliation,
        evidence_snapshot=build_snapshot(
            positions=[build_position(USDZAR_ID, "USD", "ZAR", 1000.0)],
            open_orders=[],
            executions=[build_usdzar_sell_leg_close_execution()],
        ),
    )

    if not supported_group_snapshot.groups[0].leg_operations_enabled:
        raise AssertionError("Recovered exact OPEN leg operations stayed blocked")

    external_evidence_reconciliation = reconcile_ib_virtual_position_legs(
        [build_usdzar_leg(), build_usdzar_closed_sell_leg()],
        build_snapshot(
            positions=[build_position(USDZAR_ID, "USD", "ZAR", 1000.0)],
            open_orders=[],
            executions=[
                build_usdzar_sell_leg_close_execution(),
                build_usdzar_external_execution(),
            ],
        ),
    )
    externally_ambiguous_leg = next(
        leg
        for leg in external_evidence_reconciliation.legs
        if leg.position_uid == build_usdzar_leg().position_uid
    )

    if externally_ambiguous_leg.reconciliation_status != (
        IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING
    ):
        raise AssertionError("External execution evidence was auto-recovered")

    print("IB broker residual and missing close evidence result")
    print("  virtual_fx_observation=BUY 2000")
    print("  managed_leg=SELL 1000")
    print("  exact_non_lge_execution=BUY 2000")
    print("  broker_residual=BUY 2000")
    print("  exact_leg_operations=True")
    print("  residual_survives_restart=True")
    print("  missing_broker_row_residual=False")
    print("  usdzar_status=CLOSE_EVIDENCE_MISSING")
    print("  exact_broker_exposure_recovers_open_leg=True")
    print("  recovered_open_leg_protection=NONE")
    print("  recovered_open_leg_operations=True")
    print("  external_execution_auto_recovery_blocked=True")
    print("IB_BROKER_RESIDUAL_AND_MISSING_CLOSE_EVIDENCE_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
