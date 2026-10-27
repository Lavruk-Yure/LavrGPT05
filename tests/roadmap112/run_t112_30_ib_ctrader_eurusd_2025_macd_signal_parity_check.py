"""T112-30 — causal MACD parity IB / cTrader EURUSD 2025.

TEST_ONLY / DATA_ONLY: тільки історичні CSV та production MACD source.
Це не перевірка збережених профілів живих WSP і не торговий Replay.
"""

from __future__ import annotations

import csv
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
HISTORY = ROOT / "data" / "history"
CT_CSV = "2025-01-01_2025-12-31_CTRADER_EURUSD_M1.csv"
IB_CSV = "2025-01-02_2025-12-31_IB_EURUSD_M1.csv"
COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
ONE_MINUTE = timedelta(minutes=1)
FIFTEEN_MINUTES = timedelta(minutes=15)
PIP = 0.0001


@dataclass(frozen=True, slots=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True, slots=True)
class State:
    histogram: float | None
    warmed_up: bool
    direction: str | None


def _quarter_start(value: datetime) -> datetime:
    return value.replace(minute=value.minute // 15 * 15, second=0)


def _make_completed(bucket: datetime, bars: list[Bar]) -> Bar | None:
    """Видавати тільки 15 послідовних M1; час сигналу — після кінця M15."""
    if len(bars) != 15:
        return None
    if any(bar.timestamp != bucket + i * ONE_MINUTE
           for i, bar in enumerate(bars)):
        return None
    return Bar(
        timestamp=bucket,
        open=bars[0].open,
        high=max(bar.high for bar in bars),
        low=min(bar.low for bar in bars),
        close=bars[-1].close,
    )


def _read_complete_m15(path: Path) -> tuple[int, dict[datetime, Bar]]:
    """Прочитати M1 та скласти лише завершені UTC M15 без домальовування."""
    assert path.is_file(), f"HISTORY_CSV_NOT_FOUND: {path}"
    rows = 0
    last_time: datetime | None = None
    bucket: datetime | None = None
    pending: list[Bar] = []
    completed: dict[datetime, Bar] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        assert tuple(next(reader)) == COLUMNS, path.name
        for cells in reader:
            assert len(cells) == 6, (path.name, rows)
            stamp = datetime.fromisoformat(cells[0].replace("Z", "+00:00"))
            assert stamp.tzinfo is not None
            stamp = stamp.astimezone(UTC)
            assert stamp.year == 2025
            assert stamp.second == stamp.microsecond == 0
            assert last_time is None or stamp > last_time
            o, h, l, c = map(float, cells[1:5])
            assert all(math.isfinite(p) and p > 0 for p in (o, h, l, c))
            assert l <= min(o, c) <= max(o, c) <= h
            next_bucket = _quarter_start(stamp)
            if bucket is not None and next_bucket != bucket:
                bar = _make_completed(bucket, pending)
                if bar is not None:
                    completed[bucket] = bar
                pending = []
            bucket = next_bucket
            pending.append(Bar(stamp, o, h, l, c))
            last_time = stamp
            rows += 1
    if bucket is not None:
        bar = _make_completed(bucket, pending)
        if bar is not None:
            completed[bucket] = bar
    return rows, completed


def _run_production_macd(
    bars: list[Bar], broker: str, profile_uid: str,
) -> tuple[dict[datetime, State], str]:
    """Викликати фактичний MACD-клас LGE, а не дублювати його формули."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from core.workspace_indicator_profile import (
        WorkspaceIndicatorProfileBinding,
        built_in_workspace_indicator_profile,
    )
    from core.workspace_macd import (
        WorkspaceMacdRuntimeProfile,
        WorkspaceMacdSignalSource,
    )
    from core.workspace_market_event import WorkspaceMarketEvent

    profile = built_in_workspace_indicator_profile(profile_uid)
    binding = WorkspaceIndicatorProfileBinding.from_profile(profile)
    config = WorkspaceMacdRuntimeProfile.from_binding(binding)
    source = WorkspaceMacdSignalSource(
        enabled=True,
        mode="LINEAR",
        runtime_profile=config,
    )
    signals: dict[datetime, str] = {}
    for bar in bars:
        event = WorkspaceMarketEvent(
            timestamp=bar.timestamp,
            broker=broker,
            symbol="EURUSD",
            timeframe="M15",
            bid=bar.close,
            ask=bar.close,
            spread=0.0,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=0.0,
            source_mode="REPLAY",
        )
        proposal = source.on_market_event(event)
        if proposal is not None:
            assert proposal.signal_type == "MACD_CROSS"
            assert proposal.direction in {"BUY", "SELL"}
            signals[bar.timestamp] = proposal.direction
    observations = source.observations
    assert len(observations) == len(bars)
    states = {
        item.timestamp: State(
            histogram=item.histogram,
            warmed_up=item.warmed_up,
            direction=signals.get(item.timestamp),
        )
        for item in observations
    }
    description = (
        f"{config.profile_uid}|revision:{config.profile_revision}|"
        f"periods:{config.fast_period}/{config.slow_period}/"
        f"{config.signal_period}|source:{config.source}|"
        f"ma:{config.oscillator_ma_type}/{config.signal_ma_type}|"
        f"shift:{config.shift}|mode:LINEAR_RAW_CROSS"
    )
    return states, description


def _compare(
    label: str,
    left: dict[datetime, State],
    right: dict[datetime, State],
    timestamps: list[datetime],
    *,
    examples: bool = False,
) -> tuple[int, int, int, int]:
    """Зіставити тільки однакові завершені M15 з прогрітим MACD."""
    both = 0
    same = 0
    opposite = 0
    one_only = 0
    sign_different = 0
    deltas: list[float] = []
    shown = 0
    for stamp in timestamps:
        a, b = left[stamp], right[stamp]
        if not (a.warmed_up and b.warmed_up):
            continue
        if a.histogram is None or b.histogram is None:
            continue
        both += 1
        deltas.append(abs(b.histogram - a.histogram) / PIP)
        sign_different += (a.histogram > 0) != (b.histogram > 0)
        if a.direction is not None and b.direction is not None:
            if a.direction == b.direction:
                same += 1
            else:
                opposite += 1
        elif (a.direction is None) != (b.direction is None):
            one_only += 1
        if examples and a.direction != b.direction and shown < 10:
            print(
                f"{label}|mismatch={stamp.isoformat()}|"
                f"CT:{a.direction or 'NONE'}|IB:{b.direction or 'NONE'}|"
                f"hist_ct:{a.histogram / PIP:+.5f}pip|"
                f"hist_ib:{b.histogram / PIP:+.5f}pip|"
                f"available_at:{(stamp + FIFTEEN_MINUTES).isoformat()}"
            )
            shown += 1
    assert both > 1000
    abs_median = median(deltas)
    assert math.isfinite(abs_median)
    print(
        f"{label}|compared:{both}|same_cross:{same}|"
        f"opposite_cross:{opposite}|one_side_cross:{one_only}|"
        f"hist_sign_disagree:{sign_different}|"
        f"median_abs_hist_delta_pips:{abs_median:.6f}"
    )
    return both, opposite, one_only, sign_different


def _selfcheck() -> None:
    start = datetime(2025, 2, 3, 12, tzinfo=UTC)
    data = [Bar(start + ONE_MINUTE * i, 1.10, 1.11, 1.09, 1.10)
            for i in range(15)]
    ready = _make_completed(start, data)
    assert ready is not None and ready.timestamp == start
    assert _make_completed(start, data[:-1]) is None
    data[6] = Bar(start + ONE_MINUTE * 7, 1.10, 1.11, 1.09, 1.10)
    assert _make_completed(start, data) is None
    print("SYNTHETIC_COMPLETED_M15_CAUSALITY=OK")


def main() -> None:
    print("T112_30_IB_CTRADER_EURUSD_2025_MACD_SIGNAL_PARITY")
    print("test_id=T112-30|mode=RM112_T112_30_DATA_ONLY_TEST_ONLY")
    print("symbol=EURUSD|period=2025|timeframe=M15|completed_bars_only=True")
    print("profile_scope=BUILTIN_CLASSIC_AND_NEW_DEFAULT_NOT_LIVE_WSP_SNAPSHOTS")
    print("signal_scope=MACD_RAW_CROSS_ONLY_NO_ALLIGATOR_OR_QUALITY_GATE")
    print("time_semantics=BAR_START_TIMESTAMP_AVAILABLE_AT_PLUS_15_MIN")
    _selfcheck()
    ct_path = HISTORY / "CTRADER" / "EURUSD" / "M1" / CT_CSV
    ib_path = HISTORY / "IB" / "EURUSD" / "M1" / IB_CSV
    ct_count, ct_data = _read_complete_m15(ct_path)
    ib_count, ib_data = _read_complete_m15(ib_path)
    assert (ct_count, ib_count) == (370481, 368700)
    assert (len(ct_data), len(ib_data)) == (23753, 24580)
    common = sorted(ct_data.keys() & ib_data.keys())
    assert len(common) == 23736
    print(
        f"history_verified=CT_M1:{ct_count},IB_M1:{ib_count},"
        f"CT_complete_M15:{len(ct_data)},IB_complete_M15:{len(ib_data)},"
        f"shared_M15:{len(common)}"
    )
    ct_all = [ct_data[t] for t in sorted(ct_data)]
    ib_all = [ib_data[t] for t in sorted(ib_data)]
    ct_shared = [ct_data[t] for t in common]
    ib_shared = [ib_data[t] for t in common]
    from_uids = _builtin_profile_uids()
    for name, uid in from_uids:
        ct_native, details = _run_production_macd(ct_all, "CTRADER", uid)
        ib_native, _ = _run_production_macd(ib_all, "IB", uid)
        print(f"profile={name}|{details}")
        ct_cross = sum(x.direction is not None for x in ct_native.values())
        ib_cross = sum(x.direction is not None for x in ib_native.values())
        print(
            f"profile={name}|native_crosses=CT:{ct_cross},IB:{ib_cross}|"
            f"native_streams=INDEPENDENT_COMPLETED_M15"
        )
        _compare(
            f"profile={name}|case=NATIVE", ct_native, ib_native,
            common, examples=True,
        )
        ct_common, _ = _run_production_macd(ct_shared, "CTRADER", uid)
        ib_common, _ = _run_production_macd(ib_shared, "IB", uid)
        _compare(
            f"profile={name}|case=COMMON_TIMELINE_DIFFERENT_PRICES",
            ct_common, ib_common, common,
        )
        ct_copy, _ = _run_production_macd(ct_shared, "IB", uid)
        assert ct_copy == ct_common, "SAME_INPUT_MACD_NOT_DETERMINISTIC"
        print(f"profile={name}|same_input_broker_label_invariance=OK")
    print("native_vs_common=DESCRIPTIVE_COVERAGE_AND_WARMUP_SENSITIVITY")
    print("actual_live_workspace_profiles=NOT_READ")
    print("live_2026_10_26_27=NOT_COVERED_BY_2025_HISTORY")
    print("cross_match_window=EXACT_SAME_UTC_M15_ONLY")
    print("macd_quality_and_accepted_trade_signals=NOT_TESTED")
    print("historical_broker_download=NOT_REQUESTED")
    print("source_history_modified=False")
    print("production_logic_changed=False")
    print("exit_logic_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("T112_30_IB_CTRADER_EURUSD_2025_MACD_SIGNAL_PARITY=OK")


def _builtin_profile_uids() -> tuple[tuple[str, str], ...]:
    """Обрати обидва реальні вбудовані профілі, не вгадуючи live binding."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from core.workspace_indicator_profile import (
        MACD_PROFILE_UID_LGE_CLASSIC,
        MACD_PROFILE_UID_LGE_DEFAULT,
    )
    return (
        ("CLASSIC_12_26_9", MACD_PROFILE_UID_LGE_CLASSIC),
        ("NEW_DEFAULT_8_17_5", MACD_PROFILE_UID_LGE_DEFAULT),
    )


if __name__ == "__main__":
    main()
