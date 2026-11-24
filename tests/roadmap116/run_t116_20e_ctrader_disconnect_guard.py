"""T116-20E TEST_ONLY — відключення cTrader при виході та винятках.

Виконує справжні вкладені TEST_ONLY функції через AST із фальшивими
адаптерами. LGE, PySide6, мережу й брокерські служби не запускає.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
TELEMETRY_FILE = (
    ROOT / "tests" / "roadmap116" / "run_t116_19_ctrader_raw_spot_telemetry.py"
)
AUTHORIZED_ID = 46368962


class FakeAdapter:
    """Тестова модель відключення без TCP-з'єднань."""

    def __init__(self, label: str, attempts: list[str], *, fails: bool = False):
        self.label = label
        self.attempts = attempts
        self.fails = fails

    def disconnect(self) -> None:
        self.attempts.append(self.label)
        if self.fails:
            raise RuntimeError("TEST_ONLY simulated disconnect failure")


def launcher_parts() -> tuple[ast.FunctionDef, ast.FunctionDef, ast.FunctionDef]:
    """Отримати чинні функції з реального TEST_ONLY launcher."""
    syntax = ast.parse(TELEMETRY_FILE.read_text(encoding="utf-8"))
    launcher = next(
        node for node in syntax.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "launch_live_diagnostics"
    )
    nested = {
        node.name: node
        for node in launcher.body
        if isinstance(node, ast.FunctionDef)
    }
    return (
        launcher,
        nested["demo_only_init"],
        nested["ctrader_disconnect_guard"],
    )


def actual_guard(
    node: ast.FunctionDef, tracked: list[FakeAdapter],
) -> Callable[[], Any]:
    """Виконати тільки оригінальний TEST_ONLY contextmanager."""
    statement = deepcopy(node)
    module = ast.fix_missing_locations(
        ast.Module(body=[statement], type_ignores=[])
    )
    scope: dict[str, Any] = {
        "contextmanager": contextmanager,
        "isolate_ctrader_outbound_protobuf": nullcontext,
        "Iterator": Iterator,
        "constructed_adapters": tracked,
        "sys": sys,
    }
    exec(compile(module, str(TELEMETRY_FILE), "exec"), scope)
    guard = scope["ctrader_disconnect_guard"]
    assert callable(guard)
    return guard


def actual_constructor(
    node: ast.FunctionDef,
    tracked: list[FakeAdapter],
    constructor: Callable[..., None],
) -> Callable[..., None]:
    """Виконати справжню перевірку рахунку й реєстрацію адаптера."""
    statement = deepcopy(node)
    module = ast.fix_missing_locations(
        ast.Module(body=[statement], type_ignores=[])
    )
    scope: dict[str, Any] = {
        "constructed_adapters": tracked,
        "original_init": constructor,
    }
    exec(compile(module, str(TELEMETRY_FILE), "exec"), scope)
    guarded_initializer = scope["demo_only_init"]
    assert callable(guarded_initializer)

    def invoke_constructor(*args: Any, **kwargs: Any) -> None:
        guarded_initializer(*args, **kwargs)

    return invoke_constructor


def with_call_named(node: ast.AST, name: str) -> bool:
    """Перевірити назву першого контекстного виклику в AST with."""
    if not isinstance(node, ast.With) or not node.items:
        return False
    expression = node.items[0].context_expr
    if not isinstance(expression, ast.Call):
        return False
    function = expression.func
    return isinstance(function, ast.Name) and function.id == name


def includes_lge_main(node: ast.AST) -> bool:
    """Перевірити, що вкладена конструкція охоплює LGE.main()."""
    return any(
        isinstance(item, ast.Call)
        and isinstance(item.func, ast.Attribute)
        and isinstance(item.func.value, ast.Name)
        and item.func.value.id == "LGE"
        and item.func.attr == "main"
        for item in ast.walk(node)
    )


def test_t116_20e_ctrader_disconnect_guard() -> None:
    """Перевірити штатний вихід, винятки та відмову одного disconnect."""
    launcher, initializer, disconnect_guard = launcher_parts()
    outer_guard = next(
        item for item in launcher.body
        if isinstance(item, ast.With)
        and len(item.items) == 1
        and with_call_named(item, "ctrader_disconnect_guard")
    )
    assert includes_lge_main(outer_guard)
    assert any(
        with_call_named(item, "isolate_ctrader_outbound_protobuf")
        for item in ast.walk(disconnect_guard)
    )
    assert any(
        with_call_named(item, "isolate_real_config_writes")
        for item in ast.walk(outer_guard)
    )
    assert any(
        isinstance(item, ast.Try)
        and any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "disconnect"
            for statement in item.finalbody
            for call in ast.walk(statement)
        )
        for item in ast.walk(disconnect_guard)
    )

    attempts: list[str] = []
    tracked: list[FakeAdapter] = []
    guard = actual_guard(disconnect_guard, tracked)
    with guard():
        tracked.extend([FakeAdapter("A", attempts), FakeAdapter("B", attempts)])
    assert attempts == ["B", "A"]

    attempts.clear()
    tracked.clear()
    try:
        with guard():
            tracked.append(FakeAdapter("ERROR", attempts))
            raise ValueError("TEST_ONLY simulated GUI error")
    except ValueError as exc:
        assert str(exc) == "TEST_ONLY simulated GUI error"
    else:
        raise AssertionError("Помилка GUI повинна вийти з guard")
    assert attempts == ["ERROR"]

    attempts.clear()
    tracked.clear()
    try:
        with guard():
            tracked.append(FakeAdapter("SYSTEM_EXIT", attempts))
            raise SystemExit(3)
    except SystemExit as exc:
        assert exc.code == 3
    else:
        raise AssertionError("SystemExit повинен вийти з guard")
    assert attempts == ["SYSTEM_EXIT"]

    attempts.clear()
    tracked.clear()
    with guard():
        tracked.extend([
            FakeAdapter("FIRST", attempts),
            FakeAdapter("BROKEN", attempts, fails=True),
            FakeAdapter("LAST", attempts),
        ])
    assert attempts == ["LAST", "BROKEN", "FIRST"]

    attempts.clear()
    tracked.clear()
    with guard():
        pass
    assert attempts == []

    init_attempts: list[str] = []
    constructed: list[FakeAdapter] = []

    def fake_original_init(
        instance: FakeAdapter, _config: object, _logger: object = None,
    ) -> None:
        init_attempts.append(instance.label)

    guarded_init = actual_constructor(initializer, constructed, fake_original_init)
    good = SimpleNamespace(account_mode="DEMO", ctid_trader_account_id=AUTHORIZED_ID)
    guarded_init(FakeAdapter("ALLOWED", attempts), good)
    assert len(constructed) == 1
    assert init_attempts == ["ALLOWED"]
    for mode, account_id in (("LIVE", AUTHORIZED_ID), ("DEMO", AUTHORIZED_ID + 1)):
        try:
            guarded_init(
                FakeAdapter("DENIED", attempts),
                SimpleNamespace(account_mode=mode, ctid_trader_account_id=account_id),
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("Недозволений рахунок не заблоковано")
    assert len(constructed) == 1
    assert init_attempts == ["ALLOWED"]

    partial: list[FakeAdapter] = []

    def failing_original_init(
        _instance: FakeAdapter, _config: object, _logger: object = None,
    ) -> None:
        raise ValueError("TEST_ONLY partial construction")

    partial_init = actual_constructor(initializer, partial, failing_original_init)
    try:
        partial_init(FakeAdapter("PARTIAL", attempts), good)
    except ValueError:
        pass
    else:
        raise AssertionError("Помилка конструктора не відтворена")
    assert len(partial) == 1
    with actual_guard(disconnect_guard, partial)():
        pass
    assert attempts == ["PARTIAL"]

    print("T116-20E TEST_ONLY | cTrader disconnect on LGE exit")
    print("cleanup_wraps_lge_main=YES")
    print("normal_exit_disconnect=VERIFIED")
    print("runtime_exception_disconnect=VERIFIED")
    print("system_exit_disconnect=VERIFIED")
    print("disconnect_error_next_adapter_continues=VERIFIED")
    print("partial_constructor_registered_for_cleanup=VERIFIED")
    print("live_account_constructor=DENIED")
    print("wrong_demo_account_constructor=DENIED")
    print("hard_process_termination_finally=NOT_GUARANTEED")
    print("network_disconnect_completion=NOT_VERIFIED")
    print("real_broker_requests=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    print("T116-20E=GREEN_OFFLINE_CTRADER_DISCONNECT_GUARD")
