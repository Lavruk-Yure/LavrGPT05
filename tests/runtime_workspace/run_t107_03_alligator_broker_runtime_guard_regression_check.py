"""run_t107_03_alligator_broker_runtime_guard_regression_check.py — T107-03.

TEST_ONLY regression подає безпосередньо в production
``WorkspaceAlligatorFilter`` один canonical completed ``BROKER`` M15 event і
перевіряє, що read-only live/Paper market path більше не відхиляється
Replay-only guard. Event побудовано локально без broker adapter, тому runner
не виконує broker requests або execution і не змінює математику Alligator.

RED-гілка зберігає фактичний ``WorkspaceAlgorithmError`` та завершується
ненульовим exit code. GREEN можливий лише після успішного production
observation з тим самим timestamp/timeframe; фінальний marker фіксує, що
production guard справді змінено. Runner не перевіряє торгові сигнали, SL/TP,
Profit Drawdown або Replay performance.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import WORKSPACE_DATA_MODE_BROKER  # noqa: E402
from core.workspace_algorithm import WorkspaceAlgorithmError  # noqa: E402
from core.workspace_alligator import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WorkspaceAlligatorFilter,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402

TEST_ID = "T107-03"
MODE = "RM107_T107_03_ALLIGATOR_BROKER_RUNTIME_GUARD_REGRESSION_TEST_ONLY"


def _broker_event() -> WorkspaceMarketEvent:
    """Побудувати canonical completed M15 bar без звернення до брокера."""
    return WorkspaceMarketEvent(
        timestamp=datetime(2026, 9, 1, 3, 30, tzinfo=UTC),
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        bid=1.16060,
        ask=1.16080,
        spread=0.00020,
        open=1.16065,
        high=1.16085,
        low=1.16055,
        close=1.16070,
        volume=100.0,
        source_mode=WORKSPACE_DATA_MODE_BROKER,
    )


def main() -> None:
    """Підтвердити приймання BROKER event production-фільтром Alligator."""
    alligator = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
        timeframe="M15",
    )
    event = _broker_event()

    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print(f"event_source_mode={event.source_mode}")
    print("broker_requests=0")
    print("broker_execution_attempted=False")

    try:
        observation = alligator.on_market_event(event)
    except WorkspaceAlgorithmError as exc:
        print("production_logic_changed=False")
        print(f"actual_exception={type(exc).__name__}: {exc}")
        print("expected_behavior=ALLIGATOR_ACCEPTS_COMPLETED_BROKER_BAR")
        print("T107_03_ALLIGATOR_BROKER_RUNTIME_GUARD_REGRESSION=RED")
        raise AssertionError(
            "Alligator rejected a canonical completed BROKER bar"
        ) from exc

    assert observation.timestamp == event.timestamp
    assert observation.timeframe == event.timeframe
    print("production_logic_changed=True")
    print("actual_exception=NONE")
    print("T107_03_ALLIGATOR_BROKER_RUNTIME_GUARD_REGRESSION=GREEN")


if __name__ == "__main__":
    main()
