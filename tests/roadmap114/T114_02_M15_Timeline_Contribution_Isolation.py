"""T114-02 — внесок хронології M15 у MACD raw cross EURUSD 2025.

TEST_ONLY / DATA_ONLY. Тільки локальні CSV, брокерських звернень немає.
Вплив хронології вимірюється всередині кожного брокера за незмінних OHLC.
Спільні бари визначаються ретроспективно; тест не моделює live-синхронізацію.
"""

from __future__ import annotations

import importlib
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
T112_MODULE = "run_t112_30_ib_ctrader_eurusd_2025_macd_signal_parity_check"
M15 = timedelta(minutes=15)
ANOMALY = datetime.fromisoformat("2025-04-16T21:45:00+00:00")
EXPECTED_PARITY = {
    "CLASSIC_12_26_9": ((1457, 0, 624), (1641, 0, 274)),
    "NEW_DEFAULT_8_17_5": ((2619, 1, 798), (2789, 0, 475)),
}


def _load_t112():
    """Використати перевірені CSV-агрегатор і MACD runner RoadMap112."""
    for directory in (ROOT, ROOT / "tests" / "roadmap112"):
        location = str(directory)
        if location not in sys.path:
            sys.path.insert(0, location)
    return importlib.import_module(T112_MODULE)


def _ready(*states):
    """Перевірити прогрів та визначеність гістограми всіх станів."""
    return all(state.warmed_up and state.histogram is not None for state in states)


def _parity(label, left, right, timestamps, pip):
    """Зіставити обидва брокери на строго однаковому наборі UTC M15."""
    same = opposite = one_side = none = hist_sign_disagree = 0
    histogram_differences = []
    for stamp in timestamps:
        a, b = left[stamp], right[stamp]
        assert _ready(a, b)
        histogram_differences.append(abs(a.histogram - b.histogram) / pip)
        hist_sign_disagree += (a.histogram > 0) != (b.histogram > 0)
        if a.direction is None and b.direction is None:
            none += 1
        elif a.direction is None or b.direction is None:
            one_side += 1
        elif a.direction == b.direction:
            same += 1
        else:
            opposite += 1
    assert same + opposite + one_side + none == len(timestamps)
    print(
        f"{label}|compared:{len(timestamps)}|same:{same}|"
        f"opposite:{opposite}|one_side:{one_side}|none:{none}|"
        f"hist_sign_disagree:{hist_sign_disagree}|"
        f"median_abs_hist_delta_pips:{median(histogram_differences):.6f}"
    )
    return same, opposite, one_side


def _within_broker(label, native, common, timestamps, pip):
    """Ті самі OHLC та UTC, але різна передісторія завершених M15."""
    unchanged = gained = lost = flipped = 0
    sign_changed = 0
    histogram_differences = []
    for stamp in timestamps:
        a, b = native[stamp], common[stamp]
        assert _ready(a, b)
        histogram_differences.append(abs(a.histogram - b.histogram) / pip)
        sign_changed += (a.histogram > 0) != (b.histogram > 0)
        if a.direction == b.direction:
            unchanged += 1
        elif a.direction is None:
            gained += 1
        elif b.direction is None:
            lost += 1
        else:
            assert {a.direction, b.direction} == {"BUY", "SELL"}
            flipped += 1
    changed = gained + lost + flipped
    assert changed + unchanged == len(timestamps)
    assert all(math.isfinite(v) for v in histogram_differences)
    print(
        f"{label}|compared:{len(timestamps)}|changed:{changed}|"
        f"gained:{gained}|lost:{lost}|flipped:{flipped}|"
        f"unchanged:{unchanged}|hist_sign_changed:{sign_changed}|"
        f"median_abs_hist_delta_pips:{median(histogram_differences):.6f}|"
        f"max_abs_hist_delta_pips:{max(histogram_differences):.6f}"
    )
    return changed


def main():
    """Контрольований counterfactual: тільки видалення не-спільних барів."""
    t112 = _load_t112()
    read = getattr(t112, "_read_complete_m15")
    run_macd = getattr(t112, "_run_production_macd")
    profiles = getattr(t112, "_builtin_profile_uids")()
    history = t112.HISTORY
    ct_rows, ct = read(history / "CTRADER" / "EURUSD" / "M1" / t112.CT_CSV)
    ib_rows, ib = read(history / "IB" / "EURUSD" / "M1" / t112.IB_CSV)
    assert (ct_rows, ib_rows) == (370481, 368700)
    assert (len(ct), len(ib)) == (23753, 24580)
    timestamps = sorted(ct.keys() & ib.keys())
    assert len(timestamps) == 23736
    assert ANOMALY in timestamps
    assert len(ct.keys() - ib.keys()) == 17
    assert len(ib.keys() - ct.keys()) == 844
    assert tuple(name for name, _ in profiles) == tuple(EXPECTED_PARITY)
    print("T114-02|EURUSD|2025|M15|raw_macd_cross")
    print("input=LOCAL_CSV|aggregation=COMPLETE_15_CONTIGUOUS_M1")
    print("experiment=NATIVE_VS_COMMON_WITHIN_BROKER_FIXED_OHLC")
    print("bar_timestamp=UTC_START|signal_available_not_before=UTC_START+15min")
    print(
        f"coverage|ct_native:{len(ct)}|ib_native:{len(ib)}|"
        f"shared:{len(timestamps)}|ct_only:17|ib_only:844"
    )

    for name, uid in profiles:
        ct_native, ct_description = run_macd(
            [ct[t] for t in sorted(ct)], "CTRADER", uid
        )
        ib_native, ib_description = run_macd([ib[t] for t in sorted(ib)], "IB", uid)
        ct_common, ct_common_description = run_macd(
            [ct[t] for t in timestamps], "CTRADER", uid
        )
        ib_common, ib_common_description = run_macd(
            [ib[t] for t in timestamps], "IB", uid
        )
        assert len(ct_native) == len(ct)
        assert len(ib_native) == len(ib)
        assert len(ct_common) == len(ib_common) == len(timestamps)
        assert (
            len(
                {
                    ct_description,
                    ib_description,
                    ct_common_description,
                    ib_common_description,
                }
            )
            == 1
        )
        eligible = [
            t
            for t in timestamps
            if _ready(ct_native[t], ib_native[t], ct_common[t], ib_common[t])
        ]
        assert len(eligible) > 23000
        print(f"profile={name}|{ct_description}")
        native = _parity(
            f"profile={name}|pair=NATIVE", ct_native, ib_native, eligible, t112.PIP
        )
        common = _parity(
            f"profile={name}|pair=COMMON", ct_common, ib_common, eligible, t112.PIP
        )
        assert (native, common) == EXPECTED_PARITY[name]
        ct_changes = _within_broker(
            f"profile={name}|broker=CT|native_to_common",
            ct_native,
            ct_common,
            eligible,
            t112.PIP,
        )
        ib_changes = _within_broker(
            f"profile={name}|broker=IB|native_to_common",
            ib_native,
            ib_common,
            eligible,
            t112.PIP,
        )
        print(
            f"profile={name}|changed_cross_total_CT_plus_IB:"
            f"{ct_changes + ib_changes}|not_an_additive_attribution=True"
        )
        if name == "NEW_DEFAULT_8_17_5":
            assert ANOMALY in eligible
            a = ct_native[ANOMALY]
            b = ib_native[ANOMALY]
            c = ct_common[ANOMALY]
            d = ib_common[ANOMALY]
            assert (a.direction, b.direction) == ("BUY", "SELL")
            assert (c.direction, d.direction) == ("BUY", "BUY")
            print(
                f"anomaly|bar_utc:{ANOMALY.isoformat()}|"
                f"available_not_before:{(ANOMALY + M15).isoformat()}|"
                f"ct_native:{a.direction}|ct_common:{c.direction}|"
                f"ib_native:{b.direction}|ib_common:{d.direction}|"
                f"ib_native_hist_pips:{b.histogram / t112.PIP:+.8f}|"
                f"ib_common_hist_pips:{d.histogram / t112.PIP:+.8f}"
            )
    print("scope=HISTORY_SELECTION_AND_WARMUP_NO_PRODUCTION_INTERVENTION")
    print("price_effect=NOT_ISOLATED_HERE|live_workspace_gates=NOT_TESTED")
    print("sampling=POST_HOC_SHARED_BAR_SET|synthetic_market_bars=0")
    print("completed_bars_only=True|look_ahead=False|broker_requests=0")
    print("production_logic_changed=False|md7_changed=False")
    print("T114_02_M15_TIMELINE_CONTRIBUTION_ISOLATION=OK")


if __name__ == "__main__":
    main()
