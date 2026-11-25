"""T116-38 TEST_ONLY — офлайн-контроль умов першої DEMO-сесії.

Перевірка не читає секретів, не запускає SDK Client або дочірній процес.
Orders та WSP потребують ручного підтвердження: стан активного GUI
неможливо достовірно отримати з окремого тестового процесу.
Підтвердження НЕ є технічним дозволом на мережевий запуск.
"""

from __future__ import annotations

import argparse
import ast
import inspect
import os
import textwrap
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from tests.roadmap116 import t116_29_sdk_outbound_guard as outbound
from tests.roadmap116 import t116_31_demo_readonly_discovery_session as discovery
from tests.roadmap116 import t116_32_demo_network_readonly_discovery as launcher
from tests.roadmap116 import t116_33_supervised_demo_readonly_discovery as supervisor
from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_26_process_watchdog import SUPERVISOR_TIMEOUT_SECONDS
from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied

EXPECTED_ACCOUNT_ID = 46368962
EXPECTED_REQUESTS = (
    "ProtoOAApplicationAuthReq",
    "ProtoOAAccountAuthReq",
    "ProtoOASymbolsListReq",
    "ProtoHeartbeatEvent",
)
EXPECTED_UNSCOPED = frozenset({"ProtoOAApplicationAuthReq", "ProtoHeartbeatEvent"})
EXPECTED_RESPONSES = (
    "ProtoOAApplicationAuthRes",
    "ProtoOAAccountAuthRes",
    "ProtoOASymbolsListRes",
)
EXPECTED_CHILD_MODULE = "tests.roadmap116.t116_32_demo_network_readonly_discovery"
EXPECTED_TIMEOUT_SECONDS = 75.0
SDK_READY = "VERIFIED_NO_EXTERNAL_NETWORK"
ORDERS_CONFIRMATION = "ORDERS_OFF"
WSP_CONFIRMATION = "WSP_STOPPED"
READY_MARKER = "T116-38=READY_FOR_SEPARATE_NETWORK_APPROVAL"
NOT_READY_MARKER = "T116-38=NOT_READY_OFFLINE"


@dataclass(frozen=True, slots=True)
class SafetyFacts:
    """Агреговані факти та ручні підтвердження без секретних значень."""

    orders_confirmed: bool
    wsp_confirmed: bool
    sdk_status: str
    account_match: bool
    request_policy_exact: bool
    supervisor_contract_ok: bool
    guard_wiring_ok: bool
    approval_unset: bool

    @property
    def ready_for_separate_approval(self) -> bool:
        """Тільки готовність до нового рішення, не дозвіл на мережу."""
        return all(
            (
                self.orders_confirmed,
                self.wsp_confirmed,
                self.sdk_status == SDK_READY,
                self.account_match,
                self.request_policy_exact,
                self.supervisor_contract_ok,
                self.guard_wiring_ok,
                self.approval_unset,
            )
        )


def verify_guard_wiring() -> bool:
    """Перевірити AST-межу Client() у T116-32; не виконувати її.

    Це статична перевірка проводки guard, а НЕ аудит усього SDK.
    """
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(launcher.run_demo_network)))
    except (OSError, TypeError, SyntaxError):
        return False
    guards = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.With)
        and any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Name)
            and item.context_expr.func.id == "guarded_sdk_outbound"
            for item in node.items
        )
    ]
    if len(guards) != 1:
        return False
    guard = guards[0]
    client_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "client_type"
    ]
    if len(client_calls) != 1:
        return False
    call = client_calls[0]
    if not (guard.lineno < call.lineno <= guard.end_lineno):
        return False
    if launcher.guarded_sdk_outbound is not outbound.guarded_sdk_outbound:
        return False
    return "authorized_credentials" in launcher.main.__code__.co_names


def inspect_safety(
    *,
    orders_response: str,
    wsp_response: str,
    environment: Mapping[str, str],
    check_sdk: Callable[[], str] = supervisor.sdk_offline_preflight,
) -> SafetyFacts:
    """Офлайн перевірити SDK, whitelist та ручні підтвердження."""
    with external_tcp_denied():
        try:
            status = check_sdk()
        # noinspection PyBroadException
        except Exception:  # noqa
            status = "SDK_PREFLIGHT_FAILED"
        try:
            wiring_ok = verify_guard_wiring()
        # noinspection PyBroadException
        except Exception:  # noqa
            wiring_ok = False

    request_policy_exact = (
        outbound.PERMITTED_REQUEST_NAMES == EXPECTED_REQUESTS
        and outbound.UNSCOPED_REQUEST_NAMES == EXPECTED_UNSCOPED
        and discovery.INBOUND_RESPONSE_NAMES == EXPECTED_RESPONSES
    )
    supervisor_contract_ok = (
        SUPERVISOR_TIMEOUT_SECONDS == EXPECTED_TIMEOUT_SECONDS
        and supervisor.SUPERVISOR_TIMEOUT_SECONDS == EXPECTED_TIMEOUT_SECONDS
        and supervisor.CHILD_MODULE == EXPECTED_CHILD_MODULE
        and supervisor.CHILD_GREEN == "T116-32=GREEN_DEMO_READONLY_SYMBOL_DISCOVERY"
        and "supervise_process" in supervisor.run_supervised_network.__code__.co_names
    )
    return SafetyFacts(
        orders_confirmed=orders_response == ORDERS_CONFIRMATION,
        wsp_confirmed=wsp_response == WSP_CONFIRMATION,
        sdk_status=status if status == SDK_READY else "SDK_PREFLIGHT_FAILED",
        account_match=(
            DEMO_API_ACCOUNT_ID == EXPECTED_ACCOUNT_ID
            and outbound.DEMO_API_ACCOUNT_ID == EXPECTED_ACCOUNT_ID
        ),
        request_policy_exact=request_policy_exact,
        supervisor_contract_ok=supervisor_contract_ok,
        guard_wiring_ok=wiring_ok,
        approval_unset=launcher.NETWORK_APPROVAL_VARIABLE not in environment,
    )


def format_report(facts: SafetyFacts) -> str:
    """Безпечний звіт: тільки статуси, без env, паролів і traceback."""
    return "\n".join(
        (
            "T116-38 TEST_ONLY | DEMO network safety gate OFFLINE",
            f"demo_api_account_id={EXPECTED_ACCOUNT_ID}",
            "orders_off="
            + (
                "OPERATOR_CONFIRMED_NOT_MACHINE_VERIFIED"
                if facts.orders_confirmed
                else "NOT_CONFIRMED"
            ),
            "wsp_stopped="
            + (
                "OPERATOR_CONFIRMED_NOT_MACHINE_VERIFIED"
                if facts.wsp_confirmed
                else "NOT_CONFIRMED"
            ),
            f"sdk_offline_preflight={facts.sdk_status}",
            f"demo_account_match={'YES' if facts.account_match else 'NO'}",
            "outbound_request_policy="
            + (
                "EXACT_3_READONLY_PLUS_HEARTBEAT"
                if facts.request_policy_exact
                else "FAILED"
            ),
            "supervisor_timeout_seconds="
            + ("75" if facts.supervisor_contract_ok else "CONTRACT_FAILED"),
            "sdk_guard_wiring="
            + ("STATIC_CONTRACT_OK" if facts.guard_wiring_ok else "FAILED"),
            "network_approval_env="
            + ("UNSET" if facts.approval_unset else "PRESENT_REJECTED"),
            "operator_checks=ATTESTATION_ONLY_NOT_LIVE_GUI_INSPECTION",
            "credentials=NOT_READ",
            "external_tcp=BLOCKED",
            "sdk_client_constructor=NOT_CALLED",
            "child_process=NOT_STARTED",
            "real_broker_requests=0",
            "production_changes=0",
            "network_launch_authorized=NO",
            READY_MARKER if facts.ready_for_separate_approval else NOT_READY_MARKER,
        )
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    ask: Callable[[str], str] = input,
    environment: Mapping[str, str] | None = None,
    check_sdk: Callable[[], str] = supervisor.sdk_offline_preflight,
) -> int:
    """Виконати лише офлайн-інспекцію або дві ручні атестації."""
    parser = argparse.ArgumentParser(allow_abbrev=False)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--offline-preflight", action="store_true")
    modes.add_argument("--check-machine", action="store_true")
    args = parser.parse_args(argv)
    env = os.environ if environment is None else environment
    orders_response = ""
    wsp_response = ""
    if args.check_machine:
        print("Перевір у LGE статус Orders: OFF. Це ручне підтвердження.")
        print("Перевір, що всі WSP зупинені. Це ручне підтвердження.")
        try:
            orders_response = ask("Якщо Orders: OFF, введи ORDERS_OFF: ")
            wsp_response = ask("Якщо всі WSP зупинені, введи WSP_STOPPED: ")
        except (EOFError, KeyboardInterrupt):
            pass
    report = format_report(
        inspect_safety(
            orders_response=orders_response,
            wsp_response=wsp_response,
            environment=env,
            check_sdk=check_sdk,
        )
    )
    print(report)
    return 0 if READY_MARKER in report.splitlines() else 2


if __name__ == "__main__":
    raise SystemExit(main())
