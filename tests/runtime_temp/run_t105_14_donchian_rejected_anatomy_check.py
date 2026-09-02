# -*- coding: utf-8 -*-
"""T105-14: TEST_ONLY anatomy відхилених Donchian entry signals Candidate F.

Runner не змінює entry gate і не шукає новий filter. Він бере factual production
baseline з PD=35% і аналізує лише ті Candidate F entries, які causal Donchian
Period=20 directional breakout gate відхилив би як INSIDE.
"""

from __future__ import annotations

import math
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_t105_10_pd_35_production_regression_check import (  # noqa: E402
    PERIODS,
    PRODUCTION_PD_THRESHOLD,
    PeriodSpec,
    _workspace,
)
from run_t105_11_donchian_entry_anatomy_check import (  # noqa: E402
    DONCHIAN_SHIFT,
    EPSILON,
    OUTCOME_BREAK_EVEN,
    OUTCOME_LOSS,
    OUTCOME_WIN,
    PIP_SIZE,
    STATE_INSIDE,
    DonchianAnatomyRuntime,
    DonchianEntryRow,
    _build_rows,
    _production_hashes,
)

from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)

TEST_ID = "T105-14"
EXPECTED_REJECTED = {"2025": 29, "2026": 17}
OUTCOMES = (OUTCOME_WIN, OUTCOME_LOSS, OUTCOME_BREAK_EVEN)


@dataclass(frozen=True, slots=True)
class RejectedEntryRow:
    """Causal distance snapshot одного factual entry, відхиленого як INSIDE."""

    source: DonchianEntryRow
    relevant_boundary: float
    signed_distance_pips: float
    absolute_distance_pips: float
    normalized_distance: float

    @property
    def direction(self) -> str:
        return self.source.trade.direction

    @property
    def outcome(self) -> str:
        return self.source.outcome

    @property
    def pnl(self) -> float:
        return self.source.trade.final_profit

    @property
    def close_reason(self) -> str:
        return self.source.trade.close_reason


def _rejected_row(row: DonchianEntryRow) -> RejectedEntryRow:
    """Побудувати directional distance без використання майбутніх bars."""
    trade = row.trade
    width_price = row.channel_width_pips * PIP_SIZE
    assert width_price > EPSILON

    if trade.direction == "BUY":
        relevant_boundary = row.upper
        signed_distance_pips = row.distance_to_upper_pips
    elif trade.direction == "SELL":
        relevant_boundary = row.lower
        signed_distance_pips = row.distance_to_lower_pips
    else:
        raise AssertionError(trade.direction)

    absolute_distance_pips = abs(signed_distance_pips)
    normalized_distance = absolute_distance_pips / row.channel_width_pips
    return RejectedEntryRow(
        source=row,
        relevant_boundary=relevant_boundary,
        signed_distance_pips=signed_distance_pips,
        absolute_distance_pips=absolute_distance_pips,
        normalized_distance=normalized_distance,
    )


def _stats(values: tuple[float, ...]) -> str:
    if not values:
        return "n:0"
    return (
        f"min:{min(values):.4f},median:{statistics.median(values):.4f},"
        f"mean:{statistics.fmean(values):.4f},max:{max(values):.4f}"
    )


def _group_line(name: str, rows: tuple[RejectedEntryRow, ...]) -> str:
    """Надрукувати anatomy однієї outcome-групи без selection decision."""
    if not rows:
        return f"    {name}=n:0,pnl:+0.00"
    distance_pips = tuple(row.absolute_distance_pips for row in rows)
    normalized = tuple(row.normalized_distance for row in rows)
    return (
        f"    {name}=n:{len(rows)},pnl:{math.fsum(row.pnl for row in rows):+.2f},"
        f"distance_pips[{_stats(distance_pips)}],"
        f"normalized[{_stats(normalized)}]"
    )


def _run_period(spec: PeriodSpec) -> tuple[RejectedEntryRow, ...]:
    """Виконати factual baseline і виділити тільки causal INSIDE entries."""
    runtime = DonchianAnatomyRuntime(
        _workspace(spec),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    assert isinstance(
        runtime.profit_drawdown_guard,
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )
    assert math.isclose(
        runtime.profit_protection_policy.max_drawdown_percent,
        PRODUCTION_PD_THRESHOLD,
        rel_tol=0.0,
        abs_tol=EPSILON,
    )

    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    summary = runtime.historical_summary
    assert summary is not None
    assert summary.opened_trades == spec.trades
    assert summary.winning_trades == spec.wins
    assert summary.losing_trades == spec.losses
    assert summary.break_even_trades == spec.break_even
    assert math.isclose(summary.net_profit, spec.net, rel_tol=0.0, abs_tol=0.005)
    assert math.isclose(
        summary.profit_factor,
        spec.profit_factor,
        rel_tol=0.0,
        abs_tol=0.00005,
    )
    assert math.isclose(
        summary.maximum_drawdown,
        spec.drawdown,
        rel_tol=0.0,
        abs_tol=0.005,
    )

    anatomy_rows = _build_rows(runtime)
    rejected = tuple(
        _rejected_row(row) for row in anatomy_rows if row.state == STATE_INSIDE
    )
    assert len(rejected) == EXPECTED_REJECTED[spec.code]

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    counts = Counter(row.outcome for row in rejected)
    directions = Counter(row.direction for row in rejected)
    close_reasons = Counter(row.close_reason for row in rejected)
    print(
        f"  period={spec.code},rejected:{len(rejected)},"
        f"wins:{counts[OUTCOME_WIN]},losses:{counts[OUTCOME_LOSS]},"
        f"break_even:{counts[OUTCOME_BREAK_EVEN]},"
        f"pnl:{math.fsum(row.pnl for row in rejected):+.2f},"
        f"BUY:{directions['BUY']},SELL:{directions['SELL']}"
    )
    print(
        "    close_reasons="
        + ",".join(
            f"{reason}:{count}" for reason, count in sorted(close_reasons.items())
        )
    )
    for outcome in OUTCOMES:
        group = tuple(row for row in rejected if row.outcome == outcome)
        print(_group_line(outcome, group))

    print("    factual_rejected_entries")
    for index, row in enumerate(rejected, start=1):
        trade = row.source.trade
        signal_event_close = (
            row.source.upper - row.source.distance_to_upper_pips * PIP_SIZE
        )
        print(
            f"      entry={index:02d},signal:{trade.signal_timestamp.isoformat()},"
            f"direction:{trade.direction},outcome:{row.outcome},pnl:{row.pnl:+.2f},"
            f"close_reason:{row.close_reason},signal_close:{signal_event_close:.5f},"
            f"boundary:{row.relevant_boundary:.5f},"
            f"signed_distance:{row.signed_distance_pips:+.2f}pip,"
            f"abs_distance:{row.absolute_distance_pips:.2f}pip,"
            f"channel_width:{row.source.channel_width_pips:.2f}pip,"
            f"normalized:{row.normalized_distance:.4f}"
        )
    return rejected


def main() -> None:
    """Запустити T105-14 як чисту anatomy без нового entry decision."""
    production_before = _production_hashes()

    print("T105-14 Candidate F Donchian Rejected Entry Anatomy result")
    print("  mode=TEST_ONLY_ACTUAL_CANDIDATE_F_WORKSPACE_RUNTIME")
    print("  production_profit_drawdown_threshold=35.0")
    print("  donchian_period=20_reference_not_universal_constant")
    print(f"  donchian_shift={DONCHIAN_SHIFT}")
    print("  reference_bars=previous_20_completed_M15")
    print("  current_signal_bar_excluded=True")
    print("  analyzed_population=BASELINE_FACTUAL_ENTRIES_REJECTED_AS_INSIDE")
    print("  new_entry_filter_created=False")

    rejected_by_period = tuple(_run_period(spec) for spec in PERIODS)
    assert tuple(len(rows) for rows in rejected_by_period) == (29, 17)
    assert _production_hashes() == production_before

    print("  rejected_count_check=2025:29,2026:17")
    print("  production_files_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  production_decision_made=False")
    print("  completed_market_events_only=True")
    print("  no_look_ahead=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T105_14_DONCHIAN_REJECTED_ANATOMY=OK")


if __name__ == "__main__":
    main()
