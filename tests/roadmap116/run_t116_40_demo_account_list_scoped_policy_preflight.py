"""T116-40 TEST_ONLY — три рівні AccountList guard, лише офлайн."""

from __future__ import annotations

import socket
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

from tests.roadmap116 import t116_29_sdk_outbound_guard as outbound
from tests.roadmap116.run_t116_29_sdk_outbound_transport_guard import (
    FakeClient,
    FakeFrameSender,
    FakeTcpProtocol,
    WireCase,
)
from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied
from tests.roadmap116.t116_39_demo_account_identity_preflight import (
    ACCOUNT_LIST_REQUEST,
    existing_outbound_policy_locked,
)
from tests.roadmap116.t116_40_demo_account_list_scoped_policy import (
    EXTENDED_REQUEST_NAMES,
    EXTENDED_UNSCOPED,
    SUCCESS_MARKER,
    TEST_ONLY_TOKEN,
    format_report,
    guarded_scoped_account_list,
    main,
    sdk_schema_preflight,
)


def synthetic_protobuf() -> tuple[object, object]:
    """Створити справжній protobuf клас AccountList із полем accessToken."""
    schema = getattr(descriptor_pb2, "FileDescriptorProto")()
    schema.name = "t11640_scoped_account_list.proto"
    schema.package = "t11640"
    schema.syntax = "proto2"
    field_type = getattr(descriptor_pb2, "FieldDescriptorProto")
    names = (
        *EXTENDED_REQUEST_NAMES,
        "ProtoOANewOrderReq",
        "ProtoMessage",
    )
    for index, name in enumerate(names):
        message = schema.message_type.add()
        message.name = name
        if name == "ProtoMessage":
            for number, field_name, kind in (
                (1, "payloadType", field_type.TYPE_UINT32),
                (2, "payload", field_type.TYPE_BYTES),
            ):
                field = message.field.add()
                field.name = field_name
                field.number = number
                field.label = field_type.LABEL_REQUIRED
                field.type = kind
            continue
        payload = message.field.add()
        payload.name = "payloadType"
        payload.number = 1
        payload.label = field_type.LABEL_OPTIONAL
        payload.type = field_type.TYPE_UINT32
        payload.default_value = str(1200 + index)
        if name == ACCOUNT_LIST_REQUEST:
            field = message.field.add()
            field.name = "accessToken"
            field.number = 2
            field.label = field_type.LABEL_REQUIRED
            field.type = field_type.TYPE_STRING
        elif name not in ("ProtoOAApplicationAuthReq", "ProtoHeartbeatEvent"):
            field = message.field.add()
            field.name = "ctidTraderAccountId"
            field.number = 2
            field.label = field_type.LABEL_OPTIONAL
            field.type = field_type.TYPE_UINT64
    pool = descriptor_pool.DescriptorPool()
    pool.Add(schema)
    classes = {
        name: message_factory.GetMessageClass(
            pool.FindMessageTypeByName(f"t11640.{name}")
        )
        for name in names
    }
    return SimpleNamespace(**classes), SimpleNamespace(**classes)


def test_t116_40_demo_account_list_scoped_policy_preflight() -> None:
    """AccountList проходить тільки у scoped-режимі з точним токеном."""
    denied = 0
    requests, common = synthetic_protobuf()
    samples = WireCase(requests, common)
    tcp = FakeTcpProtocol()
    tcp.envelope_class = samples.envelope_class
    client = FakeClient(tcp)
    good_list = samples.new(ACCOUNT_LIST_REQUEST, accessToken=TEST_ONLY_TOKEN)
    bad_list = samples.new(ACCOUNT_LIST_REQUEST, accessToken="OTHER_TOKEN")
    account = samples.new(
        "ProtoOAAccountAuthReq", ctidTraderAccountId=outbound.DEMO_API_ACCOUNT_ID
    )
    symbols = samples.new(
        "ProtoOASymbolsListReq", ctidTraderAccountId=outbound.DEMO_API_ACCOUNT_ID
    )
    app = samples.new("ProtoOAApplicationAuthReq")
    heartbeat = samples.new("ProtoHeartbeatEvent")
    foreign = samples.new("ProtoOASymbolsListReq", ctidTraderAccountId=9999)
    trade = samples.new(
        "ProtoOANewOrderReq", ctidTraderAccountId=outbound.DEMO_API_ACCOUNT_ID
    )

    assert existing_outbound_policy_locked()
    before_names = outbound.PERMITTED_REQUEST_NAMES
    before_unscoped = outbound.UNSCOPED_REQUEST_NAMES
    with external_tcp_denied():
        # Базовий T116-29 ніколи не пропускає AccountList.
        with outbound.guarded_sdk_outbound(
            client_type=FakeClient,
            tcp_protocol_type=FakeTcpProtocol,
            frame_sender_type=FakeFrameSender,
            request_messages=requests,
            common_messages=common,
        ):
            with pytest.raises(PermissionError):
                client.send(good_list)
            denied += 1

        def scoped(token: str = TEST_ONLY_TOKEN) -> Any:
            return guarded_scoped_account_list(
                client_type=FakeClient,
                tcp_protocol_type=FakeTcpProtocol,
                frame_sender_type=FakeFrameSender,
                request_messages=requests,
                common_messages=common,
                expected_token=token,
            )

        with scoped():
            assert outbound.PERMITTED_REQUEST_NAMES == EXTENDED_REQUEST_NAMES
            assert outbound.UNSCOPED_REQUEST_NAMES == EXTENDED_UNSCOPED
            client.send(app)
            client.send(account)
            tcp.send(symbols, instant=True)
            client.send(good_list)
            tcp.send(good_list, instant=True)
            getattr(tcp, "sendString")(samples.packet(good_list))
            getattr(tcp, "sendString")(samples.packet(heartbeat))
            assert len(tcp.transport.writes) == 7

            invalid_calls: tuple[Callable[[], object], ...] = (
                lambda: client.send(bad_list),
                lambda: tcp.send(bad_list, instant=True),
                lambda: tcp.send(bad_list, instant=False),
                lambda: getattr(tcp, "sendString")(samples.packet(bad_list)),
                lambda: client.send(foreign),
                lambda: tcp.send(foreign, instant=False),
                lambda: client.send(trade),
                lambda: tcp.send(trade, instant=True),
                lambda: getattr(tcp, "sendString")(samples.packet(trade)),
                lambda: getattr(tcp, "sendString")(b""),
                lambda: getattr(tcp, "sendString")(b"invalid frame"),
                lambda: getattr(tcp, "sendString")(
                    samples.packet(good_list) + b"garbage"
                ),
            )
            for invoke in invalid_calls:
                with pytest.raises(PermissionError):
                    invoke()
                denied += 1
            assert not tcp.queue
            assert len(tcp.transport.writes) == 7

            # Заздалегідь поставлений у чергу кадр також не обходить guard.
            tcp.queue.append(samples.packet(bad_list))
            with pytest.raises(PermissionError):
                tcp.flush()
            denied += 1
            assert len(tcp.transport.writes) == 7

        assert outbound.PERMITTED_REQUEST_NAMES is before_names
        assert outbound.UNSCOPED_REQUEST_NAMES is before_unscoped
        assert existing_outbound_policy_locked()
        with outbound.guarded_sdk_outbound(
            client_type=FakeClient,
            tcp_protocol_type=FakeTcpProtocol,
            frame_sender_type=FakeFrameSender,
            request_messages=requests,
            common_messages=common,
        ):
            with pytest.raises(PermissionError):
                client.send(good_list)
            denied += 1

        for invalid_token in ("", " ", " leading", "tailing ", "x" * 8193):
            with pytest.raises(PermissionError):
                with scoped(invalid_token):
                    raise AssertionError("має бути відхилено до входу")
            denied += 1

        with pytest.raises(RuntimeError):
            with patch.object(
                outbound, "PERMITTED_REQUEST_NAMES", ("ProtoOANewOrderReq",)
            ):
                with scoped():
                    raise AssertionError("baseline mismatch має бути відхилено")
        denied += 1

        # Навіть після винятку розширений whitelist повністю відновлюється.
        with pytest.raises(RuntimeError, match="SYNTHETIC_ABORT"):
            with scoped():
                raise RuntimeError("SYNTHETIC_ABORT")
        assert existing_outbound_policy_locked()
        denied += 1

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_probe:
            with pytest.raises(PermissionError):
                tcp_probe.connect(("192.0.2.10", 443))
        denied += 1

        for arguments in (
            [],
            ["--demo-network"],
            ["--live"],
            ["--offline-preflight", "--confirm", "YES"],
        ):
            with redirect_stderr(StringIO()):
                with pytest.raises(SystemExit):
                    main(arguments)
            denied += 1

        with patch(
            "tests.roadmap116.t116_40_demo_account_list_scoped_policy."
            "sdk_schema_preflight",
            return_value="VERIFIED_NO_EXTERNAL_NETWORK",
        ), redirect_stdout(StringIO()) as output:
            assert main(["--offline-preflight"]) == 0
        assert SUCCESS_MARKER in output.getvalue().splitlines()
        assert "network_launch_authorized=NO" in output.getvalue()

        with patch(
            "tests.roadmap116.t116_40_demo_account_list_scoped_policy."
            "sdk_schema_preflight",
            return_value="SDK_SCHEMA_INCOMPATIBLE",
        ), redirect_stdout(StringIO()) as output:
            assert main(["--offline-preflight"]) == 2
        assert "T116-40=NOT_READY_OFFLINE" in output.getvalue()
        denied += 1
        assert "real_identity_pair=NOT_QUERIED_NO_NETWORK" in format_report(
            "VERIFIED_NO_EXTERNAL_NETWORK"
        )
        assert sdk_schema_preflight() in (
            "NOT_INSTALLED_LOCAL_RUNNER",
            "VERIFIED_NO_EXTERNAL_NETWORK",
        )

    print("T116-40 TEST_ONLY | scoped DEMO AccountList policy offline")
    print(f"negative_scenarios_denied={denied}")
    print("existing_t116_29_policy=UNCHANGED_AFTER_SCOPE")
    print("account_list_policy=SCOPED_EXACT_TOKEN_THREE_OUTBOUND_LEVELS")
    print("trade_requests=DENIED")
    print("real_identity_pair=NOT_QUERIED_NO_NETWORK")
    print("sdk_client_constructor=NOT_CALLED")
    print("external_tcp=BLOCKED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print(SUCCESS_MARKER)
