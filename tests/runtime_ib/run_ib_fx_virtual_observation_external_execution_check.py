"""IB CASH Virtual FX exact external-execution direction regression check."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_position_group import build_ib_position_group_snapshot  # noqa: E402
from engine.ib_virtual_position_leg import (  # noqa: E402
    IBVirtualPositionLeg,
    reconcile_ib_virtual_position_legs,
)
from engine.runtime_constants import (  # noqa: E402
    IB_LEG_STATUS_OPEN,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_RECONCILIATION_STATUS_RECONCILED,
)

ACCOUNT_ID = "DUM513747"
POSITION_ID = f"IB:{ACCOUNT_ID}:GBPUSD"
CURRENT_CLIENT_ID = 1


def _leg(
    *,
    suffix: str,
    parent_order_id: int,
    take_profit_order_id: int,
    stop_loss_order_id: int,
) -> IBVirtualPositionLeg:
    return IBVirtualPositionLeg(
        position_uid=f"position-{suffix}",
        trade_uid=f"trade-{suffix}",
        broker_position_id=POSITION_ID,
        account_id=ACCOUNT_ID,
        symbol_name="GBPUSD",
        side="BUY",
        volume=1000.0,
        entry_price=1.345,
        opened_utc="2026-08-03T04:00:00+00:00",
        source="MANUAL",
        parent_order_id=parent_order_id,
        take_profit_order_id=take_profit_order_id,
        stop_loss_order_id=stop_loss_order_id,
        parent_order_perm_id=parent_order_id + 900000,
        take_profit_order_perm_id=take_profit_order_id + 900000,
        stop_loss_order_perm_id=stop_loss_order_id + 900000,
        take_profit=1.35225,
        stop_loss=1.3357,
        oca_group=f"LGE_{parent_order_id}",
        leg_status=IB_LEG_STATUS_OPEN,
        protection_status=IB_PROTECTION_STATUS_COMPLETE,
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
    )


def _execution(
    *,
    order_id: int,
    side: str,
    shares: float,
    time_value: str,
) -> dict[str, Any]:
    return {
        "account": ACCOUNT_ID,
        "symbol": "GBP",
        "currency": "USD",
        "sec_type": "CASH",
        "symbol_name": "GBPUSD",
        "broker_position_id": POSITION_ID,
        "side": side,
        "shares": shares,
        "price": 1.3464,
        "time": time_value,
        "order_id": order_id,
        "perm_id": order_id + 900000,
    }


def _protective_order(
    *,
    order_id: int,
    parent_id: int,
    order_type: str,
    price: float,
) -> dict[str, Any]:
    return {
        "order_id": order_id,
        "parent_id": parent_id,
        "account": ACCOUNT_ID,
        "symbol": "GBP",
        "currency": "USD",
        "sec_type": "CASH",
        "symbol_name": "GBPUSD",
        "broker_position_id": POSITION_ID,
        "action": "SELL",
        "order_type": order_type,
        "total_quantity": 1000.0,
        "lmt_price": price if order_type == "LMT" else 0.0,
        "aux_price": price if order_type == "STP" else 0.0,
        "client_id": CURRENT_CLIENT_ID,
        "same_client_id": True,
        "perm_id": order_id + 900000,
        "oca_group": f"LGE_{parent_id}",
        "status": "Submitted",
    }


def _snapshot(
    *,
    legs: list[IBVirtualPositionLeg],
    include_executions: bool,
) -> dict[str, Any]:
    executions: list[dict[str, Any]] = []

    if include_executions:
        executions = [
            _execution(
                order_id=legs[0].parent_order_id or 0,
                side="BOT",
                shares=1000.0,
                time_value="20260803 04:07:00",
            ),
            _execution(
                order_id=legs[1].parent_order_id or 0,
                side="BOT",
                shares=1000.0,
                time_value="20260803 05:30:00",
            ),
            _execution(
                order_id=9001,
                side="BOT",
                shares=1000.0,
                time_value="20260805 10:01:01",
            ),
        ]

    return {
        "broker": "IB",
        "captured_utc": "2026-08-05T07:01:02+00:00",
        "current_client_id": CURRENT_CLIENT_ID,
        "complete": True,
        "positions_complete": True,
        "open_orders_complete": True,
        "completed_orders_complete": True,
        "executions_complete": True,
        "completed_orders_api_only": False,
        "account_ids": [ACCOUNT_ID],
        "positions": [
            {
                "account": ACCOUNT_ID,
                "symbol": "GBP",
                "currency": "USD",
                "sec_type": "CASH",
                "symbol_name": "GBPUSD",
                "broker_position_id": POSITION_ID,
                "signed_quantity": 1000.0,
                "position": 1000.0,
                "avg_cost": 1.3488,
            }
        ],
        "open_orders": [
            _protective_order(
                order_id=leg.take_profit_order_id or 0,
                parent_id=leg.parent_order_id or 0,
                order_type="LMT",
                price=leg.take_profit or 0.0,
            )
            for leg in legs
        ]
        + [
            _protective_order(
                order_id=leg.stop_loss_order_id or 0,
                parent_id=leg.parent_order_id or 0,
                order_type="STP",
                price=leg.stop_loss or 0.0,
            )
            for leg in legs
        ],
        "completed_orders": [],
        "executions": executions,
    }


def main() -> int:
    legs = [
        _leg(
            suffix="first",
            parent_order_id=501,
            take_profit_order_id=502,
            stop_loss_order_id=503,
        ),
        _leg(
            suffix="second",
            parent_order_id=504,
            take_profit_order_id=505,
            stop_loss_order_id=506,
        ),
    ]
    evidence = _snapshot(legs=legs, include_executions=True)
    reconciliation = reconcile_ib_virtual_position_legs(legs, evidence)
    residual = reconciliation.group_broker_residual_signed_volumes[POSITION_ID]
    exposure = reconciliation.group_external_exposures[POSITION_ID]

    if reconciliation.group_statuses[POSITION_ID] != (
        IB_RECONCILIATION_STATUS_RECONCILED
    ):
        raise AssertionError("GBPUSD group was not reconciled")

    if residual != 1000.0:
        raise AssertionError(f"External BUY execution became {residual}")

    if exposure.signed_volume != 1000.0:
        raise AssertionError("External exposure direction differs")

    group = build_ib_position_group_snapshot(
        reconciliation_snapshot=reconciliation,
        evidence_snapshot=evidence,
    ).groups[0]

    if group.signed_open_leg_volume != 2000.0:
        raise AssertionError("Managed GBPUSD volume differs")

    if group.broker_signed_volume != 1000.0:
        raise AssertionError("Virtual FX observation differs")

    if group.broker_residual_side != "BUY":
        raise AssertionError("Exact external BUY was displayed as SELL")

    repeated = reconcile_ib_virtual_position_legs(
        reconciliation.legs,
        _snapshot(legs=reconciliation.legs, include_executions=True),
    )

    if repeated.group_broker_residual_signed_volumes[POSITION_ID] != 1000.0:
        raise AssertionError("Repeated evidence double-counted the execution")

    reused_id_evidence = _snapshot(
        legs=reconciliation.legs,
        include_executions=True,
    )
    reused_id_execution = reused_id_evidence["executions"][-1]
    reused_id_execution["order_id"] = reconciliation.legs[0].parent_order_id
    reused_id_execution["perm_id"] = 9999999
    reused_id = reconcile_ib_virtual_position_legs(
        reconciliation.legs,
        reused_id_evidence,
    )

    if reused_id.group_broker_residual_signed_volumes[POSITION_ID] != 1000.0:
        raise AssertionError("Reused orderId hid a foreign execution")

    restarted = reconcile_ib_virtual_position_legs(
        reconciliation.legs,
        _snapshot(legs=reconciliation.legs, include_executions=False),
    )

    if restarted.group_broker_residual_signed_volumes[POSITION_ID] != 1000.0:
        raise AssertionError("Persisted external direction was not retained")

    closed_evidence = _snapshot(
        legs=reconciliation.legs,
        include_executions=True,
    )
    closed_evidence["positions"][0]["signed_quantity"] = 0.0
    closed_evidence["positions"][0]["position"] = 0.0
    closed_evidence["executions"].append(
        _execution(
            order_id=9002,
            side="SLD",
            shares=1000.0,
            time_value="20260805 10:15:00",
        )
    )
    closed = reconcile_ib_virtual_position_legs(
        reconciliation.legs,
        closed_evidence,
        persisted_external_exposures=reconciliation.group_external_exposures,
    )

    if closed.group_broker_residual_signed_volumes[POSITION_ID] != 0.0:
        raise AssertionError("Opposite external execution did not clear residual")

    if POSITION_ID in closed.group_external_exposures:
        raise AssertionError("Cleared external exposure remained active")

    messages = reconciliation.group_messages[POSITION_ID]

    if not any(
        "not from Virtual FX minus managed-leg arithmetic" in message
        for message in messages
    ):
        raise AssertionError("Virtual FX arithmetic guard message is missing")

    print("IB FX Virtual FX external execution result")
    print("  managed_lge_legs=BUY 2000")
    print("  virtual_fx_observation=BUY 1000")
    print("  virtual_fx_minus_managed=SELL 1000")
    print("  exact_external_execution=BUY 1000")
    print("  displayed_external_exposure=BUY 1000")
    print("  repeated_snapshot_double_counted=False")
    print("  reused_order_id_guarded_by_perm_id=True")
    print("  persisted_direction_survives_restart=True")
    print("  opposite_external_execution_clears=True")
    print("  broker_execution_attempted=False")
    print("IB_FX_VIRTUAL_OBSERVATION_EXTERNAL_EXECUTION_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
