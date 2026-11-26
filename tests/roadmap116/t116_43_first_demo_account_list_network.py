"""T116-43 TEST_ONLY — один контрольований DEMO AccountList network child.

Без аргументів/дозволу — тільки відмова. Pytest та --offline-preflight
не читають секрети, не створюють Client і не відкривають TCP.
Реальний запуск окремо дозволяється оператором після офлайн-GREEN.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from importlib import import_module
from time import monotonic
from pathlib import Path
from typing import Any
from unittest.mock import patch

from google.protobuf.message import DecodeError, Message

from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_23_sdk_offline_bridge import (
    load_real_sdk_types,
    sdk_client_spec,
)
from tests.roadmap116.t116_26_process_watchdog import (
    SUPERVISOR_TIMEOUT_SECONDS,
    SupervisedResult,
)
from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied
from tests.roadmap116.t116_32_demo_network_readonly_discovery import (
    CREDENTIAL_VARIABLES,
    NETWORK_APPROVAL_VARIABLE as SYMBOL_APPROVAL_VARIABLE,
    SdkReadOnlyTransport,
    WATCHDOG_INTERVAL_SECONDS,
)
from tests.roadmap116.t116_36_lge_credentials_launcher_bridge import (
    BridgeRejected,
    BridgedCredentials,
    make_launcher_environment,
    read_credentials_for_bridge,
)
from tests.roadmap116.t116_39_demo_account_identity_preflight import (
    EXPECTED_GUI_TRADER_LOGIN,
)
from tests.roadmap116.t116_40_demo_account_list_scoped_policy import (
    guarded_scoped_account_list,
    sdk_schema_preflight,
)
from tests.roadmap116.t116_41_demo_account_list_session import (
    OfflineAccountListSession,
    RESPONSE_NAMES,
)
from tests.roadmap116.t116_42_supervised_account_list_offline import (
    SYSTEM_ENV_KEYS,
)

APPROVAL_VARIABLE = "T11643_ALLOW_DEMO_ACCOUNTLIST_NETWORK"
APPROVAL_VALUE = "DEMO_ACCOUNTLIST_46368962_ONE_SHOT"
CLI_CONFIRMATION = "READONLY_ACCOUNTLIST_46368962"
ORDERS_VARIABLE = "T11643_ORDERS_OFF_ATTESTED"
WSP_VARIABLE = "T11643_WSP_STOPPED_ATTESTED"
ORDERS_CONFIRMATION = "ORDERS_OFF"
WSP_CONFIRMATION = "WSP_STOPPED"
CHILD_MODULE = "tests.roadmap116.t116_43_first_demo_account_list_network"
CHILD_SUCCESS = "T116-43=GREEN_REAL_DEMO_ACCOUNT_IDENTITY"
PARENT_SUCCESS = "T116-43=GREEN_SUPERVISED_DEMO_ACCOUNT_IDENTITY"
OFFLINE_SUCCESS = "T116-43=GREEN_OFFLINE_FIRST_NETWORK_PREFLIGHT"
ERROR_PATTERN = re.compile(r"^failure_code=([A-Z][A-Z0-9_]*)$")
KNOWN_FAILURE_CODES = frozenset({
    "SDK_START_FAILED", "MISSING_CREDENTIALS",
    "APPLICATION_AUTH_REQUEST_FAILED", "ACCOUNTLIST_RESPONSE_REJECTED",
    "IDENTITY_MISMATCH", "DISCONNECTED_BEFORE_ACCOUNTLIST",
    "ACCOUNTLIST_TIMEOUT", "WATCHDOG_FAILED", "SDK_SEND_FAILED",
    "SDK_STOP_FAILED", "REACTOR_OR_SDK_FAILED",
    "REACTOR_EXITED_WITHOUT_RESULT", "NO_RESULT", "SDK_CHILD_FAILED",
})
ALLOWED_REQUEST_NAMES = frozenset({
    "ProtoOAApplicationAuthReq",
    "ProtoOAGetAccountListByAccessTokenReq",
    "ProtoHeartbeatEvent",
})


def approved(
    *, confirmation: str | None, environment: Mapping[str, str],
    operator_confirmations: bool = False,
) -> bool:
    """До будь-яких читань credentials вимагати два незалежні дозволи."""
    if confirmation != CLI_CONFIRMATION:
        return False
    if environment.get(APPROVAL_VARIABLE) != APPROVAL_VALUE:
        return False
    if SYMBOL_APPROVAL_VARIABLE in environment:
        return False
    if operator_confirmations and (
        environment.get(ORDERS_VARIABLE) != ORDERS_CONFIRMATION
        or environment.get(WSP_VARIABLE) != WSP_CONFIRMATION
    ):
        return False
    return True


def prepare_child_environment(
    credentials: BridgedCredentials,
    *, environment: Mapping[str, str],
    orders_confirmation: str,
    wsp_confirmation: str,
) -> dict[str, str]:
    """Передати мінімальний Windows env та credentials лише в пам'яті."""
    if not approved(confirmation=CLI_CONFIRMATION, environment=environment):
        raise PermissionError("T116-43: немає незалежного дозволу")
    if (
        orders_confirmation != ORDERS_CONFIRMATION
        or wsp_confirmation != WSP_CONFIRMATION
    ):
        raise PermissionError("T116-43: ручні підтвердження відсутні")
    safe_env = {
        key: value
        for key in SYSTEM_ENV_KEYS
        if isinstance((value := environment.get(key)), str) and value
    }
    if os.name == "nt" and not safe_env.get("SystemRoot"):
        raise PermissionError("T116-43: Windows SystemRoot відсутній")
    safe_env[APPROVAL_VARIABLE] = APPROVAL_VALUE
    safe_env[ORDERS_VARIABLE] = ORDERS_CONFIRMATION
    safe_env[WSP_VARIABLE] = WSP_CONFIRMATION
    child_env = make_launcher_environment(
        credentials, environment=safe_env
    )
    if not approved(
        confirmation=CLI_CONFIRMATION,
        environment=child_env,
        operator_confirmations=True,
    ):
        raise PermissionError("T116-43: дочірній дозвіл не сформовано")
    return child_env


@contextmanager
def exact_account_list_outbound(
    *, client_type: type, tcp_protocol_type: type, frame_sender_type: type,
    request_messages: object, common_messages: object, expected_token: str,
) -> Iterator[None]:
    """Поверх T116-40 заборонити навіть Symbols/AccountAuth."""
    envelope_type = getattr(common_messages, "ProtoMessage")
    permitted_ids: set[int] = set()
    for name in ALLOWED_REQUEST_NAMES:
        module = common_messages if name == "ProtoHeartbeatEvent" else request_messages
        message_type = getattr(module, name)
        if not isinstance(message_type, type) or not issubclass(message_type, Message):
            raise TypeError("T116-43: SDK request schema несумісна")
        permitted_ids.add(int(getattr(message_type(), "payloadType")))
    if len(permitted_ids) != len(ALLOWED_REQUEST_NAMES):
        raise ValueError("T116-43: неоднозначні request payloadType")

    with guarded_scoped_account_list(
        client_type=client_type,
        tcp_protocol_type=tcp_protocol_type,
        frame_sender_type=frame_sender_type,
        request_messages=request_messages,
        common_messages=common_messages,
        expected_token=expected_token,
    ):
        client_send = getattr(client_type, "send")
        tcp_send = getattr(tcp_protocol_type, "send")
        frame_send = getattr(frame_sender_type, "sendString")

        def check_object(message: object) -> None:
            message_name = getattr(getattr(message, "DESCRIPTOR", None), "name", "")
            if message_name not in ALLOWED_REQUEST_NAMES:
                raise PermissionError("T116-43: сторонній protobuf заборонений")

        def check_frame(frame: object) -> None:
            if type(frame) is not bytes:
                raise PermissionError("T116-43: очікуються bytes")
            try:
                envelope = envelope_type()
                envelope.ParseFromString(frame)
                if not envelope.IsInitialized():
                    raise ValueError("неповний envelope")
                if envelope.payloadType not in permitted_ids:
                    raise ValueError("protobuf поза AccountList")
            except (DecodeError, ValueError, TypeError) as exc:
                raise PermissionError("T116-43: кадр не дозволений") from exc

        def guarded_client(
            client: object, message: object, *args: Any, **kwargs: Any
        ) -> Any:
            check_object(message)
            return client_send(client, message, *args, **kwargs)

        def guarded_tcp(
            protocol: object, message: object, *args: Any, **kwargs: Any
        ) -> Any:
            check_object(message)
            return tcp_send(protocol, message, *args, **kwargs)

        def guarded_frame(
            protocol: object, frame: object, *args: Any, **kwargs: Any
        ) -> Any:
            check_frame(frame)
            return frame_send(protocol, frame, *args, **kwargs)

        with (
            patch.object(client_type, "send", guarded_client),
            patch.object(tcp_protocol_type, "send", guarded_tcp),
            patch.object(frame_sender_type, "sendString", guarded_frame),
        ):
            yield


class AccountListNetworkController:
    """Прив'язка callback SDK до перевіреної T116-41 state machine."""

    def __init__(
        self, *, client: object, messages: object, envelope_type: type,
        response_ids: Mapping[str, int], schedule: Callable[..., object],
        on_finished: Callable[[], None], clock: Callable[[], float],
        credentials: BridgedCredentials,
    ) -> None:
        self._client: Any = client
        self._schedule = schedule
        self._on_finished = on_finished
        self._clock = clock
        self._started_at: float | None = None
        self._credentials: BridgedCredentials | None = credentials
        self._started = False
        self._finished = False
        self.error_code: str | None = None
        self.matched = False
        self._transport = SdkReadOnlyTransport(
            client=client,
            on_send_error=lambda: self._fail("SDK_SEND_FAILED"),
        )
        self._session = OfflineAccountListSession(
            sdk_messages=messages,
            envelope_type=envelope_type,
            response_payload_types=response_ids,
            sender=self._transport.send,
            disconnect=self._transport.disconnect,
            clock=clock,
        )

    def start(self) -> None:
        if self._started:
            raise RuntimeError("T116-43: повторний запуск")
        self._started = True
        self._started_at = self._clock()
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
        credentials = self._credentials
        self._credentials = None
        if credentials is None:
            self._fail("MISSING_CREDENTIALS")
            return
        # noinspection PyBroadException
        try:
            self._session.on_connected(
                client_id=credentials.client_id,
                client_secret=credentials.client_secret,
                access_token=credentials.access_token,
            )
        except Exception:
            self._fail("APPLICATION_AUTH_REQUEST_FAILED")

    def _message(self, _client: object, envelope: object) -> None:
        if self._finished:
            return
        # noinspection PyBroadException
        try:
            result = self._session.on_envelope(envelope)
        except Exception:
            self._fail("ACCOUNTLIST_RESPONSE_REJECTED")
            return
        if result is not None:
            if not result.matched:
                self._fail("IDENTITY_MISMATCH")
                return
            self.matched = True
            self._finish()

    def _disconnected(self, _client: object, _reason: object) -> None:
        if self._finished or self._transport.stopping:
            return
        self._fail("DISCONNECTED_BEFORE_ACCOUNTLIST")

    def _watchdog(self) -> None:
        if self._finished:
            return
        # noinspection PyBroadException
        try:
            started_at = self._started_at
            if started_at is None or self._clock() - started_at >= 60:
                raise TimeoutError("T116-43: connection/session deadline")
            if self._session.phase != "NEW":
                self._session.check_deadline()
        except Exception:
            self._fail("ACCOUNTLIST_TIMEOUT")
            return
        # noinspection PyBroadException
        try:
            self._schedule(WATCHDOG_INTERVAL_SECONDS, self._watchdog)
        except Exception:
            self._fail("WATCHDOG_FAILED")

    def fail(self, code: str) -> None:
        """Дозволений supervisor fail-closed виклик."""
        self._fail(code)

    def _fail(self, code: str) -> None:
        if self._finished:
            return
        self.error_code = code
        self._finish()

    def _finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        self._credentials = None
        # noinspection PyBroadException
        try:
            self._session.close()
        except Exception:
            self.error_code = self.error_code or "SDK_STOP_FAILED"
        self._on_finished()


def run_network_child(credentials: BridgedCredentials) -> int:
    """Client створюється лише в child, всередині потрійного outbound guard."""
    endpoints, client_type, protocol_type, messages, common = load_real_sdk_types()
    spec = sdk_client_spec(endpoints, protocol_type)
    reactor = getattr(import_module("twisted.internet"), "reactor")
    frame_sender_type = getattr(
        import_module("twisted.protocols.basic"), "Int32StringReceiver"
    )
    response_ids = {
        name: int(getattr(messages, name)().payloadType)
        for name in RESPONSE_NAMES
    }

    def stop_reactor() -> None:
        if bool(getattr(reactor, "running", False)):
            reactor.stop()

    controller: AccountListNetworkController | None = None
    with exact_account_list_outbound(
        client_type=client_type,
        tcp_protocol_type=protocol_type,
        frame_sender_type=frame_sender_type,
        request_messages=messages,
        common_messages=common,
        expected_token=credentials.access_token,
    ):
        client = client_type(spec.demo_host, spec.port, protocol_type)
        controller = AccountListNetworkController(
            client=client,
            messages=messages,
            envelope_type=getattr(common, "ProtoMessage"),
            response_ids=response_ids,
            schedule=reactor.callLater,
            on_finished=lambda: reactor.callLater(0, stop_reactor),
            clock=monotonic,
            credentials=credentials,
        )
        # noinspection PyBroadException
        try:
            controller.start()
            if controller.error_code is None and not controller.matched:
                reactor.run()
        except Exception:
            controller.fail("REACTOR_OR_SDK_FAILED")
        finally:
            if controller.error_code is None and not controller.matched:
                controller.fail("REACTOR_EXITED_WITHOUT_RESULT")

    if not controller.matched or controller.error_code is not None:
        print(f"failure_code={controller.error_code or 'NO_RESULT'}")
        print("T116-43=FAILED_DEMO_ACCOUNT_IDENTITY")
        return 1
    print(f"demo_api_account_id={DEMO_API_ACCOUNT_ID}")
    print(f"gui_trader_login={EXPECTED_GUI_TRADER_LOGIN}")
    print("account_is_live=NO")
    print("request_order=APPLICATION_AUTH_ACCOUNT_LIST")
    print("production_changes=0")
    print(CHILD_SUCCESS)
    return 0


def supervise_network_child(
    environment: Mapping[str, str],
    *, popen: Callable[..., Any] = subprocess.Popen,
) -> SupervisedResult:
    """Без shell, одна спроба, hard timeout/reap, stderr не розкриваємо."""
    if not approved(
        confirmation=CLI_CONFIRMATION,
        environment=environment,
        operator_confirmations=True,
    ):
        raise PermissionError("T116-43: немає дозволу дочірньому процесу")
    if not all(environment.get(name) for name in CREDENTIAL_VARIABLES):
        raise PermissionError("T116-43: credentials відсутні")
    process = popen(
        [sys.executable, "-m", CHILD_MODULE, "--network-child",
         "--confirm", CLI_CONFIRMATION],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(Path(__file__).resolve().parents[2]),
        env=dict(environment),
    )
    try:
        try:
            stdout, stderr = process.communicate(
                timeout=SUPERVISOR_TIMEOUT_SECONDS
            )
            return SupervisedResult(
                returncode=process.wait(), hard_timeout=False,
                reaped=process.poll() is not None,
                stdout=stdout, stderr=stderr,
            )
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5.0)
            return SupervisedResult(
                returncode=124, hard_timeout=True,
                reaped=process.poll() is not None,
                stdout=stdout, stderr=stderr,
            )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5.0)


def summarize_child(result: SupervisedResult) -> bool:
    """Лише whitelist звіту; raw stdout/stderr і traceback не друкувати."""
    expected = (
        f"demo_api_account_id={DEMO_API_ACCOUNT_ID}",
        f"gui_trader_login={EXPECTED_GUI_TRADER_LOGIN}",
        "account_is_live=NO",
        "request_order=APPLICATION_AUTH_ACCOUNT_LIST",
        "production_changes=0",
        CHILD_SUCCESS,
    )
    return (
        not result.hard_timeout
        and result.reaped
        and result.returncode == 0
        and not result.stderr
        and result.stdout.splitlines() == list(expected)
    )


def safe_child_failure_code(result: SupervisedResult) -> str:
    """Лише відомі статуси, без raw child output чи traceback."""
    if result.hard_timeout:
        return "HARD_PROCESS_TIMEOUT"
    if not result.reaped:
        return "CHILD_NOT_REAPED"
    if result.returncode == 0:
        return "INVALID_CHILD_RESULT"
    matches = [
        line for line in result.stdout.splitlines()
        if ERROR_PATTERN.fullmatch(line)
    ]
    if len(matches) != 1:
        return "CHILD_PROCESS_FAILED"
    parsed = ERROR_PATTERN.fullmatch(matches[0])
    if parsed and parsed.group(1) in KNOWN_FAILURE_CODES:
        return parsed.group(1)
    return "CHILD_PROCESS_FAILED"


def sdk_offline_check() -> str:
    """Справжній SDK, два response типи та DEMO host, жодних сокетів."""
    from tests.roadmap116.t116_33_supervised_demo_readonly_discovery import (
        sdk_offline_preflight,
    )
    with external_tcp_denied():
        basic = sdk_offline_preflight()
        account = sdk_schema_preflight()
        if basic != "VERIFIED_NO_EXTERNAL_NETWORK":
            return "SDK_NOT_READY"
        if account != "VERIFIED_NO_EXTERNAL_NETWORK":
            return "ACCOUNTLIST_SCHEMA_NOT_READY"
        endpoints, client_type, protocol, messages, common = load_real_sdk_types()
        spec = sdk_client_spec(endpoints, protocol)
        if spec.demo_host == spec.live_host:
            return "HOSTS_NOT_SEPARATED"
        for name in RESPONSE_NAMES:
            response_type = getattr(messages, name, None)
            if not isinstance(response_type, type) or not issubclass(
                response_type, Message
            ):
                return "RESPONSE_SCHEMA_NOT_READY"
        frame_sender_type = getattr(
            import_module("twisted.protocols.basic"), "Int32StringReceiver"
        )
        with exact_account_list_outbound(
            client_type=client_type,
            tcp_protocol_type=protocol,
            frame_sender_type=frame_sender_type,
            request_messages=messages,
            common_messages=common,
            expected_token="T11643_OFFLINE_SYNTHETIC_TOKEN",
        ):
            pass  # Перевірка патчів SDK без Client() та без TCP.
    return "VERIFIED_NO_EXTERNAL_NETWORK"


def main(
    argv: Sequence[str] | None = None,
    *, environment: Mapping[str, str] | None = None,
    ask: Callable[[str], str] = input,
    ask_password: Callable[[str], str] = getpass.getpass,
    credential_reader: Callable[[str], BridgedCredentials] = (
        read_credentials_for_bridge
    ),
    runner: Callable[[Mapping[str, str]], SupervisedResult] = supervise_network_child,
    sdk_check: Callable[[], str] = sdk_offline_check,
    child_runner: Callable[[BridgedCredentials], int] = run_network_child,
) -> int:
    """У мережу — лише --demo-network + явний env + ручний safety gate."""
    parser = argparse.ArgumentParser(allow_abbrev=False)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--offline-preflight", action="store_true")
    modes.add_argument("--demo-network", action="store_true")
    modes.add_argument("--network-child", action="store_true")
    parser.add_argument("--confirm", default=None)
    args = parser.parse_args(argv)
    env = os.environ if environment is None else environment
    if args.offline_preflight:
        if args.confirm is not None:
            parser.error("T116-43: offline не приймає --confirm")
        # noinspection PyBroadException
        try:
            status = sdk_check()
        except Exception:
            status = "SDK_PREFLIGHT_FAILED"
        ready = status == "VERIFIED_NO_EXTERNAL_NETWORK"
        print("T116-43 TEST_ONLY | first DEMO AccountList OFFLINE preflight")
        print(f"sdk_offline_preflight={status}")
        print("child_process=NOT_STARTED")
        print("sdk_client_constructor=NOT_CALLED")
        print("real_broker_requests=0")
        print("production_changes=0")
        print("network_launch_authorized=NO")
        print(OFFLINE_SUCCESS if ready else "T116-43=NOT_READY_OFFLINE")
        return 0 if ready else 2

    if not approved(
        confirmation=args.confirm, environment=env,
        operator_confirmations=args.network_child,
    ):
        raise PermissionError("T116-43: DEMO мережа не дозволена")
    if args.network_child:
        credentials = tuple(env.get(name, "") for name in CREDENTIAL_VARIABLES)
        if not all(isinstance(v, str) and v.strip() for v in credentials):
            raise PermissionError("T116-43: немає child credentials")
        if len(credentials) != 3:
            raise PermissionError("T116-43: неповне child environment")
        # Жодних traceback із можливими секретами в stderr.
        # noinspection PyBroadException
        try:
            return child_runner(BridgedCredentials(*credentials))
        except Exception:
            print("failure_code=SDK_CHILD_FAILED")
            return 2

    if env is not os.environ:
        raise PermissionError("T116-43: network тільки з реального environment")
    status = sdk_check()
    if status != "VERIFIED_NO_EXTERNAL_NETWORK":
        raise PermissionError("T116-43: SDK offline preflight не пройшов")
    try:
        orders = ask("Перевір Orders=OFF; введи ORDERS_OFF: ")
        wsp = ask("Перевір усі WSP STOPPED; введи WSP_STOPPED: ")
    except (EOFError, KeyboardInterrupt):
        orders, wsp = "", ""
    if orders != ORDERS_CONFIRMATION or wsp != WSP_CONFIRMATION:
        raise PermissionError("T116-43: без підтверджень мережу заборонено")
    try:
        password = ask_password("Пароль LGE (не відображається): ")
    except (EOFError, KeyboardInterrupt):
        password = ""
    try:
        credentials = credential_reader(password)
        child_env = prepare_child_environment(
            credentials, environment=env,
            orders_confirmation=orders, wsp_confirmation=wsp,
        )
    except (BridgeRejected, PermissionError):
        raise PermissionError("T116-43: credentials/DEMO gate відхилено") from None
    result = runner(child_env)
    if not summarize_child(result):
        print(f"failure_code={safe_child_failure_code(result)}")
        print("T116-43=FAILED_SUPERVISED_DEMO_ACCOUNT_IDENTITY")
        return 1
    print(f"demo_api_account_id={DEMO_API_ACCOUNT_ID}")
    print(f"gui_trader_login={EXPECTED_GUI_TRADER_LOGIN}")
    print("account_is_live=NO")
    print("production_changes=0")
    print(PARENT_SUCCESS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
