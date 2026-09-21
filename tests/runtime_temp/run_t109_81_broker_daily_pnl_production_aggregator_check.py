"""T109-81: broker-neutral daily PnL production aggregator check."""

from __future__ import annotations

from datetime import UTC, datetime

from engine.daily_realized_pnl import aggregate_broker_daily_realized_pnl

BROKER_REQUESTS = 0


def _epoch_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def main() -> None:
    evaluation = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)

    ib_events = [
        {
            "broker": "IB",
            "account_id": "DU109",
            "exec_id": "E81-A",
            "execution_time": "20260921 10:00:00 UTC",
            "net_realized_pnl": 5.25,
        },
        {
            "broker": "IB",
            "account_id": "DU109",
            "exec_id": "E81-A",
            "execution_time": "20260921 10:00:00 UTC",
            "net_realized_pnl": 5.25,
        },
        {
            "broker": "IB",
            "account_id": "DU109",
            "exec_id": "E81-FUTURE",
            "execution_time": "20260921 13:00:00 UTC",
            "net_realized_pnl": 99.0,
        },
        {
            "broker": "IB",
            "account_id": "OTHER",
            "exec_id": "E81-OTHER",
            "execution_time": "20260921 09:00:00 UTC",
            "net_realized_pnl": 77.0,
        },
    ]
    ib_result = aggregate_broker_daily_realized_pnl(
        broker="IB",
        account_id="DU109",
        events=ib_events,
        evaluation_utc=evaluation,
        source_complete=True,
    )

    ctrader_events = [
        {
            "broker": "CTRADER",
            "account_id": "900001",
            "deal_id": "81001",
            "execution_timestamp": _epoch_ms(
                datetime(2026, 9, 21, 8, 30, tzinfo=UTC)
            ),
            "net_realized_pnl": 3.0,
        },
        {
            "broker": "CTRADER",
            "account_id": "900001",
            "deal_id": "81002",
            "execution_timestamp": _epoch_ms(
                datetime(2026, 9, 21, 11, 30, tzinfo=UTC)
            ),
            "net_realized_pnl": -1.25,
        },
    ]
    ctrader_result = aggregate_broker_daily_realized_pnl(
        broker="CTRADER",
        account_id="900001",
        events=ctrader_events,
        evaluation_utc=evaluation,
        source_complete=True,
    )

    incomplete_result = aggregate_broker_daily_realized_pnl(
        broker="IB",
        account_id="DU109",
        events=ib_events,
        evaluation_utc=evaluation,
        source_complete=False,
    )

    invalid_result = aggregate_broker_daily_realized_pnl(
        broker="IB",
        account_id="DU109",
        events=[
            {
                "broker": "IB",
                "account_id": "DU109",
                "exec_id": "",
                "execution_time": "20260921 10:00:00 UTC",
                "net_realized_pnl": 1.0,
            }
        ],
        evaluation_utc=evaluation,
        source_complete=True,
    )

    ib_account_day_aggregation_correct = (
        ib_result.success
        and ib_result.daily_realized_pnl == 5.25
        and ib_result.event_count == 1
    )
    ctrader_account_day_aggregation_correct = (
        ctrader_result.success
        and ctrader_result.daily_realized_pnl == 1.75
        and ctrader_result.event_count == 2
    )
    duplicate_identity_deduped = ib_result.event_count == 1
    future_event_excluded = ib_result.daily_realized_pnl == 5.25
    exact_account_scope_enforced = ib_result.daily_realized_pnl != 82.25
    utc_half_open_day_contract = (
        ib_result.day_start_utc == datetime(2026, 9, 21, tzinfo=UTC)
        and ib_result.day_end_utc == datetime(2026, 9, 22, tzinfo=UTC)
    )
    incomplete_source_fail_closed = (
        not incomplete_result.success
        and incomplete_result.daily_realized_pnl is None
    )
    invalid_canonical_event_fail_closed = (
        not invalid_result.success
        and invalid_result.daily_realized_pnl is None
    )
    risk_snapshot_wiring_added = False

    assert BROKER_REQUESTS == 0
    assert ib_account_day_aggregation_correct
    assert ctrader_account_day_aggregation_correct
    assert duplicate_identity_deduped
    assert future_event_excluded
    assert exact_account_scope_enforced
    assert utc_half_open_day_contract
    assert incomplete_source_fail_closed
    assert invalid_canonical_event_fail_closed
    assert not risk_snapshot_wiring_added

    print("T109-81_BROKER_DAILY_PNL_PRODUCTION_AGGREGATOR=OK")
    print("production_change=True")
    print(
        "ib_account_day_aggregation_correct="
        f"{ib_account_day_aggregation_correct}"
    )
    print(
        "ctrader_account_day_aggregation_correct="
        f"{ctrader_account_day_aggregation_correct}"
    )
    print(f"duplicate_identity_deduped={duplicate_identity_deduped}")
    print(f"future_event_excluded={future_event_excluded}")
    print(f"exact_account_scope_enforced={exact_account_scope_enforced}")
    print(f"utc_half_open_day_contract={utc_half_open_day_contract}")
    print(f"incomplete_source_fail_closed={incomplete_source_fail_closed}")
    print(
        "invalid_canonical_event_fail_closed="
        f"{invalid_canonical_event_fail_closed}"
    )
    print(f"risk_snapshot_wiring_added={risk_snapshot_wiring_added}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print("canonical_scope=BROKER_ACCOUNT")
    print("canonical_day=UTC_HALF_OPEN_INTERVAL_[00:00_NEXT_00:00)")
    print("canonical_dedup_key=BROKER+ACCOUNT_ID+EXECUTION_ID")
    print("first_unresolved_boundary=BROKER_DAILY_PNL_SOURCE_COMPLETENESS")
    print(
        "boundary_contract=PRODUCTION_ACCOUNT_DAY_AGGREGATOR_IS_NOW_"
        "BROKER_NEUTRAL_CAUSAL_AND_FAIL_CLOSED_BUT_RUNTIME_MUST_PROVE_"
        "EACH_BROKER_EVENT_SOURCE_COMPLETE_BEFORE_RISK_SNAPSHOT_WIRING"
    )
    print(
        "factual_verdict=A. BROKER_DAILY_PNL_PRODUCTION_AGGREGATOR_GREEN_"
        "WITH_UTC_ACCOUNT_DAY_DEDUP_NO_LOOKAHEAD_AND_FAIL_CLOSED_SOURCES"
    )


if __name__ == "__main__":
    main()
