"""Clear protective-only IB FX exposure after terminal foreign orders."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_fx_external_exposure import (  # noqa: E402
    IB_FX_EXTERNAL_EXPOSURE_CLEARED,
    IB_FX_EXTERNAL_EXPOSURE_STALE,
)
from engine.runtime_engine import RuntimeEngine  # noqa: E402
from tests.runtime_ib import (  # noqa: E402
    run_runtime_engine_ib_broker_residual_persistence_check as support,
)

ACCOUNT_ID = "DUM513747"
EURUSD_ID = f"IB:{ACCOUNT_ID}:EURUSD"
GBPUSD_ID = f"IB:{ACCOUNT_ID}:GBPUSD"


def _protective_order(
    *,
    symbol_name: str,
    order_type: str,
    perm_id: int,
    oca_group: str,
    price: float,
    status: str,
) -> dict:
    symbol = symbol_name[:3]
    currency = symbol_name[3:]
    row = {
        "broker_position_id": f"IB:{ACCOUNT_ID}:{symbol_name}",
        "account": ACCOUNT_ID,
        "symbol": symbol,
        "currency": currency,
        "symbol_name": symbol_name,
        "sec_type": "CASH",
        "order_id": 0,
        "perm_id": perm_id,
        "parent_id": 0,
        "client_id": 0,
        "same_client_id": False,
        "oca_group": oca_group,
        "order_type": order_type,
        "action": "SELL",
        "total_quantity": 1000.0,
        "status": status,
        "tif": "GTC",
    }

    if order_type == "LMT":
        row["lmt_price"] = price
    else:
        row["aux_price"] = price

    return row


def _evidence(open_orders: list[dict], captured_utc: str) -> dict:
    snapshot = support.build_live_like_evidence(include_external_execution=False)
    snapshot["captured_utc"] = captured_utc
    snapshot["positions"] = []
    snapshot["open_orders"] = [
        *snapshot["open_orders"],
        *open_orders,
    ]
    return snapshot


def _active_pair(
    *,
    symbol_name: str,
    first_perm_id: int,
    oca_group: str,
    stop_price: float,
    limit_price: float,
) -> list[dict]:
    return [
        _protective_order(
            symbol_name=symbol_name,
            order_type="LMT",
            perm_id=first_perm_id,
            oca_group=oca_group,
            price=limit_price,
            status="Submitted",
        ),
        _protective_order(
            symbol_name=symbol_name,
            order_type="STP",
            perm_id=first_perm_id + 1,
            oca_group=oca_group,
            price=stop_price,
            status="PreSubmitted",
        ),
    ]


def main() -> int:
    eurusd_active = _active_pair(
        symbol_name="EURUSD",
        first_perm_id=963655593,
        oca_group="963655591",
        stop_price=0.145,
        limit_price=1.156,
    )
    gbpusd_active = _active_pair(
        symbol_name="GBPUSD",
        first_perm_id=963655601,
        oca_group="963655600",
        stop_price=1.3385,
        limit_price=1.354,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "runtime.db"
        engine = RuntimeEngine(db_path=str(db_path))

        try:
            support.seed_runtime_position(engine)
            service = support.EvidenceService(
                _evidence(
                    eurusd_active + gbpusd_active,
                    "2026-08-04T18:35:00+00:00",
                )
            )
            engine.set_ib_runtime_service(service)
            engine.set_broker("IB")
            first_snapshot = engine.sync_active_broker_position_groups()

            if {group.symbol_name for group in first_snapshot.groups} != {
                "EURUSD",
                "GBPUSD",
            }:
                raise AssertionError("Initial protective-only groups differ")

            first_ledger = engine.repository.get_active_ib_fx_external_exposures()

            if len(first_ledger) != 2:
                raise AssertionError("Protective-only exposures were not persisted")

            if any(
                exposure.evidence_status != IB_FX_EXTERNAL_EXPOSURE_STALE
                or exposure.last_confirmed_utc
                for exposure in first_ledger
            ):
                raise AssertionError("Protective-only provenance differs")

            eurusd_terminal = [
                {**eurusd_active[0], "status": "Cancelled"},
                {**eurusd_active[1], "status": "Inactive"},
            ]
            service.snapshot = _evidence(
                eurusd_terminal + gbpusd_active,
                "2026-08-04T20:40:00+00:00",
            )
            second_snapshot = engine.sync_active_broker_position_groups()

            second_groups = {
                group.symbol_name: group for group in second_snapshot.groups
            }

            if set(second_groups) != {"EURUSD", "GBPUSD"}:
                raise AssertionError("Second position-group set differs")

            eurusd_group = second_groups["EURUSD"]

            if eurusd_group.broker_residual_present:
                raise AssertionError("Inactive EURUSD orders kept external residual")

            if eurusd_group.broker_residual_protective_orders:
                raise AssertionError("Inactive EURUSD details remained visible")

            active_ledger = engine.repository.get_active_ib_fx_external_exposures()

            if len(active_ledger) != 1:
                raise AssertionError("Active external ledger row count differs")

            remaining = active_ledger[0]

            if remaining.broker_position_id != GBPUSD_ID:
                raise AssertionError("Unrelated GBPUSD exposure was cleared")

            eurusd_row = engine.connection.execute(
                """
                SELECT signed_volume, evidence_status, cleared_utc
                FROM ib_fx_external_exposures
                WHERE broker_position_id = ?
                """,
                (EURUSD_ID,),
            ).fetchone()

            if eurusd_row is None:
                raise AssertionError("EURUSD clear ledger row is missing")

            if float(eurusd_row["signed_volume"] or 0.0) != 0.0:
                raise AssertionError("EURUSD clear volume differs")

            if str(eurusd_row["evidence_status"] or "") != (
                IB_FX_EXTERNAL_EXPOSURE_CLEARED
            ):
                raise AssertionError("EURUSD ledger status is not CLEARED")

            if not str(eurusd_row["cleared_utc"] or "").strip():
                raise AssertionError("EURUSD cleared timestamp is missing")

            if service.evidence_calls != 2:
                raise AssertionError("Unexpected broker evidence request count")
        finally:
            engine.connection.close()

    print("IB FX inactive external orders clear result")
    print("  terminal_statuses=Cancelled,Inactive")
    print("  inactive_eurusd_orders_ignored=True")
    print("  protective_only_eurusd_cleared=True")
    print("  managed_eurusd_leg_preserved=True")
    print("  active_gbpusd_preserved=True")
    print("  exact_scope=account,symbol")
    print("  broker_execution_attempted=False")
    print("IB_FX_INACTIVE_EXTERNAL_ORDERS_CLEAR_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
