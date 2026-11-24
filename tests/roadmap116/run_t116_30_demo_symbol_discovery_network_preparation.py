"""T116-30 TEST_ONLY — безпечна підготовка DEMO Symbol Discovery."""

from __future__ import annotations

import socket
from contextlib import redirect_stderr
from io import StringIO
from importlib.util import find_spec
from unittest.mock import patch

import pytest

from tests.roadmap116.run_t116_24_demo_symbol_discovery_contract import (
    synthetic_sdk_messages,
)
from tests.roadmap116.run_t116_25_demo_network_safety_preflight import (
    FakeEndpoints,
    FakeProtocol,
)
from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_30_offline_symbol_preparation import (
    REQUEST_ORDER,
    external_tcp_denied,
    main,
    prepare_offline_discovery,
)


def test_t116_30_demo_symbol_discovery_network_preparation() -> None:
    """Забезпечити готовність без жодної спроби вийти до брокера."""
    sdk_messages = synthetic_sdk_messages()
    prepared = prepare_offline_discovery(
        endpoints=FakeEndpoints(),
        protocol_type=FakeProtocol,
        sdk_messages=sdk_messages,
    )
    assert prepared.account_id == DEMO_API_ACCOUNT_ID
    assert prepared.request_names == REQUEST_ORDER
    assert prepared.disconnected
    assert not prepared.network_allowed
    assert prepared.eurusd_symbol_id is None

    for wrong_mode, wrong_account in (
        ("LIVE", DEMO_API_ACCOUNT_ID),
        ("DEMO", DEMO_API_ACCOUNT_ID + 1),
    ):
        with pytest.raises(PermissionError):
            prepare_offline_discovery(
                endpoints=FakeEndpoints(),
                protocol_type=FakeProtocol,
                sdk_messages=sdk_messages,
                account_mode=wrong_mode,
                account_id=wrong_account,
            )

    with external_tcp_denied():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            with pytest.raises(PermissionError):
                probe.connect(("192.0.2.10", 443))
            with pytest.raises(PermissionError):
                probe.connect_ex(("192.0.2.10", 443))
        with pytest.raises(PermissionError):
            socket.create_connection(("192.0.2.10", 443))

    for prohibited_args in ([], ["--live"], ["--live-worker"]):
        with redirect_stderr(StringIO()):
            with pytest.raises(SystemExit) as failure:
                main(prohibited_args)
        assert failure.value.code == 2

    sdk_status = "NOT_INSTALLED_LOCAL_RUNNER"
    if find_spec("ctrader_open_api") is not None:
        assert main(["--offline-preflight"]) == 0
        sdk_status = "VERIFIED_NO_EXTERNAL_NETWORK"
    else:
        with patch(
            "tests.roadmap116.t116_30_offline_symbol_preparation.load_real_sdk_types",
            return_value=(
                FakeEndpoints(), object, FakeProtocol, sdk_messages, object()
            ),
        ):
            assert main(["--offline-preflight"]) == 0

    print("T116-30 TEST_ONLY | standalone DEMO symbol discovery preparation")
    print("authorization_order=APPLICATION_ACCOUNT_SYMBOLS")
    print(f"demo_api_account_id={DEMO_API_ACCOUNT_ID}")
    print("readonly_request_types=3")
    print("live_worker_and_unapproved_args=DENIED")
    print("external_tcp_connect_connect_ex_create_connection=BLOCKED")
    print(f"actual_ctrader_sdk={sdk_status}")
    print("real_client_constructor=NOT_CALLED")
    print("real_eurusd_symbol_id=NOT_QUERIED_NO_NETWORK")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("live_launch_authorized=NO")
    print("T116-30=GREEN_OFFLINE_DISCOVERY_NETWORK_PREPARATION")
