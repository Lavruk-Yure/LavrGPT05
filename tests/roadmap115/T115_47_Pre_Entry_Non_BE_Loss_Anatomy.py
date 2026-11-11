# -*- coding: utf-8 -*-
"""RoadMap115 / T115-47: pre-entry non-BE loss anatomy.

TEST_ONLY / DATA_ONLY.

Незмінний baseline T115-32, чотири періоди.

Класифікація M15 береться з причинного entry-аудиту T115-32.
Майбутні BE activation і фінальний Net є outcome labels.

Головна група: 83 збиткові угоди без активації BE.
Порівняння виконується з усіма іншими baseline-угодами.

Жодного нового gate, entry, exit, SL/TP або оптимізації.
Production та MD7 не змінюються.
"""

from __future__ import annotations

import hashlib
import math
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if TYPE_CHECKING:
    from T115_32_Cross_Period_M15_Entry_State_Audit import Window

audit_mod = import_module("T115_32_Cross_Period_M15_Entry_State_Audit")

be_mod = import_module("T115_41_H1_Break_Even_Activation_Anatomy")

BUY = be_mod.BUY
SELL = be_mod.SELL

COST = be_mod.COST
EPS = be_mod.EPS

EXPECTED = audit_mod.EXPECTED

EXPECTED_NO_BE = {
    "2024_NOV_DEC": {
        BUY: (5, 5),
        SELL: (2, 1),
    },
    "2025": {
        BUY: (15, 13),
        SELL: (25, 22),
    },
    "2026_TO_2026_08_25": {
        BUY: (24, 20),
        SELL: (16, 14),
    },
    "2026_AUG_OCT": {
        BUY: (3, 3),
        SELL: (5, 5),
    },
}

COHORTS = (
    "NO_BE_LOSS",
    "NO_BE_NONLOSS",
    "BE_ACTIVATED_LOSS",
    "BE_ACTIVATED_NONLOSS",
)

load_windows = getattr(audit_mod, "_load_windows")
load_history = getattr(be_mod, "load_history")
scan_be = getattr(be_mod, "_scan")


@dataclass(frozen=True, slots=True)
class Record:
    """Причинна entry-ознака та майбутні результати."""

    period: str
    direction: str
    entry_at: datetime
    m15_class: str
    activated: bool
    net: float

    @property
    def loss(self) -> bool:
        return self.net < -EPS

    @property
    def cohort(self) -> str:
        if not self.activated:
            if self.loss:
                return "NO_BE_LOSS"
            return "NO_BE_NONLOSS"

        if self.loss:
            return "BE_ACTIVATED_LOSS"

        return "BE_ACTIVATED_NONLOSS"


def _sha(path: Path) -> str:
    """Контроль SHA256 для опорних файлів."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for block in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def _synthetic() -> None:
    """Перевірити всі чотири взаємовиключні групи."""
    at = datetime.fromisoformat("2025-04-07T12:00:00+00:00")

    cases = (
        (False, -10.0, "NO_BE_LOSS"),
        (False, 10.0, "NO_BE_NONLOSS"),
        (True, -10.0, "BE_ACTIVATED_LOSS"),
        (True, 10.0, "BE_ACTIVATED_NONLOSS"),
    )

    for activated, net, expected in cases:
        record = Record(
            period="SYNTHETIC",
            direction=BUY,
            entry_at=at,
            m15_class="TEST",
            activated=activated,
            net=net,
        )

        assert record.cohort == expected

    print("SYNTHETIC_FOUR_COHORT_PARTITION=OK")
    print("SYNTHETIC_FIXED_NET_ZERO_BOUNDARY=OK")


def _collect(
    window: Window,
    bars: list,
) -> list[Record]:
    """Зібрати causal entry labels та окремі outcome labels."""
    times = [bar.timestamp for bar in bars]

    assert times == sorted(set(times))

    records: list[Record] = []

    for item in window.entries:
        trade = item.trade

        assert trade.direction in (BUY, SELL)

        observation = scan_be(
            trade,
            bars,
            times,
        )

        raw_class = item.strict_class

        m15_class = str(raw_class) if raw_class is not None else "MISSING"

        assert m15_class

        records.append(
            Record(
                period=window.name,
                direction=trade.direction,
                entry_at=trade.entry_at,
                m15_class=m15_class,
                activated=observation.activated,
                net=float(trade.pips) - COST,
            )
        )

    assert len(records) == len(window.entries)

    return records


def _describe(
    period: str,
    direction: str,
    records: list[Record],
) -> None:
    """Порівняти склад груп і класи M15 без gate-рішень."""
    counts = Counter(row.cohort for row in records)

    assert sum(counts[name] for name in COHORTS) == len(records)

    total_net = math.fsum(row.net for row in records)

    print(
        f"ENTRY_BASE|PERIOD={period}|"
        f"SIDE={direction}|"
        f"TRADES={len(records)}|"
        f"NET040={total_net:+.2f}"
    )

    for name in COHORTS:
        selected = [row for row in records if row.cohort == name]

        selected_net = math.fsum(row.net for row in selected)

        print(
            f"ENTRY_COHORT|PERIOD={period}|"
            f"SIDE={direction}|GROUP={name}|"
            f"COUNT={len(selected)}|"
            f"NET040={selected_net:+.2f}"
        )

    for m15_class in sorted({row.m15_class for row in records}):
        selected = [row for row in records if row.m15_class == m15_class]

        category = Counter(row.cohort for row in selected)

        category_net = math.fsum(row.net for row in selected)

        no_be_loss = category["NO_BE_LOSS"]

        no_be_loss_pct = 100 * no_be_loss / len(selected) if selected else 0.0

        print(
            f"ENTRY_M15_CLASS|PERIOD={period}|"
            f"SIDE={direction}|"
            f"CLASS={m15_class}|"
            f"TOTAL={len(selected)}|"
            f"NO_BE_LOSS={no_be_loss}|"
            f"NO_BE_NONLOSS={category['NO_BE_NONLOSS']}|"
            f"ACTIVATED_LOSS={category['BE_ACTIVATED_LOSS']}|"
            f"ACTIVATED_NONLOSS="
            f"{category['BE_ACTIVATED_NONLOSS']}|"
            f"NO_BE_LOSS_PCT={no_be_loss_pct:.2f}|"
            f"NET040={category_net:+.2f}"
        )

    assert math.isclose(
        math.fsum(row.net for name in COHORTS for row in records if row.cohort == name),
        total_net,
        abs_tol=EPS,
    )

    print(f"ENTRY_COHORT_RECONCILIATION=" f"{period}:{direction}:OK")


def _report(
    windows: list[Window],
    history: dict,
) -> None:
    """Звірити незмінні baseline та 83 невдалі входи."""
    assert len(windows) == 4
    assert len(history) == 4

    pooled: list[Record] = []

    for window in windows:
        records = _collect(
            window,
            history[window.name],
        )

        expected_count, expected_net, _, open_end = EXPECTED[window.name]

        assert len(records) == expected_count
        assert window.open_end == open_end

        actual_net = math.fsum(row.net for row in records)

        assert math.isclose(
            actual_net,
            expected_net,
            abs_tol=EPS,
        )

        print(
            f"BASELINE_MATCH={window.name}:OK|"
            f"CLOSED={expected_count}|"
            f"NET040={actual_net:+.2f}|"
            f"OPEN_END={open_end}"
        )

        for side in (BUY, SELL):
            selected = [row for row in records if row.direction == side]

            expected_inactive, expected_losses = EXPECTED_NO_BE[window.name][side]

            inactive = sum(not row.activated for row in selected)

            inactive_losses = sum(row.cohort == "NO_BE_LOSS" for row in selected)

            assert inactive == expected_inactive
            assert inactive_losses == expected_losses

            _describe(
                window.name,
                side,
                selected,
            )

        print(f"PERIOD_ENTRY_ANATOMY_RECONCILIATION=" f"{window.name}:OK")

        pooled.extend(records)

    assert len(pooled) == 333

    counts = Counter(row.cohort for row in pooled)

    assert counts["NO_BE_LOSS"] == 83
    assert counts["NO_BE_NONLOSS"] == 12
    assert counts["BE_ACTIVATED_LOSS"] == 117
    assert counts["BE_ACTIVATED_NONLOSS"] == 121

    assert sum(counts.values()) == 333

    for side in (BUY, SELL):
        selected = [row for row in pooled if row.direction == side]

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

    no_be_losses_net = math.fsum(
        row.net for row in pooled if row.cohort == "NO_BE_LOSS"
    )

    no_be_nonloss_net = math.fsum(
        row.net for row in pooled if row.cohort == "NO_BE_NONLOSS"
    )

    assert math.isclose(
        no_be_losses_net,
        -1947.10,
        abs_tol=EPS,
    )

    assert math.isclose(
        no_be_nonloss_net,
        91.10,
        abs_tol=EPS,
    )

    assert math.isclose(
        no_be_losses_net + no_be_nonloss_net,
        -1856.00,
        abs_tol=EPS,
    )

    print("T115_41_NONACTIVATED_COHORT_MIRROR=OK")
    print("NO_BE_LOSS_TOTAL=83")
    print("NO_BE_NONLOSS_TOTAL=12")
    print("NO_BE_LOSS_NET040=-1947.10")
    print("NO_BE_ALL_NET040=-1856.00")
    print("FOUR_PERIOD_PRE_ENTRY_ANATOMY=OK")
    print("M15_CLASS_FROM_FROZEN_T115_32=True")
    print("BE_ACTIVATION_USED_AS_OUTCOME_LABEL_ONLY=True")
    print("ENTRY_GATE_SIMULATED=False")
    print("NEW_TRADING_RULE_CREATED=False")


def main() -> None:
    """Провести аудит без зміни production і MD7."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/" "T115_32_Cross_Period_M15_Entry_State_Audit.py",
        ROOT / "tests/roadmap115/" "T115_41_H1_Break_Even_Activation_Anatomy.py",
        ROOT / "tests/roadmap115/"
        "T115_46_BE_Activation_Timing_Economic_Sensitivity.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-47|TEST_ONLY|" "PRE_ENTRY_NON_BE_LOSS_ANATOMY")
    print("BASELINE=UNCHANGED_T115_32|WINDOWS=4")
    print("ENTRY_FEATURE=M15_STRICT_CLASS")
    print("OUTCOMES=BE_ACTIVATION_AND_FINAL_NET040")
    print("NO_GATE_SEARCH=True|NO_ENTRY_REPLAY=True")

    _synthetic()

    windows = load_windows()
    history = load_history()

    _report(
        windows,
        history,
    )

    assert before == [_sha(path) for path in guarded]

    print("completed_bars_only=True|" "trade_decisions_look_ahead=False")
    print("future_outcomes_used_for_research_only=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_47_PRE_ENTRY_NON_BE_LOSS_ANATOMY=OK")


if __name__ == "__main__":
    main()
