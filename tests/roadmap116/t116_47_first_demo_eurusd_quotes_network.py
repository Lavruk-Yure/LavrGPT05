"""T116-47 TEST_ONLY — одна контрольована DEMO-сесія EURUSD SpotEvent.

Pytest/--offline-preflight не створюють Client і не читають credentials.
Мережевий режим — тільки окремий дозвіл, safety attestations та один child.
Початковий SpotEvent не доводить, що ринок відкритий або ціна свіжа.
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
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from importlib import import_module
from pathlib import Path
from types import ModuleType
from time import monotonic
from typing import Any
from unittest.mock import patch

from google.protobuf.message import DecodeError, Message

from tests.roadmap116.t116_22_standalone_demo_reader import (
    DEMO_API_ACCOUNT_ID, QuoteObservation,
)
from tests.roadmap116.t116_23_sdk_offline_bridge import (
    load_real_sdk_types, make_reader, new_spot_subscription, sdk_client_spec,
)
from tests.roadmap116.t116_24_demo_symbol_discovery import DemoSymbolDiscovery
from tests.roadmap116.t116_26_process_watchdog import (
    SUPERVISOR_TIMEOUT_SECONDS, SupervisedResult,
)
from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied
from tests.roadmap116.t116_32_demo_network_readonly_discovery import (
    CREDENTIAL_VARIABLES, SdkReadOnlyTransport, WATCHDOG_INTERVAL_SECONDS,
)
from tests.roadmap116.t116_33_supervised_demo_readonly_discovery import (
    sdk_offline_preflight,
)
from tests.roadmap116.t116_36_lge_credentials_launcher_bridge import (
    BridgeRejected, BridgedCredentials, make_launcher_environment,
    read_credentials_for_bridge,
)
from tests.roadmap116.t116_42_supervised_account_list_offline import SYSTEM_ENV_KEYS
from tests.roadmap116.t116_43_first_demo_account_list_network import (
    APPROVAL_VARIABLE as ACCOUNTLIST_APPROVAL,
)
from tests.roadmap116.t116_44_supervised_demo_eurusd_symbol import (
    APPROVAL_VARIABLE as SYMBOL_APPROVAL,
)
from tests.roadmap116.t116_46_demo_eurusd_quotes_offline import (
    OBSERVED_EURUSD_SYMBOL_ID, guarded_scoped_quote_subscription,
    sdk_schema_preflight, validate_spot_subscription,
)

APPROVAL_VARIABLE = "T11647_ALLOW_DEMO_QUOTES_NETWORK"
APPROVAL_VALUE = "DEMO_EURUSD_QUOTES_46368962_ONE_SHOT"
CLI_CONFIRMATION = "READONLY_QUOTES_46368962"
ORDERS_ATTESTED = "T11647_ORDERS_OFF_ATTESTED"
WSP_ATTESTED = "T11647_WSP_STOPPED_ATTESTED"
ORDERS_CONFIRMATION = "ORDERS_OFF"
WSP_CONFIRMATION = "WSP_STOPPED"
CHILD_MODULE = "tests.roadmap116.t116_47_first_demo_eurusd_quotes_network"
CHILD_SUCCESS = "T116-47=GREEN_REAL_DEMO_EURUSD_QUOTES"
PARENT_SUCCESS = "T116-47=GREEN_SUPERVISED_DEMO_EURUSD_QUOTES"
OFFLINE_SUCCESS = "T116-47=GREEN_OFFLINE_FIRST_QUOTES_NETWORK_PREFLIGHT"
FAILURE = "T116-47=FAILED_SUPERVISED_DEMO_EURUSD_QUOTES"
SESSION_SECONDS = 60.0
MAX_PAYLOAD = 4 * 1024 * 1024
MAX_SIDE_AGE_SECONDS = 10.0
ALLOWED_OUTBOUND = (
    "ProtoOAApplicationAuthReq", "ProtoOAAccountAuthReq",
    "ProtoOASubscribeSpotsReq", "ProtoHeartbeatEvent",
)
INBOUND_NAMES = (
    "ProtoOAApplicationAuthRes", "ProtoOAAccountAuthRes",
    "ProtoOASubscribeSpotsRes", "ProtoOASpotEvent",
)
DIAGNOSTIC_PHASES = frozenset({
    "NEW", "APP_SENT", "ACCOUNT_SENT", "SUBSCRIBE_SENT", "SUBSCRIBED",
})
DIAGNOSTIC_INBOUND = frozenset({
    *INBOUND_NAMES, "SDK_ERROR_RESPONSE", "UNRECOGNIZED",
})
DIAGNOSTIC_CLASSES = frozenset({
    "DECODE_REJECTED", "APPLICATION_AUTH_REJECTED",
    "ACCOUNT_AUTH_REJECTED", "SUBSCRIBE_SEND_REJECTED",
    "SUBSCRIBE_ACCOUNT_MISMATCH", "SPOT_REJECTED",
    "UNEXPECTED_RESPONSE_ORDER",
})
KNOWN_ERRORS = frozenset({
    "SDK_START_FAILED", "SDK_SEND_FAILED", "APPLICATION_AUTH_FAILED",
    "INVALID_RESPONSE", "ACCOUNT_AUTH_FAILED", "SUBSCRIBE_FAILED",
    "QUOTE_SESSION_TIMEOUT", "DISCONNECTED_BEFORE_QUOTE",
    "WATCHDOG_FAILED", "SDK_STOP_FAILED", "REACTOR_OR_SDK_FAILED",
    "REACTOR_EXITED_WITHOUT_QUOTE", "NO_QUOTE", "SDK_CHILD_FAILED",
})
PRICE_PATTERN = re.compile(r"^(bid|ask)=([0-9]{1,4}\.[0-9]{5})$")
ERROR_PATTERN = re.compile(r"^failure_code=([A-Z][A-Z0-9_]*)$")


def approved(
    *, confirmation: str | None, environment: Mapping[str, str],
    child: bool = False,
) -> bool:
    """До credentials заборонити невірний режим і старі DEMO дозволи."""
    if confirmation != CLI_CONFIRMATION:
        return False
    if environment.get(APPROVAL_VARIABLE) != APPROVAL_VALUE:
        return False
    if ACCOUNTLIST_APPROVAL in environment or SYMBOL_APPROVAL in environment:
        return False
    if child and (
        environment.get(ORDERS_ATTESTED) != ORDERS_CONFIRMATION
        or environment.get(WSP_ATTESTED) != WSP_CONFIRMATION
    ):
        return False
    return True


def prepare_child_environment(
    credentials: BridgedCredentials, *, environment: Mapping[str, str],
    orders: str, wsp: str,
) -> dict[str, str]:
    """Тільки системні ключі Windows, credentials, один TEST_ONLY дозвіл."""
    if not approved(confirmation=CLI_CONFIRMATION, environment=environment):
        raise PermissionError("T116-47: немає окремого DEMO дозволу")
    if orders != ORDERS_CONFIRMATION or wsp != WSP_CONFIRMATION:
        raise PermissionError("T116-47: немає ручних підтверджень")
    minimal = {
        key: value for key in SYSTEM_ENV_KEYS
        if isinstance((value := environment.get(key)), str) and value
    }
    if os.name == "nt" and not minimal.get("SystemRoot"):
        raise PermissionError("T116-47: SystemRoot відсутній")
    minimal.update({
        APPROVAL_VARIABLE: APPROVAL_VALUE,
        ORDERS_ATTESTED: ORDERS_CONFIRMATION,
        WSP_ATTESTED: WSP_CONFIRMATION,
    })
    result = make_launcher_environment(credentials, environment=minimal)
    if not approved(confirmation=CLI_CONFIRMATION, environment=result, child=True):
        raise PermissionError("T116-47: child environment відхилено")
    if not all(result.get(key) for key in CREDENTIAL_VARIABLES):
        raise PermissionError("T116-47: немає credentials")
    return result


@contextmanager
def exact_quotes_outbound(
    *, client_type: type, tcp_protocol_type: type, frame_sender_type: type,
    request_messages: object, common_messages: object,
    access_token: str,
) -> Iterator[None]:
    """Поверх T116-46 відхилити SymbolsList та все, крім 3 запитів/heartbeat."""
    types: dict[str, type] = {}
    payload_ids: dict[int, type] = {}
    for name in ALLOWED_OUTBOUND:
        module = common_messages if name == "ProtoHeartbeatEvent" else request_messages
        klass = getattr(module, name, None)
        if not isinstance(klass, type) or not issubclass(klass, Message):
            raise RuntimeError("T116-47: невідомий тип SDK outbound")
        payload_id = getattr(klass(), "payloadType", None)
        if type(payload_id) is not int or payload_id <= 0 or payload_id in payload_ids:
            raise RuntimeError("T116-47: некоректний SDK payloadType")
        types[name] = klass
        payload_ids[payload_id] = klass
    envelope_type = getattr(common_messages, "ProtoMessage")

    def check(message: object) -> None:
        descriptor = getattr(message, "DESCRIPTOR", None)
        message_name = getattr(descriptor, "name", None)
        if message_name not in types or type(message) is not types[message_name]:
            raise PermissionError("T116-47: сторонній outbound protobuf")
        if message_name == "ProtoOAAccountAuthReq" and (
            getattr(message, "accessToken", None) != access_token
        ):
            raise PermissionError("T116-47: чужий accessToken")
        if message_name == "ProtoOASubscribeSpotsReq":
            validate_spot_subscription(message, types[message_name])

    def check_frame(frame: object) -> None:
        if (
            not isinstance(frame, bytes)
            or type(frame) is not bytes
            or len(frame) > 65536
        ):
            raise PermissionError("T116-47: frame відхилено")
        try:
            envelope = envelope_type()
            envelope.ParseFromString(frame)
            if not envelope.IsInitialized():
                raise ValueError("неповний envelope")
            payload_class = payload_ids.get(envelope.payloadType)
            if payload_class is None:
                raise ValueError("payloadType заборонено")
            message = payload_class()
            message.ParseFromString(envelope.payload)
            if not message.IsInitialized():
                raise ValueError("неповний protobuf")
            check(message)
        except (DecodeError, PermissionError, TypeError, ValueError) as exc:
            raise PermissionError("T116-47: заборонений protobuf frame") from exc

    with guarded_scoped_quote_subscription(
        client_type=client_type, tcp_protocol_type=tcp_protocol_type,
        frame_sender_type=frame_sender_type, request_messages=request_messages,
        common_messages=common_messages,
    ):
        client_send = getattr(client_type, "send")
        tcp_send = getattr(tcp_protocol_type, "send")
        frame_send = getattr(frame_sender_type, "sendString")

        def send_client(
            instance: object, message: object, *args: Any, **kwargs: Any,
        ) -> Any:
            check(message)
            return client_send(instance, message, *args, **kwargs)

        def send_tcp(
            instance: object, message: object, *args: Any, **kwargs: Any,
        ) -> Any:
            check(message)
            return tcp_send(instance, message, *args, **kwargs)

        def send_frame(
            instance: object, frame: object, *args: Any, **kwargs: Any,
        ) -> Any:
            check_frame(frame)
            return frame_send(instance, frame, *args, **kwargs)

        with (
            patch.object(client_type, "send", send_client),
            patch.object(tcp_protocol_type, "send", send_tcp),
            patch.object(frame_sender_type, "sendString", send_frame),
        ):
            yield


class QuoteNetworkController:
    """Одна callback-сесія ApplicationAuth → AccountAuth → Subscribe → Spot."""

    def __init__(
        self, *, client: object, messages: ModuleType, common: ModuleType,
        schedule: Callable[..., object], clock: Callable[[], float],
        now: Callable[[], datetime], on_finished: Callable[[], None],
        credentials: BridgedCredentials,
    ) -> None:
        self._client: Any = client
        self._messages = messages
        self._schedule = schedule
        self._clock = clock
        self._on_finished = on_finished
        self._started_at: float | None = None
        self._credentials: BridgedCredentials | None = credentials
        self._started = False
        self._finished = False
        self.phase = "NEW"
        self.error_code: str | None = None
        self.quote: QuoteObservation | None = None
        self._early_observation: QuoteObservation | None = None
        self.failure_phase = "NEW"
        self.failure_inbound = "UNRECOGNIZED"
        self.failure_class = "DECODE_REJECTED"
        self._transport = SdkReadOnlyTransport(
            client=client, on_send_error=lambda: self.fail("SDK_SEND_FAILED"),
        )
        self._discovery = DemoSymbolDiscovery(
            account_mode="DEMO", account_id=DEMO_API_ACCOUNT_ID,
            messages=messages, sender=self._transport,
        )
        self._reader = make_reader(
            symbol_id=OBSERVED_EURUSD_SYMBOL_ID, sender=self._transport,
            messages=messages,
            heartbeat_type=getattr(common, "ProtoHeartbeatEvent"),
            now_utc=now,
        )
        self._envelope_type = getattr(common, "ProtoMessage")
        self._inbound: dict[int, tuple[str, type]] = {}
        for name in INBOUND_NAMES:
            klass = getattr(messages, name)
            payload_id = getattr(klass(), "payloadType", None)
            if type(payload_id) is not int or payload_id <= 0:
                raise RuntimeError("T116-47: inbound SDK schema несумісна")
            if payload_id in self._inbound:
                raise RuntimeError("T116-47: повторний inbound payloadType")
            self._inbound[payload_id] = name, klass
        heartbeat = getattr(common, "ProtoHeartbeatEvent")()
        self._heartbeat_id = int(getattr(heartbeat, "payloadType"))
        if self._heartbeat_id in self._inbound:
            raise RuntimeError("T116-47: heartbeat payloadType конфліктує")
        self._sdk_error_ids: set[int] = set()
        for module, name in (
            (messages, "ProtoOAErrorRes"), (common, "ProtoErrorRes"),
        ):
            error_type = getattr(module, name, None)
            if isinstance(error_type, type) and issubclass(error_type, Message):
                error_id = getattr(error_type(), "payloadType", None)
                if type(error_id) is int and error_id > 0:
                    self._sdk_error_ids.add(error_id)

    def start(self) -> None:
        if self._started:
            raise RuntimeError("T116-47: повторний запуск")
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
            self.fail("SDK_START_FAILED")

    def _connected(self, _client: object) -> None:
        if self._finished or self.phase != "NEW":
            return
        credentials = self._credentials
        if credentials is None:
            self.fail("APPLICATION_AUTH_FAILED")
            return
        self.phase = "APP_SENT"
        # noinspection PyBroadException
        try:
            self._discovery.send_application_auth(
                client_id=credentials.client_id,
                client_secret=credentials.client_secret,
            )
        except Exception:
            self.fail("APPLICATION_AUTH_FAILED")

    def _decode(self, envelope: object) -> tuple[str, Message] | None:
        if (
            not isinstance(envelope, Message)
            or type(envelope) is not self._envelope_type
            or not envelope.IsInitialized()
        ):
            raise PermissionError("T116-47: невідомий envelope")
        payload_type = getattr(envelope, "payloadType", None)
        if type(payload_type) is not int:
            payload_type = None
        if payload_type == self._heartbeat_id:
            return None
        payload = getattr(envelope, "payload", None)
        info = self._inbound.get(payload_type)
        if info is None or not isinstance(payload, bytes):
            raise PermissionError("T116-47: неочікуваний payloadType")
        if len(payload) > MAX_PAYLOAD:
            raise PermissionError("T116-47: надмірний payload")
        name, klass = info
        if not payload and name != "ProtoOAApplicationAuthRes":
            raise PermissionError("T116-47: порожній payload")
        message = klass()
        message.ParseFromString(payload)
        if not message.IsInitialized():
            raise PermissionError("T116-47: неповна відповідь")
        return name, message

    def _message(self, _client: object, envelope: object) -> None:
        if self._finished:
            return
        self.failure_phase = (
            self.phase if self.phase in DIAGNOSTIC_PHASES else "NEW"
        )
        payload_type = getattr(envelope, "payloadType", None)
        info = self._inbound.get(payload_type)
        self.failure_inbound = (
            info[0] if info is not None else
            "SDK_ERROR_RESPONSE" if payload_type in self._sdk_error_ids else
            "UNRECOGNIZED"
        )
        self.failure_class = "DECODE_REJECTED"
        # noinspection PyBroadException
        try:
            decoded = self._decode(envelope)
            if decoded is None:
                return
            name, message = decoded
            if self.phase == "APP_SENT" and name == "ProtoOAApplicationAuthRes":
                self.failure_class = "APPLICATION_AUTH_REJECTED"
                self._discovery.accept_application_auth(message)
                credentials = self._credentials
                if credentials is None:
                    raise RuntimeError("відсутній token")
                self.phase = "ACCOUNT_SENT"
                self._discovery.send_account_auth(access_token=credentials.access_token)
                self._credentials = None
            elif self.phase == "ACCOUNT_SENT" and name == "ProtoOAAccountAuthRes":
                self.failure_class = "ACCOUNT_AUTH_REJECTED"
                self._discovery.accept_account_auth(message)
                self.phase = "SUBSCRIBE_SENT"
                self.failure_class = "SUBSCRIBE_SEND_REJECTED"
                self._reader.send_read_only(
                    new_spot_subscription(self._messages, OBSERVED_EURUSD_SYMBOL_ID)
                )
            elif self.phase == "SUBSCRIBE_SENT" and name == "ProtoOASpotEvent":
                # Ранній SpotEvent не підтверджує підписку; чекаємо SubscribeRes.
                self.failure_class = "SPOT_REJECTED"
                observation = self._reader.on_spot_event(message)
                if observation is None:
                    raise PermissionError("чужий SpotEvent")
                self._early_observation = observation
            elif self.phase == "SUBSCRIBE_SENT" and name == "ProtoOASubscribeSpotsRes":
                self.failure_class = "SUBSCRIBE_ACCOUNT_MISMATCH"
                if getattr(message, "ctidTraderAccountId", None) != DEMO_API_ACCOUNT_ID:
                    raise PermissionError("інший account у SubscribeRes")
                self.phase = "SUBSCRIBED"
                observation = self._early_observation
                self._early_observation = None
                if observation is not None:
                    self._complete_quote(observation)
            elif self.phase == "SUBSCRIBED" and name == "ProtoOASpotEvent":
                self.failure_class = "SPOT_REJECTED"
                observation = self._reader.on_spot_event(message)
                if observation is None:
                    raise PermissionError("чужий SpotEvent")
                self._complete_quote(observation)
            else:
                self.failure_class = "UNEXPECTED_RESPONSE_ORDER"
                raise PermissionError("порушення порядку відповідей")
        except Exception:
            self.fail("INVALID_RESPONSE")

    def _complete_quote(self, observation: QuoteObservation) -> None:
        """Завершувати лише після SubscribeRes для цільового DEMO-рахунку."""
        if (
            observation.bid is not None and observation.ask is not None
            and 0 < observation.bid <= observation.ask
            and observation.side_age_seconds is not None
            and observation.side_age_seconds <= MAX_SIDE_AGE_SECONDS
        ):
            self.quote = observation
            self._finish()

    def _disconnected(self, _client: object, _reason: object) -> None:
        if self._finished or self._transport.stopping:
            return
        self.fail("DISCONNECTED_BEFORE_QUOTE")

    def _watchdog(self) -> None:
        if self._finished:
            return
        started = self._started_at
        if started is None or self._clock() - started >= SESSION_SECONDS:
            self.fail("QUOTE_SESSION_TIMEOUT")
            return
        # noinspection PyBroadException
        try:
            self._schedule(WATCHDOG_INTERVAL_SECONDS, self._watchdog)
        except Exception:
            self.fail("WATCHDOG_FAILED")

    def fail(self, code: str) -> None:
        """Стороння помилка SDK/reactor завжди закриває TEST_ONLY сесію."""
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
            self._transport.disconnect()
        except Exception:
            self.error_code = self.error_code or "SDK_STOP_FAILED"
        self._on_finished()


def _timestamp(value: datetime | None) -> str:
    if value is None:
        return "NONE"
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _quote_lines(quote: QuoteObservation) -> list[str]:
    """Тільки безпечний мінімальний звіт, без raw SDK повідомлень."""
    if quote.bid is None or quote.ask is None:
        raise ValueError("T116-47: неповна котировка")
    return [
        f"demo_api_account_id={DEMO_API_ACCOUNT_ID}",
        f"symbol_id={OBSERVED_EURUSD_SYMBOL_ID}",
        f"bid={quote.bid:.5f}",
        f"ask={quote.ask:.5f}",
        f"broker_timestamp_utc={_timestamp(quote.broker_event_utc)}",
        "quote_kind=FIRST_RECEIVED_SNAPSHOT_NOT_LIVE_PROOF",
        "production_changes=0",
        CHILD_SUCCESS,
    ]


def run_network_child(credentials: BridgedCredentials) -> int:
    """Єдине дозволене місце SDK Client(), у child під TEST_ONLY guard."""
    endpoints, client_type, protocol, messages, common = load_real_sdk_types()
    spec = sdk_client_spec(endpoints, protocol)
    reactor = getattr(import_module("twisted.internet"), "reactor")
    frame_type = getattr(
        import_module("twisted.protocols.basic"), "Int32StringReceiver"
    )

    def stop_reactor() -> None:
        if bool(getattr(reactor, "running", False)):
            reactor.stop()

    with exact_quotes_outbound(
        client_type=client_type, tcp_protocol_type=protocol,
        frame_sender_type=frame_type, request_messages=messages,
        common_messages=common, access_token=credentials.access_token,
    ):
        client = client_type(spec.demo_host, spec.port, protocol)
        controller = QuoteNetworkController(
            client=client, messages=messages, common=common,
            schedule=reactor.callLater, clock=monotonic,
            now=lambda: datetime.now(UTC),
            on_finished=lambda: reactor.callLater(0, stop_reactor),
            credentials=credentials,
        )
        # noinspection PyBroadException
        try:
            controller.start()
            if controller.quote is None and controller.error_code is None:
                reactor.run()
        except Exception:
            controller.fail("REACTOR_OR_SDK_FAILED")
        finally:
            if controller.quote is None and controller.error_code is None:
                controller.fail("REACTOR_EXITED_WITHOUT_QUOTE")
    if controller.quote is None or controller.error_code is not None:
        if controller.error_code == "INVALID_RESPONSE":
            print(f"failure_phase={controller.failure_phase}")
            print(f"failure_inbound={controller.failure_inbound}")
            print(f"failure_class={controller.failure_class}")
        print(f"failure_code={controller.error_code or 'NO_QUOTE'}")
        return 1
    for line in _quote_lines(controller.quote):
        print(line)
    return 0


def supervise_network_child(
    environment: Mapping[str, str], *, popen: Callable[..., Any] = subprocess.Popen,
) -> SupervisedResult:
    """Одна спроба, 75 секунд, shell=False; raw stderr/traceback не показувати."""
    if not approved(confirmation=CLI_CONFIRMATION, environment=environment, child=True):
        raise PermissionError("T116-47: child не авторизований")
    if not all(environment.get(name) for name in CREDENTIAL_VARIABLES):
        raise PermissionError("T116-47: credentials відсутні")
    process = popen(
        [sys.executable, "-m", CHILD_MODULE, "--network-child",
         "--confirm", CLI_CONFIRMATION],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, shell=False, text=True,
        encoding="utf-8", errors="replace",
        cwd=str(Path(__file__).resolve().parents[2]), env=dict(environment),
    )
    try:
        try:
            stdout, stderr = process.communicate(timeout=SUPERVISOR_TIMEOUT_SECONDS)
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


def verified_quote(result: SupervisedResult) -> list[str] | None:
    """Приймати лише точну форму результату від child, без довіри до інших рядків."""
    if result.hard_timeout or not result.reaped or result.returncode != 0:
        return None
    if result.stderr:
        return None
    lines = result.stdout.splitlines()
    if len(lines) != 8:
        return None
    if lines[:2] != [
        f"demo_api_account_id={DEMO_API_ACCOUNT_ID}",
        f"symbol_id={OBSERVED_EURUSD_SYMBOL_ID}",
    ]:
        return None
    try:
        bid_match = PRICE_PATTERN.fullmatch(lines[2])
        ask_match = PRICE_PATTERN.fullmatch(lines[3])
        if not bid_match or not ask_match:
            return None
        if bid_match.group(1) != "bid" or ask_match.group(1) != "ask":
            return None
        bid = Decimal(bid_match.group(2))
        ask = Decimal(ask_match.group(2))
        if not Decimal("0") < bid <= ask < Decimal("100"):
            return None
    except (InvalidOperation, ValueError):
        return None
    timestamp = lines[4].removeprefix("broker_timestamp_utc=")
    if timestamp == lines[4]:
        return None
    if timestamp != "NONE":
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed.utcoffset() is None or not timestamp.endswith("Z"):
                return None
        except ValueError:
            return None
    if lines[5:] != [
        "quote_kind=FIRST_RECEIVED_SNAPSHOT_NOT_LIVE_PROOF",
        "production_changes=0", CHILD_SUCCESS,
    ]:
        return None
    return lines[:6]


def safe_failure_code(result: SupervisedResult) -> str:
    if result.hard_timeout:
        return "HARD_PROCESS_TIMEOUT"
    if not result.reaped:
        return "CHILD_NOT_REAPED"
    if result.returncode == 0:
        return "INVALID_CHILD_RESULT"
    matches = [ERROR_PATTERN.fullmatch(line) for line in result.stdout.splitlines()]
    recognized = [
        match.group(1) for match in matches
        if match and match.group(1) in KNOWN_ERRORS
    ]
    return recognized[0] if len(recognized) == 1 else "CHILD_PROCESS_FAILED"


def safe_failure_diagnostics(result: SupervisedResult) -> list[str]:
    """Передавати тільки три фіксовані коди, ніколи — сирий stdout child."""
    if result.hard_timeout or not result.reaped or result.returncode != 1:
        return []
    if result.stderr or safe_failure_code(result) != "INVALID_RESPONSE":
        return []
    lines = result.stdout.splitlines()
    if len(lines) != 4 or lines[3] != "failure_code=INVALID_RESPONSE":
        return []
    fields = ("failure_phase", "failure_inbound", "failure_class")
    allowed = (DIAGNOSTIC_PHASES, DIAGNOSTIC_INBOUND, DIAGNOSTIC_CLASSES)
    for line, key, valid in zip(lines[:3], fields, allowed, strict=True):
        prefix = f"{key}="
        if not line.startswith(prefix) or line[len(prefix):] not in valid:
            return []
    return lines[:3]


def sdk_offline_check() -> str:
    """Справжня SDK-схема й guard без Client() і зовнішнього TCP."""
    with external_tcp_denied():
        if sdk_offline_preflight() != "VERIFIED_NO_EXTERNAL_NETWORK":
            return "SDK_NOT_READY"
        if sdk_schema_preflight() != "VERIFIED_NO_EXTERNAL_NETWORK":
            return "QUOTE_SCHEMA_NOT_READY"
        endpoints, client_type, protocol, messages, common = load_real_sdk_types()
        spec = sdk_client_spec(endpoints, protocol)
        if spec.demo_host == spec.live_host:
            return "LIVE_HOST_CONFLICT"
        for name in INBOUND_NAMES:
            klass = getattr(messages, name, None)
            if not isinstance(klass, type) or not issubclass(klass, Message):
                return "INBOUND_SCHEMA_NOT_READY"
        frame_type = getattr(
            import_module("twisted.protocols.basic"), "Int32StringReceiver"
        )
        with exact_quotes_outbound(
            client_type=client_type, tcp_protocol_type=protocol,
            frame_sender_type=frame_type, request_messages=messages,
            common_messages=common, access_token="T11647_TEST_ONLY_TOKEN",
        ):
            pass
    return "VERIFIED_NO_EXTERNAL_NETWORK"


def main(
    argv: Sequence[str] | None = None, *,
    environment: Mapping[str, str] | None = None,
    ask: Callable[[str], str] = input,
    ask_password: Callable[[str], str] = getpass.getpass,
    credential_reader: Callable[[str], BridgedCredentials] = (
        read_credentials_for_bridge
    ),
    runner: Callable[[Mapping[str, str]], SupervisedResult] = (
        supervise_network_child
    ),
    sdk_check: Callable[[], str] = sdk_offline_check,
    child_runner: Callable[[BridgedCredentials], int] = run_network_child,
) -> int:
    """Поза явним двофакторним підтвердженням — жодної DEMO-мережі."""
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
            parser.error("T116-47: offline не приймає --confirm")
        # noinspection PyBroadException
        try:
            status = sdk_check()
        except Exception:
            status = "SDK_PREFLIGHT_FAILED"
        ready = status == "VERIFIED_NO_EXTERNAL_NETWORK"
        print("T116-47 TEST_ONLY | DEMO EURUSD Quotes OFFLINE preflight")
        print(f"sdk_offline_preflight={status}")
        print("sdk_client_constructor=NOT_CALLED")
        print("child_process=NOT_STARTED")
        print("real_broker_requests=0")
        print("production_changes=0")
        print("network_launch_authorized=NO")
        print(OFFLINE_SUCCESS if ready else "T116-47=NOT_READY_OFFLINE")
        return 0 if ready else 2

    if not approved(
        confirmation=args.confirm, environment=env, child=args.network_child,
    ):
        raise PermissionError("T116-47: DEMO network approval відхилено")
    if args.network_child:
        values = tuple(env.get(key, "") for key in CREDENTIAL_VARIABLES)
        if len(values) != 3 or not all(
            isinstance(v, str) and v.strip() for v in values
        ):
            raise PermissionError("T116-47: child credentials відсутні")
        # noinspection PyBroadException
        try:
            return child_runner(BridgedCredentials(*values))
        except Exception:
            print("failure_code=SDK_CHILD_FAILED")
            return 2

    if env is not os.environ:
        raise PermissionError("T116-47: мережа тільки з реального середовища")
    if sdk_check() != "VERIFIED_NO_EXTERNAL_NETWORK":
        raise PermissionError("T116-47: SDK preflight не пройдено")
    try:
        orders = ask("Перевір Orders=OFF; введи ORDERS_OFF: ")
        wsp = ask("Перевір усі WSP STOPPED; введи WSP_STOPPED: ")
    except (EOFError, KeyboardInterrupt):
        orders, wsp = "", ""
    if orders != ORDERS_CONFIRMATION or wsp != WSP_CONFIRMATION:
        raise PermissionError("T116-47: safety gate відхилено")
    try:
        password = ask_password("Пароль LGE (не відображається): ")
    except (EOFError, KeyboardInterrupt):
        password = ""
    try:
        credentials = credential_reader(password)
        child_env = prepare_child_environment(
            credentials, environment=env, orders=orders, wsp=wsp,
        )
    except (BridgeRejected, PermissionError):
        raise PermissionError("T116-47: credentials відхилено") from None
    # noinspection PyBroadException
    except Exception:
        raise PermissionError("T116-47: credentials reader failed") from None
    # noinspection PyBroadException
    try:
        result = runner(child_env)
    except Exception:
        print("failure_code=SUPERVISOR_FAILED")
        print(FAILURE)
        return 1
    verified = verified_quote(result)
    if verified is None:
        for line in safe_failure_diagnostics(result):
            print(line)
        print(f"failure_code={safe_failure_code(result)}")
        print(FAILURE)
        return 1
    for line in verified:
        print(line)
    print("production_changes=0")
    print(PARENT_SUCCESS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
