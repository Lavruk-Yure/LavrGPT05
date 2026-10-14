# run_t111_10_ib_gateway_connection_config_anatomy.py
"""
T111-10 — IB Gateway connection config anatomy — TEST_ONLY.

Мета:
- довести, чому IB connection fields у GUI недоступні;
- перевірити, чи engine.ib host/port/client_id реально підключені до runtime path;
- не створювати broker connection і не змінювати production logic.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIALOG = ROOT / "core" / "ib_connection_dialog.py"
MAIN_LOGIC = ROOT / "core" / "main_logic.py"
SESSION_MANAGER = ROOT / "engine" / "ib_session_manager.py"
RUNTIME_SERVICE = ROOT / "engine" / "services" / "ib_runtime_service.py"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing evidence: {label}: {needle!r}")


def main() -> None:
    dialog = DIALOG.read_text(encoding="utf-8")
    main_logic = MAIN_LOGIC.read_text(encoding="utf-8")
    session_manager = SESSION_MANAGER.read_text(encoding="utf-8")
    runtime_service = RUNTIME_SERVICE.read_text(encoding="utf-8")

    require(dialog, "self.ui.editHost.setReadOnly(True)", "host read-only")
    require(dialog, "self.ui.spinPort.setReadOnly(True)", "port read-only")
    require(dialog, "self.ui.spinClientId.setReadOnly(True)", "client id read-only")
    require(
        dialog, "self.ui.spinPort.setValue(7497)", "dialog hardcoded TWS paper port"
    )

    require(
        main_logic,
        "runtime_engine.set_ib_runtime_service(IBRuntimeService())",
        "runtime service created without config",
    )
    require(
        runtime_service,
        "self._session_manager = session_manager or IBSessionManager()",
        "default session manager created without config",
    )
    require(
        session_manager,
        'self._demo_port = demo_port or int(os.getenv("IB_DEMO_PORT", "7497"))',
        "session manager default TWS paper port",
    )

    config_is_saved = '"port": int(self.ui.spinPort.value())' in dialog
    runtime_reads_saved_ib = 'conf_obj.get("engine", "ib"' in main_logic

    print("T111-10 TEST_ONLY")
    print("verdict=IB_GATEWAY_CONFIG_NOT_WIRED_TO_RUNTIME")
    print("gui_host_read_only=True")
    print("gui_port_read_only=True")
    print("gui_client_id_read_only=True")
    print("gui_demo_port=7497")
    print(f"dialog_can_save_engine_ib={config_is_saved}")
    print(f"main_runtime_reads_engine_ib={runtime_reads_saved_ib}")
    print("runtime_service_uses_default_session_manager=True")
    print("session_manager_default_demo_port=7497")
    print("required_gateway_paper_port=4002")
    print("broker_requests=0")
    print("production_logic_changed=False")

    if not config_is_saved:
        raise AssertionError("dialog no longer saves engine.ib config")
    if runtime_reads_saved_ib:
        raise AssertionError(
            "main runtime now appears to read engine.ib; update T111-10 expectations"
        )


if __name__ == "__main__":
    main()
