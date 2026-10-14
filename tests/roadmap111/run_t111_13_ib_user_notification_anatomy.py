"""T111-13 TEST_ONLY: анатомія IB повідомлень, невидимих користувачу."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
IB_ADAPTER = ROOT / "engine" / "ib_adapter.py"
MAIN_LOGIC = ROOT / "core" / "main_logic.py"
RECONCILIATION = ROOT / "core" / "ib_reconciliation_lifecycle.py"
RUNTIME_ENGINE = ROOT / "engine" / "runtime_engine.py"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> None:
    adapter_text = read(IB_ADAPTER)
    main_text = read(MAIN_LOGIC)
    reconciliation_text = read(RECONCILIATION)
    engine_text = read(RUNTIME_ENGINE)

    adapter_has_ib_error_callback = "def error(" in adapter_text
    code_2172_has_gui_route = "2172" in main_text or "2172" in reconciliation_text
    code_2107_has_gui_route = "2107" in main_text or "2107" in reconciliation_text
    adapter_has_user_notice_callback = (
        "user_notice_callback" in adapter_text
        or "notification_callback" in adapter_text
    )
    statusbar_runtime_alert_exists = "_sb_runtime_alert" in main_text
    runtime_alert_is_broker_state_only = "def _notify_broker_state_changes(" in main_text

    lifecycle_checks_ib_service_connected = "if not health.is_connected():" in reconciliation_text
    lifecycle_checks_active_broker = (
        "get_active_broker" in reconciliation_text
        or 'broker != "IB"' in reconciliation_text
    )
    evidence_requires_active_ib = (
        'raise RuntimeError("IB virtual-leg evidence requires active IB broker")'
        in engine_text
    )

    hidden_ib_status_gap = (
        adapter_has_ib_error_callback
        and not adapter_has_user_notice_callback
        and not code_2172_has_gui_route
        and not code_2107_has_gui_route
        and statusbar_runtime_alert_exists
        and runtime_alert_is_broker_state_only
    )
    inactive_broker_reconciliation_gap = (
        lifecycle_checks_ib_service_connected
        and not lifecycle_checks_active_broker
        and evidence_requires_active_ib
    )

    verdict = (
        "IB_USER_NOTIFICATION_AND_RECONCILIATION_GAPS_CONFIRMED"
        if hidden_ib_status_gap and inactive_broker_reconciliation_gap
        else "UNEXPECTED"
    )

    print("T111-13 TEST_ONLY")
    print(f"verdict={verdict}")
    print(f"ib_error_callback_present={adapter_has_ib_error_callback}")
    print(f"ib_user_notice_callback_present={adapter_has_user_notice_callback}")
    print(f"code_2172_gui_route_present={code_2172_has_gui_route}")
    print(f"code_2107_gui_route_present={code_2107_has_gui_route}")
    print(f"statusbar_runtime_alert_present={statusbar_runtime_alert_exists}")
    print(f"runtime_alert_broker_state_only={runtime_alert_is_broker_state_only}")
    print(f"reconciliation_checks_service_connected={lifecycle_checks_ib_service_connected}")
    print(f"reconciliation_checks_active_broker={lifecycle_checks_active_broker}")
    print(f"runtime_evidence_requires_active_ib={evidence_requires_active_ib}")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("production_logic_changed=False")

    if verdict == "UNEXPECTED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
