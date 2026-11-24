"""T116-22 TEST_ONLY — офлайн-контракт ізольованого DEMO читача котирувань."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.message import Message

from tests.roadmap116.t116_22_standalone_demo_reader import (
    DEMO_API_ACCOUNT_ID,
    StandaloneDemoQuoteReader,
    capture_bounded_offline,
)

READER_FILE = Path(__file__).with_name("t116_22_standalone_demo_reader.py")


def fake_message_classes() -> dict[str, type[Message]]:
    """Створити protobuf без SDK, брокера чи TCP."""
    file_proto = getattr(descriptor_pb2, "FileDescriptorProto")()
    file_proto.name = "t11622_offline.proto"
    file_proto.package = "t11622"
    file_proto.syntax = "proto2"
    field_descriptor = getattr(descriptor_pb2, "FieldDescriptorProto")
    names = (
        "ProtoOAApplicationAuthReq",
        "ProtoOAAccountAuthReq",
        "ProtoOASubscribeSpotsReq",
        "ProtoHeartbeatEvent",
        "ProtoOANewOrderReq",
        "ProtoOASpotEvent",
    )
    for name in names:
        node = file_proto.message_type.add()
        node.name = name
        for number, field_name in enumerate(
            ("ctidTraderAccountId", "symbolId", "bid", "ask", "timestamp"), start=1
        ):
            field = node.field.add()
            field.name = field_name
            field.number = number
            field.label = field_descriptor.LABEL_OPTIONAL
            field.type = field_descriptor.TYPE_UINT64
    pool = descriptor_pool.DescriptorPool()
    pool.Add(file_proto)
    return {
        name: message_factory.GetMessageClass(
            pool.FindMessageTypeByName(f"t11622.{name}")
        )
        for name in names
    }


def new_message(message_type: type[Message], **fields: int) -> Message:
    """Створити динамічний protobuf без нетипізованих аргументів конструктора."""
    message = message_type()
    for field_name, field_value in fields.items():
        setattr(message, field_name, field_value)
    return message


class FakeSender:
    """Лише пам'ять: немає жодного мережевого методу."""

    def __init__(self) -> None:
        self.sent: list[Message] = []

    def send(self, message: Message) -> None:
        self.sent.append(message)


class FakeClock:
    """Керований час для перевірки 60 секунд без очікування."""

    def __init__(self) -> None:
        self.seconds = 0.0

    def tick(self, seconds: float) -> None:
        self.seconds += seconds

    def monotonic(self) -> float:
        return self.seconds


def test_t116_22_standalone_demo_quote_reader_contract() -> None:
    """Довести лише офлайн-безпечність нового читача."""
    tree = ast.parse(READER_FILE.read_text(encoding="utf-8"))
    imports = [
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ]
    imports.extend(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    forbidden_prefixes = (
        "LGE",
        "engine",
        "core",
        "ibapi",
        "PySide6",
        "ctrader_open_api",
    )
    assert not any(
        name == prefix or name.startswith(prefix + ".")
        for name in imports
        for prefix in forbidden_prefixes
    )

    classes = fake_message_classes()
    sender = FakeSender()
    allowed_types = {
        name: cls
        for name, cls in classes.items()
        if name not in {"ProtoOANewOrderReq", "ProtoOASpotEvent"}
    }
    current = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)

    def now() -> datetime:
        return current

    with pytest.raises(ValueError):
        StandaloneDemoQuoteReader(
            account_mode="LIVE",
            account_id=DEMO_API_ACCOUNT_ID,
            symbol_id=55,
            sender=sender,
            allowed_types=allowed_types,
            spot_event_type=classes["ProtoOASpotEvent"],
            now_utc=now,
        )
    with pytest.raises(ValueError):
        StandaloneDemoQuoteReader(
            account_mode="DEMO",
            account_id=DEMO_API_ACCOUNT_ID + 1,
            symbol_id=55,
            sender=sender,
            allowed_types=allowed_types,
            spot_event_type=classes["ProtoOASpotEvent"],
            now_utc=now,
        )

    reader = StandaloneDemoQuoteReader(
        account_mode="DEMO",
        account_id=DEMO_API_ACCOUNT_ID,
        symbol_id=55,
        sender=sender,
        allowed_types=allowed_types,
        spot_event_type=classes["ProtoOASpotEvent"],
        now_utc=now,
    )
    reader.send_read_only(
        new_message(
            classes["ProtoOAAccountAuthReq"],
            ctidTraderAccountId=DEMO_API_ACCOUNT_ID,
        )
    )
    reader.send_read_only(
        new_message(
            classes["ProtoOASubscribeSpotsReq"],
            ctidTraderAccountId=DEMO_API_ACCOUNT_ID,
        )
    )
    reader.send_read_only(new_message(classes["ProtoHeartbeatEvent"]))
    assert len(sender.sent) == 3
    blocked_messages: tuple[Any, ...] = (
        new_message(
            classes["ProtoOANewOrderReq"],
            ctidTraderAccountId=DEMO_API_ACCOUNT_ID,
        ),
        new_message(
            classes["ProtoOAAccountAuthReq"],
            ctidTraderAccountId=DEMO_API_ACCOUNT_ID + 1,
        ),
        b"fake raw trade packet",
        new_message(
            fake_message_classes()["ProtoOAAccountAuthReq"],
            ctidTraderAccountId=DEMO_API_ACCOUNT_ID,
        ),
    )
    for message in blocked_messages:
        with pytest.raises(PermissionError):
            reader.send_read_only(message)
    with pytest.raises(PermissionError):
        reader.reject_raw_packet(b"fake raw trade packet")
    assert len(sender.sent) == 3

    raw_event = classes["ProtoOASpotEvent"]
    first = reader.on_spot_event(
        new_message(
            raw_event,
            ctidTraderAccountId=DEMO_API_ACCOUNT_ID,
            symbolId=55,
            bid=109375,
            ask=109377,
            timestamp=int(current.timestamp() * 1000),
        )
    )
    assert first is not None
    assert first.bid == 1.09375 and first.ask == 1.09377
    assert first.side_age_seconds == 0
    current += timedelta(seconds=300)
    merged = reader.on_spot_event(
        new_message(
            raw_event,
            ctidTraderAccountId=DEMO_API_ACCOUNT_ID,
            symbolId=55,
            bid=109377,
            timestamp=int(current.timestamp() * 1000),
        )
    )
    assert merged is not None
    assert merged.zero_spread_origin == "CACHE_MERGE_EQUAL"
    assert merged.side_age_seconds == 300
    assert merged.raw_bid_present and not merged.raw_ask_present
    assert (
        reader.on_spot_event(
            new_message(
                raw_event,
                ctidTraderAccountId=DEMO_API_ACCOUNT_ID + 1,
                symbolId=55,
                bid=109380,
                ask=109381,
            )
        )
        is None
    )
    assert len(reader.records) == 2

    separate = StandaloneDemoQuoteReader(
        account_mode="DEMO",
        account_id=DEMO_API_ACCOUNT_ID,
        symbol_id=55,
        sender=FakeSender(),
        allowed_types=allowed_types,
        spot_event_type=classes["ProtoOASpotEvent"],
        now_utc=now,
    )
    raw_equal = separate.on_spot_event(
        new_message(
            raw_event,
            ctidTraderAccountId=DEMO_API_ACCOUNT_ID,
            symbolId=55,
            bid=109377,
            ask=109377,
        )
    )
    assert raw_equal is not None
    assert raw_equal.zero_spread_origin == "RAW_BOTH_EQUAL"

    clock = FakeClock()
    actions: list[str] = []

    def connect() -> None:
        actions.append("CONNECT_FAKE")

    def poll(timeout: float) -> None:
        assert 0 < timeout <= 1
        clock.tick(timeout)

    def disconnect() -> None:
        actions.append("DISCONNECT_FAKE")

    capture_bounded_offline(
        connect=connect,
        poll=poll,
        disconnect=disconnect,
        monotonic=clock.monotonic,
    )
    assert actions == ["CONNECT_FAKE", "DISCONNECT_FAKE"]
    assert clock.seconds == 60

    actions.clear()
    with pytest.raises(RuntimeError, match="TEST_ONLY_INJECTED"):
        capture_bounded_offline(
            connect=connect,
            poll=lambda _timeout: (_ for _ in ()).throw(
                RuntimeError("TEST_ONLY_INJECTED")
            ),
            disconnect=disconnect,
            monotonic=clock.monotonic,
        )
    assert actions == ["CONNECT_FAKE", "DISCONNECT_FAKE"]

    actions.clear()
    with pytest.raises(RuntimeError, match="CONNECT_INJECTED"):
        capture_bounded_offline(
            connect=lambda: (_ for _ in ()).throw(RuntimeError("CONNECT_INJECTED")),
            poll=poll,
            disconnect=disconnect,
            monotonic=clock.monotonic,
        )
    assert actions == ["DISCONNECT_FAKE"]
    with pytest.raises(ValueError):
        capture_bounded_offline(
            connect=connect,
            poll=poll,
            disconnect=disconnect,
            monotonic=clock.monotonic,
            duration_seconds=61,
        )
    print("T116-22 TEST_ONLY | standalone cTrader DEMO quote reader")
    print("reader_imports_lge_runtime_ib=NO")
    print("network_client_created=NO")
    print("demo_api_account_id=46368962")
    print("readonly_protobuf_send=3")
    print("trade_unknown_foreign_raw=BLOCKED")
    print("partial_bid_ask_side_age_seconds=300")
    print("zero_spread_cache_vs_raw=DISAMBIGUATED")
    print("capture_deadline_seconds=60")
    print("no_spot_event_timeout=VERIFIED_FAKE_CLOCK")
    print("exception_disconnect=VERIFIED_FAKE_TRANSPORT")
    print("actual_ctrader_sdk=NOT_REQUIRED_OFFLINE")
    print("real_broker_requests=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    print("live_launch_authorized=NO")
    print("T116-22=GREEN_OFFLINE_STANDALONE_DEMO_READER_CONTRACT")
