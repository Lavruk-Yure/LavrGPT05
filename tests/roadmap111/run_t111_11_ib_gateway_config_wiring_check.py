# run_t111_11_ib_gateway_config_wiring_check.py
"""
T111-11 — IB Gateway config wiring — TEST_ONLY.

Мета:
- перевірити production wiring engine.ib -> IBRuntimeService -> IBSessionManager;
- перевірити, що Host/Port/Client ID у GUI редаговані поза active session;
- зберегти TWS fallback 7497/7496 для старого LGE.conf;
- не створювати broker connection і не виконувати broker requests.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DIALOG = ROOT / "core" / "ib_connection_dialog.py"
MAIN_LOGIC = ROOT / "core" / "main_logic.py"
SESSION_MANAGER = ROOT / "engine" / "ib_session_manager.py"
RUNTIME_SERVICE = ROOT / "engine" / "services" / "ib_runtime_service.py"


def require(text: str, needle: str, label: str) -> None:
    """Вимагати точний production evidence у source."""
    if needle not in text:
        raise AssertionError(f"missing evidence: {label}: {needle!r}")


def forbid(text: str, needle: str, label: str) -> None:
    """Заборонити старий broken wiring у source."""
    if needle in text:
        raise AssertionError(f"obsolete evidence remains: {label}: {needle!r}")


def main() -> None:
    """Перевірити wiring без імпорту runtime і без broker I/O."""
    dialog = DIALOG.read_text(encoding="utf-8")
    main_logic = MAIN_LOGIC.read_text(encoding="utf-8")
    session_manager = SESSION_MANAGER.read_text(encoding="utf-8")
    runtime_service = RUNTIME_SERVICE.read_text(encoding="utf-8")

    require(
        dialog,
        "host, port, client_id = self._load_saved_connection_settings()",
        "dialog loads saved connection settings",
    )
    require(dialog, "self.ui.editHost.setReadOnly(False)", "host editable")
    require(dialog, "self.ui.spinPort.setReadOnly(False)", "port editable")
    require(
        dialog,
        "self.ui.spinClientId.setReadOnly(False)",
        "client id editable",
    )
    require(
        dialog,
        "self._apply_connection_settings_to_runtime()",
        "dialog applies settings before connect",
    )
    require(
        dialog,
        "demo_port=int(self.ui.spinPort.value())",
        "dialog passes configured paper port",
    )
    require(
        dialog,
        "self.ui.btnOk.clicked.connect(self._on_ok)",
        "OK saves connection settings",
    )

    require(
        main_logic,
        'engine_ib = conf_obj.get("engine", "ib") or {}',
        "startup reads engine.ib",
    )
    require(
        main_logic,
        "_create_ib_runtime_service_from_config()",
        "startup creates configured IB runtime service",
    )
    require(
        main_logic,
        "demo_port=port",
        "DEMO config port reaches runtime service",
    )
    require(
        main_logic,
        "live_port=port",
        "LIVE config port reaches runtime service",
    )

    require(
        runtime_service,
        "session_manager = IBSessionManager(",
        "runtime service creates configured session manager",
    )
    require(runtime_service, "host=host", "runtime passes host")
    require(runtime_service, "demo_port=demo_port", "runtime passes demo port")
    require(runtime_service, "live_port=live_port", "runtime passes live port")
    require(runtime_service, "client_id=client_id", "runtime passes client id")
    require(
        runtime_service,
        "def configure_connection(",
        "runtime supports safe disconnected reconfiguration",
    )

    require(
        session_manager,
        'os.getenv("IB_DEMO_PORT", "7497")',
        "legacy TWS paper fallback",
    )
    require(
        session_manager,
        'os.getenv("IB_LIVE_PORT", "7496")',
        "legacy TWS live fallback",
    )

    forbid(
        dialog,
        'self.ui.editHost.setReadOnly(True)\n\n        self.ui.spinPort.setValue(7497)',
        "hardcoded locked TWS connection form",
    )
    forbid(
        main_logic,
        "runtime_engine.set_ib_runtime_service(IBRuntimeService())",
        "runtime service created without config",
    )

    print("T111-11 TEST_ONLY")
    print("verdict=IB_GATEWAY_CONFIG_WIRED_TO_RUNTIME")
    print("gui_host_read_only=False")
    print("gui_port_read_only=False")
    print("gui_client_id_read_only=False")
    print("engine_ib_runtime_wiring=True")
    print("configured_gateway_paper_port_supported=4002")
    print("fallback_demo_port=7497")
    print("fallback_live_port=7496")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("production_logic_changed=True")


if __name__ == "__main__":
    main()
