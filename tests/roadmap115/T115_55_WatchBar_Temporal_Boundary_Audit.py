# -*- coding: utf-8 -*-
"""RoadMap115 / T115-55: WatchBar temporal boundary audit.

TEST_ONLY / DATA_ONLY.

Перевіряється часова послідовність:
strict_state.at -> boundary_state.at -> entry_at.

Окремо обліковуються зміни phase, regime та class.
Майбутній результат угоди не використовується
для класифікації або створення торгових правил.

Часова мітка не є доказом доступності значення
до фактичного рішення про відкриття ордера.

Production, MD7 та Replay не змінюються.
"""

from __future__ import annotations

import hashlib
import math
import sys
from collections import Counter
from datetime import timedelta
from importlib import import_module
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = ROOT / "tests" / "roadmap115"

for directory in (ROOT, TEST_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

t47 = import_module("T115_47_Pre_Entry_Non_BE_Loss_Anatomy")

EXPECTED_STEP = timedelta(minutes=15)
EXPECTED_TRADES = 333

BUY = t47.BUY
SELL = t47.SELL


def _sha(path: Path) -> str:
    """Обчислити контрольний SHA256."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for block in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def _changes(rows: list[Any]) -> tuple[int, int, int]:
    """Порахувати незалежні зміни трьох ознак."""
    phase = sum(item.strict_state.phase != item.boundary_state.phase for item in rows)

    regime = sum(
        item.strict_state.regime != item.boundary_state.regime for item in rows
    )

    classification = sum(item.strict_class != item.boundary_class for item in rows)

    return phase, regime, classification


def _time_audit(
    rows: list[Any],
    period: str,
) -> int:
    """Перевірити часові інваріанти без припущень про fill."""
    strict_lags: Counter[float] = Counter()
    boundary_lags: Counter[float] = Counter()
    state_steps: Counter[float] = Counter()

    anomalies = 0

    for item in rows:
        entry_at = item.entry_at

        strict_at = item.strict_state.at
        boundary_at = item.boundary_state.at

        strict_lag = entry_at - strict_at
        boundary_lag = entry_at - boundary_at
        state_step = boundary_at - strict_at

        strict_lags[strict_lag.total_seconds() / 60] += 1

        boundary_lags[boundary_lag.total_seconds() / 60] += 1

        state_steps[state_step.total_seconds() / 60] += 1

        correct = (
            strict_lag == EXPECTED_STEP
            and boundary_lag == timedelta(0)
            and state_step == EXPECTED_STEP
            and item.strict_age_min == 15
            and item.entry_at == item.trade.entry_at
        )

        if not correct:
            anomalies += 1

            print(
                f"TEMPORAL_ANOMALY|PERIOD={period}|"
                f"SIDE={item.trade.direction}|"
                f"ENTRY={entry_at.isoformat()}|"
                f"STRICT={strict_at.isoformat()}|"
                f"BOUNDARY={boundary_at.isoformat()}|"
                f"AGE_MIN={item.strict_age_min}"
            )

    print(
        f"TEMPORAL_DISTRIBUTION|PERIOD={period}|"
        f"STRICT_LAG_MIN={sorted(strict_lags.items())}|"
        f"BOUNDARY_LAG_MIN={sorted(boundary_lags.items())}|"
        f"STATE_STEP_MIN={sorted(state_steps.items())}|"
        f"ANOMALIES={anomalies}"
    )

    return anomalies


def _transition_report(rows: list[Any]) -> None:
    """Показати фактичні переходи станів."""
    phases: Counter[tuple[str, str]] = Counter()
    regimes: Counter[tuple[str, str]] = Counter()
    classes: Counter[tuple[str, str]] = Counter()

    for item in rows:
        phases[
            item.strict_state.phase,
            item.boundary_state.phase,
        ] += 1

        regimes[
            item.strict_state.regime,
            item.boundary_state.regime,
        ] += 1

        classes[
            item.strict_class,
            item.boundary_class,
        ] += 1

    assert sum(phases.values()) == len(rows)
    assert sum(regimes.values()) == len(rows)
    assert sum(classes.values()) == len(rows)

    for label, transitions in (
        ("PHASE", phases),
        ("REGIME", regimes),
        ("CLASS", classes),
    ):
        for (before, after), count in sorted(transitions.items()):
            print(
                f"WATCHBAR_TRANSITION|TYPE={label}|"
                f"FROM={before}|TO={after}|"
                f"COUNT={count}"
            )

        print(f"WATCHBAR_TRANSITION_RECONCILIATION=" f"{label}:OK")


def _synthetic() -> None:
    """Перевірити незалежність змін phase і regime."""

    class State:
        """Синтетичний стан."""

        def __init__(
            self,
            phase: str,
            regime: str,
        ) -> None:
            self.phase = phase
            self.regime = regime

    class Item:
        """Синтетичний запис аудиту."""

        def __init__(
            self,
            strict: State,
            boundary: State,
            strict_class: str,
            boundary_class: str,
        ) -> None:
            self.strict_state = strict
            self.boundary_state = boundary
            self.strict_class = strict_class
            self.boundary_class = boundary_class

    samples: list[Any] = [
        Item(
            State("ACTIVE", "UP"),
            State("ENDING", "UP"),
            "A",
            "B",
        ),
        Item(
            State("ACTIVE", "UP"),
            State("ACTIVE", "DOWN"),
            "A",
            "A",
        ),
        Item(
            State("NONE", "FLAT"),
            State("NONE", "FLAT"),
            "C",
            "C",
        ),
    ]

    assert _changes(samples) == (1, 1, 1)

    print("SYNTHETIC_INDEPENDENT_STATE_CHANGES=OK")


def main() -> None:
    """Звірити хронологію й переходи без торгових змін."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        TEST_DIR / "T115_32_Cross_Period_M15_Entry_State_Audit.py",
        TEST_DIR / "T115_47_Pre_Entry_Non_BE_Loss_Anatomy.py",
        TEST_DIR / "T115_54_WatchBar_Entry_Evidence_Schema_Audit.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-55|TEST_ONLY|" "WATCHBAR_TEMPORAL_BOUNDARY_AUDIT")
    print("SOURCE=FROZEN_T115_32")
    print("EXPECTED_STRICT_AGE_MIN=15")
    print("EXECUTION_ORDER_PROVEN=False")
    print("NO_NEW_ENTRY_RULE=True")

    _synthetic()

    windows = t47.load_windows()

    assert len(windows) == 4

    pooled: list[Any] = []
    total_anomalies = 0

    for window in windows:
        expected_count, expected_net, _, expected_open = t47.EXPECTED[window.name]

        rows: list[Any] = list(window.entries)

        assert len(rows) == expected_count
        assert window.open_end == expected_open

        net = math.fsum(float(item.trade.pips) - t47.COST for item in rows)

        assert math.isclose(
            net,
            expected_net,
            abs_tol=t47.EPS,
        )

        print(
            f"BASELINE_MATCH={window.name}:OK|"
            f"CLOSED={len(rows)}|"
            f"NET040={net:+.2f}|"
            f"OPEN_END={window.open_end}"
        )

        total_anomalies += _time_audit(
            rows,
            window.name,
        )

        for side in (BUY, SELL):
            selected = [item for item in rows if item.trade.direction == side]

            phase, regime, classification = _changes(selected)

            print(
                f"WATCHBAR_CHANGES|PERIOD={window.name}|"
                f"SIDE={side}|TRADES={len(selected)}|"
                f"PHASE={phase}|REGIME={regime}|"
                f"CLASS={classification}"
            )

        pooled.extend(rows)

    assert len(pooled) == EXPECTED_TRADES

    phase, regime, classification = _changes(pooled)

    both_phase_regime = sum(
        item.strict_state.phase != item.boundary_state.phase
        and item.strict_state.regime != item.boundary_state.regime
        for item in pooled
    )

    both_phase_class = sum(
        item.strict_state.phase != item.boundary_state.phase
        and item.strict_class != item.boundary_class
        for item in pooled
    )

    print(
        f"POOLED_WATCHBAR_CHANGES|TRADES={len(pooled)}|"
        f"PHASE={phase}|REGIME={regime}|"
        f"CLASS={classification}|"
        f"PHASE_AND_REGIME={both_phase_regime}|"
        f"PHASE_AND_CLASS={both_phase_class}"
    )

    assert (phase, regime, classification) == (56, 27, 56)

    print("T115_54_STATE_CHANGE_COUNTS_MIRROR=OK")

    _transition_report(pooled)

    print(f"TEMPORAL_SEQUENCE_ANOMALIES=" f"{total_anomalies}")

    assert total_anomalies == 0

    assert before == [_sha(path) for path in guarded]

    print("FOUR_PERIOD_BASELINE_RECONCILIATION=OK")
    print("WATCHBAR_TIMESTAMP_SEQUENCE_333_OF_333=OK")
    print("TIMESTAMPS_ARE_NOT_EXECUTION_ORDER_PROOF=True")
    print("BOUNDARY_CAUSAL_PROVENANCE_UNVERIFIED=True")
    print("FUTURE_PNL_NOT_USED=True")
    print("NO_ENTRY_GATE_CREATED=True")
    print("NO_REPLAY_CHANGE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_55_WATCHBAR_TEMPORAL_BOUNDARY_AUDIT=OK")


if __name__ == "__main__":
    main()
