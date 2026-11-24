"""T116-20G TEST_ONLY — whitelist protobuf на рівні cTrader TcpProtocol.

Тільки синтетичні protobuf і локальні виклики. Сокети та LGE не запускаються.
За наявності офіційного SDK перевіряються також його справжні класи.
"""

from __future__ import annotations

import ast
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

ROOT = Path(__file__).resolve().parents[2]
TELEMETRY_FILE = (
    ROOT / "tests" / "roadmap116" / "run_t116_19_ctrader_raw_spot_telemetry.py"
)
ADAPTER_FILE = ROOT / "engine" / "ctrader_adapter.py"


class FakeProtocol:
    """Транспортний стенд: обліковує лише допущені виклики."""

    def __init__(self) -> None:
        self.objects: list[object] = []
        self.packets: list[bytes] = []

    def send(self, message: object, *_args: Any, **_kwargs: Any) -> None:
        self.objects.append(message)

    def send_string(self, packet: bytes) -> None:
        self.packets.append(packet)


# Назва методу визначена стороннім cTrader SDK, тому встановлюємо її динамічно.
setattr(FakeProtocol, "sendString", FakeProtocol.send_string)


def fake_protobuf_modules(names: tuple[str, ...]) -> tuple[Any, Any]:
    """Створити справжні protobuf-повідомлення у пам'яті, без мережі."""
    schema = getattr(descriptor_pb2, "FileDescriptorProto")()
    field_descriptor = getattr(descriptor_pb2, "FieldDescriptorProto")
    schema.name = "t11620g_test_only.proto"
    schema.package = "t11620g"
    schema.syntax = "proto2"
    all_names = (*names, "ProtoHeartbeatEvent", "ProtoMessage", "ProtoOANewOrderReq")
    for index, name in enumerate(all_names, start=1):
        message = schema.message_type.add()
        message.name = name
        if name != "ProtoMessage":
            payload = message.field.add()
            payload.name = "payloadType"
            payload.number = 1
            payload.label = field_descriptor.LABEL_OPTIONAL
            payload.type = field_descriptor.TYPE_UINT32
            payload.default_value = str(1000 + index)
            if name not in {
                "ProtoHeartbeatEvent",
                "ProtoOAApplicationAuthReq",
                "ProtoOAGetAccountListByAccessTokenReq",
            }:
                account = message.field.add()
                account.name = "ctidTraderAccountId"
                account.number = 2
                account.label = field_descriptor.LABEL_OPTIONAL
                account.type = field_descriptor.TYPE_UINT64
        else:
            fields = (
                ("payloadType", 1, field_descriptor.TYPE_UINT32),
                ("payload", 2, field_descriptor.TYPE_BYTES),
            )
            for field_name, number, field_type in fields:
                field = message.field.add()
                field.name = field_name
                field.number = number
                field.label = field_descriptor.LABEL_REQUIRED
                field.type = field_type
    pool = descriptor_pool.DescriptorPool()
    pool.Add(schema)
    classes = {
        name: message_factory.GetMessageClass(
            pool.FindMessageTypeByName(f"t11620g.{name}")
        )
        for name in all_names
    }
    request_module = SimpleNamespace(**classes)
    common_module = SimpleNamespace(**classes)
    return request_module, common_module


def check_blocked(operation: Any) -> None:
    """Підтвердити заборону до звернення до транспортного методу."""
    try:
        operation()
    except RuntimeError:
        return
    raise AssertionError("T116-20G: небезпечний protobuf пройшов guard")


def sdk_probe(isolate_guard: Any) -> str:
    """Перевірити справжні класи SDK, якщо вони встановлені в Python."""
    try:
        from ctrader_open_api import TcpProtocol
        from ctrader_open_api.messages import (
            OpenApiCommonMessages_pb2,
            OpenApiMessages_pb2,
        )
    except ModuleNotFoundError:
        return "NOT_INSTALLED_IN_LOCAL_RUNNER"

    object_calls: list[str] = []
    packet_calls: list[bytes] = []

    def fake_send(_self: object, message: object, *_args: Any, **_kwargs: Any) -> None:
        object_calls.append(type(message).__name__)

    def fake_send_string(_self: object, frame_bytes: bytes) -> None:
        packet_calls.append(frame_bytes)

    instance = object.__new__(TcpProtocol)
    with (
        patch.object(TcpProtocol, "send", fake_send),
        patch.object(TcpProtocol, "sendString", fake_send_string),
    ):
        with isolate_guard(
            protocol_type=TcpProtocol,
            request_messages=OpenApiMessages_pb2,
            common_messages=OpenApiCommonMessages_pb2,
        ):
            heartbeat = getattr(OpenApiCommonMessages_pb2, "ProtoHeartbeatEvent")()
            TcpProtocol.send(instance, heartbeat)
            reader = getattr(OpenApiMessages_pb2, "ProtoOATraderReq")(
                ctidTraderAccountId=46368962
            )
            TcpProtocol.send(instance, reader)
            assert object_calls == ["ProtoHeartbeatEvent", "ProtoOATraderReq"]
            reader_frame = getattr(OpenApiCommonMessages_pb2, "ProtoMessage")(
                payloadType=reader.payloadType,
                payload=reader.SerializeToString(),
            ).SerializeToString()
            TcpProtocol.sendString(instance, reader_frame)
            assert packet_calls == [reader_frame]

            required_trade_fields = {
                "ctidTraderAccountId": 46368962,
                "symbolId": 1,
                "orderType": 1,
                "tradeSide": 1,
                "volume": 1000,
                "positionId": 1,
            }
            for name in (
                "ProtoOANewOrderReq",
                "ProtoOAClosePositionReq",
                "ProtoOAAmendPositionSLTPReq",
            ):
                forbidden = getattr(OpenApiMessages_pb2, name)()
                # Заповнити обов'язкові поля перед серіалізацією SDK.
                # Рахунок навмисно дозволений: відмову має спричинити тип ордера.
                for field_name in forbidden.FindInitializationErrors():
                    if field_name not in required_trade_fields:
                        raise AssertionError(
                            f"T116-20G: невідоме обов'язкове поле: {field_name}"
                        )
                    setattr(forbidden, field_name, required_trade_fields[field_name])
                assert forbidden.IsInitialized(), name
                check_blocked(lambda: TcpProtocol.send(instance, forbidden))
                forbidden_frame = getattr(OpenApiCommonMessages_pb2, "ProtoMessage")(
                    payloadType=forbidden.payloadType,
                    payload=forbidden.SerializeToString(),
                ).SerializeToString()
                check_blocked(lambda: TcpProtocol.sendString(instance, forbidden_frame))
            assert len(object_calls) == 2
            assert packet_calls == [reader_frame]
    return "VERIFIED_NO_NETWORK"


def test_t116_20g_outbound_protobuf_trade_guard() -> None:
    """Перевірити відмову торгових і сирих повідомлень до транспорту."""
    source = runpy.run_path(str(TELEMETRY_FILE), run_name="t116_20g_test_only")
    isolate_guard = source["isolate_ctrader_outbound_protobuf"]
    whitelist = source["CTRADER_READ_ONLY_PROTO_NAMES"]
    authorized = source["AUTHORIZED_DEMO_API_ID"]
    assert authorized == 46368962

    request_module, common_module = fake_protobuf_modules(whitelist)
    envelope_class = common_module.ProtoMessage
    account_class = request_module.ProtoOATraderReq
    trade_class = request_module.ProtoOANewOrderReq
    heartbeat_class = common_module.ProtoHeartbeatEvent

    def packet_for(message: Any) -> bytes:
        return envelope_class(
            payloadType=message.payloadType,
            payload=message.SerializeToString(),
        ).SerializeToString()

    protocol = FakeProtocol()
    with isolate_guard(
        protocol_type=FakeProtocol,
        request_messages=request_module,
        common_messages=common_module,
    ):
        heartbeat = heartbeat_class()
        allowed = account_class(ctidTraderAccountId=authorized)
        protocol.send(heartbeat)
        protocol.send(allowed)
        getattr(protocol, "sendString")(packet_for(heartbeat))
        getattr(protocol, "sendString")(packet_for(allowed))
        assert len(protocol.objects) == 2
        assert len(protocol.packets) == 2

        trade = trade_class(ctidTraderAccountId=authorized)
        foreign = account_class(ctidTraderAccountId=authorized + 1)
        attempts = (
            lambda: protocol.send(trade),
            lambda: protocol.send(foreign),
            lambda: protocol.send(123),
            lambda: protocol.send(envelope_class()),
            lambda: getattr(protocol, "sendString")(packet_for(trade)),
            lambda: getattr(protocol, "sendString")(packet_for(foreign)),
            lambda: getattr(protocol, "sendString")(b"broken protobuf"),
            lambda: getattr(protocol, "sendString")(b""),
        )
        for attempt in attempts:
            check_blocked(attempt)
        assert len(protocol.objects) == 2
        assert len(protocol.packets) == 2

    # Перевірити, що підміни автоматично відновлено.
    protocol.send(trade)
    getattr(protocol, "sendString")(packet_for(trade))
    assert len(protocol.objects) == 3
    assert len(protocol.packets) == 3

    tree = ast.parse(TELEMETRY_FILE.read_text(encoding="utf-8"))
    launcher = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "launch_live_diagnostics"
    )
    disconnect_guard = next(
        node
        for node in ast.walk(launcher)
        if isinstance(node, ast.FunctionDef) and node.name == "ctrader_disconnect_guard"
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "isolate_ctrader_outbound_protobuf"
        for node in ast.walk(disconnect_guard)
    )

    adapter_tree = ast.parse(ADAPTER_FILE.read_text(encoding="utf-8"))
    send_calls = [
        node
        for node in ast.walk(adapter_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "send"
    ]
    assert send_calls
    assert all(
        isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Attribute)
        and isinstance(call.func.value.value, ast.Name)
        and call.func.value.value.id == "self"
        and call.func.value.attr == "client"
        for call in send_calls
    )

    sdk_status = sdk_probe(isolate_guard)
    print("T116-20G TEST_ONLY | outbound protobuf allowlist")
    print(f"authorized_api_account_id={authorized}")
    print(f"read_only_request_types={len(whitelist)}")
    print("heartbeat=ALLOWED")
    print("trading_protobuf_object=BLOCKED")
    print("trading_protobuf_envelope=BLOCKED")
    print("wrong_account_object_and_envelope=BLOCKED")
    print("unknown_raw_bytes=BLOCKED")
    print("guard_present_during_disconnect=YES")
    print(f"actual_ctrader_sdk={sdk_status}")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("T116-20G=GREEN_OFFLINE_OUTBOUND_PROTOBUF_GUARD")
