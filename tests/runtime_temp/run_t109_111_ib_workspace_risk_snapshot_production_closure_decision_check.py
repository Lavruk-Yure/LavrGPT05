"""run_t109_111_ib_workspace_risk_snapshot_production_closure_decision_check.py.

TEST_ONLY closure checkpoint зводить фактичний IB workspace risk pipeline після
T109-93..T109-110. Runner перевіряє production durable reads для daily PnL та
open-position count, shared reconciliation watermark, post-reconciliation
coverage/resync lifecycle, передачу snapshot timestamp у WorkspaceRuntime і
decision-time freshness у risk evaluator.

Окремі production risk requests підтверджують ALLOW лише для повного causal
snapshot та fail-closed для missing PnL, missing position count, missing,
future і stale timestamp. Runner не звертається до broker, не змінює schema,
production, Replay, thresholds чи settings і лише приймає closure decision.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from inspect import getfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import WORKSPACE_DATA_MODE_BROKER  # noqa: E402
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from engine.db.runtime_db import SCHEMA_VERSION  # noqa: E402
from engine.risk.constants import (  # noqa: E402
    RISK_REASON_ACCOUNT_SNAPSHOT_FUTURE,
    RISK_REASON_ACCOUNT_SNAPSHOT_STALE,
    RISK_REASON_ACCOUNT_SNAPSHOT_TIMESTAMP_MISSING,
    RISK_REASON_APPROVED,
    RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING,
    RISK_REASON_OPEN_POSITIONS_SNAPSHOT_MISSING,
)
from engine.risk.risk_model import (  # noqa: E402
    WorkspaceRiskEvaluator,
    WorkspaceRiskPolicy,
    WorkspaceRiskRequest,
)
from engine.runtime_constants import (  # noqa: E402
    RUNTIME_ACCOUNT_REFRESH_INTERVAL_SECONDS,
)

FIRST_UNRESOLVED_BOUNDARY = (
    "WORKSPACE_BROKER_EXECUTION_POST_RISK_END_TO_END_PRODUCTION_CHECK"
)
BOUNDARY_CONTRACT = (
    "IB_WORKSPACE_RISK_SNAPSHOT_PRODUCTION_IS_CLOSED_WITH_DURABLE_DAILY_PNL_"
    "EXACT_WORKSPACE_OPEN_POSITION_COUNT_ONE_SHARED_CAUSAL_WATERMARK_AND_"
    "DECISION_TIME_FRESHNESS_WHILE_POST_RISK_BROKER_EXECUTION_REMAINS_AN_"
    "INDEPENDENT_END_TO_END_BOUNDARY"
)
FACTUAL_VERDICT = (
    "A. IB_WORKSPACE_RISK_SNAPSHOT_PRODUCTION_CLOSURE_GREEN_WITH_NO_"
    "ADDITIONAL_PRODUCTION_CHANGE_AND_POST_RISK_BROKER_EXECUTION_LEFT_"
    "AS_THE_NEXT_INDEPENDENT_BOUNDARY"
)


def _read(relative_path: str) -> str:
    """Прочитати фактичний production source від кореня WorkspaceRuntime."""
    production_root = Path(getfile(WorkspaceRuntime)).resolve().parents[1]
    return (production_root / relative_path).read_text(encoding="utf-8")


def _request(
    *,
    decision_utc: datetime,
    snapshot_utc: datetime | None,
) -> WorkspaceRiskRequest:
    """Побудувати nominal complete IB risk request для closure assertions."""
    return WorkspaceRiskRequest(
        timestamp=decision_utc,
        workspace_uid="T109-111-WSP",
        broker="IB",
        account_id="DU109111",
        symbol="AAPL",
        side="BUY",
        source_mode=WORKSPACE_DATA_MODE_BROKER,
        requested_volume=1.0,
        equity=100_000.0,
        estimated_loss_at_stop=1_000.0,
        stop_loss=189.0,
        open_positions_count=0,
        daily_realized_pnl=0.0,
        runtime_ready=True,
        binding_verified=True,
        market_valid=True,
        spread_guard_passed=True,
        signal_uid="T109-111-SIGNAL",
        account_snapshot_utc=snapshot_utc,
    )


def main() -> None:
    """Перевірити production closure та надрукувати наступну межу."""
    controller_source = _read("core/algorithm_workspace_controller.py")
    lifecycle_source = _read("core/ib_reconciliation_lifecycle.py")
    main_source = _read("core/main_logic.py")
    workspace_runtime_source = _read("core/workspace_runtime.py")
    engine_source = _read("engine/runtime_engine.py")
    repository_source = _read("engine/runtime_repository.py")
    risk_source = _read("engine/risk/risk_model.py")

    durable_daily_pnl_route_closed = all(
        token in engine_source + controller_source
        for token in (
            "read_ib_daily_realized_pnl_snapshot",
            "daily_realized_pnl=daily_realized_pnl",
        )
    )
    durable_open_positions_route_closed = all(
        token in engine_source + repository_source + controller_source
        for token in (
            "read_ib_workspace_open_positions_count",
            "open_positions_count=open_positions_count",
        )
    )
    shared_causal_watermark_route_closed = all(
        token in repository_source + engine_source + controller_source
        for token in (
            "read_ib_risk_shared_durable_watermark",
            "ib_daily_realized_coverage_is_complete",
            "shared_watermark",
        )
    )
    post_reconciliation_lifecycle_closed = all(
        token in lifecycle_source + main_source
        for token in (
            "complete_ib_risk_sources_after_reconciliation",
            "recover_ib_daily_realized_events",
            "coverage_committed",
            "sync_broker_risk_account_snapshots",
        )
    )
    runtime_snapshot_timestamp_wired = all(
        token in workspace_runtime_source
        for token in (
            "account_snapshot_utc=(",
            "snapshot.snapshot_utc if snapshot is not None else None",
        )
    )
    decision_time_freshness_closed = all(
        token in risk_source
        for token in (
            'if request.source_mode == "BROKER":',
            "snapshot_age = request.timestamp - request.account_snapshot_utc",
            "RUNTIME_ACCOUNT_REFRESH_INTERVAL_SECONDS",
        )
    )

    evaluator = WorkspaceRiskEvaluator(
        WorkspaceRiskPolicy(
            max_risk_percent=2.0,
            maximum_position_volume=2.0,
            maximum_open_positions=2,
            max_daily_loss_percent=5.0,
            require_stop_loss=True,
        )
    )
    decision_utc = datetime(2026, 9, 23, 16, 0, tzinfo=UTC)
    max_age = timedelta(seconds=RUNTIME_ACCOUNT_REFRESH_INTERVAL_SECONDS)
    complete_request = _request(
        decision_utc=decision_utc,
        snapshot_utc=decision_utc,
    )

    complete_snapshot_allows_risk = (
        evaluator.evaluate(complete_request).reason_code == RISK_REASON_APPROVED
    )
    missing_daily_pnl_blocks = (
        evaluator.evaluate(
            replace(complete_request, daily_realized_pnl=None)
        ).reason_code
        == RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING
    )
    missing_open_positions_blocks = (
        evaluator.evaluate(
            replace(complete_request, open_positions_count=None)
        ).reason_code
        == RISK_REASON_OPEN_POSITIONS_SNAPSHOT_MISSING
    )
    missing_timestamp_blocks = (
        evaluator.evaluate(
            replace(complete_request, account_snapshot_utc=None)
        ).reason_code
        == RISK_REASON_ACCOUNT_SNAPSHOT_TIMESTAMP_MISSING
    )
    future_timestamp_blocks = (
        evaluator.evaluate(
            replace(
                complete_request,
                account_snapshot_utc=decision_utc + timedelta(microseconds=1),
            )
        ).reason_code
        == RISK_REASON_ACCOUNT_SNAPSHOT_FUTURE
    )
    stale_timestamp_blocks = (
        evaluator.evaluate(
            replace(
                complete_request,
                account_snapshot_utc=(
                    decision_utc - max_age - timedelta(microseconds=1)
                ),
            )
        ).reason_code
        == RISK_REASON_ACCOUNT_SNAPSHOT_STALE
    )

    schema_change_required = SCHEMA_VERSION != 12
    production_change_required = not all(
        (
            durable_daily_pnl_route_closed,
            durable_open_positions_route_closed,
            shared_causal_watermark_route_closed,
            post_reconciliation_lifecycle_closed,
            runtime_snapshot_timestamp_wired,
            decision_time_freshness_closed,
            complete_snapshot_allows_risk,
            missing_daily_pnl_blocks,
            missing_open_positions_blocks,
            missing_timestamp_blocks,
            future_timestamp_blocks,
            stale_timestamp_blocks,
        )
    )
    risk_snapshot_boundary_closed = not production_change_required
    broker_requests = 0

    assert durable_daily_pnl_route_closed
    assert durable_open_positions_route_closed
    assert shared_causal_watermark_route_closed
    assert post_reconciliation_lifecycle_closed
    assert runtime_snapshot_timestamp_wired
    assert decision_time_freshness_closed
    assert complete_snapshot_allows_risk
    assert missing_daily_pnl_blocks
    assert missing_open_positions_blocks
    assert missing_timestamp_blocks
    assert future_timestamp_blocks
    assert stale_timestamp_blocks
    assert not schema_change_required
    assert not production_change_required
    assert risk_snapshot_boundary_closed
    assert broker_requests == 0

    print("T109-111_IB_WORKSPACE_RISK_SNAPSHOT_PRODUCTION_CLOSURE=OK")
    print("test_scope_test_only=True")
    print("production_change=False")
    print(f"schema_version={SCHEMA_VERSION}")
    print(f"durable_daily_pnl_route_closed={durable_daily_pnl_route_closed}")
    print(
        "durable_open_positions_route_closed="
        f"{durable_open_positions_route_closed}"
    )
    print(
        "shared_causal_watermark_route_closed="
        f"{shared_causal_watermark_route_closed}"
    )
    print(
        "post_reconciliation_lifecycle_closed="
        f"{post_reconciliation_lifecycle_closed}"
    )
    print(f"runtime_snapshot_timestamp_wired={runtime_snapshot_timestamp_wired}")
    print(f"decision_time_freshness_closed={decision_time_freshness_closed}")
    print(f"complete_snapshot_allows_risk={complete_snapshot_allows_risk}")
    print(f"missing_daily_pnl_blocks={missing_daily_pnl_blocks}")
    print(f"missing_open_positions_blocks={missing_open_positions_blocks}")
    print(f"missing_timestamp_blocks={missing_timestamp_blocks}")
    print(f"future_timestamp_blocks={future_timestamp_blocks}")
    print(f"stale_timestamp_blocks={stale_timestamp_blocks}")
    print(f"schema_change_required={schema_change_required}")
    print(f"production_change_required={production_change_required}")
    print(f"risk_snapshot_boundary_closed={risk_snapshot_boundary_closed}")
    print(f"broker_requests={broker_requests}")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


def test_t109_111_ib_workspace_risk_snapshot_production_closure() -> None:
    """Запустити T109-111 як pytest test."""
    main()


if __name__ == "__main__":
    main()
