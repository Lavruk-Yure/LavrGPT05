# -*- coding: utf-8 -*-
"""RoadMap103 / 7I: inventory ACTIVE Alligator trends без позиції за 2025.

Diagnostic-only runner повторює production Candidate F після 6K на frozen
2025 Replay. Замість тисяч окремих M15 bars він формує один
рядок на кожен безперервний directional Alligator ACTIVE trend і
показує, скільки bars цього trend пройшло без відкритої Replay-позиції.

Для ручного перегляду trends розбиті на три файли за повною
довжиною ACTIVE run: SHORT=1..10 bars, MEDIUM=11..20 bars,
LONG=21+ bars. У CSV є start/end trend, no-position ranges та causal
signal/lifecycle evidence, яке було відоме на відповідних completed
M15 bars. Future price не використовується як feature.

CSV пишуться у системний TEMP, тому робоче дерево LavrGPT05 не
забруднюється.
"""

from __future__ import annotations

import csv
import math
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, TEST_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    ALLIGATOR_STATE_BEARISH,
    ALLIGATOR_STATE_BULLISH,
    WorkspaceAlligatorObservation,
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402
from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)

EXPECTED_BASELINE = (59, 40, 18, 1, 9, -4.05, 0.7808, 5.80)
M15 = timedelta(minutes=15)

BUCKET_SHORT = "SHORT_1_10"
BUCKET_MEDIUM = "MEDIUM_11_20"
BUCKET_LONG = "LONG_21_PLUS"
BUCKETS = (BUCKET_SHORT, BUCKET_MEDIUM, BUCKET_LONG)

OUTPUT_DIR = (
    Path(tempfile.gettempdir())
    / "LavrGPT05"
    / "RM103_7I_Alligator_ACTIVE_No_Position_Trends_2025"
)


@dataclass(frozen=True, slots=True)
class TrendInventoryRow:
    """Один directional ACTIVE run для ручного перегляду."""

    run_id: int
    bucket: str
    direction: str
    start_utc: datetime
    end_utc: datetime
    active_bars: int
    no_position_bars: int
    position_bars: int
    no_position_ranges: str
    signal_records_no_position: int
    accepted_signals_no_position: int
    actual_trade_signals_no_position: int
    source_reason_codes_no_position: str
    filter_reason_codes_no_position: str
    lifecycle_actions_no_position: str
    lifecycle_reasons_no_position: str
    opening_start: float
    opening_end: float
    slope_start: float
    slope_end: float


class InventoryRuntime(WorkspaceRuntime):
    """Production Runtime з full signal history для діагностики."""

    @property
    def historical_signal_records(self) -> tuple[WorkspaceSignalRecord, ...]:
        """Повернути повну історію signal records Replay."""
        return tuple(self._historical_signal_records)


def _active_direction(observation: WorkspaceAlligatorObservation) -> str | None:
    if observation.regime_phase != ALLIGATOR_REGIME_PHASE_ACTIVE:
        return None
    if (
        observation.state == ALLIGATOR_STATE_BULLISH
        and observation.regime == ALLIGATOR_REGIME_TREND_UP
    ):
        return "BUY"
    if (
        observation.state == ALLIGATOR_STATE_BEARISH
        and observation.regime == ALLIGATOR_REGIME_TREND_DOWN
    ):
        return "SELL"
    return None


def _bucket(active_bars: int) -> str:
    if active_bars <= 10:
        return BUCKET_SHORT
    if active_bars <= 20:
        return BUCKET_MEDIUM
    return BUCKET_LONG


def _position_is_open(trades, timestamp: datetime) -> bool:
    return any(
        trade.entry_timestamp <= timestamp < trade.close_timestamp for trade in trades
    )


def _joined(values: list[str]) -> str:
    return "|".join(sorted({value for value in values if value}))


def _compact_ranges(timestamps: tuple[datetime, ...]) -> str:
    if not timestamps:
        return ""
    ordered = tuple(sorted(timestamps))
    ranges: list[tuple[datetime, datetime, int]] = []
    start = ordered[0]
    end = ordered[0]
    count = 1
    for timestamp in ordered[1:]:
        if timestamp - end == M15:
            end = timestamp
            count += 1
            continue
        ranges.append((start, end, count))
        start = timestamp
        end = timestamp
        count = 1
    ranges.append((start, end, count))
    return "|".join(
        f"{start.isoformat()}->{end.isoformat()}[{count}]"
        for start, end, count in ranges
    )


def _assert_baseline(runtime: InventoryRuntime) -> None:
    summary = runtime.historical_summary
    assert summary is not None
    expected = EXPECTED_BASELINE
    assert summary.opened_trades == expected[0]
    assert summary.winning_trades == expected[1]
    assert summary.losing_trades == expected[2]
    assert summary.break_even_trades == expected[3]
    assert summary.close_reason_count("STOP_LOSS") == expected[4]
    assert math.isclose(summary.net_profit, expected[5], abs_tol=0.005)
    assert summary.profit_factor is not None
    assert math.isclose(summary.profit_factor, expected[6], abs_tol=0.00005)
    assert math.isclose(summary.maximum_drawdown, expected[7], abs_tol=0.005)


def _split_active_runs(
    observations: tuple[WorkspaceAlligatorObservation, ...],
) -> tuple[tuple[WorkspaceAlligatorObservation, ...], ...]:
    runs: list[tuple[WorkspaceAlligatorObservation, ...]] = []
    current: list[WorkspaceAlligatorObservation] = []
    current_direction: str | None = None
    previous_timestamp: datetime | None = None

    for observation in observations:
        direction = _active_direction(observation)
        contiguous = (
            previous_timestamp is not None
            and observation.timestamp - previous_timestamp == M15
        )
        if direction is None:
            if current:
                runs.append(tuple(current))
                current = []
            current_direction = None
            previous_timestamp = observation.timestamp
            continue
        if current and (direction != current_direction or not contiguous):
            runs.append(tuple(current))
            current = []
        current.append(observation)
        current_direction = direction
        previous_timestamp = observation.timestamp

    if current:
        runs.append(tuple(current))
    return tuple(runs)


def _collect_inventory() -> tuple[TrendInventoryRow, ...]:
    runtime = InventoryRuntime(
        frozen_oos_workspace(),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    assert isinstance(
        runtime.profit_drawdown_guard,
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    _assert_baseline(runtime)
    execution = runtime.replay_execution
    algorithm = runtime.algorithm
    assert execution is not None
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    signal_filter = algorithm.signal_filter
    assert signal_filter is not None

    trades = execution.trade_diagnostics()
    trade_signal_timestamps = {trade.signal_timestamp for trade in trades}
    records_by_timestamp: dict[datetime, list[WorkspaceSignalRecord]] = defaultdict(
        list
    )
    for record in runtime.historical_signal_records:
        records_by_timestamp[record.timestamp].append(record)

    rows: list[TrendInventoryRow] = []
    active_runs = _split_active_runs(signal_filter.observations)
    for run_id, run in enumerate(active_runs, start=1):
        direction = _active_direction(run[0])
        assert direction is not None
        assert all(_active_direction(item) == direction for item in run)
        no_position_observations = tuple(
            item for item in run if not _position_is_open(trades, item.timestamp)
        )
        if not no_position_observations:
            continue

        no_position_timestamps = tuple(
            item.timestamp for item in no_position_observations
        )
        current_records = tuple(
            record
            for timestamp in no_position_timestamps
            for record in records_by_timestamp.get(timestamp, ())
        )
        source_reasons = [
            str(record.source_reason_code or "").strip() for record in current_records
        ]
        filter_reasons = [
            str(record.filter_reason_code or "").strip() for record in current_records
        ]
        lifecycle_actions = [
            str(record.candidate_f_lifecycle_action or "").strip()
            for record in current_records
        ]
        lifecycle_reasons = [
            str(record.candidate_f_lifecycle_reason or "").strip()
            for record in current_records
        ]
        assert run[0].normalized_opening is not None
        assert run[-1].normalized_opening is not None
        assert run[0].normalized_slope is not None
        assert run[-1].normalized_slope is not None

        rows.append(
            TrendInventoryRow(
                run_id=run_id,
                bucket=_bucket(len(run)),
                direction=direction,
                start_utc=run[0].timestamp,
                end_utc=run[-1].timestamp,
                active_bars=len(run),
                no_position_bars=len(no_position_observations),
                position_bars=len(run) - len(no_position_observations),
                no_position_ranges=_compact_ranges(no_position_timestamps),
                signal_records_no_position=len(current_records),
                accepted_signals_no_position=sum(
                    1 for record in current_records if record.accepted
                ),
                actual_trade_signals_no_position=sum(
                    1
                    for timestamp in no_position_timestamps
                    if timestamp in trade_signal_timestamps
                ),
                source_reason_codes_no_position=_joined(source_reasons),
                filter_reason_codes_no_position=_joined(filter_reasons),
                lifecycle_actions_no_position=_joined(lifecycle_actions),
                lifecycle_reasons_no_position=_joined(lifecycle_reasons),
                opening_start=float(run[0].normalized_opening),
                opening_end=float(run[-1].normalized_opening),
                slope_start=float(run[0].normalized_slope),
                slope_end=float(run[-1].normalized_slope),
            )
        )

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted
    return tuple(rows)


def _write_bucket_csv(
    bucket: str,
    rows: tuple[TrendInventoryRow, ...],
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    file_name = {
        BUCKET_SHORT: "01_SHORT_trends_1_10_bars.csv",
        BUCKET_MEDIUM: "02_MEDIUM_trends_11_20_bars.csv",
        BUCKET_LONG: "03_LONG_trends_21_plus_bars.csv",
    }[bucket]
    target = OUTPUT_DIR / file_name
    fieldnames = (
        "run_id",
        "bucket",
        "direction",
        "start_utc",
        "end_utc",
        "active_bars",
        "no_position_bars",
        "position_bars",
        "no_position_ratio_percent",
        "no_position_ranges",
        "signal_records_no_position",
        "accepted_signals_no_position",
        "actual_trade_signals_no_position",
        "source_reason_codes_no_position",
        "filter_reason_codes_no_position",
        "lifecycle_actions_no_position",
        "lifecycle_reasons_no_position",
        "opening_start",
        "opening_end",
        "slope_start",
        "slope_end",
    )
    with target.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "run_id": row.run_id,
                    "bucket": row.bucket,
                    "direction": row.direction,
                    "start_utc": row.start_utc.isoformat(),
                    "end_utc": row.end_utc.isoformat(),
                    "active_bars": row.active_bars,
                    "no_position_bars": row.no_position_bars,
                    "position_bars": row.position_bars,
                    "no_position_ratio_percent": (
                        f"{row.no_position_bars / row.active_bars * 100.0:.1f}"
                    ),
                    "no_position_ranges": row.no_position_ranges,
                    "signal_records_no_position": row.signal_records_no_position,
                    "accepted_signals_no_position": row.accepted_signals_no_position,
                    "actual_trade_signals_no_position": (
                        row.actual_trade_signals_no_position
                    ),
                    "source_reason_codes_no_position": (
                        row.source_reason_codes_no_position
                    ),
                    "filter_reason_codes_no_position": (
                        row.filter_reason_codes_no_position
                    ),
                    "lifecycle_actions_no_position": (
                        row.lifecycle_actions_no_position
                    ),
                    "lifecycle_reasons_no_position": (
                        row.lifecycle_reasons_no_position
                    ),
                    "opening_start": f"{row.opening_start:.6f}",
                    "opening_end": f"{row.opening_end:.6f}",
                    "slope_start": f"{row.slope_start:.6f}",
                    "slope_end": f"{row.slope_end:.6f}",
                }
            )
    return target


def _bucket_summary(rows: tuple[TrendInventoryRow, ...], bucket: str) -> str:
    selected = tuple(row for row in rows if row.bucket == bucket)
    directions = Counter(row.direction for row in selected)
    no_position_bars = sum(row.no_position_bars for row in selected)
    position_bars = sum(row.position_bars for row in selected)
    with_signal = sum(1 for row in selected if row.signal_records_no_position > 0)
    with_trade_signal = sum(
        1 for row in selected if row.actual_trade_signals_no_position > 0
    )
    return (
        f"runs:{len(selected)},BUY:{directions['BUY']},SELL:{directions['SELL']},"
        f"no_position_bars:{no_position_bars},position_bars:{position_bars},"
        f"runs_with_signal_records:{with_signal},"
        f"runs_with_actual_trade_signal:{with_trade_signal}"
    )


def main() -> None:
    assert_frozen_oos_snapshot()
    rows = tuple(sorted(_collect_inventory(), key=lambda item: item.start_utc))
    assert rows
    assert all(row.no_position_bars >= 1 for row in rows)

    output_paths: dict[str, Path] = {}
    for bucket in BUCKETS:
        bucket_rows = tuple(row for row in rows if row.bucket == bucket)
        output_paths[bucket] = _write_bucket_csv(bucket, bucket_rows)

    print(
        "Algorithm Workspace Candidate F Alligator ACTIVE No Position "
        "Trend Inventory 2025 result"
    )
    print("  mode=PRODUCTION_6K_CAUSAL_ACTIVE_NO_POSITION_TREND_INVENTORY_ONLY")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  signal_filter_applied=False")
    print("  alternative_stop_applied=False")
    print("  future_price_used_as_feature=False")
    print("  period=2025_frozen")
    print("  inventory_unit=ONE_DIRECTIONAL_CONTIGUOUS_ALLIGATOR_ACTIVE_RUN")
    print("  included=run_has_at_least_one_bar_without_open_position")
    print("  position_state=trade_entry<=timestamp<trade_close")
    print("  trend_buckets=SHORT:1-10,MEDIUM:11-20,LONG:21+")
    print(f"  inventory_runs={len(rows)}")
    print("  bucket_summary:")
    for bucket in BUCKETS:
        print(f"    {bucket}={_bucket_summary(rows, bucket)}")
    print(f"  output_dir={OUTPUT_DIR}")
    for bucket in BUCKETS:
        print(f"  csv_{bucket}={output_paths[bucket]}")
    print("  csv_encoding=UTF-8-SIG")
    print("  csv_delimiter=semicolon")
    print("  chronological_runs=True")
    print("  completed_bars_only=True")
    print("  causal_alligator_and_same_timestamp_signal_evidence_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print(
        "ALGORITHM_WORKSPACE_CANDIDATE_F_ALLIGATOR_ACTIVE_NO_POSITION_"
        "TREND_INVENTORY_2025_CHECK=OK"
    )


if __name__ == "__main__":
    main()
