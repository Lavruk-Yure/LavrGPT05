"""T116-48 TEST_ONLY — короткий read-only монітор EURUSD SpotEvent.

Мережевий режим заборонений без окремого one-shot дозволу та підтверджень.
Один початковий знімок не є доказом живого потоку. Production не змінюється.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from importlib import import_module
from pathlib import Path
from time import monotonic
from typing import Any

from tests.roadmap116.t116_22_standalone_demo_reader import (
    DEMO_API_ACCOUNT_ID, QuoteObservation,
)
from tests.roadmap116.t116_23_sdk_offline_bridge import (
    load_real_sdk_types, sdk_client_spec,
)
from tests.roadmap116.t116_26_process_watchdog import (
    SUPERVISOR_TIMEOUT_SECONDS, SupervisedResult,
)
from tests.roadmap116.t116_32_demo_network_readonly_discovery import (
    CREDENTIAL_VARIABLES,
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
    OBSERVED_EURUSD_SYMBOL_ID,
)
from tests.roadmap116.t116_47_first_demo_eurusd_quotes_network import (
    APPROVAL_VARIABLE as FIRST_QUOTE_APPROVAL,
    ORDERS_CONFIRMATION, WSP_CONFIRMATION,
    QuoteNetworkController, exact_quotes_outbound, sdk_offline_check,
)

APPROVAL_VARIABLE = "T11648_ALLOW_DEMO_SEQUENCE_NETWORK"
APPROVAL_VALUE = "DEMO_EURUSD_SEQUENCE_46368962_ONE_SHOT"
CLI_CONFIRMATION = "READONLY_SEQUENCE_46368962"
ORDERS_ATTESTED = "T11648_ORDERS_OFF_ATTESTED"
WSP_ATTESTED = "T11648_WSP_STOPPED_ATTESTED"
CHILD_MODULE = "tests.roadmap116.t116_48_demo_eurusd_quote_sequence"
CHILD_SUCCESS = "T116-48=GREEN_REAL_DEMO_QUOTE_SEQUENCE_CAPTURE"
PARENT_SUCCESS = "T116-48=GREEN_SUPERVISED_DEMO_QUOTE_SEQUENCE_CAPTURE"
OFFLINE_SUCCESS = "T116-48=GREEN_OFFLINE_QUOTE_SEQUENCE_PREFLIGHT"
FAILURE = "T116-48=FAILED_SUPERVISED_DEMO_QUOTE_SEQUENCE"
CAPTURE_SECONDS = 20.0
MAX_SESSION_SECONDS = 60.0
MAX_QUOTE_AGE_SECONDS = 30.0
MAX_FUTURE_TOLERANCE_SECONDS = 3.0
MAX_SPOT_EVENTS = 100_000
KNOWN_FAILURES = frozenset({
    "SDK_START_FAILED", "SDK_SEND_FAILED", "APPLICATION_AUTH_FAILED",
    "ACCOUNT_AUTH_FAILED", "SUBSCRIBE_FAILED", "INVALID_RESPONSE",
    "QUOTE_SESSION_TIMEOUT", "DISCONNECTED_BEFORE_QUOTE",
    "WATCHDOG_FAILED", "SDK_STOP_FAILED", "REACTOR_OR_SDK_FAILED",
    "REACTOR_EXITED_WITHOUT_QUOTE", "NO_COMPLETE_QUOTE",
    "SDK_CHILD_FAILED", "SUPERVISOR_FAILED", "HARD_PROCESS_TIMEOUT",
})
RECENCY = frozenset({"RECENT", "STALE", "FUTURE", "UNAVAILABLE"})
CLASSIFICATIONS = frozenset({
    "INITIAL_SNAPSHOT_ONLY", "UNCHANGED_QUOTES", "NO_TIMESTAMP_PROGRESS",
    "ZERO_SPREAD_ONLY", "TIMESTAMP_NOT_RECENT", "PROGRESS_WITH_RECENT_TIMESTAMP",
})
PRICE_RE = re.compile(r"^[0-9]{1,3}\.[0-9]{5}$")
UINT_RE = re.compile(r"^(?:0|[1-9][0-9]{0,5})$")


def approved(
    *, confirmation: str | None, environment: Mapping[str, str],
    child: bool = False,
) -> bool:
    """One-shot дозвіл без спадкування старих мережевих режимів."""
    if confirmation != CLI_CONFIRMATION:
        return False
    if environment.get(APPROVAL_VARIABLE) != APPROVAL_VALUE:
        return False
    if any(name in environment for name in (
        ACCOUNTLIST_APPROVAL, SYMBOL_APPROVAL, FIRST_QUOTE_APPROVAL,
    )):
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
    """Сформувати мінімальне середовище без запису секретів на диск."""
    if not approved(confirmation=CLI_CONFIRMATION, environment=environment):
        raise PermissionError("T116-48: one-shot дозвіл відсутній")
    if orders != ORDERS_CONFIRMATION or wsp != WSP_CONFIRMATION:
        raise PermissionError("T116-48: ручні підтвердження відсутні")
    minimal = {
        key: value for key in SYSTEM_ENV_KEYS
        if isinstance((value := environment.get(key)), str) and value
    }
    if os.name == "nt" and not minimal.get("SystemRoot"):
        raise PermissionError("T116-48: Windows SystemRoot відсутній")
    minimal.update({
        APPROVAL_VARIABLE: APPROVAL_VALUE,
        ORDERS_ATTESTED: ORDERS_CONFIRMATION,
        WSP_ATTESTED: WSP_CONFIRMATION,
    })
    result = make_launcher_environment(credentials, environment=minimal)
    if not approved(confirmation=CLI_CONFIRMATION, environment=result, child=True):
        raise PermissionError("T116-48: дочірній дозвіл відхилено")
    if not all(result.get(name) for name in CREDENTIAL_VARIABLES):
        raise PermissionError("T116-48: credentials відсутні")
    return result


@dataclass(slots=True)
class SequenceMetrics:
    """Лише числові та часові метрики; raw protobuf не зберігаємо."""

    spot_events: int = 0
    pre_ack_events: int = 0
    post_ack_events: int = 0
    complete_quotes: int = 0
    positive_spread_quotes: int = 0
    zero_spread_quotes: int = 0
    invalid_spread_quotes: int = 0
    changed_quotes: int = 0
    post_ack_changed_quotes: int = 0
    post_ack_positive_spread_quotes: int = 0
    timestamp_advances: int = 0
    post_ack_timestamp_advances: int = 0
    timestamp_regressions: int = 0
    first_quote: QuoteObservation | None = None
    last_quote: QuoteObservation | None = None
    _previous_time: datetime | None = None

    def add(self, observation: QuoteObservation, *, post_ack: bool) -> None:
        """Додати тільки перевірені за account/symbol події reader."""
        if not observation.raw_bid_present and not observation.raw_ask_present:
            return
        self.spot_events += 1
        if self.spot_events > MAX_SPOT_EVENTS:
            raise ValueError("T116-48: надмірний потік подій")
        if post_ack:
            self.post_ack_events += 1
        else:
            self.pre_ack_events += 1
        when = observation.broker_event_utc
        if when is not None:
            if self._previous_time is not None:
                if when > self._previous_time:
                    self.timestamp_advances += 1
                    if post_ack:
                        self.post_ack_timestamp_advances += 1
                elif when < self._previous_time:
                    self.timestamp_regressions += 1
            self._previous_time = when
        bid, ask = observation.bid, observation.ask
        if bid is None or ask is None:
            return
        if not 0 < bid < 100 or not 0 < ask < 100:
            return
        if observation.side_age_seconds is None or (
            observation.side_age_seconds > 10
        ):
            return
        if bid > ask:
            self.invalid_spread_quotes += 1
            return
        prior = self.last_quote
        if prior is not None and (bid, ask) != (prior.bid, prior.ask):
            self.changed_quotes += 1
            if post_ack:
                self.post_ack_changed_quotes += 1
        self.complete_quotes += 1
        self.positive_spread_quotes += int(ask > bid)
        if post_ack and ask > bid:
            self.post_ack_positive_spread_quotes += 1
        self.zero_spread_quotes += int(ask == bid)
        if self.first_quote is None:
            self.first_quote = observation
        self.last_quote = observation

    def recency(self, *, now: datetime) -> str:
        last = self.last_quote
        if last is None or last.broker_event_utc is None:
            return "UNAVAILABLE"
        age = (now.astimezone(UTC) - last.broker_event_utc).total_seconds()
        if age < -MAX_FUTURE_TOLERANCE_SECONDS:
            return "FUTURE"
        if age > MAX_QUOTE_AGE_SECONDS:
            return "STALE"
        return "RECENT"

    def classification(self, *, now: datetime) -> str:
        """Не називати один знімок або нульовий спред живим потоком."""
        if self.complete_quotes <= 1 or self.post_ack_events < 2:
            return "INITIAL_SNAPSHOT_ONLY"
        if self.post_ack_changed_quotes == 0:
            return "UNCHANGED_QUOTES"
        if self.post_ack_timestamp_advances == 0:
            return "NO_TIMESTAMP_PROGRESS"
        if self.post_ack_positive_spread_quotes == 0:
            return "ZERO_SPREAD_ONLY"
        if self.recency(now=now) != "RECENT":
            return "TIMESTAMP_NOT_RECENT"
        return "PROGRESS_WITH_RECENT_TIMESTAMP"


class QuoteSequenceController(QuoteNetworkController):
    """Повторно використати перевірену T116-47 сесію без змін SDK guard."""

    def __init__(self, *, now: Callable[[], datetime], **kwargs: Any) -> None:
        super().__init__(now=now, **kwargs)
        self.metrics = SequenceMetrics()
        self._now_utc = now
        self._ack_monotonic: float | None = None

    def _complete_quote(self, observation: QuoteObservation) -> None:
        """Не завершувати сесію після першого знімка."""
        del observation

    def _message(self, client: object, envelope: object) -> None:
        count_before = len(self._reader.records)
        before = self.phase
        super()._message(client, envelope)
        if self.error_code is not None:
            return
        if before == "SUBSCRIBE_SENT" and self.phase == "SUBSCRIBED":
            self._ack_monotonic = self._clock()
        new_records = self._reader.records[count_before:]
        try:
            for observation in new_records:
                self.metrics.add(
                    observation, post_ack=before == "SUBSCRIBED",
                )
        except (TypeError, ValueError):
            self.fail("INVALID_RESPONSE")

    def _watchdog(self) -> None:
        if self._finished:
            return
        if self._ack_monotonic is not None and (
            self._clock() - self._ack_monotonic >= CAPTURE_SECONDS
        ):
            if self.metrics.complete_quotes == 0:
                self.fail("NO_COMPLETE_QUOTE")
            else:
                self.quote = self.metrics.last_quote
                self._finish()
            return
        super()._watchdog()


def timestamp_text(value: datetime | None) -> str:
    if value is None:
        return "NONE"
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def metric_lines(metrics: SequenceMetrics, *, now: datetime) -> list[str]:
    """Строга структура знеособленого звіту одного child."""
    quote = metrics.last_quote
    if quote is None or quote.bid is None or quote.ask is None:
        raise ValueError("T116-48: немає повної котировки")
    return [
        f"demo_api_account_id={DEMO_API_ACCOUNT_ID}",
        f"symbol_id={OBSERVED_EURUSD_SYMBOL_ID}",
        f"spot_events={metrics.spot_events}",
        f"pre_ack_events={metrics.pre_ack_events}",
        f"post_ack_events={metrics.post_ack_events}",
        f"complete_quotes={metrics.complete_quotes}",
        f"positive_spread_quotes={metrics.positive_spread_quotes}",
        f"zero_spread_quotes={metrics.zero_spread_quotes}",
        f"post_ack_changed_quotes={metrics.post_ack_changed_quotes}",
        f"post_ack_positive_spread_quotes={metrics.post_ack_positive_spread_quotes}",
        f"post_ack_timestamp_advances={metrics.post_ack_timestamp_advances}",
        f"timestamp_regressions={metrics.timestamp_regressions}",
        f"last_bid={quote.bid:.5f}",
        f"last_ask={quote.ask:.5f}",
        f"last_broker_timestamp_utc={timestamp_text(quote.broker_event_utc)}",
        f"timestamp_recency={metrics.recency(now=now)}",
        f"quote_sequence={metrics.classification(now=now)}",
        "quote_kind=BOUNDED_SEQUENCE_NOT_CONTINUOUS_PROOF",
        "production_changes=0",
        CHILD_SUCCESS,
    ]


def verify_child(result: SupervisedResult) -> list[str] | None:
    """Відхиляти сторонні рядки, некоректні ціни та нелогічні лічильники."""
    if result.hard_timeout or not result.reaped or result.returncode != 0:
        return None
    if result.stderr:
        return None
    lines = result.stdout.splitlines()
    if len(lines) != 20 or lines[:2] != [
        f"demo_api_account_id={DEMO_API_ACCOUNT_ID}",
        f"symbol_id={OBSERVED_EURUSD_SYMBOL_ID}",
    ] or lines[-3:] != [
        "quote_kind=BOUNDED_SEQUENCE_NOT_CONTINUOUS_PROOF",
        "production_changes=0", CHILD_SUCCESS,
    ]:
        return None
    names = (
        "spot_events", "pre_ack_events", "post_ack_events",
        "complete_quotes", "positive_spread_quotes", "zero_spread_quotes",
        "post_ack_changed_quotes", "post_ack_positive_spread_quotes",
        "post_ack_timestamp_advances", "timestamp_regressions",
    )
    counters: dict[str, int] = {}
    for offset, name in enumerate(names, start=2):
        raw = lines[offset].removeprefix(f"{name}=")
        if raw == lines[offset] or not UINT_RE.fullmatch(raw):
            return None
        counters[name] = int(raw)
    total = counters["spot_events"]
    complete = counters["complete_quotes"]
    if not 1 <= complete <= total <= MAX_SPOT_EVENTS:
        return None
    if counters["pre_ack_events"] + counters["post_ack_events"] != total:
        return None
    if (counters["positive_spread_quotes"] +
            counters["zero_spread_quotes"] != complete):
        return None
    if (counters["post_ack_changed_quotes"] >= complete or
            counters["post_ack_positive_spread_quotes"] > complete or
            counters["post_ack_timestamp_advances"] >= total or
            counters["timestamp_regressions"] >= total):
        return None
    prices: list[Decimal] = []
    for index, name in ((12, "last_bid"), (13, "last_ask")):
        prefix = f"{name}="
        raw = lines[index].removeprefix(prefix)
        if raw == lines[index] or not PRICE_RE.fullmatch(raw):
            return None
        try:
            prices.append(Decimal(raw))
        except InvalidOperation:
            return None
    if not Decimal("0") < prices[0] <= prices[1] < Decimal("100"):
        return None
    if lines[14].startswith("last_broker_timestamp_utc="):
        stamp = lines[14].split("=", 1)[1]
        if stamp != "NONE":
            try:
                parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                if not stamp.endswith("Z") or parsed.tzinfo is None:
                    return None
            except ValueError:
                return None
    else:
        return None
    recency = lines[15].removeprefix("timestamp_recency=")
    classification = lines[16].removeprefix("quote_sequence=")
    if recency not in RECENCY or classification not in CLASSIFICATIONS:
        return None
    if (stamp == "NONE") != (recency == "UNAVAILABLE"):
        return None
    if (classification == "PROGRESS_WITH_RECENT_TIMESTAMP" and (
        recency != "RECENT" or counters["post_ack_changed_quotes"] == 0
        or counters["post_ack_timestamp_advances"] == 0
        or counters["post_ack_positive_spread_quotes"] == 0
        or complete < 2 or counters["post_ack_events"] < 2
    )):
        return None
    return lines[:18]


def run_network_child(credentials: BridgedCredentials) -> int:
    """Єдине місце створення Client; guard до SDK-конструктора."""
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
        controller = QuoteSequenceController(
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
        code = controller.error_code or "NO_COMPLETE_QUOTE"
        print(f"failure_code={code if code in KNOWN_FAILURES else 'SDK_CHILD_FAILED'}")
        return 1
    for line in metric_lines(controller.metrics, now=datetime.now(UTC)):
        print(line)
    return 0


def supervise_child(
    environment: Mapping[str, str], *, popen: Callable[..., Any] = subprocess.Popen,
) -> SupervisedResult:
    """Одна DEMO-сесія; таймаут 75 с, без автоповтору."""
    if not approved(confirmation=CLI_CONFIRMATION, environment=environment, child=True):
        raise PermissionError("T116-48: child не авторизований")
    if not all(environment.get(key) for key in CREDENTIAL_VARIABLES):
        raise PermissionError("T116-48: credentials відсутні")
    process = popen(
        [sys.executable, "-m", CHILD_MODULE, "--network-child", "--confirm",
         CLI_CONFIRMATION],
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
                reaped=process.poll() is not None, stdout=stdout, stderr=stderr,
            )
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
            return SupervisedResult(
                returncode=124, hard_timeout=True,
                reaped=process.poll() is not None, stdout=stdout, stderr=stderr,
            )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def safe_failure(result: SupervisedResult) -> str:
    """Безпечна класифікація з виходу дочірнього процесу."""
    if result.hard_timeout:
        return "HARD_PROCESS_TIMEOUT"
    if not result.reaped:
        return "CHILD_NOT_REAPED"
    if result.returncode == 0 or result.stderr:
        return "INVALID_CHILD_RESULT"
    lines = result.stdout.splitlines()
    if len(lines) == 1 and lines[0].startswith("failure_code="):
        code = lines[0].removeprefix("failure_code=")
        if code in KNOWN_FAILURES:
            return code
    return "SDK_CHILD_FAILED"


def main(
    argv: Sequence[str] | None = None, *,
    environment: Mapping[str, str] | None = None,
    ask: Callable[[str], str] = input,
    ask_password: Callable[[str], str] = getpass.getpass,
    credential_reader: Callable[[str], BridgedCredentials] = (
        read_credentials_for_bridge
    ),
    runner: Callable[[Mapping[str, str]], SupervisedResult] = supervise_child,
    sdk_check: Callable[[], str] = sdk_offline_check,
    child_runner: Callable[[BridgedCredentials], int] = run_network_child,
) -> int:
    """Звичайний offline, мережа — тільки через подвійний явний дозвіл."""
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
            parser.error("T116-48: offline не приймає --confirm")
        # noinspection PyBroadException
        try:
            status = sdk_check()
        except Exception:
            status = "SDK_PREFLIGHT_FAILED"
        ready = status == "VERIFIED_NO_EXTERNAL_NETWORK"
        print("T116-48 TEST_ONLY | EURUSD quote sequence OFFLINE preflight")
        print(f"sdk_offline_preflight={status}")
        print("sdk_client_constructor=NOT_CALLED")
        print("real_broker_requests=0")
        print("production_changes=0")
        print("network_launch_authorized=NO")
        print(OFFLINE_SUCCESS if ready else "T116-48=NOT_READY_OFFLINE")
        return 0 if ready else 2

    if not approved(
        confirmation=args.confirm, environment=env, child=args.network_child,
    ):
        raise PermissionError("T116-48: DEMO network approval відхилено")
    if args.network_child:
        fields = tuple(env.get(name, "") for name in CREDENTIAL_VARIABLES)
        if len(fields) != 3 or not all(
            isinstance(field, str) and field.strip() for field in fields
        ):
            raise PermissionError("T116-48: credentials відсутні")
        # noinspection PyBroadException
        try:
            return child_runner(BridgedCredentials(*fields))
        except Exception:
            print("failure_code=SDK_CHILD_FAILED")
            return 2

    if env is not os.environ:
        raise PermissionError("T116-48: мережа тільки з реального середовища")
    if sdk_check() != "VERIFIED_NO_EXTERNAL_NETWORK":
        raise PermissionError("T116-48: SDK offline preflight не пройдено")
    try:
        orders = ask("Перевір Orders=OFF; введи ORDERS_OFF: ")
        wsp = ask("Перевір усі WSP STOPPED; введи WSP_STOPPED: ")
    except (EOFError, KeyboardInterrupt):
        orders, wsp = "", ""
    if orders != ORDERS_CONFIRMATION or wsp != WSP_CONFIRMATION:
        raise PermissionError("T116-48: ручні підтвердження відхилено")
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
        raise PermissionError("T116-48: credentials відхилено") from None
    # noinspection PyBroadException
    except Exception:
        raise PermissionError("T116-48: credentials reader failed") from None
    # noinspection PyBroadException
    try:
        result = runner(child_env)
    except Exception:
        print("failure_code=SUPERVISOR_FAILED")
        print(FAILURE)
        return 1
    safe = verify_child(result)
    if safe is None:
        print(f"failure_code={safe_failure(result)}")
        print(FAILURE)
        return 1
    for line in safe:
        print(line)
    print("production_changes=0")
    print(PARENT_SUCCESS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
