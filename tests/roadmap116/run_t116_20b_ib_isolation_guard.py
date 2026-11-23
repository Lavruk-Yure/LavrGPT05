"""T116-20B TEST_ONLY — IB Network Isolation Guard перед запуском LGE."""

from __future__ import annotations

import ast
import runpy
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
TELEMETRY_FILE = (
    ROOT / "tests" / "roadmap116" / "run_t116_19_ctrader_raw_spot_telemetry.py"
)


def test_t116_20b_ib_isolation_guard() -> None:
    """Перевірити 8 блокувань IB та їх установлення перед import LGE."""
    tree = ast.parse(TELEMETRY_FILE.read_text(encoding="utf-8"))
    launcher = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "launch_live_diagnostics"
    )
    installs = [
        node
        for node in ast.walk(launcher)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "install_ib_network_guard"
    ]
    lge_imports = [
        node
        for node in ast.walk(launcher)
        if isinstance(node, ast.Import)
        and any(alias.name == "LGE" for alias in node.names)
    ]
    assert len(installs) == 1
    assert len(lge_imports) == 1
    assert installs[0].lineno < lge_imports[0].lineno
    guard_sources = {
        item.arg: item.value.id
        for item in installs[0].keywords
        if item.arg is not None and isinstance(item.value, ast.Name)
    }
    assert guard_sources == {
        "ib_adapter": "IBAdapter",
        "ib_session_manager": "IBSessionManager",
        "ib_runtime_service": "IBRuntimeService",
        "ib_api_client": "EClient",
    }

    scope = runpy.run_path(str(TELEMETRY_FILE), run_name="t116_20b_offline")
    install_guard: Callable[..., tuple[str, ...]] = scope["install_ib_network_guard"]
    attempts: list[str] = []

    def fake_connect(*_args: object, **_kwargs: object) -> None:
        attempts.append("NETWORK_CONNECT")

    adapter = type("FakeIBAdapter", (), {"connect": fake_connect})
    manager = type(
        "FakeIBSessionManager",
        (),
        {name: fake_connect for name in ("connect_demo", "connect_live", "reconnect")},
    )
    service = type(
        "FakeIBRuntimeService",
        (),
        {name: fake_connect for name in ("connect_demo", "connect_live", "reconnect")},
    )
    client = type("FakeIBApiClient", (), {"connect": fake_connect})
    allowed = {
        "ib_adapter": adapter,
        "ib_session_manager": manager,
        "ib_runtime_service": service,
        "ib_api_client": client,
    }

    # Невідомий API зупиняє запуск до часткового встановлення блокувань.
    missing = type("FakeMissingIBClient", (), {})
    try:
        install_guard(**{**allowed, "ib_api_client": missing})
    except RuntimeError as error:
        assert "boundary not found" in str(error)
    else:
        raise AssertionError("Невідомий IB API не заблокував запуск")
    adapter().connect()
    assert attempts == ["NETWORK_CONNECT"]
    attempts.clear()

    installed = install_guard(**allowed)
    assert len(installed) == 8
    boundaries = (
        (adapter, ("connect",)),
        (manager, ("connect_demo", "connect_live", "reconnect")),
        (service, ("connect_demo", "connect_live", "reconnect")),
        (client, ("connect",)),
    )
    for owner, methods in boundaries:
        for name in methods:
            try:
                getattr(owner(), name)()
            except RuntimeError as error:
                assert "IB-підключення заборонено" in str(error)
            else:
                raise AssertionError(f"Незахищена IB-точка: {owner.__name__}.{name}")
    assert not attempts
    print("T116-20B TEST_ONLY | IB network isolation before LGE bootstrap")
    print("ib_guard_before_lge_import=YES")
    print("ib_network_boundaries_blocked=8/8")
    print("unknown_ib_api_fails_closed=YES")
    print("ib_connect_attempts_reaching_network=0")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("T116-20B=GREEN_OFFLINE_IB_ISOLATION_GUARD")
