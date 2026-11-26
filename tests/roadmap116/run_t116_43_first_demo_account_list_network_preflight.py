"""T116-43 TEST_ONLY — перший DEMO AccountList, суто офлайн-перевірки."""

from __future__ import annotations

import ast
import os
import socket
import subprocess
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from tests.roadmap116 import t116_29_sdk_outbound_guard as outbound
from tests.roadmap116.run_t116_29_sdk_outbound_transport_guard import (
    FakeClient,
    FakeFrameSender,
    FakeTcpProtocol,
)
from tests.roadmap116.run_t116_32_demo_network_readonly_discovery_preflight import (
    FakeClock,
    FakeScheduler,
    FakeSdkClient,
)
from tests.roadmap116.run_t116_41_demo_account_list_session_preflight import (
    RESPONSE_IDS,
    account_list,
    make_envelope,
    synthetic_sdk,
)
from tests.roadmap116.t116_26_process_watchdog import SupervisedResult
from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied
from tests.roadmap116.t116_36_lge_credentials_launcher_bridge import (
    BridgedCredentials,
)
from tests.roadmap116.t116_43_first_demo_account_list_network import (
    APPROVAL_VALUE,
    APPROVAL_VARIABLE,
    CHILD_SUCCESS,
    CLI_CONFIRMATION,
    OFFLINE_SUCCESS,
    ORDERS_CONFIRMATION,
    ORDERS_VARIABLE,
    WSP_CONFIRMATION,
    WSP_VARIABLE,
    AccountListNetworkController,
    approved,
    exact_account_list_outbound,
    main,
    prepare_child_environment,
    safe_child_failure_code,
    summarize_child,
    supervise_network_child,
)

SOURCE = Path(__file__).with_name("t116_43_first_demo_account_list_network.py")
SYNTHETIC_CREDENTIALS = BridgedCredentials(
    client_id="T11643_TEST_CLIENT",
    client_secret="T11643_TEST_SECRET",
    access_token="T11643_TEST_TOKEN",
)
GOOD_CHILD_LINES = (
    "demo_api_account_id=46368962",
    "gui_trader_login=9870599",
    "account_is_live=NO",
    "request_order=APPLICATION_AUTH_ACCOUNT_LIST",
    "production_changes=0",
    CHILD_SUCCESS,
)


def test_t116_43_first_demo_account_list_network_preflight(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Перевірити callbacks, scoped whitelist, env/CLI і timeout без TCP."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    assert any(
        isinstance(node, ast.FunctionDef) and node.name == "run_network_child"
        for node in tree.body
    )
    assert any(
        isinstance(node, ast.FunctionDef) and node.name == "supervise_network_child"
        for node in tree.body
    )
    assert "guarded_scoped_account_list" in SOURCE.read_text(encoding="utf-8")
    assert "spec.demo_host, spec.port, protocol_type" in SOURCE.read_text(
        encoding="utf-8"
    )

    denied = 0
    with external_tcp_denied():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_probe:
            with pytest.raises(PermissionError):
                tcp_probe.connect(("192.0.2.1", 443))
        denied += 1

        base_env = {
            key: os.environ[key]
            for key in ("SystemRoot", "WINDIR", "PATH", "TEMP", "TMP")
            if key in os.environ
        }
        assert not approved(confirmation=CLI_CONFIRMATION, environment=base_env)
        denied += 1
        complete_env = {
            **base_env,
            APPROVAL_VARIABLE: APPROVAL_VALUE,
        }
        for invalid_confirmation in (None, "", "WRONG"):
            assert not approved(
                confirmation=invalid_confirmation,
                environment=complete_env,
            )
            denied += 1
        assert approved(
            confirmation=CLI_CONFIRMATION,
            environment=complete_env,
        )
        assert not approved(
            confirmation=CLI_CONFIRMATION,
            environment=complete_env,
            operator_confirmations=True,
        )
        denied += 1

        for orders, wsp in (
            ("", WSP_CONFIRMATION),
            (ORDERS_CONFIRMATION, ""),
            ("OFF", WSP_CONFIRMATION),
            (ORDERS_CONFIRMATION, "STOPPED"),
        ):
            with pytest.raises(PermissionError):
                prepare_child_environment(
                    SYNTHETIC_CREDENTIALS,
                    environment=complete_env,
                    orders_confirmation=orders,
                    wsp_confirmation=wsp,
                )
            denied += 1
        with pytest.raises(PermissionError):
            prepare_child_environment(
                SYNTHETIC_CREDENTIALS,
                environment=base_env,
                orders_confirmation=ORDERS_CONFIRMATION,
                wsp_confirmation=WSP_CONFIRMATION,
            )
        denied += 1

        child_env = prepare_child_environment(
            SYNTHETIC_CREDENTIALS,
            environment=complete_env,
            orders_confirmation=ORDERS_CONFIRMATION,
            wsp_confirmation=WSP_CONFIRMATION,
        )
        assert approved(
            confirmation=CLI_CONFIRMATION,
            environment=child_env,
            operator_confirmations=True,
        )
        assert child_env["CTRADER_ACCESS_TOKEN"] == (SYNTHETIC_CREDENTIALS.access_token)
        assert child_env["CTRADER_CLIENT_SECRET"] == (
            SYNTHETIC_CREDENTIALS.client_secret
        )
        assert not set(child_env).intersection(
            {
                "LGE_PASSWORD",
                "T11632_ALLOW_DEMO_READONLY_NETWORK",
            }
        )
        if os.name == "nt":
            assert child_env.get("SystemRoot")

        for changed in (
            {ORDERS_VARIABLE: ""},
            {WSP_VARIABLE: ""},
            {APPROVAL_VARIABLE: ""},
            {"CTRADER_ACCESS_TOKEN": ""},
        ):
            with pytest.raises(PermissionError):
                supervise_network_child({**child_env, **changed})
            denied += 1

        # Справжній protobuf у fake SDK; усі три outbound-рівні під guard.
        messages, common = synthetic_sdk()
        tcp = FakeTcpProtocol()
        tcp.envelope_class = getattr(common, "ProtoMessage")
        client = FakeClient(tcp)
        baseline = outbound.PERMITTED_REQUEST_NAMES
        original_send = FakeClient.send
        application = getattr(messages, "ProtoOAApplicationAuthReq")()
        application.clientId = SYNTHETIC_CREDENTIALS.client_id
        application.clientSecret = SYNTHETIC_CREDENTIALS.client_secret
        list_request = getattr(messages, "ProtoOAGetAccountListByAccessTokenReq")()
        list_request.accessToken = SYNTHETIC_CREDENTIALS.access_token
        wrong_token = getattr(messages, "ProtoOAGetAccountListByAccessTokenReq")()
        wrong_token.accessToken = "WRONG"
        symbols = getattr(messages, "ProtoOASymbolsListReq")()
        symbols.ctidTraderAccountId = 46368962
        account_auth = getattr(messages, "ProtoOAAccountAuthReq")()
        account_auth.ctidTraderAccountId = 46368962
        trade = getattr(messages, "ProtoOANewOrderReq")()
        trade.ctidTraderAccountId = 46368962
        heartbeat = getattr(common, "ProtoHeartbeatEvent")()

        with exact_account_list_outbound(
            client_type=FakeClient,
            tcp_protocol_type=FakeTcpProtocol,
            frame_sender_type=FakeFrameSender,
            request_messages=messages,
            common_messages=common,
            expected_token=SYNTHETIC_CREDENTIALS.access_token,
        ):
            client.send(application)
            tcp.send(list_request, instant=True)
            client.send(heartbeat)
            assert len(tcp.transport.writes) == 3
            for blocked in (
                lambda: client.send(symbols),
                lambda: client.send(account_auth),
                lambda: client.send(trade),
                lambda: client.send(wrong_token),
                lambda: tcp.send(symbols, instant=True),
                lambda: tcp.send(wrong_token, instant=True),
            ):
                before = len(tcp.transport.writes)
                with pytest.raises(PermissionError):
                    blocked()
                assert len(tcp.transport.writes) == before
                denied += 1
            envelope = getattr(common, "ProtoMessage")()
            envelope.payloadType = symbols.payloadType
            envelope.payload = symbols.SerializeToString()
            with pytest.raises(PermissionError):
                getattr(tcp, "sendString")(envelope.SerializeToString())
            denied += 1
        assert outbound.PERMITTED_REQUEST_NAMES == baseline
        assert FakeClient.send is original_send

        def make_controller() -> tuple[
            AccountListNetworkController,
            FakeSdkClient,
            FakeScheduler,
            FakeClock,
            list[bool],
        ]:
            fake_sdk_client = FakeSdkClient()
            fake_scheduler = FakeScheduler()
            fake_clock = FakeClock()
            completed: list[bool] = []
            new_controller = AccountListNetworkController(
                client=fake_sdk_client,
                messages=messages,
                envelope_type=getattr(common, "ProtoMessage"),
                response_ids=RESPONSE_IDS,
                schedule=fake_scheduler.schedule,
                on_finished=lambda: completed.append(True),
                clock=fake_clock,
                credentials=SYNTHETIC_CREDENTIALS,
            )
            return (
                new_controller,
                fake_sdk_client,
                fake_scheduler,
                fake_clock,
                completed,
            )

        controller, sdk_client, scheduler, clock, finished = make_controller()
        controller.start()
        assert sdk_client.started
        scheduler.tick()  # Connected ще не стався — не повинно бути early timeout.
        assert controller.error_code is None
        sdk_client.dispatch_connected()
        response = getattr(messages, "ProtoOAApplicationAuthRes")()
        sdk_client.dispatch_message(make_envelope(messages, response))
        sdk_client.dispatch_message(make_envelope(messages, account_list(messages)))
        assert controller.matched and controller.error_code is None
        assert [msg.DESCRIPTOR.name for msg in sdk_client.sent] == [
            "ProtoOAApplicationAuthReq",
            "ProtoOAGetAccountListByAccessTokenReq",
        ]
        assert sdk_client.stop_calls == 1 and finished == [True]
        sdk_client.dispatch_disconnected("after completion")
        assert sdk_client.stop_calls == 1 and finished == [True]

        controller, sdk_client, scheduler, clock, finished = make_controller()
        controller.start()
        clock.seconds += 61
        scheduler.tick()
        assert controller.error_code == "ACCOUNTLIST_TIMEOUT"
        assert sdk_client.stop_calls == 1 and finished == [True]
        denied += 1

        controller, sdk_client, scheduler, clock, finished = make_controller()
        controller.start()
        sdk_client.dispatch_connected()
        sdk_client.dispatch_disconnected("drop")
        assert controller.error_code == "DISCONNECTED_BEFORE_ACCOUNTLIST"
        assert sdk_client.stop_calls == 1 and finished == [True]
        denied += 1

        controller, sdk_client, scheduler, clock, finished = make_controller()
        controller.start()
        sdk_client.dispatch_connected()
        sdk_client.dispatch_message(
            make_envelope(messages, account_list(messages, login=12345))
        )
        assert controller.error_code == "ACCOUNTLIST_RESPONSE_REJECTED"
        assert not controller.matched and finished == [True]
        denied += 1

        controller, sdk_client, scheduler, clock, finished = make_controller()
        controller.start()
        sdk_client.dispatch_connected()
        sdk_client.pending[0].reject("SYNTHETIC_SEND_ERROR")
        assert controller.error_code == "SDK_SEND_FAILED"
        assert finished == [True]
        denied += 1

        # CLI без дозволу не викликає ні SDK, ні читання LGE credentials.
        with patch(
            "tests.roadmap116.t116_43_first_demo_account_list_network"
            ".run_network_child",
            side_effect=AssertionError("NO NETWORK"),
        ) as forbidden_network:
            assert (
                main(
                    ["--offline-preflight"],
                    sdk_check=lambda: "VERIFIED_NO_EXTERNAL_NETWORK",
                )
                == 0
            )
            for arguments in (
                [],
                ["--live"],
                ["--demo-network"],
                ["--network-child"],
                ["--offline-preflight", "--confirm", CLI_CONFIRMATION],
            ):
                if arguments in (
                    [],
                    ["--live"],
                    [
                        "--offline-preflight",
                        "--confirm",
                        CLI_CONFIRMATION,
                    ],
                ):
                    with redirect_stderr(StringIO()):
                        with pytest.raises(SystemExit):
                            main(arguments)
                else:
                    with pytest.raises(PermissionError):
                        main(arguments, environment={})
                denied += 1
            assert forbidden_network.call_count == 0

        assert main(["--offline-preflight"], sdk_check=lambda: "SDK_NOT_READY") == 2
        denied += 1
        good = SupervisedResult(
            returncode=0,
            hard_timeout=False,
            reaped=True,
            stdout="\n".join(GOOD_CHILD_LINES) + "\n",
            stderr="",
        )
        assert summarize_child(good)
        assert safe_child_failure_code(good) == "INVALID_CHILD_RESULT"
        for bad_result in (
            SupervisedResult(1, False, True, good.stdout, ""),
            SupervisedResult(0, True, True, good.stdout, ""),
            SupervisedResult(0, False, False, good.stdout, ""),
            SupervisedResult(0, False, True, good.stdout, "SENSITIVE"),
            SupervisedResult(0, False, True, "", ""),
            SupervisedResult(0, False, True, good.stdout + "EXTRA\n", ""),
        ):
            assert not summarize_child(bad_result)
            denied += 1

        # Popen лише fake: перевіряємо час, env, kill/reap без SDK.
        class FakeProcess:
            def __init__(self, *, timeout: bool = False) -> None:
                self.timeout = timeout
                self.killed = False
                self.calls = 0

            def communicate(self, *, timeout: float) -> tuple[str, str]:
                self.calls += 1
                assert timeout > 0
                if self.timeout and not self.killed:
                    raise subprocess.TimeoutExpired("SYNTHETIC_CHILD", timeout)
                return good.stdout, ""

            def wait(self, timeout: float | None = None) -> int:
                assert timeout is None or timeout > 0
                assert not self.timeout or self.killed
                return 124 if self.killed else 0

            def poll(self) -> int | None:
                return 124 if self.killed else 0

            def kill(self) -> None:
                self.killed = True

        fake_child = FakeProcess()
        launch_calls: list[dict[str, Any]] = []

        def fake_popen(_args: list[str], **kwargs: Any) -> FakeProcess:
            launch_calls.append(kwargs)
            return fake_child

        result = supervise_network_child(child_env, popen=fake_popen)
        assert summarize_child(result)
        assert len(launch_calls) == 1
        assert launch_calls[0]["env"] is not os.environ
        assert launch_calls[0]["shell"] is False
        assert launch_calls[0]["env"]["CTRADER_ACCESS_TOKEN"] == (
            SYNTHETIC_CREDENTIALS.access_token
        )
        timeout_child = FakeProcess(timeout=True)
        timed_out = supervise_network_child(
            child_env, popen=lambda _args, **_kwargs: timeout_child
        )
        assert timed_out.hard_timeout and timeout_child.killed
        assert not summarize_child(timed_out)
        assert safe_child_failure_code(timed_out) == "HARD_PROCESS_TIMEOUT"
        denied += 1

    captured = capsys.readouterr().out
    assert OFFLINE_SUCCESS in captured
    assert SYNTHETIC_CREDENTIALS.client_secret not in captured
    assert SYNTHETIC_CREDENTIALS.access_token not in captured
    print("T116-43 TEST_ONLY | first DEMO AccountList network OFFLINE")
    print(f"negative_scenarios_denied={denied}")
    print("sdk_callbacks=VERIFIED_SYNTHETIC")
    print("strict_outbound=APPLICATION_ACCOUNTLIST_HEARTBEAT_ONLY")
    print("credentials=SYNTHETIC_ONLY")
    print("child_process=NOT_STARTED_NETWORK")
    print("external_tcp=BLOCKED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print("T116-43=GREEN_OFFLINE_FIRST_NETWORK_PREFLIGHT")
