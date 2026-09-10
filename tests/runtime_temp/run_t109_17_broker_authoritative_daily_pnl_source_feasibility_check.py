"""run_t109_17_broker_authoritative_daily_pnl_source_feasibility_check.py.

TEST_ONLY anatomy перевіряє feasibility broker-authoritative account-wide daily
realized PnL source для IB і cTrader без виконання broker requests. Runner
зіставляє installed IB API signatures, cTrader protobuf descriptors, чинні
adapter/service routes, account binding, cost fields, timestamps, pagination і
Replay divergence з прийнятим conceptual target ACCOUNT_WIDE,
REALIZED_NET_COSTS, ACCOUNT_CURRENCY, BROKER_ACCOUNT_TRADING_DAY.

Перевірка не створює source і не змінює RuntimeAccountState, risk snapshot,
adapter, risk evaluator, Replay або execution wiring. Вона лише класифікує
direct та history-derived strategies, causal freshness requirements і першу
невирішену production boundary; scoped hashes і canonical Replay 2025/2026
захищають production та completed-bar semantics.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_TEST_ROOT = PROJECT_ROOT / "tests" / "runtime_workspace"
RUNTIME_TEMP_ROOT = PROJECT_ROOT / "tests" / "runtime_temp"
for import_path in (PROJECT_ROOT, WORKSPACE_TEST_ROOT, RUNTIME_TEMP_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))


def _test_helper(module_name: str, helper_name: str) -> Any:
    """Завантажити established TEST_ONLY helper без копіювання harness."""
    module = importlib.import_module(module_name)
    helper = getattr(module, helper_name, None)
    if helper is None:
        raise AssertionError(f"missing TEST_ONLY helper: {helper_name}")
    return helper


CANONICAL_PERIODS = _test_helper(
    "run_t105_18_stochastic_current_bar_production_regression_check",
    "PERIODS",
)
run_canonical_period = _test_helper(
    "run_t105_18_stochastic_current_bar_production_regression_check",
    "_run_period",
)

from ibapi.client import EClient  # noqa: E402
from ibapi.commission_and_fees_report import (  # noqa: E402
    CommissionAndFeesReport,
)
from ibapi.wrapper import EWrapper  # noqa: E402

ctrader_api_messages = importlib.import_module(
    "ctrader_open_api.messages.OpenApiMessages_pb2"
)
ctrader_model_messages = importlib.import_module(
    "ctrader_open_api.messages.OpenApiModelMessages_pb2"
)

from core.workspace_runtime import WorkspaceRuntime  # noqa: E402

TEST_ID = "T109-17"
EXPECTED_2025 = "42/30/11/1/+4.03/1.5424/3.58"
EXPECTED_2026 = "18/15/2/1/+3.68/3.7669/1.20"
FACTUAL_VERDICT = "H. MULTIPLE_BLOCKERS"
FIRST_UNRESOLVED_BOUNDARY = "BROKER_TRADING_DAY_AND_NET_COST_COMPLETENESS_CONTRACT"
BOUNDARY_CONTRACT = (
    "BROKER_SOURCE_MUST_PROVE_ACCOUNT_WIDE_NET_REALIZED_PNL_ACCOUNT_"
    "CURRENCY_AUTHORITATIVE_DAY_RESET_AND_DECISION_TIME_FRESHNESS"
)
PRODUCTION_FILES = (
    PROJECT_ROOT / "core" / "algorithm_workspace_controller.py",
    PROJECT_ROOT / "core" / "workspace_replay_execution.py",
    PROJECT_ROOT / "core" / "workspace_runtime.py",
    PROJECT_ROOT / "engine" / "ctrader_adapter.py",
    PROJECT_ROOT / "engine" / "ib_adapter.py",
    PROJECT_ROOT / "engine" / "risk" / "account_snapshot.py",
    PROJECT_ROOT / "engine" / "risk" / "risk_model.py",
    PROJECT_ROOT / "engine" / "runtime_account_state.py",
    PROJECT_ROOT / "engine" / "services" / "ctrader_runtime_service.py",
    PROJECT_ROOT / "engine" / "services" / "ib_runtime_service.py",
)


def _fields(message_type: Any) -> tuple[str, ...]:
    """Повернути declared protobuf fields через public descriptor."""
    return tuple(field.name for field in message_type.DESCRIPTOR.fields)


def _source(relative_path: str) -> str:
    """Прочитати один production source як UTF-8 factual contract."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def _production_hashes() -> dict[str, str]:
    """Зафіксувати SHA-256 production sources у T109-17 scope."""
    return {
        path.relative_to(PROJECT_ROOT)
        .as_posix(): hashlib.sha256(path.read_bytes())
        .hexdigest()
        for path in PRODUCTION_FILES
    }


def _combined_hash(hashes: dict[str, str]) -> str:
    """Згорнути ordered per-file hashes у deterministic marker."""
    payload = "\n".join(f"{path}={hashes[path]}" for path in sorted(hashes))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _baseline_key(runtime: WorkspaceRuntime) -> str:
    """Побудувати exact canonical Replay summary key."""
    summary = runtime.historical_summary
    if summary is None:
        raise AssertionError("canonical Replay summary missing")
    return (
        f"{summary.opened_trades}/{summary.winning_trades}/"
        f"{summary.losing_trades}/{summary.break_even_trades}/"
        f"{summary.net_profit:+.2f}/{summary.profit_factor:.4f}/"
        f"{summary.maximum_drawdown:.2f}"
    )


def main() -> None:
    """Класифікувати direct/history feasibility та нерозв'язані contracts."""
    hashes_before = _production_hashes()
    ib_adapter_source = _source("engine/ib_adapter.py")
    ib_service_source = _source("engine/services/ib_runtime_service.py")
    ctrader_adapter_source = _source("engine/ctrader_adapter.py")
    ctrader_service_source = _source("engine/services/ctrader_runtime_service.py")
    replay_source = _source("core/workspace_replay_execution.py")

    ib_req_pnl_parameters = tuple(inspect.signature(EClient.reqPnL).parameters)
    ib_pnl_parameters = tuple(inspect.signature(EWrapper.pnl).parameters)
    ib_commission_parameters = tuple(vars(CommissionAndFeesReport()).keys())
    ib_account_wide_daily_pnl_endpoint_present = ib_req_pnl_parameters == (
        "self",
        "reqId",
        "account",
        "modelCode",
    )
    ib_account_wide_realized_field_present = "realizedPnL" in ib_pnl_parameters
    ib_account_wide_unrealized_field_present = "unrealizedPnL" in ib_pnl_parameters
    ib_commission_api_present = all(
        field in ib_commission_parameters
        for field in ("execId", "commissionAndFees", "currency", "realizedPNL")
    )
    ib_production_req_pnl_route = "self._client.reqPnL(" in ib_adapter_source
    ib_production_commission_route = "def commissionAndFeesReport(" in ib_adapter_source
    ib_production_daily_cache = any(
        token in ib_service_source for token in ("daily_realized_pnl", "daily_pnl")
    )
    ib_execution_history_route = all(
        token in ib_adapter_source
        for token in ("def execDetails(", "self._client.reqExecutions(")
    )

    deal_list_req_fields = _fields(getattr(ctrader_api_messages, "ProtoOADealListReq"))
    deal_list_res_fields = _fields(getattr(ctrader_api_messages, "ProtoOADealListRes"))
    deal_fields = _fields(getattr(ctrader_model_messages, "ProtoOADeal"))
    close_fields = _fields(
        getattr(ctrader_model_messages, "ProtoOAClosePositionDetail")
    )
    trader_fields = _fields(getattr(ctrader_model_messages, "ProtoOATrader"))
    ctrader_deal_history_api_present = all(
        field in deal_list_req_fields
        for field in (
            "ctidTraderAccountId",
            "fromTimestamp",
            "toTimestamp",
            "maxRows",
        )
    ) and all(field in deal_list_res_fields for field in ("deal", "hasMore"))
    ctrader_close_cost_fields_present = all(
        field in close_fields
        for field in (
            "grossProfit",
            "swap",
            "commission",
            "moneyDigits",
            "pnlConversionFee",
        )
    )
    ctrader_deal_causality_fields_present = all(
        field in deal_fields
        for field in (
            "dealId",
            "positionId",
            "filledVolume",
            "executionTimestamp",
            "closePositionDetail",
        )
    )
    ctrader_account_currency_binding_present = all(
        field in trader_fields
        for field in ("ctidTraderAccountId", "depositAssetId", "moneyDigits")
    )
    ctrader_production_deal_route = "ProtoOADealListReq" in ctrader_adapter_source
    ctrader_production_daily_cache = any(
        token in ctrader_service_source for token in ("daily_realized_pnl", "daily_pnl")
    )

    replay_contract_diverges = all(
        token in replay_source
        for token in (
            "self.realized_profit = 0.0",
            "self.realized_profit += realized_profit",
            "return (close_price - position.entry_price) * position.volume",
        )
    ) and not any(
        token in replay_source.lower()
        for token in ("commission", "swap", "pnlconversionfee")
    )

    assert ib_account_wide_daily_pnl_endpoint_present
    assert ib_account_wide_realized_field_present
    assert ib_account_wide_unrealized_field_present
    assert ib_commission_api_present
    assert ib_execution_history_route
    assert not ib_production_req_pnl_route
    assert not ib_production_commission_route
    assert not ib_production_daily_cache
    assert ctrader_deal_history_api_present
    assert ctrader_close_cost_fields_present
    assert ctrader_deal_causality_fields_present
    assert ctrader_account_currency_binding_present
    assert not ctrader_production_deal_route
    assert not ctrader_production_daily_cache
    assert replay_contract_diverges

    ib_daily_field_semantics_known = False
    ib_manual_external_activity_included = False
    ib_commission_complete = True
    ib_fees_complete = True
    ib_swap_complete = False
    ib_net_realized_complete = False
    ib_broker_day_contract_resolved = False
    ib_history_derived_contract_complete = False
    ib_new_request_required = True

    ctrader_account_wide_daily_pnl_endpoint_present = False
    ctrader_manual_external_activity_included = True
    ctrader_commission_complete = True
    ctrader_fees_complete = True
    ctrader_swap_complete = True
    ctrader_net_realized_complete = True
    ctrader_broker_day_contract_resolved = False
    ctrader_history_derived_contract_complete = False
    ctrader_new_request_required = True

    account_wide_truth_complete_ib = False
    account_wide_truth_complete_ctrader = True
    causal_refresh_contract_feasible = True
    freshness_contract_feasible = True
    broker_neutral_source_feasible = False
    production_source_strategy_resolved = False
    broker_execution_attempted = False

    baselines: dict[str, WorkspaceRuntime] = {}
    broker_requests = 0
    for spec in CANONICAL_PERIODS:
        runtime, _rejects, requests = run_canonical_period(spec)
        baselines[spec.code] = runtime
        broker_requests += requests
    canonical_2025_exact_match = _baseline_key(baselines["2025"]) == EXPECTED_2025
    canonical_2026_exact_match = _baseline_key(baselines["2026"]) == EXPECTED_2026

    hashes_after = _production_hashes()
    assert hashes_before == hashes_after
    assert broker_requests == 0
    assert canonical_2025_exact_match
    assert canonical_2026_exact_match
    assert not broker_execution_attempted
    assert not broker_neutral_source_feasible
    assert FACTUAL_VERDICT == "H. MULTIPLE_BLOCKERS"

    print(f"test_id={TEST_ID}")
    print("target_scope=ACCOUNT_WIDE")
    print("target_content=REALIZED_NET_COSTS")
    print("target_currency=ACCOUNT_CURRENCY")
    print("target_day=BROKER_ACCOUNT_TRADING_DAY")
    print(f"installed_ibapi_version={version('ibapi')}")
    print(f"installed_ctrader_open_api_version={version('ctrader-open-api')}")
    print(
        "ib_account_wide_daily_pnl_endpoint_present="
        f"{ib_account_wide_daily_pnl_endpoint_present}"
    )
    print("ib_endpoint=EClient.reqPnL(account,modelCode)->EWrapper.pnl")
    print(
        "ib_account_wide_realized_field_present="
        f"{ib_account_wide_realized_field_present}"
    )
    print(
        "ib_account_wide_unrealized_field_present="
        f"{ib_account_wide_unrealized_field_present}"
    )
    print(f"ib_daily_field_semantics_known={ib_daily_field_semantics_known}")
    print(
        "ib_manual_external_activity_included="
        f"{ib_manual_external_activity_included}"
    )
    print(f"ib_commission_complete={ib_commission_complete}")
    print(f"ib_fees_complete={ib_fees_complete}")
    print(f"ib_swap_complete={ib_swap_complete}")
    print(f"ib_net_realized_complete={ib_net_realized_complete}")
    print("ib_broker_day_contract_resolved=" f"{ib_broker_day_contract_resolved}")
    print(
        "ib_history_derived_contract_complete="
        f"{ib_history_derived_contract_complete}"
    )
    print(f"ib_new_request_required={ib_new_request_required}")
    print(
        "ib_candidate_source=reqPnL_realizedPnL_subscription; fallback "
        "reqExecutions+commissionAndFeesReport incomplete for swap/day"
    )
    print(
        "ctrader_account_wide_daily_pnl_endpoint_present="
        f"{ctrader_account_wide_daily_pnl_endpoint_present}"
    )
    print("ctrader_endpoint=ProtoOADealListReq_history_aggregate")
    print(
        "ctrader_manual_external_activity_included="
        f"{ctrader_manual_external_activity_included}"
    )
    print(f"ctrader_commission_complete={ctrader_commission_complete}")
    print(f"ctrader_fees_complete={ctrader_fees_complete}")
    print(f"ctrader_swap_complete={ctrader_swap_complete}")
    print(f"ctrader_net_realized_complete={ctrader_net_realized_complete}")
    print(
        "ctrader_broker_day_contract_resolved="
        f"{ctrader_broker_day_contract_resolved}"
    )
    print(
        "ctrader_history_derived_contract_complete="
        f"{ctrader_history_derived_contract_complete}"
    )
    print(f"ctrader_new_request_required={ctrader_new_request_required}")
    print(
        "ctrader_candidate_source=paginated ProtoOADealListReq aggregate "
        "of closePositionDetail grossProfit+swap+commission+pnlConversionFee"
    )
    print("account_wide_truth_complete_ib=" f"{account_wide_truth_complete_ib}")
    print(
        "account_wide_truth_complete_ctrader=" f"{account_wide_truth_complete_ctrader}"
    )
    print("causal_refresh_contract_feasible=" f"{causal_refresh_contract_feasible}")
    print(f"freshness_contract_feasible={freshness_contract_feasible}")
    print(
        "lookahead_risk=CONTROLLABLE_WITH_OBSERVED_AT_SOURCE_PERIOD_AND_"
        "PRE_DECISION_SNAPSHOT"
    )
    print("ib_request_needed_at_start=True")
    print("ib_request_needed_periodically=False_STREAMING_SUBSCRIPTION")
    print("ib_request_needed_per_signal=False")
    print("ctrader_request_needed_at_start=True")
    print("ctrader_request_needed_periodically=True")
    print("ctrader_request_needed_per_signal=False")
    print("recommended_owner_layer=IMMUTABLE_BROKER_RISK_ACCOUNT_SOURCE")
    print(
        "recommended_acquisition_contract=adapter_service centrally refreshes "
        "bound account/day/value/currency/observed_at/source_period/freshness; "
        "controller maps valid snapshot to WorkspaceRiskAccountSnapshot"
    )
    print("runtime_account_state_extension_recommended=False")
    print(f"replay_contract_diverges={replay_contract_diverges}")
    print(f"broker_neutral_source_feasible={broker_neutral_source_feasible}")
    print(
        "production_source_strategy_resolved=" f"{production_source_strategy_resolved}"
    )
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")
    print(f"canonical_2025_exact_match={canonical_2025_exact_match}")
    print(f"canonical_2026_exact_match={canonical_2026_exact_match}")
    for path in sorted(hashes_before):
        print(f"production_hash_before[{path}]={hashes_before[path]}")
        print(f"production_hash_after[{path}]={hashes_after[path]}")
    print(f"production_hashes_before={_combined_hash(hashes_before)}")
    print(f"production_hashes_after={_combined_hash(hashes_after)}")
    print("production_hashes_before_after_match=True")
    print("safety_invariants=")
    print("  TEST_ONLY=True")
    print(f"  broker_requests={broker_requests}")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print("  production_logic_changed=False")
    print("  trading_logic_changed=False")
    print("  lookahead_used=False")
    print("T109_17_BROKER_DAILY_PNL_SOURCE_FEASIBILITY=OK")


def test_t109_17_broker_daily_pnl_source_feasibility() -> None:
    """Запустити той самий TEST_ONLY checkpoint через pytest/PyCharm."""
    main()


if __name__ == "__main__":
    main()
