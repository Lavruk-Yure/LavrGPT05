"""T114-03 — вплив брокерських OHLC на MACD за однакової UTC-хронології.

TEST_ONLY / DATA_ONLY. Виключно локальні CSV EURUSD M1 за 2025 рік.
В обох прогонах однакові завершені UTC M15, порядок і cold start MACD.
Змінюються лише ціни; жодних production-виправлень або broker requests.
"""

from __future__ import annotations

import importlib
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
T112 = "run_t112_30_ib_ctrader_eurusd_2025_macd_signal_parity_check"
ANOMALY = datetime.fromisoformat("2025-04-16T21:45:00+00:00")
M15 = timedelta(minutes=15)
EXPECTED = {
    "CLASSIC_12_26_9": (23702, 1641, 0, 274, 21787),
    "NEW_DEFAULT_8_17_5": (23715, 2789, 0, 475, 20451),
}


def _load_t112():
    """Завантажити перевірений T112-30 без статичних нерозпізнаних імпортів."""
    for directory in (ROOT, ROOT / "tests" / "roadmap112"):
        location = str(directory)
        if location not in sys.path:
            sys.path.insert(0, location)
    return importlib.import_module(T112)


def _price_statistics(ct, ib, times, pip):
    """Зіставити OHLC тільки на спільних завершених UTC M15."""
    close_deltas = []
    differing_close = differing_ohlc = 0
    for stamp in times:
        left, right = ct[stamp], ib[stamp]
        assert left.timestamp == right.timestamp == stamp
        lc = (left.open, left.high, left.low, left.close)
        rc = (right.open, right.high, right.low, right.close)
        differing_ohlc += lc != rc
        differing_close += left.close != right.close
        close_deltas.append(abs(left.close - right.close) / pip)
    assert all(math.isfinite(value) for value in close_deltas)
    print(
        f"prices|compared:{len(times)}|different_ohlc:{differing_ohlc}|"
        f"different_close:{differing_close}|"
        f"median_abs_close_delta_pips:{median(close_deltas):.6f}|"
        f"max_abs_close_delta_pips:{max(close_deltas):.6f}"
    )
    assert 0 < differing_close <= differing_ohlc


def _compare_prices(label, ct_states, ib_states, timestamps, pip):
    """Підрахувати price-only відмінності MACD при однаковому warm-up."""
    same = opposite = one_side = none = sign_disagree = 0
    hist_deltas = []
    eligible = []
    for stamp in timestamps:
        left, right = ct_states[stamp], ib_states[stamp]
        assert left.warmed_up == right.warmed_up
        assert (left.histogram is None) == (right.histogram is None)
        if not left.warmed_up:
            continue
        assert left.histogram is not None and right.histogram is not None
        eligible.append(stamp)
        hist_deltas.append(abs(left.histogram - right.histogram) / pip)
        sign_disagree += (left.histogram > 0) != (right.histogram > 0)
        if left.direction is None and right.direction is None:
            none += 1
        elif left.direction is None or right.direction is None:
            one_side += 1
        elif left.direction == right.direction:
            same += 1
        else:
            opposite += 1
    counts = len(eligible), same, opposite, one_side, none
    assert sum(counts[1:]) == counts[0]
    assert all(math.isfinite(value) for value in hist_deltas)
    print(
        f"profile={label}|price_only|compared:{counts[0]}|same:{same}|"
        f"opposite:{opposite}|one_side:{one_side}|none:{none}|"
        f"hist_sign_disagree:{sign_disagree}|"
        f"median_abs_hist_delta_pips:{median(hist_deltas):.6f}|"
        f"max_abs_hist_delta_pips:{max(hist_deltas):.6f}"
    )
    return counts


def main():
    """Два cold-start MACD над однаковими UTC M15; міняється лише OHLC."""
    t112 = _load_t112()
    read = getattr(t112, "_read_complete_m15")
    run = getattr(t112, "_run_production_macd")
    profiles = getattr(t112, "_builtin_profile_uids")()

    history = t112.HISTORY
    ct_rows, ct = read(history / "CTRADER" / "EURUSD" / "M1" / t112.CT_CSV)
    ib_rows, ib = read(history / "IB" / "EURUSD" / "M1" / t112.IB_CSV)
    assert (ct_rows, ib_rows) == (370481, 368700)
    assert (len(ct), len(ib)) == (23753, 24580)
    timestamps = sorted(ct.keys() & ib.keys())
    assert len(timestamps) == 23736 and ANOMALY in timestamps
    assert len(set(timestamps)) == len(timestamps)
    assert all(a < b for a, b in zip(timestamps, timestamps[1:]))
    assert tuple(name for name, _ in profiles) == tuple(EXPECTED)
    ct_bars = [ct[stamp] for stamp in timestamps]
    ib_bars = [ib[stamp] for stamp in timestamps]

    print("T114-03|EURUSD|2025|M15|raw_macd_cross")
    print("input=LOCAL_CSV|aggregation=COMPLETE_15_CONTIGUOUS_M1")
    print("experiment=FIXED_UTC_TIMELINE_COLD_START_PRICE_ONLY")
    print("input_variable=CT_VS_IB_OHLC|broker_label=CTRADER_IN_BOTH_RUNS")
    print("bar_timestamp=UTC_START|available_not_before=UTC_START+15min")
    print(f"coverage|ct_native:{len(ct)}|ib_native:{len(ib)}|shared:{len(timestamps)}")
    _price_statistics(ct, ib, timestamps, t112.PIP)

    for name, uid in profiles:
        ct_states, ct_config = run(ct_bars, "CTRADER", uid)
        ib_prices, ib_config = run(ib_bars, "CTRADER", uid)
        assert ct_config == ib_config
        assert len(ct_states) == len(ib_prices) == len(timestamps)
        # Негативний контроль: брокерський ярлик не впливає на MACD.
        ib_label_control, control_config = run(ib_bars, "IB", uid)
        assert control_config == ct_config
        assert ib_label_control == ib_prices
        assert "source:CLOSE" in ct_config
        assert "ma:EXPONENTIAL/EXPONENTIAL|shift:0" in ct_config
        print(f"profile={name}|{ct_config}")
        print(f"profile={name}|same_prices_different_broker_label=IDENTICAL")
        result = _compare_prices(name, ct_states, ib_prices, timestamps, t112.PIP)
        assert result == EXPECTED[name], (name, result)
        if name == "NEW_DEFAULT_8_17_5":
            a, b = ct_states[ANOMALY], ib_prices[ANOMALY]
            assert a.warmed_up and b.warmed_up
            assert (a.direction, b.direction) == ("BUY", "BUY")
            print(
                f"anomaly|bar_utc:{ANOMALY.isoformat()}|"
                f"available_not_before:{(ANOMALY + M15).isoformat()}|"
                f"ct_price_cross:{a.direction}|ib_price_cross:{b.direction}|"
                f"ct_hist_pips:{a.histogram / t112.PIP:+.8f}|"
                f"ib_hist_pips:{b.histogram / t112.PIP:+.8f}"
            )
    print("attribution=PRICE_HISTORY_ONLY_UNDER_POST_HOC_COMMON_TIMELINE")
    print("limits=NO_NATIVE_TIMELINE_CAUSAL_DECOMPOSITION|LIVE_GATES_NOT_TESTED")
    print("synthetic_market_bars=0|macd_parameter_tuning=False")
    print("completed_bars_only=True|look_ahead=False|broker_requests=0")
    print("production_logic_changed=False|md7_changed=False")
    print("T114_03_BROKER_PRICE_CONTRIBUTION_ISOLATION=OK")


if __name__ == "__main__":
    main()
