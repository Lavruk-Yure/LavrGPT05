"""T116-32 TEST_ONLY — ізольований cTrader DEMO read-only discovery.

Звичайний запуск дозволяє лише offline-preflight. Мережевий режим потребує
двох явних незалежних підтверджень і credentials тільки з environment.
LGE, WSP, RuntimeEngine, IB та production-конфігурація не використовуються.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable, Mapping, Sequence
from importlib import import_module
from time import monotonic
from types import ModuleType
from typing import Any

from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_23_sdk_offline_bridge import (
    load_real_sdk_types,
    sdk_client_spec,
)
from tests.roadmap116.t116_29_sdk_outbound_guard import guarded_sdk_outbound
from tests.roadmap116.t116_31_demo_readonly_discovery_session import (
    DemoReadOnlyDiscoverySession,
    INBOUND_RESPONSE_NAMES,
)

NETWORK_APPROVAL_VARIABLE = "T11632_ALLOW_DEMO_READONLY_NETWORK"
NETWORK_APPROVAL_VALUE = "DEMO_46368962_SYMBOLS_ONLY"
NETWORK_CONFIRMATION = "READONLY_DEMO_46368962"
CREDENTIAL_VARIABLES = (
    "CTRADER_CLIENT_ID",
    "CTRADER_CLIENT_SECRET",
    "CTRADER_ACCESS_TOKEN",
)
WATCHDOG_INTERVAL_SECONDS = 0.25


class SdkReadOnlyTransport:
    """Відправляти лише через підконтрольну SDK Client.send межу."""

    def __init__(
        self,
        *,
        client: object,
        on_send_error: Callable[[], None],
    ) -> None:
        self._client = client
        self._on_send_error = on_send_error
        self._disconnected = False

    def send(self, message: object) -> None:
        """Не допускати безконтрольних Deferred-помилок."""
        send = getattr(self._client, "send")
        pending = send(message)
        add_errback = getattr(pending, "addErrback", None)
        if not callable(add_errback):
            raise RuntimeError("T116-32: SDK.send без Deferred")

        def on_error(_failure: object) -> None:
            self._on_send_error()

        add_errback(on_error)

    @property
    def stopping(self) -> bool:
        """Відрізняти власний stopService від зовнішнього розриву."""
        return self._disconnected

    def disconnect(self) -> None:
        """Зупинити SDK service не більш ніж один раз."""
        if self._disconnected:
            return
        self._disconnected = True
        stop_service = getattr(self._client, "stopService")
        stop_service()


class DemoNetworkDiscoveryController:
    """Зв'язати SDK callbacks з уже перевіреною T116-31 сесією."""

    def __init__(
        self,
        *,
        client: object,
        endpoints: object,
        protocol_type: type,
        messages: ModuleType,
        envelope_type: type,
        response_payload_types: Mapping[str, int],
        monotonic_clock: Callable[[], float],
        schedule: Callable[[float, Callable[[], None]], object],
        on_finished: Callable[[], None],
        client_id: str,
        client_secret: str,
        access_token: str,
    ) -> None:
        # SDK Client надається динамічно: контракт callbacks перевіряє preflight.
        self._client: Any = client
        self._schedule = schedule
        self._on_finished = on_finished
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token = access_token
        self.result_symbol_id: int | None = None
        self.error_code: str | None = None
        self._finished = False
        self._started = False
        self._transport = SdkReadOnlyTransport(
            client=client,
            on_send_error=lambda: self._fail("SDK_SEND_FAILED"),
        )
        self._session = DemoReadOnlyDiscoverySession(
            endpoints=endpoints,
            protocol_type=protocol_type,
            messages=messages,
            envelope_type=envelope_type,
            response_payload_types=response_payload_types,
            transport=self._transport,
            monotonic_clock=monotonic_clock,
        )

    def start(self) -> None:
        """Підписати callbacks і запустити watchdog перед startService."""
        if self._started:
            raise RuntimeError("T116-32: повторний запуск заборонений")
        self._started = True
        self._session.__enter__()
        # noinspection PyBroadException
        try:
            self._client.setConnectedCallback(self._connected)
            self._client.setDisconnectedCallback(self._disconnected)
            self._client.setMessageReceivedCallback(self._message)
            self._schedule(WATCHDOG_INTERVAL_SECONDS, self._watchdog)
            self._client.startService()
        except Exception:
            self._fail("SDK_START_FAILED")

    def _connected(self, _client: object) -> None:
        if self._finished:
            return
        client_id, client_secret, access_token = (
            self._client_id, self._client_secret, self._access_token
        )
        self._client_id = ""
        self._client_secret = ""
        self._access_token = ""
        # noinspection PyBroadException
        try:
            self._session.on_connected(
                client_id=client_id,
                client_secret=client_secret,
                access_token=access_token,
            )
        except Exception:
            self._fail("APPLICATION_AUTH_REQUEST_FAILED")

    def _message(self, _client: object, envelope: Any) -> None:
        if self._finished:
            return
        # noinspection PyBroadException
        try:
            symbol_id = self._session.on_envelope(envelope)
        except Exception:
            self._fail("UNEXPECTED_OR_INVALID_RESPONSE")
            return
        if symbol_id is not None:
            self.result_symbol_id = symbol_id
            self._finish()

    def _disconnected(self, _client: object, _reason: object) -> None:
        if self._finished:
            return
        # stopService() може синхронно спричинити callback від'єднання.
        # Коли закриття ініційоване нашою сесією, результат визначає
        # зовнішній callback, що викликав close(), а не це повідомлення.
        if self._transport.stopping:
            return
        self._fail("DISCONNECTED_BEFORE_SYMBOLS")

    def _watchdog(self) -> None:
        if self._finished:
            return
        # noinspection PyBroadException
        try:
            self._session.check_deadline()
        except Exception:
            self._fail("DISCOVERY_TIMEOUT")
            return
        # noinspection PyBroadException
        try:
            self._schedule(WATCHDOG_INTERVAL_SECONDS, self._watchdog)
        except Exception:
            self._fail("WATCHDOG_SCHEDULING_FAILED")

    def fail_closed(self, error_code: str) -> None:
        """Завершити сесію у разі зовнішньої помилки reactor/SDK."""
        self._fail(error_code)

    def _fail(self, error_code: str) -> None:
        if self._finished:
            return
        self.error_code = error_code
        self._finish()

    def _finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        self._client_id = ""
        self._client_secret = ""
        self._access_token = ""
        # noinspection PyBroadException
        try:
            self._session.close()
        except Exception:
            self.error_code = self.error_code or "SDK_STOP_FAILED"
        self._on_finished()


def authorized_credentials(
    *,
    confirmation: str | None,
    environment: Mapping[str, str],
) -> tuple[str, str, str]:
    """Fail-closed перевірка перед будь-яким створенням реального Client."""
    if confirmation != NETWORK_CONFIRMATION:
        raise PermissionError("T116-32: немає явного CLI підтвердження")
    if environment.get(NETWORK_APPROVAL_VARIABLE) != NETWORK_APPROVAL_VALUE:
        raise PermissionError("T116-32: немає окремого environment дозволу")
    credentials = tuple(
        environment.get(name, "").strip()
        for name in CREDENTIAL_VARIABLES
    )
    if len(credentials) != 3 or not all(credentials):
        raise PermissionError("T116-32: відсутні DEMO credentials у environment")
    return credentials[0], credentials[1], credentials[2]


def run_demo_network(*, credentials: tuple[str, str, str]) -> int:
    """Єдине місце, де після авторизації допускається SDK Client()."""
    endpoints, client_type, protocol_type, messages, common = load_real_sdk_types()
    spec = sdk_client_spec(endpoints, protocol_type)
    reactor = getattr(import_module("twisted.internet"), "reactor")
    frame_sender_type = getattr(
        import_module("twisted.protocols.basic"), "Int32StringReceiver"
    )
    envelope_type = getattr(common, "ProtoMessage")
    response_types = {
        name: int(getattr(getattr(messages, name)(), "payloadType"))
        for name in INBOUND_RESPONSE_NAMES
    }

    def stop_reactor() -> None:
        if bool(getattr(reactor, "running", False)):
            reactor.stop()

    controller: DemoNetworkDiscoveryController | None = None
    with guarded_sdk_outbound(
        client_type=client_type,
        tcp_protocol_type=protocol_type,
        frame_sender_type=frame_sender_type,
        request_messages=messages,
        common_messages=common,
    ):
        # Конструктор SDK може почати TCP-з'єднання: тільки всередині guard.
        client = client_type(spec.demo_host, spec.port, protocol_type)
        controller = DemoNetworkDiscoveryController(
            client=client,
            endpoints=endpoints,
            protocol_type=protocol_type,
            messages=messages,
            envelope_type=envelope_type,
            response_payload_types=response_types,
            monotonic_clock=monotonic,
            schedule=reactor.callLater,
            on_finished=lambda: reactor.callLater(0, stop_reactor),
            client_id=credentials[0],
            client_secret=credentials[1],
            access_token=credentials[2],
        )
        # noinspection PyBroadException
        try:
            controller.start()
            if controller.error_code is None and controller.result_symbol_id is None:
                reactor.run()
        except Exception:
            controller.fail_closed("REACTOR_OR_SDK_FAILED")
        finally:
            if controller.result_symbol_id is None and controller.error_code is None:
                controller.fail_closed("REACTOR_EXITED_WITHOUT_RESULT")

    if controller.result_symbol_id is None or controller.error_code is not None:
        print("T116-32=FAILED_DEMO_READONLY_DISCOVERY")
        print(f"failure_code={controller.error_code or 'NO_RESULT'}")
        return 1
    print(f"demo_api_account_id={DEMO_API_ACCOUNT_ID}")
    print(f"real_eurusd_symbol_id={controller.result_symbol_id}")
    print("outbound_request_policy=APPLICATION_ACCOUNT_SYMBOLS_HEARTBEAT_ONLY")
    print("production_changes=0")
    print("T116-32=GREEN_DEMO_READONLY_SYMBOL_DISCOVERY")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Без аргументів, --live або без двох дозволів — не виходити в мережу."""
    parser = argparse.ArgumentParser(allow_abbrev=False)
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--offline-preflight", action="store_true")
    options.add_argument("--demo-network", action="store_true")
    parser.add_argument("--confirm", default=None)
    args = parser.parse_args(argv)
    if args.offline_preflight:
        if args.confirm is not None:
            parser.error("T116-32: confirm не використовується в offline-preflight")
        print("T116-32 TEST_ONLY | network launcher OFFLINE")
        print("sdk_client_constructor=NOT_CALLED")
        print("real_broker_requests=0")
        print("network_launch_authorized=NO")
        print("T116-32=GREEN_OFFLINE_NETWORK_LAUNCH_GUARD")
        return 0

    credentials = authorized_credentials(
        confirmation=args.confirm,
        environment=os.environ,
    )
    return run_demo_network(credentials=credentials)


if __name__ == "__main__":
    raise SystemExit(main())
