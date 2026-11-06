# -*- coding: utf-8 -*-
"""RoadMap115 / T115-35: first-H1 risk separation.

TEST_ONLY / DATA_ONLY.

Незмінний baseline T115-32 для чотирьох періодів.
Перша завершена H1: негативний чи ненегативний рух.

Умови придатності:
- H1 повністю завершена;
- позиція ще відкрита після контрольного моменту;
- немає підстановки відсутніх історичних даних.

Кінцевий PnL — тільки outcome label.
Жодних нових entry, exit, SL/TP або торгових порогів.
"""

from __future__ import annotations

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
    from T115_01_Alligator_Entry_Only_Events import Bar
    from T115_02_Alligator_Exit_Only_Trades import ClosedTrade
    from T115_32_Cross_Period_M15_Entry_State_Audit import Window

early_mod = import_module("T115_34_H1_Early_Close_Outcome_Anatomy")

audit_mod = import_module("T115_32_Cross_Period_M15_Entry_State_Audit")

BUY = early_mod.BUY
SELL = early_mod.SELL

COST = early_mod.COST
EPS = 1e-6
H1_SPAN = timedelta(hours=1)

EXPECTED = audit_mod.EXPECTED

load_windows = getattr(early_mod, "load_windows")
load_history = getattr(early_mod, "load_history")
early_close = getattr(early_mod, "_early_close")
synthetic_early = getattr(early_mod, "_synthetic")


@dataclass(frozen=True, slots=True)
class Record:
    """Causal H1-ознака та майбутній результат baseline."""

    first_h1_pips: float
    final_net_pips: float


@dataclass(frozen=True, slots=True)
class Coverage:
    """Кількість придатних і виключених угод."""

    total: int
    active: int
    closed_at_checkpoint: int
    missing_h1: int


def _sha(path: Path) -> str:
    """Обчислити SHA256 для контролю незмінності файлів."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _net(trade: ClosedTrade) -> float:
    """Фактичний baseline PnL з умовними витратами."""
    return float(trade.pips) - COST


def _still_open(
    entry_at: datetime,
    exit_at: datetime,
) -> bool:
    """Позиція повинна існувати після завершення першої H1."""
    assert entry_at < exit_at

    checkpoint = entry_at + H1_SPAN

    return exit_at > checkpoint


def _negative(value: float) -> bool:
    """Фіксований нульовий роздільник, без оптимізації."""
    return value < -EPS


def _loss(value: float) -> bool:
    """Мітка збиткової завершеної угоди."""
    return value < -EPS


def _synthetic() -> None:
    """Перевірити часову межу та бухгалтерію груп."""
    at = datetime(2026, 1, 12, 10, tzinfo=UTC)

    assert not _still_open(
        at,
        at + H1_SPAN,
    )

    assert _still_open(
        at,
        at + 2 * H1_SPAN,
    )

    assert _negative(-0.01)
    assert not _negative(0.0)
    assert not _negative(0.01)

    rows = [
        Record(-5.0, -20.0),
        Record(-2.0, 10.0),
        Record(3.0, -4.0),
        Record(2.0, 7.0),
    ]

    negative = [row for row in rows if _negative(row.first_h1_pips)]

    nonnegative = [row for row in rows if not _negative(row.first_h1_pips)]

    assert len(negative) == 2
    assert len(nonnegative) == 2

    assert sum(_loss(row.final_net_pips) for row in negative) == 1

    assert sum(_loss(row.final_net_pips) for row in nonnegative) == 1

    assert math.isclose(
        math.fsum(row.final_net_pips for row in rows),
        -7.0,
        abs_tol=EPS,
    )

    print("SYNTHETIC_STRICT_OPEN_CHECKPOINT=OK")
    print("SYNTHETIC_FIXED_ZERO_PARTITION=OK")
    print("SYNTHETIC_OUTCOME_PARTITION=OK")


def _collect(
    window: Window,
    side: str,
    bars: list[Bar],
) -> tuple[list[Record], Coverage]:
    """Зібрати лише доступні для спостереження позиції."""
    times = [bar.timestamp for bar in bars]

    assert times == sorted(set(times))

    entries = [item for item in window.entries if item.trade.direction == side]

    records: list[Record] = []

    already_closed = 0
    missing_h1 = 0

    for item in entries:
        trade = item.trade

        if not _still_open(
            trade.entry_at,
            trade.exit_at,
        ):
            already_closed += 1
            continue

        value = early_close(
            trade,
            bars,
            times,
            1,
        )

        if value is None:
            missing_h1 += 1
            continue

        assert math.isfinite(value)

        records.append(
            Record(
                first_h1_pips=value,
                final_net_pips=_net(trade),
            )
        )

    coverage = Coverage(
        total=len(entries),
        active=len(records),
        closed_at_checkpoint=already_closed,
        missing_h1=missing_h1,
    )

    assert (
        coverage.active + coverage.closed_at_checkpoint + coverage.missing_h1
        == coverage.total
    )

    return records, coverage


def _fmt(value: float | None) -> str:
    """Показати відсутню оцінку без вигаданого нуля."""
    if value is None:
        return "NA"

    return f"{value:+.2f}"


def _describe(
    period: str,
    side: str,
    records: list[Record],
) -> None:
    """Побудувати 2x2 таблицю без торгового рішення."""
    negative = [row for row in records if _negative(row.first_h1_pips)]

    nonnegative = [row for row in records if not _negative(row.first_h1_pips)]

    assert len(negative) + len(nonnegative) == len(records)

    for label, group in (
        ("NEGATIVE", negative),
        ("NONNEGATIVE", nonnegative),
    ):
        count = len(group)

        losses = sum(_loss(row.final_net_pips) for row in group)

        nonlosses = count - losses

        net = math.fsum(row.final_net_pips for row in group)

        loss_rate = 100 * losses / count if count else None

        mean_net = net / count if count else None

        print(
            f"H1_GROUP|PERIOD={period}|"
            f"SIDE={side}|SIGN={label}|"
            f"COUNT={count}|LOSSES={losses}|"
            f"NONLOSSES={nonlosses}|"
            f"LOSS_RATE_PCT={_fmt(loss_rate)}|"
            f"NET040={net:+.2f}|"
            f"MEAN_NET040={_fmt(mean_net)}"
        )

    a = sum(_loss(row.final_net_pips) for row in negative)

    b = len(negative) - a

    c = sum(_loss(row.final_net_pips) for row in nonnegative)

    d = len(nonnegative) - c

    if negative and nonnegative:
        risk_negative = a / len(negative)
        risk_nonnegative = c / len(nonnegative)

        risk_diff = 100 * (risk_negative - risk_nonnegative)
    else:
        risk_diff = None

    assert a + b + c + d == len(records)

    print(
        f"H1_2X2|PERIOD={period}|"
        f"SIDE={side}|"
        f"NEG_LOSS={a}|NEG_NONLOSS={b}|"
        f"NONNEG_LOSS={c}|NONNEG_NONLOSS={d}|"
        f"RISK_DIFF_PP={_fmt(risk_diff)}"
    )

    print(f"H1_PARTITION_RECONCILIATION=" f"{period}:{side}:OK")


def _report(
    windows: list[Window],
    history: dict[str, list[Bar]],
) -> None:
    """Порівняти всі чотири періоди без зміни Replay."""
    assert len(windows) == 4
    assert len(history) == 4

    pooled: dict[str, list[Record]] = {
        BUY: [],
        SELL: [],
    }

    for window in windows:
        count, expected_net, _, open_end = EXPECTED[window.name]

        assert len(window.entries) == count
        assert window.open_end == open_end

        baseline_net = math.fsum(_net(item.trade) for item in window.entries)

        assert math.isclose(
            baseline_net,
            expected_net,
            abs_tol=EPS,
        )

        print(
            f"BASELINE|PERIOD={window.name}|"
            f"CLOSED={count}|"
            f"NET040={expected_net:+.2f}|"
            f"OPEN_END={open_end}"
        )

        for side in (BUY, SELL):
            records, coverage = _collect(
                window,
                side,
                history[window.name],
            )

            print(
                f"H1_COVERAGE|PERIOD={window.name}|"
                f"SIDE={side}|"
                f"TOTAL={coverage.total}|"
                f"ACTIVE={coverage.active}|"
                f"CLOSED_AT_CHECKPOINT="
                f"{coverage.closed_at_checkpoint}|"
                f"MISSING_H1={coverage.missing_h1}"
            )

            _describe(
                window.name,
                side,
                records,
            )

            pooled[side].extend(records)

        print(f"PERIOD_FIRST_H1_RECONCILIATION=" f"{window.name}:OK")

    for side in (BUY, SELL):
        print(
            f"POOLED|SIDE={side}|"
            f"ACTIVE={len(pooled[side])}|"
            "DESCRIPTIVE_ONLY=True"
        )

        _describe(
            "POOLED",
            side,
            pooled[side],
        )

    print("FOUR_PERIOD_FIRST_H1_RECONCILIATION=OK")
    print("EARLY_EXIT_SIMULATED=False")
    print("PARAMETER_OPTIMIZATION=False")


def main() -> None:
    """Провести аудит, не змінюючи production та MD7."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/" "T115_34_H1_Early_Close_Outcome_Anatomy.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-35|TEST_ONLY|FIRST_H1_RISK_SEPARATION")
    print("BASELINE=UNCHANGED_T115_32|WINDOWS=4")
    print("CHECKPOINT=ONE_COMPLETED_H1|STRICT_OPEN=True")
    print("SIGN_THRESHOLD=ZERO|NO_TUNING=True")
    print("OUTCOME=FINAL_NET040|NO_TRADING_DECISIONS=True")

    _synthetic()
    synthetic_early()

    windows = load_windows()
    history = load_history()

    _report(
        windows,
        history,
    )

    assert before == [_sha(path) for path in guarded]

    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("outcome_labels_use_future=True|future_used_for_entry=False")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_35_FIRST_H1_RISK_SEPARATION=OK")


if __name__ == "__main__":
    main()
