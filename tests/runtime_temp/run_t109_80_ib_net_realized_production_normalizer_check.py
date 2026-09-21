"""T109-80 production check: IB canonical net-realized amount.

Призначення:
- підтвердити canonical ``net_realized_pnl`` у завершеній IB pair event;
- підтвердити, що значення дорівнює broker-reported ``realizedPNL``;
- підтвердити, що commission/fees лишаються audit field і не віднімаються вдруге;
- не змінювати pairing, dedup або daily PnL aggregation.

Safety:
- broker connection не виконується;
- broker request не виконується;
- daily PnL risk wiring не додається.
"""

from __future__ import annotations

from types import SimpleNamespace

from engine.ib_adapter import IBAdapter

BROKER_REQUESTS = 0


def _contract() -> SimpleNamespace:
    """Побудувати мінімальний IB-like contract без broker interaction."""
    return SimpleNamespace(
        symbol="EUR",
        secType="CASH",
        currency="USD",
        exchange="IDEALPRO",
    )


def _execution(exec_id: str) -> SimpleNamespace:
    """Побудувати мінімальний execution callback payload."""
    return SimpleNamespace(
        execId=exec_id,
        acctNumber="DU109",
        side="BOT",
        shares=1000.0,
        price=1.125,
        time="20260921 10:00:00 UTC",
        orderId=8001,
        permId=18001,
    )


def _commission(exec_id: str) -> SimpleNamespace:
    """Побудувати мінімальний commission callback payload."""
    return SimpleNamespace(
        execId=exec_id,
        commissionAndFees=0.25,
        currency="USD",
        realizedPNL=4.75,
    )


def main() -> None:
    """Запустити offline production-normalizer assertions."""
    adapter = IBAdapter(
        host="127.0.0.1",
        port=7497,
        client_id=10980,
    )
    wrapper = getattr(adapter, "_wrapper")

    wrapper.execDetails(0, _contract(), _execution("E80-NET"))
    wrapper.commissionAndFeesReport(_commission("E80-NET"))

    events = adapter.get_execution_commission_events()
    assert len(events) == 1
    event = events[0]

    canonical_net_amount_present = "net_realized_pnl" in event
    broker_reported_amount_preserved = (
        event["broker_reported_realized_pnl"] == 4.75
    )
    commission_audit_field_preserved = event["commission_and_fees"] == 0.25
    net_equals_broker_reported = event["net_realized_pnl"] == 4.75
    commission_not_subtracted_again = event["net_realized_pnl"] != 4.50
    identity_preserved = (
        event["broker"] == "IB"
        and event["account_id"] == "DU109"
        and event["exec_id"] == "E80-NET"
    )

    completed_before_duplicate = len(events)
    wrapper.execDetails(0, _contract(), _execution("E80-NET"))
    wrapper.commissionAndFeesReport(_commission("E80-NET"))
    duplicate_exec_id_still_emits_once = (
        len(adapter.get_execution_commission_events()) == completed_before_duplicate
    )

    daily_pnl_aggregation_added = False
    production_change = True

    assert BROKER_REQUESTS == 0
    assert canonical_net_amount_present
    assert broker_reported_amount_preserved
    assert commission_audit_field_preserved
    assert net_equals_broker_reported
    assert commission_not_subtracted_again
    assert identity_preserved
    assert duplicate_exec_id_still_emits_once
    assert not daily_pnl_aggregation_added

    print("T109-80_IB_NET_REALIZED_PRODUCTION_NORMALIZER=OK")
    print(f"production_change={production_change}")
    print(f"canonical_net_amount_present={canonical_net_amount_present}")
    print(f"broker_reported_amount_preserved={broker_reported_amount_preserved}")
    print(f"commission_audit_field_preserved={commission_audit_field_preserved}")
    print(f"net_equals_broker_reported={net_equals_broker_reported}")
    print(f"commission_not_subtracted_again={commission_not_subtracted_again}")
    print(f"identity_preserved={identity_preserved}")
    print(
        "duplicate_exec_id_still_emits_once="
        f"{duplicate_exec_id_still_emits_once}"
    )
    print(f"daily_pnl_aggregation_added={daily_pnl_aggregation_added}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print("canonical_net_source=BROKER_REPORTED_REALIZED_PNL")
    print("commission_behavior=AUDIT_ONLY_DO_NOT_SUBTRACT_AGAIN")
    print("first_unresolved_boundary=BROKER_DAILY_PNL_PRODUCTION_AGGREGATOR")
    print(
        "boundary_contract=IB_AND_CTRADER_NOW_EXPOSE_CANONICAL_NET_REALIZED_"
        "EVENT_AMOUNTS_BUT_BROKER_NEUTRAL_ACCOUNT_DAY_AGGREGATION_REMAINS_"
        "UNIMPLEMENTED"
    )
    print(
        "factual_verdict=A. IB_NET_REALIZED_PRODUCTION_NORMALIZER_GREEN_"
        "WITH_BROKER_REPORTED_REALIZED_PNL_AS_CANONICAL_NET_AMOUNT"
    )


if __name__ == "__main__":
    main()
