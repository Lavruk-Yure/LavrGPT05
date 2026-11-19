"""T116-05 · TEST_ONLY · ізольована перевірка global OFF на Workspace submission.

Лише fake repository та fake broker service. Без конфігурації, БД, мережі й ордерів.
RED означає, що production boundary дійшов до підставного place_market_order при OFF.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.runtime_account_state import RuntimeAccountState  # noqa: E402
from engine.runtime_broker_health import RuntimeBrokerHealth  # noqa: E402
from engine.runtime_context import RuntimeContext  # noqa: E402
from engine.runtime_engine import (  # noqa: E402
    CTraderRuntimeServiceProtocol,
    RuntimeEngine,
)
from engine.runtime_state import RuntimeState  # noqa: E402

TRADE = "T11605-FAKE-TRADE"
PLAN = "T11605-FAKE-PLAN"
ACCOUNT = "T11605-FAKE-ACCOUNT"


class FakeOrderIntercept(Exception):
    """Зупинити виконання на межі підставного брокерського сервісу."""


def make_trade_chain() -> dict:
    """Зібрати валідний Workspace chain тільки в пам'яті."""
    return {
        "trade": {
            "source": "WORKSPACE",
            "broker": "CTRADER",
            "account_id": ACCOUNT,
            "control_mode": "AUTO",
            "execution_state": "READY_FOR_SUBMISSION",
            "symbol": "EURUSD",
            "volume": 1000.0,
        },
        "order_plans": [
            {
                "source": "WORKSPACE",
                "order_plan_uid": PLAN,
                "order_type": "MARKET",
                "side": "BUY",
                "volume": 1000.0,
                "stop_loss": 1.08,
            }
        ],
        "broker_orders": [],
    }


def probe_mode(mode: str) -> tuple[str, str, int]:
    """Викликати справжній RuntimeEngine.submit на ізольованих об'єктах."""
    engine = RuntimeEngine.__new__(RuntimeEngine)
    engine.context = RuntimeContext(
        runtime_state=RuntimeState.RUNNING,
        broker="CTRADER",
        account_mode="DEMO",
        execution_mode=mode,
    )
    repository = Mock()
    repository.get_trade_chain.return_value = make_trade_chain()
    repository.create_broker_order.side_effect = AssertionError(
        "TEST_ONLY: запис у БД заборонено"
    )
    engine.repository = repository

    health = RuntimeBrokerHealth()
    health.set_connected()
    service = Mock(spec=CTraderRuntimeServiceProtocol)
    service.get_broker_health.return_value = health
    service.get_account_state.return_value = RuntimeAccountState(
        account_id=ACCOUNT, broker_name="CTRADER", currency="USD"
    )
    service.place_market_order.side_effect = FakeOrderIntercept(
        "TEST_ONLY: досягнуто fake place_market_order"
    )
    engine.ctrader_runtime_service = service
    engine.ib_runtime_service = None

    # Навіть помилкова спроба встановити мережеве з'єднання буде заблокована.
    with (
        patch.object(
            socket.socket, "connect", side_effect=AssertionError("network forbidden")
        ),
        patch.object(
            socket.socket, "connect_ex", side_effect=AssertionError("network forbidden")
        ),
    ):
        try:
            engine.submit_workspace_execution_plan(TRADE, PLAN)
        except FakeOrderIntercept:
            return "FAKE_SUBMIT_REACHED", "", service.place_market_order.call_count
        except RuntimeError as error:  # noqa
            return "BLOCKED", str(error), service.place_market_order.call_count

    return "RETURNED", "", service.place_market_order.call_count


def test() -> None:
    print("T116-05 TEST_ONLY | global OFF execution boundary")

    auto_status, auto_reason, auto_attempts = probe_mode("AUTO")
    print(f"auto_result={auto_status}")
    print(f"auto_fake_attempts={auto_attempts}")
    assert (
        auto_status == "FAKE_SUBMIT_REACHED" and auto_attempts == 1
    ), f"Контроль AUTO не досяг fake boundary: {auto_reason}"

    off_status, off_reason, off_attempts = probe_mode("OFF")
    print(f"off_result={off_status}")
    print(f"off_fake_attempts={off_attempts}")
    print("real_broker_requests=0")
    print("database_writes=0")
    print("production_changes=0")
    print("active_lge_session=NOT_CHECKED")

    if off_status == "FAKE_SUBMIT_REACHED":
        print("T116-05=RED_GLOBAL_OFF_BYPASS")
        raise AssertionError("Execution OFF не заблокував fake place_market_order")

    reason = off_reason.casefold()
    if (
        off_status == "BLOCKED"
        and off_attempts == 0
        and any(word in reason for word in ("off", "execution", "disabled", "вимк"))
    ):
        print("T116-05=GREEN_OFF_BLOCKS_SUBMISSION")
        return

    print(f"unexpected_block_reason={off_reason}")
    print("T116-05=RED_INCONCLUSIVE")
    raise AssertionError("OFF не підтверджений окремим execution guard")


if __name__ == "__main__":
    try:
        test()
    except Exception as error:
        print(f"failure={type(error).__name__}: {error}")
        raise SystemExit(1)
