"""T116-20 TEST_ONLY — офлайн-аудит безпеки LIVE-телеметрії T116-19.

Не викликає launch_live_diagnostics(), LGE.main(), мережу або брокера.
RED означає, що запуск T116-19 з --live поки не дозволено.
"""

from __future__ import annotations

import ast
import runpy
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, cast

ROOT = Path(__file__).resolve().parents[2]
TELEMETRY_FILE = (
    ROOT / "tests" / "roadmap116" / "run_t116_19_ctrader_raw_spot_telemetry.py"
)
ADAPTER_FILE = ROOT / "engine" / "ctrader_adapter.py"
AUTHORIZED_CTRADER_API_ID = 46368962
TRADE_METHODS = frozenset(
    {
        "place_market_buy",
        "place_market_sell",
        "place_market_order",
        "close_position",
        "modify_position_sl_tp",
    }
)


def function_node(tree: ast.Module, name: str) -> ast.FunctionDef:
    """Знайти точну функцію верхнього рівня у файлі."""
    return next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )


def nested_function(node: ast.FunctionDef, name: str) -> ast.FunctionDef:
    """Знайти вкладену функцію без виконання її батьківського коду."""
    return next(
        item
        for item in ast.walk(node)
        if isinstance(item, ast.FunctionDef) and item.name == name
    )


def demo_account_guard(launcher: ast.FunctionDef) -> Callable[..., None]:
    """Виконати лише вкладену перевірку акаунта з фальшивим конструктором."""
    source_function = nested_function(launcher, "demo_only_init")
    code_module = ast.Module(body=[cast(ast.stmt, source_function)], type_ignores=[])
    ast.fix_missing_locations(code_module)

    def intercepted_constructor(
        instance: object, _config: object, _logger: object = None
    ) -> None:
        setattr(instance, "constructed", True)

    namespace: dict[str, Any] = {"original_init": intercepted_constructor}
    exec(compile(code_module, str(TELEMETRY_FILE), "exec"), namespace)
    return cast(Callable[..., None], namespace["demo_only_init"])


def constructor_permits(
    guard: Callable[..., None], *, mode: str, account_id: int
) -> bool:
    """Перевірити дозвіл без створення адаптера або TCP-клієнта."""
    instance = SimpleNamespace(constructed=False)
    config = SimpleNamespace(
        account_mode=mode,
        ctid_trader_account_id=account_id,
    )
    try:
        guard(instance, config, None)
    except RuntimeError:
        return False
    return instance.constructed


def installed_trade_guards(launcher: ast.FunctionDef) -> set[str]:
    """Визначити, які методи adapter реально замінюються на deny_trade."""
    covered: set[str] = set()
    for loop in ast.walk(launcher):
        if not isinstance(loop, ast.For) or not isinstance(loop.target, ast.Name):
            continue
        if not isinstance(loop.iter, (ast.Tuple, ast.List)):
            continue
        names = {
            element.value
            for element in loop.iter.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        }
        for statement in loop.body:
            for call in ast.walk(cast(Any, statement)):
                if not isinstance(call, ast.Call):
                    continue
                if not isinstance(call.func, ast.Name):
                    continue
                if call.func.id != "setattr" or len(call.args) != 3:
                    continue
                instance, target, replacement = call.args
                if (
                    isinstance(instance, ast.Name)
                    and instance.id == "adapter"
                    and isinstance(target, ast.Name)
                    and target.id == loop.target.id
                    and isinstance(replacement, ast.Name)
                    and replacement.id == "deny_trade"
                ):
                    covered.update(names)
    return covered


def source_mentions(node: ast.AST, identifiers: set[str]) -> bool:
    """Виявити явне звернення до зовнішньої залежності у LIVE launcher."""
    return any(
        isinstance(item, ast.Name)
        and item.id in identifiers
        or isinstance(item, ast.Attribute)
        and item.attr in identifiers
        for item in ast.walk(node)
    )


def explicit_disconnect_in_finally(launcher: ast.FunctionDef) -> bool:
    """Чи вказано відключення брокера в гарантованій секції finally."""
    for part in ast.walk(launcher):
        if not isinstance(part, ast.Try):
            continue
        if any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr in {"disconnect", "stopService"}
            for statement in part.finalbody
            for call in ast.walk(cast(Any, statement))
        ):
            return True
    return False


def event_cap_works() -> bool:
    """Перевірити ліміт записів у пам'яті, без запису JSONL на диск."""
    module = runpy.run_path(str(TELEMETRY_FILE), run_name="t116_20_offline_import")
    recorder_type = module["RawSpotRecorder"]
    recorder = recorder_type(max_events=2)
    stamp = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
    for _ in range(3):
        recorder.observe(
            symbol_id=55,
            symbol="EURUSD",
            event_timestamp=int(stamp.timestamp() * 1000),
            received_at=stamp,
            raw_bid=109370,
            raw_ask=109372,
            cached_bid=1.09370,
            cached_ask=1.09372,
        )
    return recorder.seen == 3 and len(recorder.records) == 2 and recorder.path is None


def test_t116_20_ctrader_live_telemetry_safety_preflight() -> None:
    """Не дозволити LIVE-збір, якщо захисні межі не підтверджені."""
    telemetry = ast.parse(TELEMETRY_FILE.read_text(encoding="utf-8"))
    adapter = ast.parse(ADAPTER_FILE.read_text(encoding="utf-8"))
    launcher = function_node(telemetry, "launch_live_diagnostics")
    guard = demo_account_guard(launcher)

    adapter_class = next(
        item
        for item in adapter.body
        if isinstance(item, ast.ClassDef) and item.name == "CTraderAdapter"
    )
    declared_methods = {
        item.name for item in adapter_class.body if isinstance(item, ast.FunctionDef)
    }
    blocked_methods = installed_trade_guards(launcher)
    mode_only_is_rejected = not constructor_permits(
        guard, mode="LIVE", account_id=AUTHORIZED_CTRADER_API_ID
    )
    correct_demo_is_permitted = constructor_permits(
        guard, mode="DEMO", account_id=AUTHORIZED_CTRADER_API_ID
    )
    different_demo_is_rejected = not constructor_permits(
        guard, mode="DEMO", account_id=AUTHORIZED_CTRADER_API_ID + 1
    )

    # Програмні перевірки та статичні ознаки ізоляції в LIVE launcher.
    checks = [
        ("DEMO_MODE_ONLY", mode_only_is_rejected),
        (
            "EXACT_DEMO_ACCOUNT_ID",
            correct_demo_is_permitted and different_demo_is_rejected,
        ),
        (
            "ADAPTER_TRADE_METHODS_BLOCKED",
            TRADE_METHODS <= blocked_methods & declared_methods,
        ),
        (
            "IB_PATH_EXPLICITLY_ISOLATED",
            source_mentions(
                launcher,
                {"IBAdapter", "ib_adapter", "IBRuntimeService", "ib_runtime_service"},
            ),
        ),
        (
            "REAL_CONFIG_WRITES_ISOLATED",
            source_mentions(
                launcher,
                {"ConfigManager", "config_manager", "ROOT_CONF_PATH"},
            ),
        ),
        ("JSONL_EVENT_COUNT_CAPPED", event_cap_works()),
        (
            "LIVE_CAPTURE_DURATION_BOUNDED",
            source_mentions(launcher, {"Timer", "QTimer", "singleShot"}),
        ),
        (
            "EXPLICIT_CTRADER_DISCONNECT_IN_FINALLY",
            explicit_disconnect_in_finally(launcher),
        ),
    ]

    mismatches = sum(not ok for _, ok in checks)
    print("T116-20 TEST_ONLY | cTrader DEMO live telemetry safety preflight")
    for name, ok in checks:
        print(f"case={name} result={'OK' if ok else 'MISSING_GUARD'}")
    print(f"authorized_api_account_id={AUTHORIZED_CTRADER_API_ID}")
    print(
        "blocked_adapter_trade_methods="
        f"{len(blocked_methods & TRADE_METHODS)}/{len(TRADE_METHODS)}"
    )
    print("jsonl_file_byte_cap=NOT_VERIFIED_EVENT_COUNT_ONLY")
    print("outbound_protobuf_trade_guard=NOT_VERIFIED")
    print(f"preflight_cases={len(checks)}")
    print(f"preflight_mismatches={mismatches}")
    print("live_launch_allowed=NO_SEPARATE_AUTHORIZATION_REQUIRED")
    print("real_broker_requests=0")
    print("real_database_writes=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    print(
        "T116-20="
        + (
            "GREEN_OFFLINE_LIVE_SAFETY_PREFLIGHT"
            if mismatches == 0
            else "RED_LIVE_SAFETY_PREFLIGHT"
        )
    )
    if mismatches:
        raise AssertionError(
            f"T116-20: відсутні {mismatches} із {len(checks)} захисних умов"
        )
