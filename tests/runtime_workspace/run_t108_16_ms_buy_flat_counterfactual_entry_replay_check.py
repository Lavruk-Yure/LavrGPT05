"""run_t108_16_ms_buy_flat_counterfactual_entry_replay_check.py — T108-16.

TEST_ONLY runner перевіряє одну заздалегідь визначену гіпотезу entry:
exact normalized composition MS_BUY (MACD=BUY, Alligator=NEUTRAL,
Stochastic=BUY) на factual production state FLAT для persistence P3 і P4.
Кандидати формуються з causal completed M15 bars за незміненою семантикою
T108-11/T108-12; Supertrend, weights, score і threshold selection відсутні.

Пропущені production opportunities окремо проходять штатний Replay execution
pipeline: сигнал на completed M15, fill NEXT_BAR_OPEN, одна позиція за раз,
SL=max(signal range, spread*10), TP=2R, Profit Drawdown 35% і чинний
negative-PD recovery guard. Factual production trades не домішуються до
counterfactual detail. Runner не звертається до broker, не використовує
look-ahead, не створює reverse/alternative exit logic і не змінює production,
thresholds або MD7.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_algorithm_workspace_replay_virtual_execution_check import (  # noqa: E402
    BrokerRequestProbe,
)

from core.workspace_alligator import (  # noqa: E402
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_runtime import WorkspaceRuntimeContext  # noqa: E402
from core.workspace_signal import WorkspaceSignalProposal  # noqa: E402

TEST_ID = "T108-16"
MODE = "RM108_T108_16_MS_BUY_FLAT_COUNTERFACTUAL_ENTRY_REPLAY_TEST_ONLY"
POSITION_SCRIPT = "run_t108_13_exact_family_composition_position_state_anatomy_check.py"
VARIANTS = (3, 4)
PERIOD_CODES = ("2025", "2026")
MS_BUY_STATE = (1, 0, 1)
EPSILON = 1e-12
EXPECTED_BASELINE = {
    "2025": (42, 30, 11, 1, 4.03, 1.5424, 3.58),
    "2026": (18, 15, 2, 1, 3.68, 3.7669, 1.20),
}


def _load_position_module() -> ModuleType:
    """Завантажити GREEN T108-13 як єдине джерело family/state anatomy."""

    file_path = TEST_ROOT / POSITION_SCRIPT
    assert file_path.is_file(), file_path
    spec = importlib.util.spec_from_file_location(
        "rm108_t108_16_position",
        file_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


POSITION = _load_position_module()
PERIODS = getattr(POSITION, "PERIODS")
DECISION_ROWS: Callable[..., Any] = getattr(POSITION, "DECISION_ROWS")
PRODUCTION_HASHES: Callable[..., dict[str, str]] = getattr(
    POSITION,
    "PRODUCTION_HASHES",
)
RUN_WITH_RUNTIME: Callable[..., tuple[Any, Any]] = getattr(
    POSITION,
    "_run_with_runtime",
)
POSITION_LABELS: Callable[..., dict[datetime, Any]] = getattr(
    POSITION,
    "_position_labels",
)
BUILD_WORKSPACE: Callable[..., Any] = getattr(POSITION.PERSISTENCE, "_workspace")
ASSERT_POLICY: Callable[..., None] = getattr(POSITION.PERSISTENCE, "_assert_policy")
ASSERT_GEOMETRY: Callable[..., None] = getattr(
    POSITION.PERSISTENCE,
    "_assert_geometry",
)
BROKER_EXECUTION_ATTEMPTED: Callable[..., bool] = getattr(
    POSITION.PERSISTENCE,
    "_broker_execution_attempted",
)
BASE_RUNTIME = getattr(POSITION, "BASE_RUNTIME")


@dataclass(frozen=True, slots=True)
class CandidateAudit:
    """Exact MS_BUY/FLAT bars та їх factual production overlap."""

    all_timestamps: tuple[datetime, ...]
    overlap_timestamps: tuple[datetime, ...]
    missed_timestamps: tuple[datetime, ...]


@dataclass(frozen=True, slots=True)
class CounterfactualResult:
    """Один завершений P3/P4 Replay та лічильники його added trades."""

    period: str
    persistence: int
    audit: CandidateAudit
    runtime: Any
    entries_created: int
    entries_blocked: int
    broker_requests: int


class MsBuyFlatCounterfactualAlgorithm(WorkspaceMacdAlligatorReplayAlgorithm):
    """Емітувати BUY лише на наперед causal визначених missed MS_BUY bars."""

    def __init__(
        self,
        algorithm_id: str,
        candidate_timestamps: frozenset[datetime],
    ) -> None:
        super().__init__(algorithm_id)
        self.candidate_timestamps = candidate_timestamps

    def configure(
        self,
        context: WorkspaceRuntimeContext,
        parameters: Mapping[str, Any],
    ) -> None:
        """Зберегти production configuration/warm-up та test-only candidates."""

        super().configure(context, parameters)

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalProposal | None:
        """Повернути exact MS_BUY proposal без production signal evaluation."""

        if not self.started:
            raise RuntimeError("Counterfactual algorithm is not started")
        if event.timestamp not in self.candidate_timestamps:
            return None
        return WorkspaceSignalProposal(
            signal_type="T108_16_MS_BUY_FLAT",
            direction="BUY",
            strength=1.0,
            macd_state="BUY",
            alligator_confirmation="NEUTRAL",
            reason="Exact MS_BUY on factual FLAT completed M15 bar.",
        )


def _metric(actual: float, expected: float, tolerance: float) -> None:
    """Перевірити deterministic numeric metric із заданою похибкою."""

    assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance), (
        actual,
        expected,
    )


def _trades(runtime: Any) -> tuple[Any, ...]:
    """Прочитати immutable trade diagnostics завершеного Replay."""

    execution = runtime.replay_execution
    assert execution is not None
    return tuple(execution.trade_diagnostics())


def _assert_baseline(period: str, runtime: Any) -> None:
    """Підтвердити заданий factual Candidate F baseline перед CF Replay."""

    summary = runtime.historical_summary
    assert summary is not None
    expected = EXPECTED_BASELINE[period]
    assert (
        summary.opened_trades,
        summary.winning_trades,
        summary.losing_trades,
        summary.break_even_trades,
    ) == expected[:4]
    _metric(summary.net_profit, expected[4], 0.005)
    assert summary.profit_factor is not None
    _metric(summary.profit_factor, expected[5], 0.00005)
    _metric(summary.maximum_drawdown, expected[6], 0.005)


def _candidate_audit(
    replay: Any,
    labels: dict[datetime, Any],
    persistence: int,
) -> CandidateAudit:
    """Виділити MS_BUY/FLAT та відокремити production overlap від missed."""

    decision_rows, _, _ = DECISION_ROWS(replay, persistence)
    all_timestamps: list[datetime] = []
    overlap_timestamps: list[datetime] = []
    missed_timestamps: list[datetime] = []
    for row in decision_rows:
        state = (row.macd_vote, row.alligator_vote, row.stochastic_vote)
        position = labels[row.timestamp]
        if state != MS_BUY_STATE or position.state != "FLAT":
            continue
        all_timestamps.append(row.timestamp)
        if position.entry_directions:
            overlap_timestamps.append(row.timestamp)
        else:
            missed_timestamps.append(row.timestamp)
    assert len(all_timestamps) == len(overlap_timestamps) + len(missed_timestamps)
    return CandidateAudit(
        tuple(all_timestamps),
        tuple(overlap_timestamps),
        tuple(missed_timestamps),
    )


def _counterfactual_workspace(spec: Any) -> Any:
    """Створити test-only copy production workspace з one-position limit."""

    workspace = BUILD_WORKSPACE(spec)
    risk_settings: dict[str, Any] = dict(workspace.risk_settings)
    risk_settings["maximum_open_positions"] = 1
    workspace.risk_settings = risk_settings
    return workspace


def _run_counterfactual(
    spec: Any,
    persistence: int,
    audit: CandidateAudit,
) -> CounterfactualResult:
    """Прогнати missed candidates через canonical Replay execution stack."""

    broker_probe = BrokerRequestProbe()
    candidates = frozenset(audit.missed_timestamps)

    def algorithm_factory(algorithm_id: str) -> MsBuyFlatCounterfactualAlgorithm:
        """Створити один test-only algorithm для поточного P variant."""

        return MsBuyFlatCounterfactualAlgorithm(algorithm_id, candidates)

    runtime = BASE_RUNTIME(
        _counterfactual_workspace(spec),
        algorithm_factory=algorithm_factory,
        broker_market_provider=broker_probe,
    )
    ASSERT_POLICY(runtime)
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    ASSERT_GEOMETRY(runtime)
    assert runtime.replay_execution is not None
    assert runtime.replay_execution.policy.maximum_open_positions == 1
    created = sum(entry.event == "VIRTUAL_ORDER_CREATED" for entry in runtime.journal)
    blocked = sum(entry.event == "VIRTUAL_ORDER_BLOCKED" for entry in runtime.journal)
    assert created + blocked == len(audit.missed_timestamps)
    assert broker_probe.requests == 0
    assert not BROKER_EXECUTION_ATTEMPTED(runtime)
    return CounterfactualResult(
        period=spec.code,
        persistence=persistence,
        audit=audit,
        runtime=runtime,
        entries_created=created,
        entries_blocked=blocked,
        broker_requests=broker_probe.requests,
    )


def _profit_factor_text(value: float | None) -> str:
    """Форматувати PF без вигаданого numeric sentinel."""

    return "NONE" if value is None else f"{value:.4f}"


def _close_reason_text(runtime: Any) -> str:
    """Сформувати deterministic close-reason counts одного CF population."""

    counts = Counter(trade.close_reason for trade in _trades(runtime))
    return "|".join(f"{reason}:{counts[reason]}" for reason in sorted(counts)) or "NONE"


def _outcome(trade: Any) -> str:
    """Класифікувати factual counterfactual PnL як WIN/LOSS/BE."""

    if trade.final_profit > EPSILON:
        return "WIN"
    if trade.final_profit < -EPSILON:
        return "LOSS"
    return "BE"


def _r_result(trade: Any) -> float:
    """Нормувати realized PnL на factual initial stop risk."""

    initial_risk = trade.stop_loss_distance * trade.volume
    assert initial_risk > 0.0
    return trade.final_profit / initial_risk


def _print_baseline(period: str, runtime: Any) -> None:
    """Надрукувати canonical production baseline окремою population."""

    summary = runtime.historical_summary
    assert summary is not None
    print(
        f"population=CANONICAL_PRODUCTION_BASELINE|period={period}|"
        f"trades={summary.opened_trades}|wins={summary.winning_trades}|"
        f"losses={summary.losing_trades}|"
        f"break_even={summary.break_even_trades}|net={summary.net_profit:+.2f}|"
        f"profit_factor={_profit_factor_text(summary.profit_factor)}|"
        f"max_drawdown={summary.maximum_drawdown:.2f}"
    )


def _print_counterfactual(result: CounterfactualResult) -> None:
    """Надрукувати P3/P4 summary та overlap audit однаковими полями."""

    summary = result.runtime.historical_summary
    assert summary is not None
    skipped = len(result.audit.overlap_timestamps) + result.entries_blocked
    print(
        f"population=COUNTERFACTUAL_MS_BUY_P{result.persistence}|"
        f"period={result.period}|candidate_bars={len(result.audit.all_timestamps)}|"
        f"entries_created={result.entries_created}|"
        f"entries_skipped_existing_position={skipped}|"
        f"trades={summary.opened_trades}|wins={summary.winning_trades}|"
        f"losses={summary.losing_trades}|"
        f"break_even={summary.break_even_trades}|net={summary.net_profit:+.2f}|"
        f"profit_factor={_profit_factor_text(summary.profit_factor)}|"
        f"max_drawdown={summary.maximum_drawdown:.2f}|"
        f"close_reason_counts={_close_reason_text(result.runtime)}|"
        f"incremental_trades_vs_baseline={summary.opened_trades}|"
        f"incremental_net_vs_baseline={summary.net_profit:+.2f}"
    )
    print(
        f"overlap_audit|period={result.period}|variant=P{result.persistence}|"
        f"ms_buy_candidate_bars={len(result.audit.all_timestamps)}|"
        "factual_production_entry_opportunity_overlap="
        f"{len(result.audit.overlap_timestamps)}|"
        f"truly_missed_by_production={len(result.audit.missed_timestamps)}"
    )


def _print_trade_details(results: tuple[CounterfactualResult, ...]) -> None:
    """Надрукувати лише added counterfactual trades, без baseline rows."""

    print("COUNTERFACTUAL_TRADE_DETAIL")
    for result in results:
        for trade in _trades(result.runtime):
            print(
                f"period={result.period}|variant=P{result.persistence}|"
                f"trade_id={trade.position_id}|"
                f"signal_bar_time={trade.signal_timestamp.isoformat()}|"
                f"entry_time={trade.entry_timestamp.isoformat()}|"
                f"exit_time={trade.close_timestamp.isoformat()}|"
                f"entry_price={trade.entry_price:.5f}|"
                f"exit_price={trade.close_price:.5f}|"
                f"outcome={_outcome(trade)}|close_reason={trade.close_reason}|"
                f"pnl={trade.final_profit:+.2f}|R_result={_r_result(trade):+.4f}"
            )


def main() -> int:
    """Виконати baseline anatomy, P3/P4 CF Replay і safety assertions."""

    before_hashes = PRODUCTION_HASHES()
    baseline: dict[str, tuple[Any, Any, dict[datetime, Any]]] = {}
    results: list[CounterfactualResult] = []
    print("T108_16_MS_BUY_FLAT_COUNTERFACTUAL_ENTRY_REPLAY")
    for spec in PERIODS:
        print(f"running_baseline_period={spec.code}", flush=True)
        replay, runtime = RUN_WITH_RUNTIME(spec)
        _assert_baseline(spec.code, runtime)
        assert not BROKER_EXECUTION_ATTEMPTED(runtime)
        labels = POSITION_LABELS(replay, runtime)
        baseline[spec.code] = (replay, runtime, labels)
        _print_baseline(spec.code, runtime)

    for spec in PERIODS:
        replay, _, labels = baseline[spec.code]
        for persistence in VARIANTS:
            audit = _candidate_audit(replay, labels, persistence)
            print(
                f"running_counterfactual_period={spec.code}|" f"variant=P{persistence}",
                flush=True,
            )
            result = _run_counterfactual(spec, persistence, audit)
            results.append(result)
            _print_counterfactual(result)

    result_tuple = tuple(results)
    assert len(result_tuple) == len(PERIOD_CODES) * len(VARIANTS)
    assert PRODUCTION_HASHES() == before_hashes
    _print_trade_details(result_tuple)

    broker_requests = sum(result.broker_requests for result in result_tuple)
    broker_execution_attempted = any(
        BROKER_EXECUTION_ATTEMPTED(runtime) for _, runtime, _ in baseline.values()
    ) or any(BROKER_EXECUTION_ATTEMPTED(result.runtime) for result in result_tuple)
    print("SAFETY")
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("hypothesis=EXACT_MS_BUY_FLAT_ONLY")
    print("variants=P3_P4_PREDEFINED")
    print("supertrend_included=False")
    print("generic_score_model_created=False")
    print("weights_used=False")
    print("threshold_sweep_performed=False")
    print("persistence_sweep_performed=False")
    print("reverse_logic_created=False")
    print("alternative_exit_logic_created=False")
    print("canonical_exit_stack_preserved=True")
    print("next_bar_open=True")
    print("completed_bars_only=True")
    print("lookahead_used=False")
    print("optimization_performed=False")
    print("production_logic_changed=False")
    print("production_threshold_changed=False")
    print("md7_changed=False")
    print(f"broker_requests={broker_requests}")
    print(f"broker_execution_attempted={broker_execution_attempted}")
    assert broker_requests == 0
    assert not broker_execution_attempted
    print("T108_16_MS_BUY_FLAT_COUNTERFACTUAL_ENTRY_REPLAY=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
