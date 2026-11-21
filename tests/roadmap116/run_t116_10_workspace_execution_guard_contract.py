"""T116-10 · TEST_ONLY · регресійний контракт глобального guard для Workspace.

Тест виконує фактичне тіло RuntimeEngine.submit_workspace_execution_plan,
витягнуте через AST, на підставних репозиторії та брокерських сервісах.
Реальні LGE, Gateway, конфігурація, БД і брокерські з'єднання не запускаються.

Поки production guard відсутній, очікується FAIL (fail-first regression).
Після погодженої production-правки тест має проходити без змін контракту.
"""

from __future__ import annotations

import ast
import copy
import math
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
ENGINE_FILE = ROOT / "engine" / "runtime_engine.py"
TRADE_UID = "T116-10-SYNTH-TRADE"
PLAN_UID = "T116-10-SYNTH-PLAN"
ACCOUNT_ID = "T116-10-FAKE-ACCOUNT"


class AdapterIntercept(Exception):
    """Перехопити спробу submission до будь-якої зовнішньої дії."""


class UnusedBrokerException(Exception):
    """Тип для невикористаних гілок broker-exception."""


def load_workspace_submission() -> Callable[..., dict[str, Any]]:
    """Завантажити лише production-метод без імпорту runtime-пакетів."""
    tree = ast.parse(
        ENGINE_FILE.read_text(encoding="utf-8"),
        filename=str(ENGINE_FILE),
    )
    engine_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RuntimeEngine"
    )
    original_method = next(
        node for node in engine_class.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "submit_workspace_execution_plan"
    )
    method = copy.deepcopy(original_method)
    method.decorator_list = []
    module = ast.fix_missing_locations(
        ast.Module(body=[method], type_ignores=[])
    )
    namespace: dict[str, Any] = {
        "math": math,
        "datetime": datetime,
        "UTC": UTC,
        "build_broker_order_comment": (
            lambda label, control: f"{label}:{control}"
        ),
        "IBMarketOrderTimeoutError": UnusedBrokerException,
        "CTraderMarketOrderTimeoutError": UnusedBrokerException,
        "BrokerTerminalOrderFailure": UnusedBrokerException,
    }
    exec(compile(module, str(ENGINE_FILE), "exec"), namespace)
    return cast(Callable[..., dict[str, Any]], namespace[method.name])


def run_case(
    submit: Callable[..., dict[str, Any]],
    mode: str | None,
    control: str,
    broker: str,
) -> str:
    """Перевірити, чи реальний boundary дозволив перехід до fake adapter."""
    repository = Mock()
    repository.get_trade_chain.return_value = {
        "trade": {
            "source": "WORKSPACE",
            "broker": broker,
            "account_id": ACCOUNT_ID,
            "control_mode": control,
            "execution_state": "READY_FOR_SUBMISSION",
            "symbol": "EURUSD",
            "volume": 1000.0,
        },
        "order_plans": [{
            "source": "WORKSPACE",
            "order_plan_uid": PLAN_UID,
            "side": "BUY",
            "volume": 1000.0,
            "stop_loss": 1.08,
        }],
        "broker_orders": [],
    }
    repository.create_broker_order.side_effect = AssertionError(
        "TEST_ONLY: спроба запису в БД"
    )

    service = Mock()

    def intercept_market_order(**payload: Any) -> None:
        """Перевірити payload та зупинитися перед broker API."""
        assert payload["symbol_name"] == "EURUSD"
        assert payload["side"] == "BUY"
        if broker == "CTRADER":
            assert math.isclose(payload["lots"], 0.01, abs_tol=1e-12)
        else:
            assert math.isclose(payload["quantity"], 1000.0, abs_tol=1e-12)
        raise AdapterIntercept()

    service.place_market_order.side_effect = intercept_market_order

    def validate_binding(name: str, account: str) -> None:
        assert name == broker and account == ACCOUNT_ID

    engine = SimpleNamespace(
        context=SimpleNamespace(execution_mode=mode),
        repository=repository,
        ctrader_runtime_service=service if broker == "CTRADER" else None,
        ib_runtime_service=service if broker == "IB" else None,
        validate_workspace_broker_binding=validate_binding,
    )

    try:
        submit(engine, TRADE_UID, PLAN_UID)
    except AdapterIntercept:
        observed = "FAKE_SUBMIT_REACHED"
    except (RuntimeError, PermissionError, ValueError):
        observed = "BLOCKED"
    else:
        raise AssertionError("Тестовий submission повернув результат без перехоплення")

    assert repository.create_broker_order.call_count == 0
    assert service.place_market_order.call_count == int(
        observed == "FAKE_SUBMIT_REACHED"
    )
    return observed


def test_workspace_global_execution_guard() -> None:
    """Вимагати незалежний fail-closed guard для двох брокерів."""
    print("T116-10 TEST_ONLY | Workspace execution fail-closed contract")
    submit = load_workspace_submission()
    modes = ("OFF", "MANUAL", "SEMI", "AUTO", "INVALID", "", None)
    brokers = ("CTRADER", "IB")
    controls = ("AUTO", "SEMI")
    mismatches = []
    cases = 0

    for broker in brokers:
        for mode in modes:
            for control in controls:
                cases += 1
                expected = (
                    "FAKE_SUBMIT_REACHED"
                    if mode == "AUTO" and control == "AUTO"
                    else "BLOCKED"
                )
                observed = run_case(submit, mode, control, broker)
                displayed_mode = "NONE" if mode is None else (mode or "EMPTY")
                print(
                    f"broker={broker} global={displayed_mode} wsp={control} "
                    f"expected={expected} actual={observed}"
                )
                if observed != expected:
                    mismatches.append((broker, displayed_mode, control))

    print(f"policy_cases={cases}")
    print(f"policy_mismatches={len(mismatches)}")
    print("broker_requests=0")
    print("database_writes=0")
    print("config_writes=0")
    print("production_changes=0")
    print("manual_order_paths=NOT_TESTED")
    print("gui_runtime_sync=NOT_TESTED")

    if mismatches:
        print("T116-10=RED_WORKSPACE_GUARD_CONTRACT")
        raise AssertionError(
            "Workspace execution guard порушує модель допуску: "
            f"{len(mismatches)} із {cases} сценаріїв; "
            "це очікуваний fail-first RED для поточного production"
        )

    print("T116-10=GREEN_WORKSPACE_GUARD_CONTRACT")


if __name__ == "__main__":
    test_workspace_global_execution_guard()
