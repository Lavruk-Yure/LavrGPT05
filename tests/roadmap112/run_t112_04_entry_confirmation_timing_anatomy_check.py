# -*- coding: utf-8 -*-
"""T112-04 — хронологія підтверджень пропущених price-only трендів.

TEST_ONLY: чинний Replay, без зміни entry/exit чи додаткових ордерів.
Price-only labels будуються тільки після Replay; вони не керують входом.
Таймінг — описова діагностика, не counterfactual entry або його PnL.
"""

from __future__ import annotations

import hashlib
import math
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.workspace_market_event import WorkspaceMarketEvent
    from core.workspace_signal import WorkspaceSignalRecord

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ID = "T112-04"
MODE = "RM112_T112_04_ENTRY_CONFIRMATION_TIMING_ANATOMY_TEST_ONLY"
BAR_INTERVAL = timedelta(minutes=15)
EXPECTED_WINDOWS = {"2025": 17, "2026": 13}
EXPECTED_COVERED = {"2025": 3, "2026": 0}
EXPECTED_MISSED = 27
BASELINE_TOLERANCE = 0.005
STOCH_K_PERIOD = 14
STOCH_D_PERIOD = 3
STOCH_EPSILON = 1e-12


def _bootstrap() -> None:
    """Налаштувати імпорти для прямого запуску з tests/roadmap112."""
    project = str(PROJECT_ROOT)
    if project not in sys.path:
        sys.path.insert(0, project)


def _source_hashes() -> dict[str, str]:
    """Перевірити незмінність production Python, MD7 і strings.json."""
    roots = (PROJECT_ROOT / "core", PROJECT_ROOT / "engine")
    files = sorted(file for root in roots for file in root.rglob("*.py"))
    for relative in ("doc/LGE_Runtime_07.md", "lang/strings.json"):
        file = PROJECT_ROOT / relative
        if file.is_file():
            files.append(file)
    assert files, "Production code not found"
    return {
        str(file.relative_to(PROJECT_ROOT)): hashlib.sha256(
            file.read_bytes()
        ).hexdigest()
        for file in files
    }


def _workspace(spec):
    """Відтворити canonical Candidate F, 35% PD, historical M1 feed."""
    from engine.runtime_constants import (
        DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT,
    )
    from tests.runtime_workspace import (
        run_algorithm_workspace_candidate_f_frozen_oos_2025_check as frozen,
    )

    workspace = frozen.frozen_oos_workspace()
    workspace.broker = "CTRADER"
    protection = dict(workspace.profit_protection)
    protection["max_profit_drawdown_percent"] = (
        DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT
    )
    workspace.profit_protection = protection
    settings = dict(workspace.replay_settings)
    file = (
        PROJECT_ROOT / "data" / "history" / "CTRADER" / "EURUSD"
        / "M1" / spec.file_name
    )
    assert file.is_file(), str(file)
    settings.update(
        {
            "file_path": str(file),
            "start_utc": spec.start_utc,
            "end_utc": spec.end_utc,
            "source": Path(spec.file_name).stem,
            "source_timeframe": "M1",
        }
    )
    workspace.replay_settings = settings
    return workspace


def _baseline(spec, runtime) -> str:
    """Перевірити Replay та незмінність прийнятої exit geometry."""
    from core.workspace_alligator import WorkspaceMacdAlligatorReplayAlgorithm
    from tests.runtime_workspace import (
        run_t105_18_stochastic_current_bar_production_regression_check as baseline,
    )

    expected = baseline.EXPECTATIONS[spec.code]
    summary = runtime.historical_summary
    session = runtime.replay_session
    execution = runtime.replay_execution
    assert summary is not None and session is not None and execution is not None
    assert session.completed
    assert isinstance(runtime.algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    assert (
        summary.opened_trades,
        summary.winning_trades,
        summary.losing_trades,
        summary.break_even_trades,
    ) == (expected.trades, expected.wins, expected.losses, expected.break_even)
    assert math.isclose(
        summary.net_profit, expected.net,
        rel_tol=0.0, abs_tol=BASELINE_TOLERANCE,
    )
    assert math.isclose(
        summary.profit_factor, expected.profit_factor,
        rel_tol=0.0, abs_tol=0.00005,
    )
    assert math.isclose(
        summary.maximum_drawdown, expected.drawdown,
        rel_tol=0.0, abs_tol=BASELINE_TOLERANCE,
    )
    assert execution.policy.stop_range_multiplier == 1.0
    assert execution.policy.minimum_spread_multiples == 10.0
    assert execution.policy.take_profit_r_multiple == 2.0
    assert summary.close_reason_count("SESSION_END") == 0
    return (
        f"trades:{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},be:{summary.break_even_trades},"
        f"net:{summary.net_profit:+.2f},pf:{summary.profit_factor:.4f},"
        f"dd:{summary.maximum_drawdown:.2f}"
    )


def _active_side(observation) -> str | None:
    """Брати causal ACTIVE з фактичних production observations."""
    from core.workspace_alligator import (
        ALLIGATOR_REGIME_PHASE_ACTIVE,
        ALLIGATOR_REGIME_TREND_DOWN,
        ALLIGATOR_REGIME_TREND_UP,
        ALLIGATOR_STATE_BEARISH,
        ALLIGATOR_STATE_BULLISH,
    )

    if observation.regime_phase != ALLIGATOR_REGIME_PHASE_ACTIVE:
        return None
    if (
        observation.regime == ALLIGATOR_REGIME_TREND_UP
        and observation.state == ALLIGATOR_STATE_BULLISH
    ):
        return "BUY"
    if (
        observation.regime == ALLIGATOR_REGIME_TREND_DOWN
        and observation.state == ALLIGATOR_STATE_BEARISH
    ):
        return "SELL"
    return None


def _stochastic_crosses(
    events: tuple[WorkspaceMarketEvent, ...],
) -> dict[object, str]:
    """Діагностично відтворити CURRENT_BAR cross 14/1/3, без look-ahead.

    Значення не передаються в Replay і не використовуються як entry gate.
    Повторюємо completed-bar формулу production, включно з warm-up.
    """
    recent: list[WorkspaceMarketEvent] = []
    k_values: list[float] = []
    previous_k: float | None = None
    previous_d: float | None = None
    crosses: dict[object, str] = {}
    for event in events:
        assert event.timeframe == "M15"
        recent.append(event)
        if len(recent) > STOCH_K_PERIOD:
            del recent[0]
        if len(recent) < STOCH_K_PERIOD:
            continue
        highest = max(float(bar.high) for bar in recent)
        lowest = min(float(bar.low) for bar in recent)
        width = highest - lowest
        k = 50.0 if width <= STOCH_EPSILON else (
            100.0 * (float(event.close) - lowest) / width
        )
        k_values.append(k)
        if len(k_values) > STOCH_D_PERIOD:
            del k_values[0]
        if len(k_values) < STOCH_D_PERIOD:
            previous_k = k
            continue
        d = math.fsum(k_values) / STOCH_D_PERIOD
        if previous_k is not None and previous_d is not None:
            if previous_k <= previous_d + STOCH_EPSILON and k > d + STOCH_EPSILON:
                crosses[event.timestamp] = "UP"
            elif previous_k >= previous_d - STOCH_EPSILON and k < d - STOCH_EPSILON:
                crosses[event.timestamp] = "DOWN"
        previous_k = k
        previous_d = d
    return crosses


def _bar(indexes: dict[object, int], timestamp: object | None) -> str:
    """Повернути номер завершеного M15 бару вікна або NONE."""
    if timestamp is None:
        return "NONE"
    index = indexes.get(timestamp)
    return str(index) if index is not None else "OUTSIDE_WINDOW"


def _first(items):
    """Повернути перший timestamp або None для порожньої послідовності."""
    return min(items) if items else None


def _window_timing(
    chunk: tuple[WorkspaceMarketEvent, ...],
    direction: str,
    active_by_time: dict,
    quality: tuple,
    records: tuple[WorkspaceSignalRecord, ...],
    crosses: dict,
) -> tuple[str, Counter[str]]:
    """Класифікувати часові факти без створення умовного входу."""
    from core.workspace_alligator import (
        ALLIGATOR_DEFERRED_SIGNAL_TYPE,
        ALLIGATOR_REASON_DEFERRED_ARMED,
        ALLIGATOR_REASON_STOCHASTIC_CURRENT_BAR_CROSS,
    )

    start = chunk[0].timestamp
    end = chunk[-1].timestamp
    indexes = {bar.timestamp: index for index, bar in enumerate(chunk)}
    active = [
        time for time in indexes if active_by_time.get(time) == direction
    ]
    assert active, "Aligned ACTIVE expected by T112-02"
    first_active = min(active)
    active_bar = indexes[first_active]
    aligned_records = sorted(
        (
            record for record in records
            if start <= record.timestamp <= end and record.direction == direction
        ),
        key=lambda record: (record.timestamp, record.signal_uid),
    )
    aligned_quality = sorted(
        (
            item for item in quality
            if start <= item.timestamp <= end and item.direction == direction
        ),
        key=lambda item: item.timestamp,
    )
    # Quality diagnostics створює production MACD для completed crossover.
    if aligned_quality:
        first_cross = aligned_quality[0].timestamp
    else:
        first_cross = None
    if first_cross is None:
        timing = "NO_ALIGNED_MACD_CROSS"
    elif first_cross < first_active:
        timing = "FIRST_CROSS_BEFORE_ACTIVE"
    else:
        timing = "FIRST_CROSS_AT_OR_AFTER_ACTIVE"

    passed = [item for item in aligned_quality if item.final_quality_pass]
    failed = [item for item in aligned_quality if not item.final_quality_pass]
    early_pass = [item for item in passed if item.timestamp < first_active]
    late_pass = [item for item in passed if item.timestamp >= first_active]
    pass_during_active = [
        item for item in passed
        if active_by_time.get(item.timestamp) == direction
    ]
    early_fail = [item for item in failed if item.timestamp < first_active]
    late_fail = [item for item in failed if item.timestamp >= first_active]
    first_proposal = _first([item.timestamp for item in aligned_records])
    stoch_times = [time for time in indexes if time in crosses]
    stoch_at_proposal = sum(
        record.timestamp in crosses for record in aligned_records
    )
    stoch_on_quality_pass = sum(
        item.timestamp in crosses for item in passed
    )
    stoch_neighbor_quality_pass = sum(
        any(
            chunk[neighbor].timestamp in crosses
            for neighbor in (indexes[item.timestamp] - 1, indexes[item.timestamp] + 1)
            if 0 <= neighbor < len(chunk)
        )
        for item in passed
    )
    stoch_rejects = [
        record for record in aligned_records
        if record.filter_reason_code == (
            ALLIGATOR_REASON_STOCHASTIC_CURRENT_BAR_CROSS
        )
    ]
    assert all(record.timestamp in crosses for record in stoch_rejects), (
        "Stochastic causal diagnostic does not match production gate"
    )
    armed = [
        record for record in aligned_records
        if record.filter_reason_code == ALLIGATOR_REASON_DEFERRED_ARMED
    ]
    releases = [
        record for record in aligned_records
        if record.signal_type == ALLIGATOR_DEFERRED_SIGNAL_TYPE
    ]
    terminal_in_window = [
        record for record in records
        if record.direction == direction
        and record.filter_reason_code == ALLIGATOR_REASON_DEFERRED_ARMED
        and record.candidate_f_lifecycle_timestamp is not None
        and start <= record.candidate_f_lifecycle_timestamp <= end
    ]
    terminal = Counter(
        record.candidate_f_lifecycle_action or "PENDING_AT_END_OF_REPLAY"
        for record in armed
    )
    terminal_reasons = Counter(
        record.candidate_f_lifecycle_reason or "NONE" for record in armed
    )
    arm_rows = ",".join(
        f"{indexes[record.timestamp]}:"
        f"{record.candidate_f_lifecycle_action or 'PENDING'}:"
        f"{record.candidate_f_lifecycle_reason or 'NONE'}:"
        f"{_bar(indexes, record.candidate_f_lifecycle_timestamp)}:"
        f"{record.candidate_f_lifecycle_delay_bars}"
        for record in armed
    ) or "NONE"
    matched_active_at_record = sum(
        active_by_time.get(record.timestamp) == direction
        for record in aligned_records
    )
    quality_reasons = Counter(item.reason_code for item in aligned_quality)
    reasons_text = ",".join(
        f"{code}:{count}" for code, count in sorted(quality_reasons.items())
    ) or "NONE"
    first_delta = (
        active_bar - indexes[first_cross] if first_cross is not None else "NONE"
    )
    counts: Counter[str] = Counter(
        {
            f"timing:{timing}": 1,
            "quality_pass_before_active": len(early_pass),
            "quality_pass_at_or_after_active": len(late_pass),
            "quality_pass_on_aligned_active_bar": len(pass_during_active),
            "quality_reject_before_active": len(early_fail),
            "quality_reject_at_or_after_active": len(late_fail),
            "proposals_during_aligned_active": matched_active_at_record,
            "stoch_cross_at_proposal": stoch_at_proposal,
            "stoch_cross_on_quality_pass_bar": stoch_on_quality_pass,
            "stoch_cross_neighbor_quality_pass": stoch_neighbor_quality_pass,
            "production_stoch_reject": len(stoch_rejects),
            "armed_candidates": len(armed),
            "deferred_releases_in_window": len(releases),
            "lifecycle_terminals_in_window": len(terminal_in_window),
        }
    )
    for code, count in terminal.items():
        counts[f"terminal:{code}"] += count
    for code, count in terminal_reasons.items():
        counts[f"terminal_reason:{code}"] += count
    line = (
        f"first_active_bar={active_bar}"
        f"|first_macd_cross_bar={_bar(indexes, first_cross)}"
        f"|active_minus_first_cross_bars={first_delta}"
        f"|timing_class={timing}"
        f"|first_proposal_bar={_bar(indexes, first_proposal)}"
        f"|quality_pass_pre_active={len(early_pass)}"
        f"|quality_pass_active_or_later={len(late_pass)}"
        f"|quality_pass_on_active_bar={len(pass_during_active)}"
        f"|quality_reject_pre_active={len(early_fail)}"
        f"|quality_reject_active_or_later={len(late_fail)}"
        f"|quality_reasons={reasons_text}"
        f"|proposals={len(aligned_records)}"
        f"|proposals_during_active={matched_active_at_record}"
        f"|stoch_cross_bars={len(stoch_times)}"
        f"|first_stoch_cross_bar={_bar(indexes, _first(stoch_times))}"
        f"|stoch_cross_at_proposal={stoch_at_proposal}"
        f"|stoch_cross_on_quality_pass={stoch_on_quality_pass}"
        f"|stoch_cross_neighbor_quality_pass={stoch_neighbor_quality_pass}"
        f"|stoch_gate_rejects={len(stoch_rejects)}"
        f"|armed={len(armed)}|releases={len(releases)}"
        f"|terminals_in_window={len(terminal_in_window)}"
        f"|arm_terminal_rows={arm_rows}"
    )
    return line, counts


def _run_period(spec) -> tuple[int, Counter[str]]:
    """Один детермінований Replay і діагностика пропущених вікон."""
    from core.workspace_algorithm import create_registered_workspace_algorithm
    from core.workspace_alligator import WorkspaceMacdAlligatorReplayAlgorithm
    from tests.runtime_temp import (
        run_algorithm_workspace_candidate_f_trend_coverage_2025_check as detector,
    )
    from tests.runtime_workspace import (
        run_algorithm_workspace_replay_virtual_execution_check as regression,
    )
    from tests.runtime_workspace.run_t105_15_stochastic_entry_anatomy_check import (
        StochasticAnatomyRuntime,
    )

    probe = regression.BrokerRequestProbe()
    runtime = StochasticAnatomyRuntime(
        _workspace(spec),
        algorithm_factory=create_registered_workspace_algorithm,
        broker_market_provider=probe,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()
    baseline = _baseline(spec, runtime)
    assert probe.requests == 0
    assert not any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal if isinstance(entry.details, dict)
    )
    algorithm = runtime.algorithm
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    signal_filter = algorithm.signal_filter
    source = algorithm.source
    assert signal_filter is not None and source is not None
    active_by_time = {
        item.timestamp: _active_side(item)
        for item in signal_filter.observations
    }
    strategy = runtime.strategy_events
    events = tuple(strategy[time] for time in sorted(strategy))
    assert len(events) > 96
    assert len({event.timestamp for event in events}) == len(events)
    assert all(
        events[index].timestamp > events[index - 1].timestamp
        for index in range(1, len(events))
    )
    assert detector.EXPECTED_M15_DELTA == BAR_INTERVAL
    windows = detector.strongest_non_overlapping(
        detector.price_only_trend_candidates(events)
    )
    assert len(windows) == EXPECTED_WINDOWS[spec.code]
    stochastic = _stochastic_crosses(events)
    records = runtime.historical_signal_records
    qualities = source.quality_diagnostics
    execution = runtime.replay_execution
    assert execution is not None
    trades = execution.trade_diagnostics()
    covered = 0
    missed = 0
    totals: Counter[str] = Counter()
    print(f"period={spec.code}|baseline={baseline}")
    print(f"price_only_windows={len(windows)}")
    print("MISSED_TIMING_WINDOW_ROWS")
    for window in windows:
        chunk = events[window.start_index:window.end_index + 1]
        assert len(chunk) == 32
        assert all(
            chunk[index].timestamp - chunk[index - 1].timestamp == BAR_INTERVAL
            for index in range(1, len(chunk))
        )
        if any(
            chunk[0].timestamp <= trade.signal_timestamp <= chunk[-1].timestamp
            and trade.direction == window.direction
            for trade in trades
        ):
            covered += 1
            continue
        missed += 1
        details, counts = _window_timing(
            chunk, window.direction, active_by_time,
            qualities, records, stochastic,
        )
        totals.update(counts)
        print(
            f"window={chunk[0].timestamp.isoformat()}"
            f"|end={chunk[-1].timestamp.isoformat()}"
            f"|direction={window.direction}|{details}"
        )
    assert covered == EXPECTED_COVERED[spec.code]
    assert missed == len(windows) - covered
    print(f"covered_windows={covered}|missed_windows={missed}")
    print("TIMING_AGGREGATES_PERIOD")
    for code, count in sorted(totals.items()):
        print(f"metric={code}|count={count}")
    print(f"period={spec.code}|broker_requests={probe.requests}")
    return missed, totals


def main() -> None:
    """Дослідити timing без нових entry rules, періоди окремо."""
    _bootstrap()
    from tests.runtime_workspace.run_t105_10_pd_35_production_regression_check import (
        PERIODS,
    )

    before = _source_hashes()
    print("T112_04_ENTRY_CONFIRMATION_TIMING_ANATOMY")
    print("population=PRICE_ONLY_32_COMPLETED_M15_EX_POST_ONLY")
    print("timing=MACD_CROSS_AND_QUALITY_VS_FIRST_ALIGNED_ALLIGATOR_ACTIVE")
    print("candidate_f_lifecycle=EXISTING_ARMED_RELEASE_CANCEL_EXPIRE_ONLY")
    print("stochastic=CAUSAL_CURRENT_BAR_14_1_3_DIAGNOSTIC_ONLY")
    print("2026_period=PARTIAL_THROUGH_2026_08_25")
    print("comparison=PER_WINDOW_NOT_RAW_ANNUAL_TOTALS")
    total_missed = 0
    totals: Counter[str] = Counter()
    for spec in PERIODS:
        missed, counts = _run_period(spec)
        total_missed += missed
        totals.update(counts)
    assert total_missed == EXPECTED_MISSED
    assert _source_hashes() == before
    assert (
        totals["timing:FIRST_CROSS_BEFORE_ACTIVE"]
        + totals["timing:FIRST_CROSS_AT_OR_AFTER_ACTIVE"]
        + totals["timing:NO_ALIGNED_MACD_CROSS"]
    ) == EXPECTED_MISSED
    print("AGGREGATE_TIMING_FACTS")
    for code, count in sorted(totals.items()):
        print(f"metric={code}|count={count}")
    print(f"total_missed_windows={total_missed}")
    print("SAFETY")
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("ex_post_labels_used_for_entry=False")
    print("new_entry_rule_created=False")
    print("production_logic_changed=False")
    print("exit_logic_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("T112_04_ENTRY_CONFIRMATION_TIMING_ANATOMY=OK")


if __name__ == "__main__":
    main()
