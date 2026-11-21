"""T116-11 · TEST_ONLY · fail-first контракт Manual Order execution guard.

Фактичні production-методи витягуються через AST та викликаються лише
з підставними broker service / repository. Мережа, LGE.conf, БД і GUI
не відкриваються. RED до production-виправлення є очікуваним.
"""

from __future__ import annotations

import ast
import copy
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "engine" / "runtime_engine.py"
ACCOUNT = "T116-11-FAKE-DEMO-ACCOUNT"
MODES = ("OFF", "MANUAL", "SEMI", "AUTO", "INVALID", "", None)
ALLOWED_MODES = frozenset({"MANUAL", "SEMI", "AUTO"})
ROUTES = ("CTRADER_PUBLIC", "IB_PUBLIC", "IB_DIRECT")


class FakeBrokerIntercept(Exception):
    """Зупинити дозволений сценарій на підставному брокерському сервісі."""


class FakeIBTimeout(Exception):
    """Заглушка невикористаної гілки IB timeout."""


def read_methods() -> tuple[Callable[..., Any], Callable[..., Any]]:
    """Завантажити рівно два методи RuntimeEngine без імпорту LGE."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    engine = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RuntimeEngine"
    )
    names = {"place_manual_market_order", "_place_manual_market_order_ib"}
    selected = []

    for node in engine.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            method = copy.deepcopy(node)
            method.decorator_list = []
            selected.append(method)

    assert len(selected) == 2, "Не знайдено обидва production-методи"
    unit = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))

    def normalize_control(value: str) -> str:
        normalized = str(value).strip().upper()
        if normalized not in {"MANUAL", "SEMI", "AUTO"}:
            raise ValueError("Некоректний control_mode")
        return normalized

    namespace: dict[str, Any] = {
        "ORDER_CONTROL_MODE_MANUAL": "MANUAL",
        "normalize_order_control_mode": normalize_control,
        "strip_broker_order_identity": lambda comment: str(comment),
        "build_broker_order_comment": lambda comment, mode: f"[{mode}] {comment}",
        "IBMarketOrderTimeoutError": FakeIBTimeout,
    }
    exec(compile(unit, str(SOURCE), "exec"), namespace)
    public = cast(Callable[..., Any], namespace["place_manual_market_order"])
    direct_ib = cast(Callable[..., Any], namespace["_place_manual_market_order_ib"])
    return public, direct_ib


def run_case(
    public: Callable[..., Any],
    direct_ib: Callable[..., Any],
    route: str,
    mode: str | None,
) -> tuple[str, int, int]:
    """Повернути фактичний допуск, кількість fake-write та викликів сервісу."""
    broker = "CTRADER" if route == "CTRADER_PUBLIC" else "IB"
    repository = Mock()
    repository.create_trade.return_value = "T116-11-FAKE-TRADE"
    repository.create_order_plan.return_value = "T116-11-FAKE-PLAN"
    repository.get_pending_ib_manual_opens.return_value = []
    service = Mock()
    service.get_account_state.return_value = SimpleNamespace(account_id=ACCOUNT)
    service.get_positions.return_value = []

    def intercept_order(**payload: Any) -> None:
        assert payload["symbol_name"] == "EURUSD"
        assert payload["side"] == "BUY"
        if broker == "CTRADER":
            assert payload["lots"] == 0.01
        else:
            assert payload["quantity"] == 1000.0
        raise FakeBrokerIntercept()

    service.place_market_order.side_effect = intercept_order
    engine = SimpleNamespace(
        context=SimpleNamespace(execution_mode=mode),
        repository=repository,
        ctrader_runtime_service=service if broker == "CTRADER" else None,
        ib_runtime_service=service if broker == "IB" else None,
        get_active_broker=lambda: broker,
        _ib_lots_to_fx_quantity=lambda lots: float(lots) * 100000.0,
        _assert_ib_fx_execution_safe=Mock(),
    )
    engine._place_manual_market_order_ib = lambda **kwargs: direct_ib(engine, **kwargs)
    target = direct_ib if route == "IB_DIRECT" else public

    try:
        target(
            engine,
            symbol_name="EURUSD",
            side="BUY",
            lots=0.01,
            stop_loss=1.08,
            take_profit=1.10,
            comment="T116-11 TEST_ONLY",
            control_mode="MANUAL",
        )
    except FakeBrokerIntercept:
        observed = "FAKE_SUBMIT_REACHED"
    except (RuntimeError, PermissionError, ValueError):
        observed = "BLOCKED"
    else:
        raise AssertionError("Ордерний шлях завершився без TEST_ONLY перехоплення")

    fake_writes = (
        repository.create_trade.call_count
        + repository.create_order_plan.call_count
        + repository.create_broker_order.call_count
    )
    fake_attempts = service.place_market_order.call_count
    if observed == "FAKE_SUBMIT_REACHED":
        assert fake_writes == 2, "Некоректна тестова persistence-послідовність"
        assert (
            fake_attempts == 1
        ), "Підставний broker service не був викликаний один раз"
    else:
        assert fake_writes == 0, "Заблокований ордер уже торкнувся persistence"
        assert fake_attempts == 0, "Заблокований ордер дійшов до broker service"
    return observed, fake_writes, fake_attempts


def test_manual_order_execution_guard() -> None:
    """Вимагати fail-closed на трьох входах для семи значень режиму."""
    print("T116-11 TEST_ONLY | Manual Order execution guard contract")
    public, direct_ib = read_methods()
    mismatches = []
    cases = 0
    fake_write_count = 0
    fake_attempt_count = 0

    for route in ROUTES:
        for mode in MODES:
            expected = "FAKE_SUBMIT_REACHED" if mode in ALLOWED_MODES else "BLOCKED"
            actual, fake_writes, fake_attempts = run_case(
                public, direct_ib, route, mode
            )
            cases += 1
            fake_write_count += fake_writes
            fake_attempt_count += fake_attempts
            shown = "NONE" if mode is None else mode or "EMPTY"
            print(f"route={route} global={shown} expected={expected} actual={actual}")
            if actual != expected:
                mismatches.append((route, shown))

    print(f"policy_cases={cases}")
    print(f"policy_mismatches={len(mismatches)}")
    print(f"fake_persistence_calls={fake_write_count}")
    print(f"fake_broker_intercepts={fake_attempt_count}")
    print("real_broker_requests=0")
    print("real_database_writes=0")
    print("config_writes=0")
    print("production_changes=0")
    print("workspace_order_paths=NOT_TESTED")
    print("gui_runtime_sync=NOT_TESTED")
    print("manual_close_modify_paths=NOT_TESTED")

    if mismatches:
        print("T116-11=RED_MANUAL_GUARD_CONTRACT")
        raise AssertionError(
            f"Manual execution guard: {len(mismatches)} з {cases} сценаріїв "
            "не відповідають політиці; очікуваний fail-first RED"
        )

    print("T116-11=GREEN_MANUAL_GUARD_CONTRACT")


if __name__ == "__main__":
    test_manual_order_execution_guard()
