"""T111-14 — IB user notice + reconciliation guard — TEST_ONLY.

Призначення:
- перевірити production wiring для user-visible IB code 2172;
- залишити service code 2107 лише informational log;
- перевірити once-per-application-session dedupe;
- блокувати IB reconciliation, якщо active broker не IB.

Pipeline:
source inspection -> exact production evidence -> deterministic verdict.

Джерела:
ib_adapter -> ib_runtime_service -> main_logic status bar;
ib_reconciliation_lifecycle -> RuntimeEngine active broker guard.

Safety:
- production runtime не імпортується;
- broker API не викликається;
- broker_requests=0;
- broker_execution_attempted=False.

Output:
IB_USER_NOTIFICATION_AND_RECONCILIATION_GUARD_WIRED або assertion failure.

Non-goals:
broker connection, ордери або зміна trading logic/strings.json.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
IB_ADAPTER = ROOT / "engine" / "ib_adapter.py"
IB_RUNTIME_SERVICE = ROOT / "engine" / "services" / "ib_runtime_service.py"
MAIN_LOGIC = ROOT / "core" / "main_logic.py"
RECONCILIATION = ROOT / "core" / "ib_reconciliation_lifecycle.py"


def require(text: str, needle: str, label: str) -> None:
    """Вимагати точний production evidence у source."""
    if needle not in text:
        raise AssertionError(f"missing evidence: {label}: {needle!r}")


def main() -> None:
    """Перевірити wiring без runtime import і broker I/O."""
    adapter = IB_ADAPTER.read_text(encoding="utf-8")
    service = IB_RUNTIME_SERVICE.read_text(encoding="utf-8")
    main_logic = MAIN_LOGIC.read_text(encoding="utf-8")
    reconciliation = RECONCILIATION.read_text(encoding="utf-8")

    require(
        adapter,
        "self.user_notice_callback: Callable[[dict[str, Any]], None] | None = None",
        "adapter wrapper has user notice callback",
    )
    require(adapter, "if error_code == 2172:", "2172 is classified separately")
    require(
        adapter,
        "self.user_notice_callback(",
        "2172 enters user notice channel",
    )
    require(
        adapter,
        "2100, 2104, 2106, 2107, 2158",
        "2107 remains informational only",
    )
    require(
        adapter,
        "if code in self._user_notice_codes:",
        "notice dedupe is once per IBAdapter generation",
    )
    require(
        adapter,
        "def drain_user_notices(self) -> list[dict[str, Any]]:",
        "adapter exposes read-only notice drain",
    )
    require(
        service,
        "def drain_user_notices(self) -> list[dict[str, object]]:",
        "runtime service exposes notice drain",
    )
    require(
        main_logic,
        "self._consume_ib_user_notices(ib_service)",
        "main window polls IB user notices",
    )
    require(
        main_logic,
        "self._ib_user_notice_codes_seen: set[int] = set()",
        "main window owns application-session notice dedupe",
    )
    require(
        main_logic,
        "if code in self._ib_user_notice_codes_seen:",
        "2172 is not repeated after IB reconnect",
    )
    require(
        main_logic,
        '"RuntimeAlert.ibApiVersionUpdateRequired"',
        "2172 has statusbar user message",
    )
    require(
        main_logic,
        "self._sb_runtime_alert.setToolTip(broker_message)",
        "full broker warning is available to user",
    )
    require(
        reconciliation,
        'get_active_broker = getattr(runtime_engine, "get_active_broker", None)',
        "reconciliation reads active broker safely",
    )
    require(
        reconciliation,
        'get_active_broker() != "IB"',
        "reconciliation checks active broker before worker",
    )
    require(
        reconciliation,
        'self._last_discard_reason = "IB broker is not active"',
        "inactive IB reconciliation is cleanly skipped",
    )

    print("T111-14 TEST_ONLY")
    print("verdict=IB_USER_NOTIFICATION_AND_RECONCILIATION_GUARD_WIRED")
    print("code_2172_user_visible=True")
    print("code_2172_once_per_application_session=True")
    print("code_2107_user_visible=False")
    print("runtime_notice_channel=True")
    print("statusbar_warning_route=True")
    print("inactive_ib_reconciliation_skipped=True")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("production_logic_changed=True")


if __name__ == "__main__":
    main()
