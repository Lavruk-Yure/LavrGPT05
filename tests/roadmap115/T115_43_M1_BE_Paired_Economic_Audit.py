# -*- coding: utf-8 -*-
"""RoadMap115 / T115-43: M1 BE paired economic audit.

TEST_ONLY / RESEARCH_ONLY.

Використовується незмінний baseline T115-32 та T115-42.

Оцінюється парний ефект лише контактів BE, спостережених
до першої прогалини M1.

Умовна ціна:
- BE mid-рівень, якщо open ще на сприятливому боці;
- M1 open, якщо ціна вже відкрилася за BE проти позиції.

Це лише proxy стоп-виконання, не брокерський fill.
Невизначені M1-випадки не мають оціненого ефекту.

Затримка від активації: одна хвилина, як у T115-42.
Нові входи, зайнятість позиції та повний Replay відсутні.
Production і MD7 не змінюються.
"""

from __future__ import annotations

import csv
import hashlib
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if TYPE_CHECKING:
    from T115_02_Alligator_Exit_Only_Trades import ClosedTrade
    from T115_32_Cross_Period_M15_Entry_State_Audit import Window
    from T115_42_M1_Break_Even_First_Breach_Audit import Target

be_mod = import_module("T115_41_H1_Break_Even_Activation_Anatomy")

m1_mod = import_module("T115_36_First_H1_Negative_Early_Exit_Counterfactual")

breach_mod = import_module("T115_42_M1_Break_Even_First_Breach_Audit")

BUY = be_mod.BUY
SELL = be_mod.SELL
COST = be_mod.COST
PIP = be_mod.PIP
EPS = be_mod.EPS

EXPECTED = be_mod.EXPECTED

KNOWN = (
    breach_mod.BREACH_NO_GAP,
    breach_mod.BREACH_BEFORE_GAP,
)

UNCERTAIN = (
    breach_mod.GAP_BEFORE_BREACH,
    breach_mod.GAP_NO_BREACH,
)

NO_TOUCH = breach_mod.NO_BREACH
INACTIVE = breach_mod.NOT_ACTIVATED

SOURCE_FILES = breach_mod.SOURCE_FILES
M1_DIRECTORY = breach_mod.M1_DIRECTORY
M1_HEADER = breach_mod.M1_HEADER

parse_timestamp = getattr(m1_mod, "_timestamp")
build_targets = getattr(breach_mod, "_targets")
read_source = getattr(breach_mod, "_read_source")

load_windows = be_mod.load_windows
load_history = be_mod.load_history


Key = tuple[str, datetime, str]


@dataclass(frozen=True, slots=True)
class FillBar:
    """Фактичний OHLC M1 першого спостереженого контакту."""

    at: datetime
    open: float
    high: float
    low: float


@dataclass(frozen=True, slots=True)
class Pair:
    """Baseline і частково визначений BE-контрфактичний PnL."""

    trade: ClosedTrade
    status: str
    baseline_net: float
    partial_net: float
    adverse_open_gap: bool

    @property
    def delta(self) -> float:
        return self.partial_net - self.baseline_net

    @property
    def evaluated(self) -> bool:
        return self.status in KNOWN

    @property
    def unknown(self) -> bool:
        return self.status in UNCERTAIN


def _sha(path: Path) -> str:
    """Перевірити незмінність контрольних файлів."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for block in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def _baseline_net(trade: ClosedTrade) -> float:
    """Net незмінної baseline-угоди."""
    return float(trade.pips) - COST


def _proxy_net(
    trade: ClosedTrade,
    bar: FillBar,
) -> tuple[float, bool]:
    """Умовне BE-виконання на mid-OHLC, не брокерський fill."""
    assert bar.low <= bar.open <= bar.high

    if trade.direction == BUY:
        be_price = trade.entry_price + COST * PIP

        assert bar.low <= be_price + EPS * PIP

        adverse_open_gap = bar.open < be_price - EPS * PIP

        fill_price = min(
            be_price,
            bar.open,
        )

        gross = (fill_price - trade.entry_price) / PIP

    else:
        assert trade.direction == SELL

        be_price = trade.entry_price - COST * PIP

        assert bar.high >= be_price - EPS * PIP

        adverse_open_gap = bar.open > be_price + EPS * PIP

        fill_price = max(
            be_price,
            bar.open,
        )

        gross = (trade.entry_price - fill_price) / PIP

    result = gross - COST

    assert math.isfinite(result)
    assert result <= EPS

    return result, adverse_open_gap


def _synthetic() -> None:
    """Контроль ціни BE, несприятливого open та BUY/SELL."""
    make_trade = be_mod.make_trade

    at = datetime(2025, 4, 7, 12, tzinfo=UTC)

    buy = make_trade(
        direction=BUY,
        entry_at=at,
        exit_at=at + timedelta(hours=2),
        entry_price=1.1000,
        exit_price=1.0980,
        pips=-20.0,
        holding_bars=2,
        holding_minutes=120,
        exit_reason="ENDING",
        exit_gap=False,
    )

    sample_at = at + timedelta(hours=1, minutes=1)

    ordinary = FillBar(
        at=sample_at,
        open=1.1005,
        high=1.1008,
        low=1.1000,
    )

    net, adverse = _proxy_net(
        buy,
        ordinary,
    )

    assert not adverse
    assert math.isclose(net, 0.0, abs_tol=EPS)

    assert math.isclose(
        net - _baseline_net(buy),
        20.4,
        abs_tol=EPS,
    )

    gap = FillBar(
        at=sample_at,
        open=1.0990,
        high=1.0992,
        low=1.0988,
    )

    gap_net, gap_adverse = _proxy_net(
        buy,
        gap,
    )

    assert gap_adverse

    assert math.isclose(
        gap_net,
        -10.4,
        abs_tol=EPS,
    )

    sell = make_trade(
        direction=SELL,
        entry_at=at,
        exit_at=at + timedelta(hours=2),
        entry_price=1.1000,
        exit_price=1.1020,
        pips=-20.0,
        holding_bars=2,
        holding_minutes=120,
        exit_reason="ENDING",
        exit_gap=False,
    )

    sell_bar = FillBar(
        at=sample_at,
        open=1.0995,
        high=1.1001,
        low=1.0990,
    )

    sell_net, sell_adverse = _proxy_net(
        sell,
        sell_bar,
    )

    assert not sell_adverse
    assert math.isclose(
        sell_net,
        0.0,
        abs_tol=EPS,
    )

    sell_gap = FillBar(
        at=sample_at,
        open=1.1010,
        high=1.1012,
        low=1.1008,
    )

    sell_gap_net, sell_gap_adverse = _proxy_net(
        sell,
        sell_gap,
    )

    assert sell_gap_adverse

    assert math.isclose(
        sell_gap_net,
        -10.4,
        abs_tol=EPS,
    )

    # Той самий BE може обірвати майбутню прибуткову угоду.
    winner = make_trade(
        direction=BUY,
        entry_at=at,
        exit_at=at + timedelta(hours=2),
        entry_price=1.1000,
        exit_price=1.1030,
        pips=30.0,
        holding_bars=2,
        holding_minutes=120,
        exit_reason="ENDING",
        exit_gap=False,
    )

    winner_net, _ = _proxy_net(
        winner,
        ordinary,
    )

    assert winner_net - _baseline_net(winner) < 0

    print("SYNTHETIC_BE_LEVEL_NET_ZERO_PROXY=OK")
    print("SYNTHETIC_ADVERSE_OPEN_GAP_BUY=OK")
    print("SYNTHETIC_ADVERSE_OPEN_GAP_SELL=OK")
    print("SYNTHETIC_BUY_SELL_ACCOUNTING=OK")
    print("SYNTHETIC_WINNER_HARM_POSSIBLE=OK")


def _fetch_breach_bars(
    targets: dict[Key, Target],
) -> dict[Key, FillBar]:
    """Витягти M1 OHLC тільки для відомих перших контактів."""
    requested: dict[str, dict[datetime, list[Target]]] = {}

    total_requested = 0

    for target in targets.values():
        if target.status not in KNOWN:
            continue

        assert target.first_breach_at is not None

        assert target.start_at <= target.first_breach_at < target.exit_at

        filename = SOURCE_FILES[target.period]

        by_time = requested.setdefault(
            filename,
            {},
        )

        by_time.setdefault(
            target.first_breach_at,
            [],
        ).append(target)

        total_requested += 1

    assert total_requested == 169

    output: dict[Key, FillBar] = {}

    for filename, by_time in requested.items():
        path = M1_DIRECTORY / filename

        assert path.is_file()

        found_times: set[datetime] = set()

        with path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as stream:
            reader = csv.reader(stream)

            assert tuple(next(reader)) == M1_HEADER

            for cells in reader:
                assert len(cells) == len(M1_HEADER)

                at = parse_timestamp(cells[0])

                matching = by_time.get(at)

                if matching is None:
                    continue

                assert at not in found_times
                found_times.add(at)

                opening = float(cells[1])
                high = float(cells[2])
                low = float(cells[3])

                assert all(
                    math.isfinite(price) and price > 0 for price in (opening, high, low)
                )

                assert low <= opening <= high

                bar = FillBar(
                    at=at,
                    open=opening,
                    high=high,
                    low=low,
                )

                for target in matching:
                    assert target.key not in output
                    output[target.key] = bar

        assert found_times == set(by_time)

        print(
            f"M1_FILL_SOURCE|FILE={filename}|"
            f"REQUESTED_TIMESTAMPS={len(by_time)}|"
            f"FOUND_TIMESTAMPS={len(found_times)}|"
            "PRICES_IMPUTED=False"
        )

    assert len(output) == total_requested

    print("FIRST_BREACH_M1_OHLC_EXACT_MATCH=OK")

    return output


def _pair(
    period: str,
    trade: ClosedTrade,
    targets: dict[Key, Target],
    fill_bars: dict[Key, FillBar],
) -> Pair:
    """Оцінити лише визначені контакти, інші не підміняти."""
    key = (
        period,
        trade.entry_at,
        trade.direction,
    )

    baseline = _baseline_net(trade)
    target = targets.get(key)

    if target is None:
        return Pair(
            trade=trade,
            status=INACTIVE,
            baseline_net=baseline,
            partial_net=baseline,
            adverse_open_gap=False,
        )

    status = target.status

    if status in KNOWN:
        bar = fill_bars[key]

        assert target.first_breach_at == bar.at

        scenario, adverse = _proxy_net(
            trade,
            bar,
        )

        return Pair(
            trade=trade,
            status=status,
            baseline_net=baseline,
            partial_net=scenario,
            adverse_open_gap=adverse,
        )

    assert status in UNCERTAIN or status == NO_TOUCH

    # Baseline збережено тільки для бухгалтерської звірки.
    # Для UNCERTAIN результат BE лишається невідомим.
    return Pair(
        trade=trade,
        status=status,
        baseline_net=baseline,
        partial_net=baseline,
        adverse_open_gap=False,
    )


def _describe(
    period: str,
    side: str,
    rows: list[Pair],
) -> None:
    """Парний економічний баланс визначеної частини вибірки."""
    known = [row for row in rows if row.evaluated]

    unknown = [row for row in rows if row.unknown]

    untouched = [row for row in rows if row.status == NO_TOUCH]

    inactive = [row for row in rows if row.status == INACTIVE]

    assert len(known) + len(unknown) + len(untouched) + len(inactive) == len(rows)

    baseline = math.fsum(row.baseline_net for row in rows)

    partial = math.fsum(row.partial_net for row in rows)

    known_delta = math.fsum(row.delta for row in known)

    assert math.isclose(
        partial - baseline,
        known_delta,
        abs_tol=EPS,
    )

    improved = [row for row in known if row.delta > EPS]

    harmed = [row for row in known if row.delta < -EPS]

    neutral = len(known) - len(improved) - len(harmed)

    savings = math.fsum(row.delta for row in improved)

    harm = math.fsum(row.delta for row in harmed)

    assert math.isclose(
        savings + harm,
        known_delta,
        abs_tol=EPS,
    )

    affected_nonloss = sum(row.baseline_net >= -EPS for row in known)

    adverse_open = sum(row.adverse_open_gap for row in known)

    unknown_net = math.fsum(row.baseline_net for row in unknown)

    print(
        f"BE_PAIRED|PERIOD={period}|SIDE={side}|"
        f"TRADES={len(rows)}|"
        f"KNOWN_TOUCHES={len(known)}|"
        f"UNKNOWN={len(unknown)}|"
        f"NO_TOUCH={len(untouched)}|"
        f"INACTIVE={len(inactive)}|"
        f"BASE_NET040={baseline:+.2f}|"
        f"PARTIAL_NET040={partial:+.2f}|"
        f"KNOWN_DELTA={known_delta:+.2f}"
    )

    print(
        f"BE_IMPACT|PERIOD={period}|SIDE={side}|"
        f"IMPROVED={len(improved)}|"
        f"HARMED={len(harmed)}|"
        f"NEUTRAL={neutral}|"
        f"SAVINGS={savings:+.2f}|"
        f"HARM={harm:+.2f}|"
        f"BASE_NONLOSS_INTERRUPTED={affected_nonloss}|"
        f"ADVERSE_OPEN_GAP={adverse_open}"
    )

    print(
        f"BE_UNCERTAINTY|PERIOD={period}|SIDE={side}|"
        f"UNKNOWN_TRADES={len(unknown)}|"
        f"UNKNOWN_BASE_NET040={unknown_net:+.2f}|"
        "UNKNOWN_BE_RESULT=NA|"
        "FULL_STRATEGY_RESULT_AVAILABLE=False"
    )

    top_savings = sorted(
        [row.delta for row in improved],
        reverse=True,
    )[:3]

    top_sum = math.fsum(top_savings)

    print(
        f"BE_TAIL|PERIOD={period}|SIDE={side}|"
        f"TOP3_SAVINGS={top_sum:+.2f}|"
        f"DELTA_EXCLUDING_TOP3="
        f"{known_delta - top_sum:+.2f}"
    )

    print(f"BE_ECONOMIC_RECONCILIATION=" f"{period}:{side}:OK")


def _report(
    windows: list[Window],
    targets: dict[Key, Target],
    fill_bars: dict[Key, FillBar],
) -> None:
    """Виконати парну звірку всіх baseline без нових входів."""
    assert len(windows) == 4

    pooled: list[Pair] = []

    for window in windows:
        expected_count, expected_net, _, open_end = EXPECTED[window.name]

        assert len(window.entries) == expected_count
        assert window.open_end == open_end

        rows = [
            _pair(
                window.name,
                item.trade,
                targets,
                fill_bars,
            )
            for item in window.entries
        ]

        baseline = math.fsum(row.baseline_net for row in rows)

        assert math.isclose(
            baseline,
            expected_net,
            abs_tol=EPS,
        )

        print(
            f"BASELINE_MATCH={window.name}:OK|"
            f"CLOSED={expected_count}|"
            f"NET040={baseline:+.2f}|"
            f"OPEN_END={open_end}"
        )

        for side in (BUY, SELL):
            selected = [row for row in rows if row.trade.direction == side]

            _describe(
                window.name,
                side,
                selected,
            )

        _describe(
            window.name,
            "ALL",
            rows,
        )

        print(f"PERIOD_BE_ECONOMIC_RECONCILIATION=" f"{window.name}:OK")

        pooled.extend(rows)

    assert len(pooled) == 333

    for side in (BUY, SELL):
        selected = [row for row in pooled if row.trade.direction == side]

        _describe(
            "POOLED",
            side,
            selected,
        )

    _describe(
        "POOLED",
        "ALL",
        pooled,
    )

    assert sum(row.evaluated for row in pooled) == 169

    assert sum(row.unknown for row in pooled) == 34

    assert sum(row.status == NO_TOUCH for row in pooled) == 35

    assert sum(row.status == INACTIVE for row in pooled) == 95

    print("T115_42_FIRST_BREACH_COUNTS_MIRROR=OK")
    print("FOUR_PERIOD_BE_PAIRED_RECONCILIATION=OK")
    print("UNKNOWN_BE_RESULTS_NOT_ESTIMATED=True")
    print("POSITION_OCCUPANCY_REPLAYED=False")
    print("REPLACEMENT_ENTRIES_MODELLED=False")
    print("REAL_STOP_FILL_VERIFIED=False")
    print("NEW_TRADING_RULE_CREATED=False")


def main() -> None:
    """Оцінити BE без зміни production та MD7."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/" "T115_42_M1_Break_Even_First_Breach_Audit.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-43|TEST_ONLY|M1_BE_PAIRED_ECONOMIC_AUDIT")
    print("BASELINE=UNCHANGED_T115_32|WINDOWS=4")
    print("BE_ACTIVATION=FROZEN_T115_41")
    print("BE_FIRST_BREACH=FROZEN_T115_42")
    print("EXECUTION_PROXY=MID_BE_OR_ADVERSE_M1_OPEN")
    print("EFFECT_KNOWN_TOUCHES_ONLY=True")
    print("THRESHOLD_SEARCH=False|NOT_FULL_REPLAY=True")

    _synthetic()

    windows = load_windows()
    history = load_history()

    targets = build_targets(
        windows,
        history,
    )

    grouped: dict[str, list[Target]] = {}

    for target in targets.values():
        filename = SOURCE_FILES[target.period]

        grouped.setdefault(
            filename,
            [],
        ).append(target)

    for filename, selected in grouped.items():
        read_source(
            filename,
            selected,
        )

    fill_bars = _fetch_breach_bars(targets)

    _report(
        windows,
        targets,
        fill_bars,
    )

    assert before == [_sha(path) for path in guarded]

    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("M1_proxy_uses_future_only_after_activation=True")
    print("broker_requests=0|TEST_ONLY=True|RESEARCH_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_43_M1_BE_PAIRED_ECONOMIC_AUDIT=OK")


if __name__ == "__main__":
    main()
