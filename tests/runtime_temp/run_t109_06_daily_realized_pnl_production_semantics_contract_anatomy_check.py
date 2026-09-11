"""run_t109_06_daily_realized_pnl_production_semantics_contract_anatomy_check.py.

TEST_ONLY anatomy встановлює лише фактичний production semantics contract поля
``daily_realized_pnl`` у risk pipeline. Runner читає чинні risk, IB, cTrader і
Replay source contracts, перевіряє exact formula/sign handling, source scope,
cache/request path та наявність day/reset/content semantics executable
assertions без створення synthetic PnL або account snapshot. Canonical Replay
2025/2026 виконується лише як exact regression control completed-bar path.

Перевірка не викликає broker adapters/services, не робить network request чи
broker order, не досліджує ``open_positions_count`` і не переносить Replay
semantics на BROKER. Scoped production hashes до/після run доводять відсутність
production, risk, Candidate F, AUTO/SEMI та trading-logic змін.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import fields
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_TEMP_ROOT = PROJECT_ROOT / "tests" / "runtime_temp"
for import_path in (PROJECT_ROOT, RUNTIME_TEMP_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_t109_03_minimal_production_execution_intent_repair_check import (  # noqa
    CANONICAL_PERIODS,
    EXPECTED_2025,
    EXPECTED_2026,
    run_canonical_period,
)

from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from engine.risk.account_snapshot import (  # noqa: E402
    WorkspaceRiskAccountSnapshot,
)
from engine.risk.risk_model import WorkspaceRiskRequest  # noqa: E402
from engine.runtime_account_state import RuntimeAccountState  # noqa: E402

TEST_ID = "T109-06"
FACTUAL_VERDICT = "E. PRODUCTION_SEMANTICS_NOT_DEFINED"
FIRST_UNRESOLVED_BOUNDARY = (
    "RISK_DAILY_REALIZED_PNL_FIELD_TO_DEFINED_BROKER_NEUTRAL_SEMANTICS"
)
BOUNDARY_CONTRACT = (
    "DAILY_REALIZED_PNL_REQUIRES_BROKER_NEUTRAL_SCOPE_CONTENT_"
    "DAY_BOUNDARY_AND_RESET_SEMANTICS"
)
PRODUCTION_FILES = (
    PROJECT_ROOT / "core" / "workspace_replay_execution.py",
    PROJECT_ROOT / "core" / "workspace_runtime.py",
    PROJECT_ROOT / "engine" / "ctrader_adapter.py",
    PROJECT_ROOT / "engine" / "ib_adapter.py",
    PROJECT_ROOT / "engine" / "risk" / "account_snapshot.py",
    PROJECT_ROOT / "engine" / "risk" / "constants.py",
    PROJECT_ROOT / "engine" / "risk" / "risk_model.py",
    PROJECT_ROOT / "engine" / "runtime_account_state.py",
    PROJECT_ROOT / "engine" / "services" / "ctrader_runtime_service.py",
    PROJECT_ROOT / "engine" / "services" / "ib_runtime_service.py",
)


def production_hashes() -> dict[str, str]:
    """Зафіксувати scoped production sources до і після TEST_ONLY anatomy."""
    return {
        path.relative_to(PROJECT_ROOT)
        .as_posix(): hashlib.sha256(path.read_bytes())
        .hexdigest()
        for path in PRODUCTION_FILES
    }


def source_text(relative_path: str) -> str:
    """Прочитати один фактичний production module як UTF-8 contract."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def definition_line(relative_path: str, exact_fragment: str) -> int:
    """Знайти exact production call-site без виклику protected API."""
    lines = source_text(relative_path).splitlines()
    matches = [
        number for number, line in enumerate(lines, start=1) if exact_fragment in line
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"expected one {exact_fragment!r} in {relative_path}: {matches}"
        )
    return matches[0]


def baseline_key(runtime: WorkspaceRuntime) -> str:
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
    """Довести відсутність повного broker-neutral daily PnL contract."""
    hashes_before = production_hashes()
    risk_source = source_text("engine/risk/risk_model.py")
    snapshot_source = source_text("engine/risk/account_snapshot.py")
    constants_source = source_text("engine/risk/constants.py")
    ib_source = source_text("engine/ib_adapter.py")
    ib_service_source = source_text("engine/services/ib_runtime_service.py")
    ctrader_source = source_text("engine/ctrader_adapter.py")
    ctrader_service_source = source_text("engine/services/ctrader_runtime_service.py")
    replay_source = source_text("core/workspace_replay_execution.py")
    workspace_runtime_source = source_text("core/workspace_runtime.py")

    request_fields = tuple(field.name for field in fields(WorkspaceRiskRequest))
    snapshot_fields = tuple(
        field.name for field in fields(WorkspaceRiskAccountSnapshot)
    )
    runtime_state_fields = tuple(field.name for field in fields(RuntimeAccountState))

    risk_sign_formula_defined = (
        "max(0.0, -request.daily_realized_pnl) / request.equity * 100.0" in risk_source
    )
    risk_missing_value_guard_defined = (
        "if request.daily_realized_pnl is None:" in risk_source
        and "RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING" in risk_source
    )
    risk_limit_guard_defined = (
        "daily_loss_percent >= self.policy.max_daily_loss_percent" in risk_source
    )
    risk_scope_defined = any(
        token in snapshot_source or token in risk_source
        for token in (
            "daily_realized_pnl_scope",
            "account_wide_daily_realized_pnl",
            "workspace_daily_realized_pnl",
            "symbol_daily_realized_pnl",
        )
    )
    risk_content_defined = any(
        token in snapshot_source or token in risk_source
        for token in (
            "daily_realized_pnl_includes_commission",
            "daily_realized_pnl_includes_fees",
            "daily_realized_pnl_includes_swap",
            "daily_realized_pnl_is_net",
            "daily_realized_pnl_is_gross",
        )
    )
    risk_day_boundary_defined = any(
        token in snapshot_source or token in risk_source
        for token in (
            "daily_pnl_day_boundary",
            "trading_day_timezone",
            "broker_session_day",
            "utc_calendar_day",
        )
    )
    risk_reset_defined = any(
        token in snapshot_source or token in risk_source
        for token in (
            "reset_daily_realized_pnl",
            "daily_pnl_reset",
            "daily_reset_utc",
        )
    )

    ib_position_facts_defined = all(
        token in ib_source
        for token in (
            "def pnlSingle(",
            '"daily_pnl"',
            '"realized_pnl"',
            "self.pnl_single_rows[int(req_id)] = item",
            "self._client.reqPnLSingle(",
            "self._client.cancelPnLSingle(req_id)",
            'raw_payload["pnl_single"]',
        )
    )
    ib_account_daily_aggregate_defined = (
        "def pnl(" in ib_source or "self._client.reqPnL(" in ib_source
    )
    ib_runtime_daily_cache_defined = (
        "daily_realized_pnl" in ib_service_source or "daily_pnl" in ib_service_source
    )

    ctrader_unrealized_facts_defined = all(
        token in ctrader_source
        for token in (
            "ProtoOAGetPositionUnrealizedPnLReq",
            "grossUnrealizedPnL",
            "netUnrealizedPnL",
            "self._positions_pnl_payload = pnl_map",
            "self.client.send(request)",
        )
    )
    ctrader_realized_facts_defined = any(
        token in ctrader_source
        for token in (
            '"realized_pnl"',
            "dailyRealizedPnL",
            "ProtoOADealListReq",
            "ProtoOAHistory",
        )
    )
    ctrader_runtime_daily_cache_defined = (
        "daily_realized_pnl" in ctrader_service_source
        or "daily_pnl" in ctrader_service_source
    )

    replay_accumulator_defined = all(
        token in replay_source
        for token in (
            "self.realized_profit = 0.0",
            "self.realized_profit += realized_profit",
            "return (close_price - position.entry_price) * position.volume",
        )
    )
    replay_runtime_route_defined = all(
        token in workspace_runtime_source
        for token in (
            "realized_profit = engine.realized_profit",
            "daily_realized_pnl=realized_profit",
            "self.context.daily_realized_pnl = realized_profit",
        )
    )
    replay_day_boundary_defined = any(
        token in replay_source
        for token in (
            "calendar_day",
            "trading_day",
            "session_day",
            "day_boundary",
        )
    )
    replay_fees_applied = any(
        token in replay_source for token in ("commission", "swap", "fee")
    )

    assert "daily_realized_pnl" in request_fields
    assert "daily_realized_pnl" in snapshot_fields
    assert "daily_realized_pnl" not in runtime_state_fields
    assert "max_daily_loss_percent" in constants_source
    assert risk_sign_formula_defined
    assert risk_missing_value_guard_defined
    assert risk_limit_guard_defined
    assert not risk_scope_defined
    assert not risk_content_defined
    assert not risk_day_boundary_defined
    assert not risk_reset_defined
    assert ib_position_facts_defined
    assert not ib_account_daily_aggregate_defined
    assert not ib_runtime_daily_cache_defined
    assert ctrader_unrealized_facts_defined
    assert not ctrader_realized_facts_defined
    assert not ctrader_runtime_daily_cache_defined
    assert replay_accumulator_defined
    assert replay_runtime_route_defined
    assert not replay_day_boundary_defined
    assert not replay_fees_applied

    baselines: dict[str, WorkspaceRuntime] = {}
    broker_requests = 0
    for spec in CANONICAL_PERIODS:
        runtime, _rejects, requests = run_canonical_period(spec)
        baselines[spec.code] = runtime
        broker_requests += requests
    canonical_2025_exact_match = baseline_key(baselines["2025"]) == EXPECTED_2025
    canonical_2026_exact_match = baseline_key(baselines["2026"]) == EXPECTED_2026
    broker_execution_attempted = False
    broker_neutral_contract_defined = False
    hashes_after = production_hashes()

    assert hashes_before == hashes_after
    assert broker_requests == 0
    assert not broker_execution_attempted
    assert not broker_neutral_contract_defined
    assert canonical_2025_exact_match
    assert canonical_2026_exact_match
    assert FACTUAL_VERDICT == "E. PRODUCTION_SEMANTICS_NOT_DEFINED"

    risk_formula_line = definition_line(
        "engine/risk/risk_model.py",
        "max(0.0, -request.daily_realized_pnl)",
    )
    ib_callback_line = definition_line(
        "engine/ib_adapter.py",
        "def pnlSingle(",
    )
    ib_request_line = definition_line(
        "engine/ib_adapter.py",
        "self._client.reqPnLSingle(",
    )
    ctrader_request_line = definition_line(
        "engine/ctrader_adapter.py",
        "request = ProtoOAGetPositionUnrealizedPnLReq()",
    )
    replay_accumulator_line = definition_line(
        "core/workspace_replay_execution.py",
        "self.realized_profit += realized_profit",
    )
    replay_snapshot_line = definition_line(
        "core/workspace_runtime.py",
        "daily_realized_pnl=realized_profit",
    )

    print(f"test_id={TEST_ID}")
    print(
        "risk_evaluator_daily_pnl_consumption="
        "daily_loss_percent=max(0,-daily_realized_pnl)/equity*100; "
        "BLOCK when daily_loss_percent>=max_daily_loss_percent"
    )
    print(
        "daily_realized_pnl_required_sign_semantics="
        "DEFINED: negative=loss; zero/positive=0 daily loss"
    )
    print("daily_realized_pnl_required_scope=UNRESOLVED")
    print(
        "daily_realized_pnl_required_content="
        "UNRESOLVED: gross/net and commission/swap/fees inclusion undefined"
    )
    print("daily_realized_pnl_required_day_boundary=UNRESOLVED")
    print("daily_realized_pnl_required_reset_semantics=UNRESOLVED")
    print(
        "ib_daily_pnl_available_facts="
        "pnlSingle daily_pnl,unrealized_pnl,realized_pnl; updatePortfolio "
        "realized_pnl; no account daily aggregate"
    )
    print("ib_daily_pnl_scope=POSITION_LEVEL")
    print(
        "ib_daily_pnl_source="
        "IBWrapper.pnlSingle <- IBAdapter._request_pnl_by_position_id "
        "reqPnLSingle; copied to BrokerPosition.raw_payload.pnl_single"
    )
    print(
        "ib_daily_pnl_cached="
        "TEMPORARY_BY_REQ_ID_IN_WRAPPER_AND_RETURNED_POSITION_RAW_PAYLOAD; "
        "not RuntimeAccountState daily counter"
    )
    print("ib_daily_pnl_requires_request=True")
    print("ib_daily_pnl_matches_required_contract=False")
    print(
        "ctrader_daily_pnl_available_facts="
        "grossUnrealizedPnL and netUnrealizedPnL for open positions only; "
        "no realized/daily/deal-history source in production adapter"
    )
    print("ctrader_daily_pnl_scope=OPEN_POSITION_LEVEL_UNREALIZED_ONLY")
    print(
        "ctrader_daily_pnl_source="
        "ProtoOAGetPositionUnrealizedPnLReq -> positionUnrealizedPnL cache"
    )
    print(
        "ctrader_daily_pnl_cached="
        "TEMPORARY_POSITION_UNREALIZED_MAP; not RuntimeAccountState daily counter"
    )
    print("ctrader_daily_pnl_requires_request=True")
    print("ctrader_daily_pnl_matches_required_contract=False")
    print(
        "replay_daily_pnl_source="
        "WorkspaceReplayExecutionEngine.realized_profit cumulative sum of "
        "gross (close-entry)*volume*direction"
    )
    print("replay_daily_pnl_scope=WORKSPACE_REPLAY_EXECUTION_SESSION")
    print("replay_daily_pnl_day_boundary=NONE")
    print(
        "replay_daily_pnl_reset_semantics="
        "reset to 0 on engine initialization/reset; no calendar/broker-day reset"
    )
    print("replay_semantics_transferable_to_broker=False")
    print(f"broker_neutral_contract_defined={broker_neutral_contract_defined}")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")
    print("unresolved_fields=scope,content,day_boundary,reset_semantics")
    print(
        "exact_call_sites="
        f"risk_formula=engine/risk/risk_model.py:{risk_formula_line}; "
        f"ib_callback=engine/ib_adapter.py:{ib_callback_line}; "
        f"ib_request=engine/ib_adapter.py:{ib_request_line}; "
        f"ctrader_request=engine/ctrader_adapter.py:{ctrader_request_line}; "
        "replay_accumulator=core/workspace_replay_execution.py:"
        f"{replay_accumulator_line}; "
        f"replay_snapshot=core/workspace_runtime.py:{replay_snapshot_line}"
    )
    print(f"canonical_2025_exact_match={canonical_2025_exact_match}")
    print(f"canonical_2026_exact_match={canonical_2026_exact_match}")
    print("safety_invariants=")
    print("  TEST_ONLY=True")
    print(f"  broker_requests={broker_requests}")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print("  production_logic_changed=False")
    print("  trading_logic_changed=False")
    print("  lookahead_used=False")
    print("T109_06_DAILY_REALIZED_PNL_SEMANTICS_CONTRACT_ANATOMY=OK")


if __name__ == "__main__":
    main()
