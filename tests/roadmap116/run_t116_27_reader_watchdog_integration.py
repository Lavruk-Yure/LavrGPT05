"""T116-27 TEST_ONLY — інтеграція читача cTrader DEMO з watchdog без TCP."""

from __future__ import annotations

import ast
import sys
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from threading import Event

import pytest
from google.protobuf.message import Message

from tests.roadmap116.run_t116_22_standalone_demo_quote_reader_contract import (
    fake_message_classes,
)
from tests.roadmap116.run_t116_24_demo_symbol_discovery_contract import (
    proto,
    synthetic_sdk_messages,
)
from tests.roadmap116.run_t116_25_demo_network_safety_preflight import (
    FakeClock,
    FakeTransport,
    session,
)
from tests.roadmap116.t116_22_standalone_demo_reader import (
    DEMO_API_ACCOUNT_ID,
    StandaloneDemoQuoteReader,
)
from tests.roadmap116.t116_25_demo_network_safety import (
    OfflineDemoSafetySession,
)
from tests.roadmap116.t116_26_process_watchdog import (
    CAPTURE_DEADLINE_SECONDS,
    SUPERVISOR_TIMEOUT_SECONDS,
    supervise_process,
)
from tests.roadmap116.t116_27_reader_watchdog_integration import (
    run_offline_reader_capture,
)

INTEGRATION_FILE = Path(__file__).with_name(
    "t116_27_reader_watchdog_integration.py"
)
SYNTHETIC_SYMBOL_ID = 55


@lru_cache(maxsize=1)
def spot_message_types() -> dict[str, type[Message]]:
    """Повторно використовувати однакові класи protobuf у всіх SpotEvent."""
    return fake_message_classes()


def make_test_reader() -> tuple[
    StandaloneDemoQuoteReader, OfflineDemoSafetySession, FakeTransport
]:
    """Створити штатний читач із TEST_ONLY сесією та без мережі."""
    messages = synthetic_sdk_messages()
    transport = FakeTransport()
    guarded_session = session(messages, transport, FakeClock())
    spot_messages = spot_message_types()
    allowed_names = (
        "ProtoOAApplicationAuthReq",
        "ProtoOAAccountAuthReq",
        "ProtoOASymbolsListReq",
    )
    allowed = {name: getattr(messages, name) for name in allowed_names}
    reader = StandaloneDemoQuoteReader(
        account_mode="DEMO",
        account_id=DEMO_API_ACCOUNT_ID,
        symbol_id=SYNTHETIC_SYMBOL_ID,
        sender=guarded_session,
        allowed_types=allowed,
        spot_event_type=spot_messages["ProtoOASpotEvent"],
        now_utc=lambda: datetime.now(UTC),
    )
    return reader, guarded_session, transport


def spot_event(*, bid: int | None = None, ask: int | None = None) -> Message:
    """Створити синтетичний SpotEvent, без фактичного symbolId брокера."""
    event_type = spot_message_types()["ProtoOASpotEvent"]
    event = event_type()
    setattr(event, "ctidTraderAccountId", DEMO_API_ACCOUNT_ID)
    setattr(event, "symbolId", SYNTHETIC_SYMBOL_ID)
    if bid is not None:
        setattr(event, "bid", bid)
    if ask is not None:
        setattr(event, "ask", ask)
    return event


def test_t116_27_reader_watchdog_integration() -> None:
    """Верифікувати зупинку реального читача без подій і при зависанні."""
    tree = ast.parse(INTEGRATION_FILE.read_text(encoding="utf-8"))
    imported = [
        item.module or ""
        for item in ast.walk(tree)
        if isinstance(item, ast.ImportFrom)
    ]
    imported.extend(
        alias.name
        for item in ast.walk(tree)
        if isinstance(item, ast.Import)
        for alias in item.names
    )
    forbidden = (
        "LGE", "core", "engine", "ibapi", "ctrader_open_api",
        "PySide6", "socket",
    )
    assert not any(
        name == prefix or name.startswith(prefix + ".")
        for name in imported for prefix in forbidden
    )
    assert CAPTURE_DEADLINE_SECONDS == 60.0
    assert SUPERVISOR_TIMEOUT_SECONDS == 75.0

    reader_idle, session_idle, transport_idle = make_test_reader()

    def idle_receive(stop: Event) -> Message | None:
        stop.wait(timeout=2.0)
        return None

    idle = run_offline_reader_capture(
        reader=reader_idle,
        session=session_idle,
        receive=idle_receive,
        deadline_seconds=0.06,
    )
    assert idle.reason == "SOFT_DEADLINE"
    assert idle.timer_fired and idle.spot_events == 0
    assert not reader_idle.records
    assert transport_idle.disconnect_calls == 1
    assert not transport_idle.sent

    reader_events, session_events, transport_events = make_test_reader()
    foreign_event = spot_event(bid=109200, ask=109202)
    setattr(foreign_event, "ctidTraderAccountId", DEMO_API_ACCOUNT_ID + 1)
    events = [
        foreign_event,
        spot_event(bid=109375, ask=109377),
        spot_event(bid=109377),
    ]

    def next_event(_stop: Event) -> Message | None:
        return events.pop(0) if events else None

    completed = run_offline_reader_capture(
        reader=reader_events,
        session=session_events,
        receive=next_event,
        deadline_seconds=0.5,
        max_observations=2,
    )
    assert completed.reason == "OBSERVATION_LIMIT"
    assert completed.spot_events == 3 and completed.accepted_observations == 2
    assert not completed.timer_fired
    assert reader_events.records[-1].zero_spread_origin == "CACHE_MERGE_EQUAL"
    assert transport_events.disconnect_calls == 1 and not transport_events.sent

    reader_error, session_error, transport_error = make_test_reader()

    def failing_receive(_stop: Event) -> Message | None:
        raise RuntimeError("T116-27_INJECTED_RECEIVE_FAILURE")

    with pytest.raises(RuntimeError, match="T116-27_INJECTED_RECEIVE_FAILURE"):
        run_offline_reader_capture(
            reader=reader_error,
            session=session_error,
            receive=failing_receive,
            deadline_seconds=0.2,
        )
    assert transport_error.disconnect_calls == 1

    reader_guard, session_guard, transport_guard = make_test_reader()
    messages = synthetic_sdk_messages()

    def forbidden_receive(_stop: Event) -> Message | None:
        reader_guard.send_read_only(proto(
            messages,
            "ProtoOANewOrderReq",
            ctidTraderAccountId=DEMO_API_ACCOUNT_ID,
        ))
        return None

    with pytest.raises(PermissionError):
        run_offline_reader_capture(
            reader=reader_guard,
            session=session_guard,
            receive=forbidden_receive,
            deadline_seconds=0.2,
        )
    assert transport_guard.disconnect_calls == 1
    with pytest.raises(PermissionError):
        reader_guard.reject_raw_packet(b"TEST_ONLY_FORBIDDEN_RAW")
    assert not transport_guard.sent
    with pytest.raises(ValueError):
        run_offline_reader_capture(
            reader=reader_guard,
            session=session_events,
            receive=next_event,
            deadline_seconds=0.1,
        )

    # У дочірньому процесі зависає саме receive автономного читача.
    child_code = "\n".join((
        "import time",
        "from tests.roadmap116.run_t116_27_reader_watchdog_integration "
        "import make_test_reader",
        "from tests.roadmap116.t116_27_reader_watchdog_integration "
        "import run_offline_reader_capture",
        "reader, session, transport = make_test_reader()",
        "def blocked_receive(_stop):",
        "    print('T116-27_CHILD_RECEIVE_ENTERED', flush=True)",
        "    time.sleep(30)",
        "    return None",
        "run_offline_reader_capture(reader=reader, session=session,",
        "    receive=blocked_receive, deadline_seconds=0.05)",
    ))
    killed = supervise_process(
        [sys.executable, "-c", child_code],
        hard_timeout_seconds=6.0,
    )
    assert killed.hard_timeout and killed.returncode == 124 and killed.reaped
    assert "T116-27_CHILD_RECEIVE_ENTERED" in killed.stdout

    print("T116-27 TEST_ONLY | standalone reader + watchdog integration")
    print("capture_deadline_seconds=60")
    print("supervisor_timeout_seconds=75")
    print("no_spot_events_reader_stopped=REAL_TIMER")
    print("synthetic_spot_events_processed=3_valid=2")
    print("zero_spread_cache_merge=OBSERVED")
    print("normal_and_error_disconnect=VERIFIED_FAKE_TRANSPORT")
    print("trade_unknown_raw=BLOCKED_DURING_CAPTURE")
    print("blocked_reader_child=KILLED_AND_REAPED")
    print("hard_kill_finally=NOT_GUARANTEED")
    print("real_sdk_client_created=NO")
    print("real_broker_requests=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    print("live_launch_authorized=NO")
    print("T116-27=GREEN_OFFLINE_READER_WATCHDOG_INTEGRATION")
