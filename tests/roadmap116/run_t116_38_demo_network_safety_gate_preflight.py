"""T116-38 TEST_ONLY — негативна офлайн-перевірка DEMO safety gate."""

from __future__ import annotations

import socket
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import patch

import pytest

from tests.roadmap116 import t116_29_sdk_outbound_guard as outbound
from tests.roadmap116 import t116_31_demo_readonly_discovery_session as discovery
from tests.roadmap116 import t116_33_supervised_demo_readonly_discovery as supervisor
from tests.roadmap116 import t116_38_demo_network_safety_gate as gate
from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied


def sdk_ready() -> str:
    """Імітувати успішний локальний SDK-огляд, без реального Client()."""
    return gate.SDK_READY


def evaluate(
    *,
    orders_response: str = gate.ORDERS_CONFIRMATION,
    wsp_response: str = gate.WSP_CONFIRMATION,
    environment: dict[str, str] | None = None,
    check_sdk=sdk_ready,
) -> gate.SafetyFacts:
    """Тестові підтвердження, не справжні стани GUI."""
    return gate.inspect_safety(
        orders_response=orders_response,
        wsp_response=wsp_response,
        environment={} if environment is None else environment,
        check_sdk=check_sdk,
    )


def test_t116_38_demo_network_safety_gate_preflight() -> None:
    """Заблокувати відсутність будь-якої передумови та будь-яку мережу."""
    negative = 0
    with external_tcp_denied():
        facts = evaluate()
        assert facts.ready_for_separate_approval
        assert facts.account_match
        assert facts.request_policy_exact
        assert facts.supervisor_contract_ok
        assert facts.guard_wiring_ok
        assert facts.approval_unset
        assert gate.verify_guard_wiring()
        good_report = gate.format_report(facts)
        assert gate.READY_MARKER in good_report
        assert "network_launch_authorized=NO" in good_report
        assert "operator_checks=ATTESTATION_ONLY_NOT_LIVE_GUI_INSPECTION" in good_report

        for bad_orders, bad_wsp in (
            ("", gate.WSP_CONFIRMATION),
            ("OFF", gate.WSP_CONFIRMATION),
            ("orders_off", gate.WSP_CONFIRMATION),
            (gate.ORDERS_CONFIRMATION, ""),
            (gate.ORDERS_CONFIRMATION, "STOPPED"),
            (gate.ORDERS_CONFIRMATION, "wsp_stopped"),
            ("", ""),
        ):
            assert not evaluate(
                orders_response=bad_orders, wsp_response=bad_wsp
            ).ready_for_separate_approval
            negative += 1

        approval_variable = gate.launcher.NETWORK_APPROVAL_VARIABLE
        approval_value = gate.launcher.NETWORK_APPROVAL_VALUE
        for denied_env in (
            {approval_variable: ""},
            {approval_variable: approval_value},
        ):
            assert not evaluate(environment=denied_env).ready_for_separate_approval
            negative += 1

        for invalid_probe in (
            lambda: "NOT_INSTALLED_LOCAL_RUNNER",
            lambda: "",
            lambda: "WRONG_STATUS",
        ):
            assert not evaluate(check_sdk=invalid_probe).ready_for_separate_approval
            negative += 1

        def broken_probe() -> str:
            raise RuntimeError("TEST_ONLY SDK import failure")

        assert not evaluate(check_sdk=broken_probe).ready_for_separate_approval
        negative += 1

        # Whitelist зіпсовано: жодна додаткова торгова protobuf не допускається.
        with patch.object(
            outbound,
            "PERMITTED_REQUEST_NAMES",
            (*gate.EXPECTED_REQUESTS, "ProtoOANewOrderReq"),
        ):
            assert not evaluate().ready_for_separate_approval
        negative += 1
        with patch.object(outbound, "UNSCOPED_REQUEST_NAMES", frozenset()):
            assert not evaluate().ready_for_separate_approval
        negative += 1
        with patch.object(
            discovery, "INBOUND_RESPONSE_NAMES", ("ProtoOAAccountAuthRes",)
        ):
            assert not evaluate().ready_for_separate_approval
        negative += 1
        with patch.object(outbound, "DEMO_API_ACCOUNT_ID", 100):
            assert not evaluate().ready_for_separate_approval
        negative += 1
        with patch.object(supervisor, "CHILD_MODULE", "tests.fake_live_broker"):
            assert not evaluate().ready_for_separate_approval
        negative += 1
        with patch.object(gate, "SUPERVISOR_TIMEOUT_SECONDS", 0):
            assert not evaluate().ready_for_separate_approval
        negative += 1
        with patch.object(gate, "verify_guard_wiring", return_value=False):
            assert not evaluate().ready_for_separate_approval
        negative += 1
        with patch.object(gate.launcher, "guarded_sdk_outbound", object()):
            assert not evaluate().ready_for_separate_approval
        negative += 1

        # TCP заборонено і для injected SDK-проби.
        def test_network_probe() -> str:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe_socket:
                probe_socket.connect(("192.0.2.1", 443))
            return gate.SDK_READY

        assert not evaluate(check_sdk=test_network_probe).ready_for_separate_approval
        negative += 1

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
            with pytest.raises(PermissionError):
                connection.connect(("192.0.2.1", 443))
        negative += 1

        # Жодні режими --live або --demo-network у T116-38 не існують.
        for forbidden_args in (
            [],
            ["--live"],
            ["--demo-network"],
            ["--check-machine", "--confirm", "READONLY"],
            ["--check-machine", "--offline-preflight"],
        ):
            with redirect_stderr(StringIO()):
                with pytest.raises(SystemExit) as exit_result:
                    gate.main(forbidden_args, check_sdk=sdk_ready, environment={})
            assert exit_result.value.code == 2
            negative += 1

        # Звичайний pytest ніколи не опитує користувача.
        def must_not_ask(_prompt: str) -> str:
            raise AssertionError("OFFLINE_PREFLIGHT_MUST_NOT_ASK")

        with redirect_stdout(StringIO()) as offline_output:
            assert (
                gate.main(
                    ["--offline-preflight"],
                    ask=must_not_ask,
                    environment={},
                    check_sdk=sdk_ready,
                )
                == 2
            )
        assert gate.NOT_READY_MARKER in offline_output.getvalue()
        negative += 1

        # Ручне підтвердження — тільки декларація, ніколи дозвіл мережі.
        answer_iter = iter((gate.ORDERS_CONFIRMATION, gate.WSP_CONFIRMATION))
        with redirect_stdout(StringIO()) as machine_output:
            assert (
                gate.main(
                    ["--check-machine"],
                    ask=lambda _prompt: next(answer_iter),
                    environment={},
                    check_sdk=sdk_ready,
                )
                == 0
            )
        assert gate.READY_MARKER in machine_output.getvalue()
        assert "network_launch_authorized=NO" in machine_output.getvalue()
        assert "credentials=NOT_READ" in machine_output.getvalue()

        with redirect_stdout(StringIO()) as rejected_output:
            assert (
                gate.main(
                    ["--check-machine"],
                    ask=lambda _prompt: "NO",
                    environment={},
                    check_sdk=sdk_ready,
                )
                == 2
            )
        assert gate.NOT_READY_MARKER in rejected_output.getvalue()
        negative += 1

    print("T116-38 TEST_ONLY | DEMO network safety gate offline")
    print(f"demo_api_account_id={gate.EXPECTED_ACCOUNT_ID}")
    print(f"negative_scenarios_denied={negative}")
    print("orders_off=OPERATOR_CONFIRMATION_REQUIRED")
    print("wsp_stopped=OPERATOR_CONFIRMATION_REQUIRED")
    print("outbound_request_policy=EXACT_3_READONLY_PLUS_HEARTBEAT")
    print("sdk_guard_wiring=STATIC_CONTRACT_VERIFIED")
    print("supervisor_timeout_seconds=75")
    print("credentials=NOT_READ")
    print("external_tcp=BLOCKED")
    print("sdk_client_constructor=NOT_CALLED")
    print("child_process=NOT_STARTED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print("T116-38=GREEN_OFFLINE_DEMO_NETWORK_SAFETY_GATE")
