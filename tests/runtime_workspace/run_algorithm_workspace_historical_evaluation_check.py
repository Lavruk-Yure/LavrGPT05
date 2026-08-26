# -*- coding: utf-8 -*-
"""Перевірка великого Historical Replay та гіпотетичного PnL."""

from __future__ import annotations

import math
import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_MANUAL,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_alligator import (  # noqa: E402
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_broker_market import (  # noqa: E402
    WorkspaceBrokerMarketProviderProtocol,
)
from core.workspace_historical_evaluation import (  # noqa: E402
    WorkspaceHistoricalEvaluationError,
    WorkspaceHistoricalEvaluationPolicy,
    WorkspaceHistoricalEvaluationReport,
    WorkspaceHistoricalVariantEvaluation,
    build_workspace_historical_evaluation,
)
from core.workspace_history import WorkspaceHistoryReport  # noqa: E402
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay import (  # noqa: E402
    REPLAY_SPEED_MAX,
    WorkspaceReplaySession,
)
from core.workspace_runtime import (  # noqa: E402
    MAX_WORKSPACE_SIGNAL_RECORDS,
    WorkspaceRuntime,
)
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402
from core.workspace_signal_statistics import (  # noqa: E402
    WorkspaceSignalComparisonReport,
    WorkspaceSignalQualityPolicy,
    build_workspace_signal_comparison,
)
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1,
    WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2,
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WORKSPACE_REPLAY_SOURCE_CSV,
)

HISTORY_FILE = (
    PROJECT_ROOT
    / "data"
    / "history"
    / "IB"
    / "EURUSD"
    / "M15"
    / "2026-01-02_2026-07-27_IB_EURUSD_M15.csv"
)
REPLAY_SPEEDS = (10, 100, 1000, REPLAY_SPEED_MAX)


class BrokerRequestProbe(WorkspaceBrokerMarketProviderProtocol):
    def __init__(self) -> None:
        self.requests = 0

    def start_workspace(
        self,
        *,
        workspace_uid: str,
        broker: str,
        account_id: str | None,
        symbol: str,
        timeframe: str,
        warmup_bars: int,
        spread_limit: float,
    ) -> tuple[WorkspaceMarketEvent, ...]:
        _ = (
            workspace_uid,
            broker,
            account_id,
            symbol,
            timeframe,
            warmup_bars,
            spread_limit,
        )
        self.requests += 1
        return ()

    def poll_workspace(
        self,
        workspace_uid: str,
    ) -> WorkspaceMarketEvent | None:
        _ = workspace_uid
        self.requests += 1
        return None

    def is_workspace_broker_connected(self, workspace_uid: str) -> bool:
        _ = workspace_uid
        self.requests += 1
        return True

    def suspend_workspace(self, workspace_uid: str) -> None:
        _ = workspace_uid
        self.requests += 1

    def resume_workspace(
        self,
        workspace_uid: str,
    ) -> tuple[WorkspaceMarketEvent, ...]:
        _ = workspace_uid
        self.requests += 1
        return ()

    def stop_workspace(self, workspace_uid: str) -> None:
        _ = workspace_uid
        self.requests += 1


def _workspace(mode: str, speed: int) -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_MANUAL,
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "LINEAR",
            "alligator_filter_enabled": True,
            "alligator_confirmation": mode,
            "warmup_bars": 2,
            "spread_limit": 0.00020,
        },
        replay_settings={
            "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
            "file_path": str(HISTORY_FILE),
            "source_timezone": "UTC",
            "delimiter": ",",
            "decimal_separator": ".",
            "spread": 0.00012,
            "speed": speed,
        },
    )


def _run(
    workspace: AlgorithmWorkspace,
    speed: int,
) -> tuple[
    tuple[WorkspaceSignalRecord, ...],
    WorkspaceReplaySession,
    int,
    int,
]:
    replay_settings = dict(workspace.replay_settings)
    replay_settings["speed"] = speed
    run_workspace = replace(workspace, replay_settings=replay_settings)
    algorithm = WorkspaceMacdAlligatorReplayAlgorithm(run_workspace.algorithm)
    broker_probe = BrokerRequestProbe()
    complete_records: list[WorkspaceSignalRecord] = []
    runtime = WorkspaceRuntime(
        run_workspace,
        algorithm_factory=lambda _algorithm_id: algorithm,
        broker_market_provider=broker_probe,
        signal_record_observer=complete_records.append,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()
    assert session.history_report is not None
    visible_records = runtime.signal_records()
    assert visible_records == tuple(complete_records[-MAX_WORKSPACE_SIGNAL_RECORDS:])
    return (
        tuple(complete_records),
        session,
        len(visible_records),
        broker_probe.requests,
    )


def _records_by_mode() -> tuple[
    tuple[tuple[WorkspaceSignalRecord, ...], ...],
    tuple[WorkspaceMarketEvent, ...],
    int,
    int,
    WorkspaceHistoryReport,
]:
    variants: list[tuple[WorkspaceSignalRecord, ...]] = []
    canonical_events: tuple[WorkspaceMarketEvent, ...] | None = None
    canonical_history_report: WorkspaceHistoryReport | None = None
    broker_requests = 0
    ui_signal_records = 0
    for mode in (
        WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
        WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1,
        WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2,
    ):
        canonical_records: tuple[WorkspaceSignalRecord, ...] | None = None
        workspace = _workspace(mode, REPLAY_SPEEDS[0])
        for speed in REPLAY_SPEEDS:
            records, session, ui_records, requests = _run(workspace, speed)
            assert session.history_report is not None
            assert session.history_report.accepted_rows == 13926
            assert session.history_report.derived_quotes == 13926
            if canonical_history_report is None:
                canonical_history_report = session.history_report
            else:
                assert session.history_report == canonical_history_report
            if canonical_events is None:
                canonical_events = session.events
            else:
                assert session.events == canonical_events
            if canonical_records is None:
                canonical_records = records
            else:
                assert records == canonical_records
            ui_signal_records = ui_records
            broker_requests += requests
        assert canonical_records is not None
        variants.append(canonical_records)
    assert canonical_events is not None
    assert canonical_history_report is not None
    return (
        tuple(variants),
        canonical_events,
        ui_signal_records,
        broker_requests,
        canonical_history_report,
    )


def _assert_trade_contract(
    report: WorkspaceHistoricalEvaluationReport,
    events: tuple[WorkspaceMarketEvent, ...],
) -> None:
    event_index = {event.timestamp: index for index, event in enumerate(events)}
    for variant in report.variants:
        assert variant.allowed == (
            variant.evaluated_trades + variant.skipped_incomplete_horizon
        )
        assert variant.signals == variant.allowed + variant.rejected
        assert (
            variant.winning_trades + variant.losing_trades + variant.break_even_trades
            == variant.evaluated_trades
        )
        assert variant.maximum_drawdown >= 0.0
        for trade in variant.trades:
            signal_index = event_index[trade.signal_timestamp]
            assert event_index[trade.entry_timestamp] == signal_index + 1
            assert (
                event_index[trade.exit_timestamp]
                == signal_index + report.policy.horizon_bars
            )
            expected_net = (
                trade.gross_profit
                - trade.spread_cost
                - trade.commission_cost
                - trade.slippage_cost
            )
            assert math.isclose(
                trade.net_profit,
                expected_net,
                rel_tol=0.0,
                abs_tol=1e-9,
            )


def _assert_input_guards(
    variants: tuple[tuple[WorkspaceSignalRecord, ...], ...],
    events: tuple[WorkspaceMarketEvent, ...],
    policy: WorkspaceHistoricalEvaluationPolicy,
) -> None:
    duplicate_uid_blocked = False
    try:
        build_workspace_historical_evaluation(
            (variants[0] + (variants[0][0],),),
            events,
            policy,
        )
    except WorkspaceHistoricalEvaluationError:
        duplicate_uid_blocked = True
    assert duplicate_uid_blocked

    duplicate_variant_blocked = False
    try:
        build_workspace_historical_evaluation(
            (variants[0], variants[0]),
            events,
            policy,
        )
    except WorkspaceHistoricalEvaluationError:
        duplicate_variant_blocked = True
    assert duplicate_variant_blocked

    foreign_binding_blocked = False
    foreign_record = replace(variants[0][0], symbol="GBPUSD")
    try:
        build_workspace_historical_evaluation(
            ((foreign_record,) + variants[0][1:],),
            events,
            policy,
        )
    except WorkspaceHistoricalEvaluationError:
        foreign_binding_blocked = True
    assert foreign_binding_blocked

    currency_mismatch_blocked = False
    try:
        build_workspace_historical_evaluation(
            (variants[0],),
            events,
            replace(policy, pnl_currency="EUR"),
        )
    except WorkspaceHistoricalEvaluationError:
        currency_mismatch_blocked = True
    assert currency_mismatch_blocked


def main() -> None:
    (
        record_variants,
        events,
        ui_records,
        broker_requests,
        history_report,
    ) = _records_by_mode()
    assert all(len(records) == 1072 for records in record_variants)
    assert ui_records == MAX_WORKSPACE_SIGNAL_RECORDS
    assert len(record_variants[0]) > ui_records

    quality_report: WorkspaceSignalComparisonReport = build_workspace_signal_comparison(
        record_variants,
        events,
        WorkspaceSignalQualityPolicy(
            horizon_bars=8,
            minimum_directional_move=0.00020,
        ),
    )
    policy = WorkspaceHistoricalEvaluationPolicy(
        horizon_bars=8,
        fixed_volume=1000.0,
        pnl_currency="USD",
        commission_per_trade=0.0,
        slippage_per_side=0.0,
    )
    report: WorkspaceHistoricalEvaluationReport = build_workspace_historical_evaluation(
        record_variants,
        events,
        policy,
    )
    repeat = build_workspace_historical_evaluation(
        record_variants,
        events,
        policy,
    )
    assert report == repeat
    assert report.historical_bars == 13926
    assert report.proposal_signatures_identical
    assert quality_report.proposal_signatures_identical
    assert report.deterministic
    assert report.broker_requests == 0
    assert not report.broker_execution_attempted
    assert broker_requests == 0
    _assert_trade_contract(report, events)
    _assert_input_guards(record_variants, events, policy)

    evaluations: tuple[WorkspaceHistoricalVariantEvaluation, ...] = report.variants
    quality_by_mode = {item.mode: item for item in quality_report.variants}
    print("Algorithm Workspace Historical Evaluation result")
    print(f"  history_file={HISTORY_FILE.name}")
    print(f"  historical_bars={report.historical_bars}")
    print(f"  history_gap_count={history_report.gap_count}")
    print(f"  history_derived_quotes={history_report.derived_quotes}")
    print(
        "  history_period="
        f"{history_report.first_timestamp.isoformat()}.."
        f"{history_report.last_timestamp.isoformat()}"
    )
    print("  history_spread_model=CONSTANT_REPLAY_SETTING")
    print("  history_assumed_spread=0.00012")
    print(f"  policy_horizon_bars={report.policy.horizon_bars}")
    print("  policy_entry=NEXT_BAR_OPEN")
    print(f"  policy_exit=BAR_{report.policy.horizon_bars}_CLOSE")
    print(f"  policy_fixed_volume={report.policy.fixed_volume:.2f}")
    print(f"  policy_pnl_currency={report.policy.pnl_currency}")
    print("  policy_commission_per_trade=" f"{report.policy.commission_per_trade:.2f}")
    print("  policy_slippage_per_side=" f"{report.policy.slippage_per_side:.5f}")
    print(f"  complete_signal_records={len(record_variants[0])}")
    print(f"  ui_signal_record_limit={ui_records}")
    for item in evaluations:
        quality = quality_by_mode[item.mode]
        print(
            f"  {item.mode}: signals={item.signals}, "
            f"allow={item.allowed}, reject={item.rejected}, "
            f"trades={item.evaluated_trades}, "
            f"wins={item.winning_trades}, "
            f"losses={item.losing_trades}, "
            f"break_even={item.break_even_trades}, "
            f"skipped={item.skipped_incomplete_horizon}, "
            f"gross_{item.pnl_currency.lower()}={item.gross_profit:.2f}, "
            f"spread_{item.pnl_currency.lower()}={item.spread_cost:.2f}, "
            f"commission_{item.pnl_currency.lower()}="
            f"{item.commission_cost:.2f}, "
            f"slippage_{item.pnl_currency.lower()}="
            f"{item.slippage_cost:.2f}, "
            f"net_{item.pnl_currency.lower()}={item.net_profit:.2f}, "
            f"max_drawdown_{item.pnl_currency.lower()}="
            f"{item.maximum_drawdown:.2f}, "
            f"quality_after={quality.quality_after_filter}"
        )
    print("  independent_signal_trades=True")
    print("  next_bar_open_entry_no_look_ahead=True")
    print("  complete_signal_observer_bypasses_ui_limit=True")
    print("  speed_10x_100x_1000x_max_deterministic=True")
    print("  duplicate_signal_uid_blocked=True")
    print("  duplicate_variant_blocked=True")
    print("  foreign_binding_blocked=True")
    print("  currency_mismatch_blocked=True")
    print("  proposal_signatures_identical=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    net_summary = ",".join(f"{item.mode}:{item.net_profit:.2f}" for item in evaluations)
    print(f"  historical_hypothetical_net_profit_usd={net_summary}")
    print("ALGORITHM_WORKSPACE_HISTORICAL_EVALUATION_CHECK=OK")


if __name__ == "__main__":
    main()
