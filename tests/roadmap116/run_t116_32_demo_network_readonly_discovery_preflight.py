"""T116-32 TEST_ONLY — перевірка мережевого launcher без створення Client()."""

from __future__ import annotations

import ast
import socket
from collections.abc import Callable
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from importlib import import_module
from importlib.util import find_spec
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from tests.roadmap116.run_t116_24_demo_symbol_discovery_contract import (
    synthetic_sdk_messages,
)
from tests.roadmap116.run_t116_25_demo_network_safety_preflight import (
    FakeClock,
    FakeEndpoints,
    FakeProtocol,
)
from tests.roadmap116.run_t116_31_demo_readonly_symbol_discovery_preflight import (
    FAKE_PAYLOAD_TYPES,
    SYNTHETIC_EURUSD_SYMBOL_ID,
    FakeEnvelope,
    envelope_for,
    response_sequence,
)
from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_23_sdk_offline_bridge import load_real_sdk_types
from tests.roadmap116.t116_29_sdk_outbound_guard import guarded_sdk_outbound
from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied
from tests.roadmap116.t116_31_demo_readonly_discovery_session import (
    INBOUND_RESPONSE_NAMES,
)
from tests.roadmap116.t116_32_demo_network_readonly_discovery import (
    CREDENTIAL_VARIABLES,
    NETWORK_APPROVAL_VALUE,
    NETWORK_APPROVAL_VARIABLE,
    NETWORK_CONFIRMATION,
    DemoNetworkDiscoveryController,
    authorized_credentials,
    main,
    run_demo_network,
)

SOURCE = Path(__file__).with_name("t116_32_demo_network_readonly_discovery.py")


class FakeDeferred:
    """Синтетичний результат Client.send()."""

    def __init__(self) -> None:
        self.error_callback: Callable[[object], None] | None = None

    # noinspection PyPep8Naming
    def addErrback(self, callback: Callable[[object], None]) -> None:
        self.error_callback = callback

    def reject(self, error: object) -> None:
        assert self.error_callback is not None
        self.error_callback(error)


class FakeSdkClient:
    """SDK-подібний Client без конструктора мережевої бібліотеки."""

    def __init__(self) -> None:
        self.sent: list[Any] = []
        self.pending: list[FakeDeferred] = []
        self.started = False
        self.stop_calls = 0
        self.connected: Callable[[object], None] | None = None
        self.disconnected: Callable[[object, object], None] | None = None
        self.message_received: Callable[[object, object], None] | None = None

    # noinspection PyPep8Naming
    def setConnectedCallback(self, callback: Callable[[object], None]) -> None:
        self.connected = callback

    # noinspection PyPep8Naming
    def setDisconnectedCallback(
        self, callback: Callable[[object, object], None]
    ) -> None:
        self.disconnected = callback

    # noinspection PyPep8Naming
    def setMessageReceivedCallback(
        self, callback: Callable[[object, object], None]
    ) -> None:
        self.message_received = callback

    def dispatch_connected(self) -> None:
        assert self.connected is not None
        self.connected(self)

    def dispatch_disconnected(self, reason: object) -> None:
        assert self.disconnected is not None
        self.disconnected(self, reason)

    def dispatch_message(self, envelope: object) -> None:
        assert self.message_received is not None
        self.message_received(self, envelope)

    def send(self, message: Any) -> FakeDeferred:
        self.sent.append(message)
        pending = FakeDeferred()
        self.pending.append(pending)
        return pending

    # noinspection PyPep8Naming
    def startService(self) -> None:
        self.started = True

    # noinspection PyPep8Naming
    def stopService(self) -> None:
        self.stop_calls += 1
        if self.disconnected is not None:
            self.dispatch_disconnected("SDK transport closed")


class FakeScheduler:
    """Контрольовані ticks без Twisted reactor."""

    def __init__(self) -> None:
        self.callbacks: list[Any] = []

    def schedule(self, delay: float, callback: Any) -> None:
        assert 0 < delay <= 1
        self.callbacks.append(callback)

    def tick(self) -> None:
        callback = self.callbacks.pop(0)
        callback()


def build_controller() -> tuple[
    DemoNetworkDiscoveryController,
    FakeSdkClient,
    FakeScheduler,
    FakeClock,
    list[bool],
]:
    client = FakeSdkClient()
    scheduler = FakeScheduler()
    clock = FakeClock()
    finished: list[bool] = []
    controller = DemoNetworkDiscoveryController(
        client=client,
        endpoints=FakeEndpoints(),
        protocol_type=FakeProtocol,
        messages=synthetic_sdk_messages(),
        envelope_type=FakeEnvelope,
        response_payload_types=FAKE_PAYLOAD_TYPES,
        monotonic_clock=clock,
        schedule=scheduler.schedule,
        on_finished=lambda: finished.append(True),
        client_id="TEST_ONLY_CLIENT",
        client_secret="TEST_ONLY_SECRET",
        access_token="TEST_ONLY_TOKEN",
    )
    return controller, client, scheduler, clock, finished


def test_t116_32_demo_network_readonly_discovery_preflight() -> None:
    """Перевірити мережеву межу та callback-адаптер у безмережевому режимі."""
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "guarded_sdk_outbound" in source
    assert "spec.demo_host, spec.port, protocol_type" in source
    assert "DemoReadOnlyDiscoverySession" in source
    assert "reactor.run()" in source
    assert not any(
        name in source
        for name in ("ProtoOANewOrderReq", "ProtoOAClosePositionReq", "LGE.conf")
    )
    assert any(
        isinstance(item, ast.FunctionDef) and item.name == "run_demo_network"
        for item in tree.body
    )

    denied = 0
    with external_tcp_denied():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            with pytest.raises(PermissionError):
                probe.connect(("192.0.2.10", 443))

        with patch(
            "tests.roadmap116.t116_32_demo_network_readonly_discovery.run_demo_network",
            side_effect=AssertionError("Зовнішня мережа не повинна запускатися"),
        ) as network_launch:
            assert main(["--offline-preflight"]) == 0
            assert network_launch.call_count == 0

            for arguments in (
                [],
                ["--live"],
                ["--demo-network"],
                ["--offline-preflight", "--confirm", NETWORK_CONFIRMATION],
                ["--demo-network", "--confirm", "WRONG"],
                ["--demo-network", "--confirm", NETWORK_CONFIRMATION],
            ):
                if arguments == ["--demo-network", "--confirm", "WRONG"]:
                    with pytest.raises(PermissionError):
                        main(arguments)
                elif arguments == ["--demo-network", "--confirm", NETWORK_CONFIRMATION]:
                    with patch.dict("os.environ", {NETWORK_APPROVAL_VARIABLE: ""}):
                        with pytest.raises(PermissionError):
                            main(arguments)
                elif arguments == ["--demo-network"]:
                    with pytest.raises(PermissionError):
                        main(arguments)
                else:
                    with redirect_stderr(StringIO()):
                        with pytest.raises(SystemExit) as error:
                            main(arguments)
                    assert error.value.code == 2
                denied += 1
            assert network_launch.call_count == 0

        good_env = dict(
            zip(
                CREDENTIAL_VARIABLES,
                ("TEST_ONLY_CLIENT", "TEST_ONLY_SECRET", "TEST_ONLY_TOKEN"),
                strict=True,
            )
        )
        with pytest.raises(PermissionError):
            authorized_credentials(
                confirmation=NETWORK_CONFIRMATION,
                environment=good_env,
            )
        denied += 1
        with pytest.raises(PermissionError):
            authorized_credentials(
                confirmation="WRONG",
                environment={
                    NETWORK_APPROVAL_VARIABLE: NETWORK_APPROVAL_VALUE,
                    **good_env,
                },
            )
        denied += 1
        with pytest.raises(PermissionError):
            authorized_credentials(
                confirmation=NETWORK_CONFIRMATION,
                environment={
                    NETWORK_APPROVAL_VARIABLE: NETWORK_APPROVAL_VALUE,
                    **{key: "" for key in CREDENTIAL_VARIABLES},
                },
            )
        denied += 1
        assert authorized_credentials(
            confirmation=NETWORK_CONFIRMATION,
            environment={NETWORK_APPROVAL_VARIABLE: NETWORK_APPROVAL_VALUE, **good_env},
        ) == tuple(good_env[key] for key in CREDENTIAL_VARIABLES)

        controller, client, scheduler, _clock, finished = build_controller()
        controller.start()
        assert client.started and len(scheduler.callbacks) == 1
        client.dispatch_connected()
        messages = synthetic_sdk_messages()
        for response in response_sequence(messages):
            client.dispatch_message(
                envelope_for(response, FakeEnvelope, FAKE_PAYLOAD_TYPES)
            )
        assert [packet.DESCRIPTOR.name for packet in client.sent] == [
            "ProtoOAApplicationAuthReq",
            "ProtoOAAccountAuthReq",
            "ProtoOASymbolsListReq",
        ]
        assert controller.result_symbol_id == SYNTHETIC_EURUSD_SYMBOL_ID
        assert controller.error_code is None
        assert client.stop_calls == 1
        assert finished == [True]
        scheduler.tick()
        client.dispatch_disconnected("after completion")
        assert client.stop_calls == 1 and finished == [True]

        controller, client, _scheduler, _clock, finished = build_controller()
        controller.start()
        client.dispatch_connected()
        client.dispatch_disconnected("offline drop")
        assert controller.error_code == "DISCONNECTED_BEFORE_SYMBOLS"
        assert client.stop_calls == 1 and finished == [True]
        denied += 1

        controller, client, scheduler, clock, finished = build_controller()
        controller.start()
        clock.seconds += 61.0
        scheduler.tick()
        assert controller.error_code == "DISCOVERY_TIMEOUT"
        assert client.stop_calls == 1 and finished == [True]
        denied += 1

        controller, client, _scheduler, _clock, finished = build_controller()
        controller.start()
        client.dispatch_connected()
        client.dispatch_message(FakeEnvelope(9999, b"unknown"))
        assert controller.error_code == "UNEXPECTED_OR_INVALID_RESPONSE"
        assert client.stop_calls == 1 and finished == [True]
        denied += 1

        controller, client, _scheduler, _clock, finished = build_controller()
        controller.start()
        client.dispatch_connected()
        client.pending[0].reject("synthetic deferred failure")
        assert controller.error_code == "SDK_SEND_FAILED"
        assert client.stop_calls == 1 and finished == [True]
        denied += 1

        # Повний run_demo_network() із синтетичним Client та reactor.
        # Зовнішній TCP залишається заблокованим, жодних реальних credentials.
        runtime_messages = synthetic_sdk_messages()
        for name, payload_id in FAKE_PAYLOAD_TYPES.items():
            setattr(getattr(runtime_messages, name), "payloadType", payload_id)
        guard_active = [False]
        guard_uses: list[dict[str, Any]] = []
        created_clients: list[FakeSdkClient] = []

        class FakeNetworkClient(FakeSdkClient):
            def __init__(self, host: str, port: int, protocol: type) -> None:
                assert guard_active == [True]
                assert host == FakeEndpoints.PROTOBUF_DEMO_HOST
                assert port == FakeEndpoints.PROTOBUF_PORT
                assert protocol is FakeProtocol
                super().__init__()
                created_clients.append(self)

        class FakeNetworkReactor:
            def __init__(self) -> None:
                self.running = False
                self.callbacks: list[tuple[float, Any]] = []

            # noinspection PyPep8Naming
            def callLater(self, delay: float, callback: Any) -> None:
                self.callbacks.append((delay, callback))

            def run(self) -> None:
                self.running = True
                live_client = created_clients[0]
                live_client.dispatch_connected()
                for synthetic_response in response_sequence(runtime_messages):
                    live_client.dispatch_message(
                        envelope_for(
                            synthetic_response, FakeEnvelope, FAKE_PAYLOAD_TYPES
                        )
                    )
                for delay, callback in self.callbacks:
                    if delay == 0:
                        callback()
                assert not self.running

            def stop(self) -> None:
                self.running = False

        fake_reactor = FakeNetworkReactor()

        @contextmanager
        def fake_guard(**kwargs: Any) -> Any:
            assert kwargs["client_type"] is FakeNetworkClient
            assert kwargs["tcp_protocol_type"] is FakeProtocol
            guard_uses.append(kwargs)
            guard_active[0] = True
            try:
                yield
            finally:
                guard_active[0] = False

        def fake_import(name: str) -> Any:
            if name == "twisted.internet":
                return SimpleNamespace(reactor=fake_reactor)
            if name == "twisted.protocols.basic":
                return SimpleNamespace(Int32StringReceiver=type("FakeFrames", (), {}))
            raise AssertionError(f"Unexpected import: {name}")

        with (
            patch(
                "tests.roadmap116.t116_32_demo_network_readonly_discovery."
                "load_real_sdk_types",
                return_value=(
                    FakeEndpoints(),
                    FakeNetworkClient,
                    FakeProtocol,
                    runtime_messages,
                    SimpleNamespace(ProtoMessage=FakeEnvelope),
                ),
            ),
            patch(
                "tests.roadmap116.t116_32_demo_network_readonly_discovery."
                "import_module",
                side_effect=fake_import,
            ),
            patch(
                "tests.roadmap116.t116_32_demo_network_readonly_discovery."
                "guarded_sdk_outbound",
                side_effect=fake_guard,
            ),
            redirect_stdout(StringIO()) as fake_output,
        ):
            assert (
                run_demo_network(
                    credentials=(
                        "TEST_ONLY_CLIENT",
                        "TEST_ONLY_SECRET",
                        "TEST_ONLY_TOKEN",
                    )
                )
                == 0
            )
        assert len(guard_uses) == 1 and guard_active == [False]
        assert len(created_clients) == 1
        assert created_clients[0].stop_calls == 1
        assert [msg.DESCRIPTOR.name for msg in created_clients[0].sent] == [
            "ProtoOAApplicationAuthReq",
            "ProtoOAAccountAuthReq",
            "ProtoOASymbolsListReq",
        ]
        assert (
            f"real_eurusd_symbol_id={SYNTHETIC_EURUSD_SYMBOL_ID}"
            in fake_output.getvalue()
        )

    print("T116-32 TEST_ONLY | DEMO read-only network launcher offline preflight")
    print(f"demo_api_account_id={DEMO_API_ACCOUNT_ID}")
    print("network_mode=LOCKED_WITH_TWO_INDEPENDENT_CONFIRMATIONS")
    print("sdk_callbacks=VERIFIED_SYNTHETIC")
    print("network_orchestration=VERIFIED_FAKE_CLIENT_AND_REACTOR")
    print("application_account_symbols=VERIFIED_OFFLINE")
    print(f"negative_scenarios_denied={denied}")
    print("timeout_disconnect_deferred_error=FAIL_CLOSED")
    print("production_changes=0")
    if find_spec("ctrader_open_api") is not None:
        with external_tcp_denied():
            endpoints, real_client, real_protocol, sdk_messages, sdk_common = (
                load_real_sdk_types()
            )
            for callback_method in (
                "setConnectedCallback",
                "setDisconnectedCallback",
                "setMessageReceivedCallback",
                "startService",
                "stopService",
                "send",
            ):
                assert callable(getattr(real_client, callback_method, None))
            assert getattr(endpoints, "PROTOBUF_DEMO_HOST") != getattr(
                endpoints, "PROTOBUF_LIVE_HOST"
            )
            response_ids = [
                int(getattr(getattr(sdk_messages, name)(), "payloadType"))
                for name in INBOUND_RESPONSE_NAMES
            ]
            assert len(set(response_ids)) == 3
            frame_sender = getattr(
                import_module("twisted.protocols.basic"), "Int32StringReceiver"
            )
            with guarded_sdk_outbound(
                client_type=real_client,
                tcp_protocol_type=real_protocol,
                frame_sender_type=frame_sender,
                request_messages=sdk_messages,
                common_messages=sdk_common,
            ):
                pass

        print("actual_ctrader_sdk=VERIFIED_NO_EXTERNAL_NETWORK")
    else:
        print("actual_ctrader_sdk=NOT_INSTALLED_LOCAL_RUNNER")
    print("sdk_client_constructor=NOT_CALLED")
    print("external_tcp=BLOCKED")
    print("real_broker_requests=0")
    print("real_eurusd_symbol_id=NOT_QUERIED_NO_NETWORK")
    print("network_launch_authorized=NO")
    print("T116-32=GREEN_OFFLINE_NETWORK_LAUNCH_PREFLIGHT")
