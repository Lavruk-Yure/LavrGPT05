"""T114-01: аудит протилежного MACD-cross за локальними CSV.

TEST_ONLY / DATA_ONLY. Production без змін, broker_requests=0.
"""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STEP = timedelta(minutes=15)
T112_MODULE = "run_t112_30_ib_ctrader_eurusd_2025_macd_signal_parity_check"


def _load_t112():
    """Підключити наявний offline-агрегатор T112-30 без імпортів E402."""
    for directory in (ROOT, ROOT / "tests" / "roadmap112"):
        directory_str = str(directory)
        if directory_str not in sys.path:
            sys.path.insert(0, directory_str)
    return importlib.import_module(T112_MODULE)


def macd(bars, broker):
    """Обчислити raw cross штатним MACD-класом без брокерських звернень."""
    from core.workspace_indicator_profile import (
        MACD_PROFILE_UID_LGE_DEFAULT,
        WorkspaceIndicatorProfileBinding,
        built_in_workspace_indicator_profile,
    )
    from core.workspace_macd import (
        WorkspaceMacdRuntimeProfile,
        WorkspaceMacdSignalSource,
    )
    from core.workspace_market_event import WorkspaceMarketEvent

    binding = WorkspaceIndicatorProfileBinding.from_profile(
        built_in_workspace_indicator_profile(MACD_PROFILE_UID_LGE_DEFAULT)
    )
    profile = WorkspaceMacdRuntimeProfile.from_binding(binding)
    assert (
        profile.fast_period,
        profile.slow_period,
        profile.signal_period,
    ) == (8, 17, 5)
    assert (
        profile.source,
        profile.oscillator_ma_type,
        profile.signal_ma_type,
        profile.shift,
    ) == ("CLOSE", "EXPONENTIAL", "EXPONENTIAL", 0)

    source = WorkspaceMacdSignalSource(
        enabled=True, mode="LINEAR", runtime_profile=profile
    )
    signals = {}
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
        signal = source.on_market_event(event)
        if signal:
            assert signal.signal_type == "MACD_CROSS"
            signals[bar.timestamp] = signal.direction
    assert len(source.observations) == len(bars)
    return {item.timestamp: item for item in source.observations}, signals, profile


def value(number, pip):
    """Відформатувати стан MACD у pips."""
    return "NONE" if number is None else f"{number / pip:+.8f}pip"


def main():
    """Відтворити той самий єдиний протилежний перетин MACD."""
    t112 = _load_t112()
    history = getattr(t112, "HISTORY")
    ct_csv = getattr(t112, "CT_CSV")
    ib_csv = getattr(t112, "IB_CSV")
    pip = getattr(t112, "PIP")
    read_complete_m15 = getattr(t112, "_read_complete_m15")

    ct_n, ct = read_complete_m15(history / "CTRADER" / "EURUSD" / "M1" / ct_csv)
    ib_n, ib = read_complete_m15(history / "IB" / "EURUSD" / "M1" / ib_csv)
    assert (ct_n, ib_n, len(ct), len(ib)) == (370481, 368700, 23753, 24580)
    shared = sorted(ct.keys() & ib.keys())
    assert len(shared) == 23736

    native_ct = macd([ct[t] for t in sorted(ct)], "CTRADER")
    native_ib = macd([ib[t] for t in sorted(ib)], "IB")
    a, ad, p = native_ct
    b, bd, q = native_ib
    assert p == q
    anomalies = [
        t
        for t in shared
        if a[t].warmed_up
        and b[t].warmed_up
        and ad.get(t) in {"BUY", "SELL"}
        and bd.get(t) in {"BUY", "SELL"}
        and ad[t] != bd[t]
    ]
    assert len(anomalies) == 1, f"opposites={anomalies}"
    t = anomalies[0]
    assert t == datetime.fromisoformat("2025-04-16T21:45:00+00:00")
    assert ad[t] == "BUY" and bd[t] == "SELL"

    print(f"ANOMALY_UTC_BAR_START={t.isoformat()}")
    print(f"AVAILABLE_NOT_BEFORE_UTC={(t + STEP).isoformat()}")
    print(
        f"PROFILE={p.fast_period}/{p.slow_period}/{p.signal_period},"
        f"revision:{p.profile_revision}"
    )
    for label, data, states, directions in (
        ("CT_NATIVE", ct, a, ad),
        ("IB_NATIVE", ib, b, bd),
    ):
        times = sorted(data)
        index = times.index(t)
        prev = times[index - 1]
        for stamp in (prev, t):
            bar, state = data[stamp], states[stamp]
            assert state.warmed_up and state.bars_processed >= p.required_bars
            print(
                f"{label}|utc:{stamp.isoformat()}|ohlc:"
                f"{bar.open:.6f},{bar.high:.6f},{bar.low:.6f},{bar.close:.6f}|"
                f"macd:{value(state.macd_value, pip)}|"
                f"signal:{value(state.signal_value, pip)}|"
                f"hist:{value(state.histogram, pip)}|"
                f"cross:{directions.get(stamp, 'NONE')}"
            )
        assert states[prev].histogram is not None
        assert states[t].histogram is not None
        if directions[t] == "BUY":
            assert states[prev].histogram <= 0 < states[t].histogram
        else:
            assert states[prev].histogram >= 0 > states[t].histogram
        print(
            f"{label}|previous_gap_minutes:" f"{int((t - prev).total_seconds() / 60)}"
        )

    common_ct = macd([ct[s] for s in shared], "CTRADER")
    common_ib = macd([ib[s] for s in shared], "IB")
    ca, cad, _ = common_ct
    cb, cbd, _ = common_ib
    opposites_common = [
        s
        for s in shared
        if ca[s].warmed_up
        and cb[s].warmed_up
        and cad.get(s) in {"BUY", "SELL"}
        and cbd.get(s) in {"BUY", "SELL"}
        and cad[s] != cbd[s]
    ]
    assert not opposites_common
    assert cad[t] == cbd[t] == "BUY"
    print(
        f"COMMON_TIMELINE|utc:{t.isoformat()}|CT:{cad[t]}|IB:{cbd[t]}|"
        f"CT_hist:{value(ca[t].histogram, pip)}|"
        f"IB_hist:{value(cb[t].histogram, pip)}"
    )
    print("native_opposite=1|common_timeline_opposite=0")
    print("cause=NOT_UNIQUELY_IDENTIFIED_BY_T114_01")
    print("completed_bars_only=True|look_ahead=False|broker_requests=0")
    print("T114_01_SINGLE_OPPOSITE_MACD_CROSS_AUDIT=OK")


if __name__ == "__main__":
    main()
