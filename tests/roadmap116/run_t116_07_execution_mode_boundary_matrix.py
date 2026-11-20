"""T116-07 · TEST_ONLY · матриця глобального execution_mode на Workspace boundary.

Виконує лише витягнутий AST-метод із підставними repo/service.
Без імпорту RuntimeEngine, конфігурації, БД або broker API.
"""

from __future__ import annotations

import ast
import copy
import math
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, cast
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "engine" / "runtime_engine.py"
TRADE = "T116-FAKE-TRADE"
PLAN = "T116-FAKE-PLAN"
ACCOUNT = "T116-FAKE-DEMO-ACCOUNT"


class InterceptBeforeBroker(Exception):
    """Перехопити виклик перед будь-яким мережевим запитом."""


class UnusedBrokerException(Exception):
    """Заглушка для except-гілок production-методу."""


def load_submit() -> Callable[..., dict[str, Any]]:
    """Витягнути фактичне тіло submit без запуску пакета LGE."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), str(SOURCE))
    runtime_cls = next(
        item
        for item in tree.body
        if isinstance(item, ast.ClassDef) and item.name == "RuntimeEngine"
    )
    method = next(
        item
        for item in runtime_cls.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "submit_workspace_execution_plan"
    )
    method = copy.deepcopy(method)
    method.decorator_list = []
    unit = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    namespace: dict[str, Any] = {
        "math": math,
        "datetime": datetime,
        "UTC": UTC,
        "build_broker_order_comment": lambda label, mode: f"{label}:{mode}",
        "IBMarketOrderTimeoutError": UnusedBrokerException,
        "CTraderMarketOrderTimeoutError": UnusedBrokerException,
        "BrokerTerminalOrderFailure": UnusedBrokerException,
    }
    exec(compile(unit, str(SOURCE), "exec"), namespace)
    return cast(Callable[..., dict[str, Any]], namespace[method.name])


def check_mode(submit: Callable[..., dict[str, Any]], mode: str, control: str) -> str:
    """Перевірити, чи production-метод дійде до підставного service."""
    repo = Mock()
    repo.get_trade_chain.return_value = {
        "trade": {
            "source": "WORKSPACE",
            "broker": "CTRADER",
            "account_id": ACCOUNT,
            "control_mode": control,
            "execution_state": "READY_FOR_SUBMISSION",
            "symbol": "EURUSD",
            "volume": 1000.0,
        },
        "order_plans": [
            {
                "source": "WORKSPACE",
                "order_plan_uid": PLAN,
                "side": "BUY",
                "volume": 1000.0,
                "stop_loss": 1.0800,
            }
        ],
        "broker_orders": [],
    }
    repo.create_broker_order.side_effect = AssertionError(
        "TEST_ONLY: DB write forbidden"
    )
    service = Mock()

    def fake_place_market_order(**payload: Any) -> None:
        assert payload["symbol_name"] == "EURUSD"
        assert payload["side"] == "BUY"
        assert math.isclose(payload["lots"], 0.01, abs_tol=1e-12)
        raise InterceptBeforeBroker()

    service.place_market_order.side_effect = fake_place_market_order

    def fake_validate_binding(broker: str, account: str) -> None:
        assert broker == "CTRADER" and account == ACCOUNT

    engine = SimpleNamespace(
        context=SimpleNamespace(execution_mode=mode),
        repository=repo,
        ctrader_runtime_service=service,
        ib_runtime_service=None,
        validate_workspace_broker_binding=fake_validate_binding,
    )

    try:
        submit(engine, TRADE, PLAN)
    except InterceptBeforeBroker:
        result = "FAKE_SUBMIT_REACHED"
    except RuntimeError:
        result = "BLOCKED"
    else:
        raise AssertionError("Unexpected execution result")

    assert repo.create_broker_order.call_count == 0
    assert service.place_market_order.call_count == int(result == "FAKE_SUBMIT_REACHED")
    print(f"global={mode or 'EMPTY'} wsp={control} boundary={result}")
    return result


def test() -> None:
    """Фіксувати поточний дефект; PASS означає RED безпеки."""
    print("T116-07 TEST_ONLY | execution-mode boundary matrix")
    submit = load_submit()
    observed = {
        (mode, control): check_mode(submit, mode, control)
        for mode in ("OFF", "MANUAL", "SEMI", "AUTO")
        for control in ("AUTO", "SEMI")
    }
    invalid = check_mode(submit, "INVALID", "AUTO")
    assert observed["OFF", "AUTO"] == "FAKE_SUBMIT_REACHED"
    assert observed["OFF", "SEMI"] == "FAKE_SUBMIT_REACHED"
    assert invalid == "FAKE_SUBMIT_REACHED"
    print("OFF_blocks_workspace_submission=NO")
    print("invalid_mode_fails_closed=NO")
    print("MANUAL_SEMI_policy=NOT_YET_APPROVED")
    print("broker_requests=0")
    print("database_writes=0")
    print("config_writes=0")
    print("production_changes=0")
    print("T116-07=RED_MODE_GUARD_ABSENT_REPRODUCED")


if __name__ == "__main__":
    test()
