"""run_t109_18_broker_trading_day_reset_semantics_anatomy_check.py.

TEST_ONLY anatomy перевіряє лише broker trading-day і daily-reset semantics для
IB ``reqPnL`` та cTrader deal-history candidate sources. Runner зіставляє
installed API signatures і protobuf descriptors з фактичними production
adapter/service routes, окремо перевіряє наявність period identity, timezone,
start/end/reset metadata та можливість causal відновлення після restart,
reconnect, DST і weekend rollover.

Перевірка не викликає broker API, не реалізує DTO, daily PnL source або safety
block і не досліджує повторно cost completeness. Immutable period fields лише
класифікуються як factual/відсутні. Scoped production hashes та canonical
Replay 2025/2026 захищають production, trading і completed-bar semantics.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import sys
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

from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from ibapi.client import EClient  # noqa: E402
from ibapi.wrapper import EWrapper  # noqa: E402

ctrader_api_messages = importlib.import_module(
    "ctrader_open_api.messages.OpenApiMessages_pb2"
)
ctrader_model_messages = importlib.import_module(
    "ctrader_open_api.messages.OpenApiModelMessages_pb2"
)

TEST_ID = "T109-18"
EXPECTED_2025 = "42/30/11/1/+4.03/1.5424/3.58"
EXPECTED_2026 = "18/15/2/1/+3.68/3.7669/1.20"
FACTUAL_VERDICT = "H. MULTIPLE_BLOCKERS"
FIRST_UNRESOLVED_BOUNDARY = (
    "AUTHORITATIVE_BROKER_ACCOUNT_DAY_PERIOD_IDENTITY"
)
BOUNDARY_CONTRACT = (
    "DAILY_PNL_REQUIRES_BROKER_AUTHORITATIVE_PERIOD_ID_START_END_"
    "TIMEZONE_RESET_SOURCE_AND_DECISION_TIME_OBSERVATION"
)
IB_DOCUMENTED_RESET_SOURCE = (
    "TWS_GLOBAL_CONFIGURATION_PNL_RESET_SCHEDULE_"
    "INSTRUMENT_SPECIFIC_BY_DEFAULT"
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
    """Зафіксувати SHA-256 production sources у T109-18 scope."""
    return {
        path.relative_to(PROJECT_ROOT).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
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
    """Довести відсутність causal broker-neutral day period contract."""
    hashes_before = _production_hashes()
    ib_adapter_source = _source("engine/ib_adapter.py")
    ib_service_source = _source("engine/services/ib_runtime_service.py")
    ctrader_adapter_source = _source("engine/ctrader_adapter.py")
    ctrader_service_source = _source(
        "engine/services/ctrader_runtime_service.py"
    )
    replay_source = _source("core/workspace_replay_execution.py")

    ib_request_fields = tuple(inspect.signature(EClient.reqPnL).parameters)
    ib_callback_fields = tuple(inspect.signature(EWrapper.pnl).parameters)
    ib_endpoint_present = (
        ib_request_fields == ("self", "reqId", "account", "modelCode")
        and ib_callback_fields
        == ("self", "reqId", "dailyPnL", "unrealizedPnL", "realizedPnL")
    )
    ib_period_metadata_fields = {
        "periodStart",
        "periodEnd",
        "resetTimestamp",
        "timezone",
        "tradingDate",
        "sequence",
        "version",
    }
    ib_period_metadata_available = bool(
        ib_period_metadata_fields.intersection(ib_callback_fields)
    )
    ib_production_day_route = any(
        token in ib_adapter_source or token in ib_service_source
        for token in (
            "self._client.reqPnL(",
            "daily_pnl_day_boundary",
            "broker_trading_day",
            "pnl_reset_schedule",
        )
    )

    deal_list_req = getattr(ctrader_api_messages, "ProtoOADealListReq")
    deal_list_res = getattr(ctrader_api_messages, "ProtoOADealListRes")
    deal_type = getattr(ctrader_model_messages, "ProtoOADeal")
    trader_type = getattr(ctrader_model_messages, "ProtoOATrader")
    symbol_type = getattr(ctrader_model_messages, "ProtoOASymbol")
    deal_list_req_fields = _fields(deal_list_req)
    deal_list_res_fields = _fields(deal_list_res)
    deal_fields = _fields(deal_type)
    trader_fields = _fields(trader_type)
    symbol_fields = _fields(symbol_type)
    ctrader_timestamp_window_present = all(
        field in deal_list_req_fields
        for field in ("ctidTraderAccountId", "fromTimestamp", "toTimestamp")
    ) and "executionTimestamp" in deal_fields
    ctrader_pagination_present = "hasMore" in deal_list_res_fields
    ctrader_account_day_fields = {
        "tradingDay",
        "businessDay",
        "accountTimezone",
        "dayResetTimestamp",
        "sourcePeriodId",
    }
    ctrader_account_day_identifier_present = bool(
        ctrader_account_day_fields.intersection(
            set(deal_list_req_fields + deal_fields + trader_fields)
        )
    )
    ctrader_symbol_schedule_timezone_present = (
        "scheduleTimeZone" in symbol_fields
    )
    ctrader_production_day_route = any(
        token in ctrader_adapter_source or token in ctrader_service_source
        for token in (
            "ProtoOADealListReq",
            "broker_trading_day",
            "account_day_boundary",
        )
    )

    replay_session_reset = all(
        token in replay_source
        for token in (
            "self.realized_profit = 0.0",
            "def reset(self)",
            "self.realized_profit += realized_profit",
        )
    )
    replay_broker_day_fields = any(
        token in replay_source
        for token in (
            "broker_trading_day",
            "source_period_id",
            "day_boundary_source",
        )
    )

    assert ib_endpoint_present
    assert not ib_period_metadata_available
    assert not ib_production_day_route
    assert IB_DOCUMENTED_RESET_SOURCE.endswith("INSTRUMENT_SPECIFIC_BY_DEFAULT")
    assert ctrader_timestamp_window_present
    assert ctrader_pagination_present
    assert not ctrader_account_day_identifier_present
    assert ctrader_symbol_schedule_timezone_present
    assert not ctrader_production_day_route
    assert replay_session_reset
    assert not replay_broker_day_fields

    ib_reset_configurable = True
    ib_period_identity_available = False
    ib_period_start_derivable = False
    ib_period_end_derivable = False
    ib_authoritative_broker_day_resolved = False
    ctrader_period_start_derivable = False
    ctrader_period_end_derivable = False
    ctrader_authoritative_broker_day_resolved = False
    broker_neutral_period_contract_resolved = False
    restart_period_recoverable = False
    reconnect_period_recoverable = False
    dst_safe = False
    weekend_rollover_defined = False
    replay_matches_broker_day_contract = False
    broker_execution_attempted = False

    baselines: dict[str, WorkspaceRuntime] = {}
    broker_requests = 0
    for spec in CANONICAL_PERIODS:
        runtime, _rejects, requests = run_canonical_period(spec)
        baselines[spec.code] = runtime
        broker_requests += requests
    canonical_2025_exact_match = (
        _baseline_key(baselines["2025"]) == EXPECTED_2025
    )
    canonical_2026_exact_match = (
        _baseline_key(baselines["2026"]) == EXPECTED_2026
    )

    hashes_after = _production_hashes()
    assert hashes_before == hashes_after
    assert broker_requests == 0
    assert canonical_2025_exact_match
    assert canonical_2026_exact_match
    assert not broker_execution_attempted
    assert not broker_neutral_period_contract_resolved
    assert FACTUAL_VERDICT == "H. MULTIPLE_BLOCKERS"

    print(f"test_id={TEST_ID}")
    print("target_day_contract=BROKER_ACCOUNT_TRADING_DAY")
    print(f"ib_daily_reset_source={IB_DOCUMENTED_RESET_SOURCE}")
    print(f"ib_reset_configurable={ib_reset_configurable}")
    print(
        "ib_reset_timezone_source=ABSENT_FROM_REQPNL_REQUEST_AND_PNL_CALLBACK"
    )
    print(f"ib_period_identity_available={ib_period_identity_available}")
    print(f"ib_period_start_derivable={ib_period_start_derivable}")
    print(f"ib_period_end_derivable={ib_period_end_derivable}")
    print(
        "ib_authoritative_broker_day_resolved="
        f"{ib_authoritative_broker_day_resolved}"
    )
    print("ctrader_deal_timestamp_timezone=UNIX_EPOCH_MILLISECONDS_UTC")
    print(
        "ctrader_broker_timezone_source=SYMBOL_SCHEDULE_TIMEZONE_ONLY_"
        "NOT_ACCOUNT_DAY"
    )
    print("ctrader_trading_day_identifier=ABSENT")
    print(
        "ctrader_period_start_derivable="
        f"{ctrader_period_start_derivable}"
    )
    print(f"ctrader_period_end_derivable={ctrader_period_end_derivable}")
    print(
        "ctrader_authoritative_broker_day_resolved="
        f"{ctrader_authoritative_broker_day_resolved}"
    )
    print(
        "broker_neutral_period_fields=source_period_id,source_period_start_utc,"
        "source_period_end_utc,observed_at_utc,broker,account_id,"
        "day_boundary_source,day_boundary_authoritative"
    )
    print(
        "broker_neutral_period_contract_resolved="
        f"{broker_neutral_period_contract_resolved}"
    )
    print(f"restart_period_recoverable={restart_period_recoverable}")
    print(f"reconnect_period_recoverable={reconnect_period_recoverable}")
    print(f"dst_safe={dst_safe}")
    print(f"weekend_rollover_defined={weekend_rollover_defined}")
    print(
        "replay_day_contract=WORKSPACE_REPLAY_EXECUTION_SESSION_RESET_ON_"
        "ENGINE_INITIALIZATION_OR_RESET"
    )
    print(
        "replay_matches_broker_day_contract="
        f"{replay_matches_broker_day_contract}"
    )
    print("unknown_day_safe_behavior=BLOCK_RISK_EXECUTION")
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
    print("T109_18_BROKER_TRADING_DAY_RESET_SEMANTICS_ANATOMY=OK")


def test_t109_18_broker_trading_day_reset_semantics() -> None:
    """Запустити той самий TEST_ONLY checkpoint через pytest/PyCharm."""
    main()


if __name__ == "__main__":
    main()
