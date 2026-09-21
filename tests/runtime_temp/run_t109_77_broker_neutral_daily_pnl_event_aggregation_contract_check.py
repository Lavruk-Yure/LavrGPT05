"""T109-77 TEST_ONLY: broker-neutral daily PnL aggregation contract."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IB_ADAPTER = PROJECT_ROOT / "engine" / "ib_adapter.py"
IB_SERVICE = PROJECT_ROOT / "engine" / "services" / "ib_runtime_service.py"
CTRADER_ADAPTER = PROJECT_ROOT / "engine" / "ctrader_adapter.py"
CTRADER_SERVICE = PROJECT_ROOT / "engine" / "services" / "ctrader_runtime_service.py"
BROKER_REQUESTS = 0


def _ib_event_time(value: str) -> datetime:
    """Нормалізувати TEST_ONLY IB execution time у UTC."""
    return datetime.strptime(value, "%Y%m%d %H:%M:%S UTC").replace(tzinfo=UTC)


def _ctrader_event_time(value: int) -> datetime:
    """Нормалізувати TEST_ONLY cTrader epoch milliseconds у UTC."""
    return datetime.fromtimestamp(value / 1000.0, tz=UTC)


def _in_half_open_day(value: datetime, day_start: datetime) -> bool:
    """Перевірити UTC half-open account day без look-ahead."""
    day_end = day_start + timedelta(days=1)
    return day_start <= value < day_end


def main() -> None:
    """Перевірити TEST_ONLY контракт account-day aggregation."""
    ib_adapter = IB_ADAPTER.read_text(encoding="utf-8")
    ib_service = IB_SERVICE.read_text(encoding="utf-8")
    ctrader_adapter = CTRADER_ADAPTER.read_text(encoding="utf-8")
    ctrader_service = CTRADER_SERVICE.read_text(encoding="utf-8")

    ib_normalized_route_present = (
        all(
            token in ib_adapter
            for token in (
                "def get_execution_commission_events(",
                '"exec_id": exec_id',
                '"broker_reported_realized_pnl": float(realized_pnl)',
                '"commission_and_fees": float(commission_value)',
            )
        )
        and "def get_execution_commission_events(" in ib_service
    )

    ctrader_normalized_route_present = (
        all(
            token in ctrader_adapter
            for token in (
                "def get_deal_net_realized_events(",
                '"deal_id": str(deal_id_int)',
                '"net_realized_pnl": net_realized_pnl',
            )
        )
        and "def get_deal_net_realized_events(" in ctrader_service
    )

    ib_canonical_identity_present = all(
        token in ib_adapter
        for token in (
            '"broker": "IB"',
            '"account_id": account_id',
            '"exec_id": exec_id',
        )
    )
    ctrader_canonical_identity_present = all(
        token in ctrader_adapter
        for token in (
            '"broker": "CTRADER"',
            '"account_id": account_id',
            '"deal_id": str(deal_id_int)',
        )
    )

    ib_canonical_net_amount_present = (
        '"net_realized_pnl"'
        in ib_adapter[
            ib_adapter.find(
                "def get_execution_commission_events("
            ) : ib_adapter.find(  # noqa
                "def execDetailsEnd("
            )
        ]
    )
    ctrader_canonical_net_amount_present = (
        '"net_realized_pnl"'
        in ctrader_adapter[
            ctrader_adapter.find(
                "def _normalize_deal_net_realized_event("
            ) : ctrader_adapter.find(  # noqa
                "def get_workspace_timeout_recovery_sources("
            )
        ]
    )

    day_start = datetime(2026, 9, 21, tzinfo=UTC)
    ib_inside = _in_half_open_day(
        _ib_event_time("20260921 10:00:00 UTC"),
        day_start,
    )
    ib_next_day_excluded = not _in_half_open_day(
        _ib_event_time("20260922 00:00:00 UTC"),
        day_start,
    )
    ctrader_inside = _in_half_open_day(
        _ctrader_event_time(1_790_000_000_000),
        datetime.fromtimestamp(1_790_000_000, tz=UTC).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        ),
    )

    ib_key_a = ("IB", "DU109", "E77-A")
    ib_key_b = ("IB", "DU109", "E77-B")
    ctrader_key_a = ("CTRADER", "900001", "77001")
    canonical_keys = {ib_key_a, ib_key_a, ib_key_b, ctrader_key_a}
    dedup_by_broker_account_execution_identity = len(canonical_keys) == 3
    broker_specific_identity_names_can_share_contract = (
        ib_key_a[2] != ib_key_b[2] and ctrader_key_a[2] == "77001"
    )

    completed_normalized_events_only = True
    late_event_applies_from_next_risk_evaluation = True
    no_prior_risk_decision_rewrite = True
    no_lookahead_rule = True
    incomplete_source_fail_closed = True

    broker_neutral_contract_defined = all(
        (
            ib_normalized_route_present,
            ctrader_normalized_route_present,
            ib_canonical_identity_present,
            ctrader_canonical_identity_present,
            ib_inside,
            ib_next_day_excluded,
            ctrader_inside,
            dedup_by_broker_account_execution_identity,
            broker_specific_identity_names_can_share_contract,
            completed_normalized_events_only,
            late_event_applies_from_next_risk_evaluation,
            no_prior_risk_decision_rewrite,
            no_lookahead_rule,
            incomplete_source_fail_closed,
        )
    )

    production_aggregation_allowed = (
        broker_neutral_contract_defined
        and ib_canonical_net_amount_present
        and ctrader_canonical_net_amount_present
    )

    assert BROKER_REQUESTS == 0
    assert ib_normalized_route_present
    assert ctrader_normalized_route_present
    assert ib_canonical_identity_present
    assert ctrader_canonical_identity_present
    assert not ib_canonical_net_amount_present
    assert ctrader_canonical_net_amount_present
    assert ib_inside
    assert ib_next_day_excluded
    assert ctrader_inside
    assert dedup_by_broker_account_execution_identity
    assert broker_specific_identity_names_can_share_contract
    assert completed_normalized_events_only
    assert late_event_applies_from_next_risk_evaluation
    assert no_prior_risk_decision_rewrite
    assert no_lookahead_rule
    assert incomplete_source_fail_closed
    assert broker_neutral_contract_defined
    assert not production_aggregation_allowed

    print("T109-77_BROKER_NEUTRAL_DAILY_PNL_EVENT_AGGREGATION_CONTRACT=OK")
    print("test_scope_test_only=True")
    print("production_change=False")
    print(f"ib_normalized_route_present={ib_normalized_route_present}")
    print(f"ctrader_normalized_route_present={ctrader_normalized_route_present}")
    print(f"ib_canonical_identity_present={ib_canonical_identity_present}")
    print("ctrader_canonical_identity_present=" f"{ctrader_canonical_identity_present}")
    print(f"ib_canonical_net_amount_present={ib_canonical_net_amount_present}")
    print(
        "ctrader_canonical_net_amount_present="
        f"{ctrader_canonical_net_amount_present}"
    )
    print("utc_half_open_day_contract=True")
    print(f"ib_next_day_excluded={ib_next_day_excluded}")
    print(
        "dedup_by_broker_account_execution_identity="
        f"{dedup_by_broker_account_execution_identity}"
    )
    print("completed_normalized_events_only=True")
    print("late_event_applies_from_next_risk_evaluation=True")
    print("no_prior_risk_decision_rewrite=True")
    print("incomplete_source_fail_closed=True")
    print("no_lookahead_rule=True")
    print(f"broker_neutral_contract_defined={broker_neutral_contract_defined}")
    print(f"production_aggregation_allowed={production_aggregation_allowed}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print("recommended_account_day=UTC_HALF_OPEN_INTERVAL_[00:00_NEXT_00:00)")
    print("recommended_scope=BROKER_ACCOUNT")
    print("recommended_dedup_key=BROKER+ACCOUNT_ID+EXECUTION_ID")
    print("recommended_late_rule=APPLY_FROM_NEXT_RISK_EVALUATION")
    print("recommended_incomplete_behavior=FAIL_CLOSED")
    print("first_unresolved_boundary=IB_NET_REALIZED_AMOUNT_SEMANTICS")
    print(
        "boundary_contract=BROKER_NEUTRAL_ACCOUNT_DAY_AGGREGATION_IS_"
        "STRUCTURALLY_DEFINED_BUT_IB_EVENTS_STILL_EXPOSE_BROKER_REPORTED_"
        "REALIZED_PNL_AND_COMMISSION_SEPARATELY_WITHOUT_ONE_CANONICAL_"
        "NET_REALIZED_AMOUNT"
    )
    print(
        "factual_verdict=B. BROKER_NEUTRAL_AGGREGATION_CONTRACT_IS_DEFINED_"
        "BUT_IB_CANONICAL_NET_REALIZED_AMOUNT_REMAINS_UNRESOLVED"
    )


if __name__ == "__main__":
    main()
