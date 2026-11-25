"""T116-39 TEST_ONLY — офлайн-контракт DEMO account ID / GUI login."""

from __future__ import annotations

import socket
from collections.abc import Sequence
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from unittest.mock import patch

import pytest

from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied
from tests.roadmap116.t116_39_demo_account_identity_preflight import (
    EXPECTED_API_ACCOUNT_ID,
    EXPECTED_GUI_TRADER_LOGIN,
    SUCCESS_MARKER,
    existing_outbound_policy_locked,
    format_report,
    main,
    sdk_schema_preflight,
    verify_account_identity,
)


@dataclass(frozen=True, slots=True)
class FakeAccount:
    """Мінімальна синтетична відповідь SDK з protobuf presence flags."""

    ctidTraderAccountId: object  # noqa: N815
    traderLogin: object  # noqa: N815
    isLive: object  # noqa: N815
    present: frozenset[str] = frozenset({"traderLogin", "isLive"})

    # noinspection PyPep8Naming
    def HasField(self, field: str) -> bool:
        """Емуляція protobuf HasField без використання реального SDK."""
        return field in self.present


def account(
    api_id: object = EXPECTED_API_ACCOUNT_ID,
    login: object = EXPECTED_GUI_TRADER_LOGIN,
    live: object = False,
    present: frozenset[str] = frozenset({"traderLogin", "isLive"}),
) -> FakeAccount:
    """Створити синтетичну облікову сутність без credentials."""
    return FakeAccount(api_id, login, live, present)


def test_t116_39_demo_account_identity_preflight() -> None:
    """Ідентичність, DEMO, дублікати, схема, заборона мережі."""
    denied = 0
    with external_tcp_denied():
        # API ID і GUI login мають бути різними та перевіреними однією сутністю.
        good = verify_account_identity((
            account(111, 222, True),
            account(),
            account(333, 444, False),
        ))
        assert good.matched
        assert good.reason == "IDENTITY_PAIR_MATCHES_DEMO"

        invalid_cases: Sequence[tuple[object, ...]] = (
            (),
            (account(1, EXPECTED_GUI_TRADER_LOGIN),),
            (account(EXPECTED_API_ACCOUNT_ID, 123),),
            (account(live=True),),
            (account(present=frozenset({"traderLogin"})),),
            (account(present=frozenset({"isLive"})),),
            (account(present=frozenset()),),
            (account(api_id="46368962"),),
            (account(login="9870599"),),
            (account(live=0),),
            (account(api_id=True),),
            (account(login=False),),
            (account(api_id=0),),
            (account(login=-1),),
            (account(), account()),
            (account(), account(222, EXPECTED_GUI_TRADER_LOGIN)),
            (account(), account(EXPECTED_API_ACCOUNT_ID, 333)),
            (account(), account(api_id=0)),
            (object(),),
            (account(111, 222), account(222, 333)),
            tuple(account(i + 1, i + 1001) for i in range(101)),
        )
        for records in invalid_cases:
            result = verify_account_identity(records)
            assert not result.matched
            denied += 1

        # Поточний outbound guard НЕ має права відправити AccountList.
        assert existing_outbound_policy_locked()
        assert "account_list_outbound=BLOCKED_PENDING_NEW_POLICY" in (
            format_report("VERIFIED_NO_EXTERNAL_NETWORK")
        )
        assert "real_identity_pair=NOT_QUERIED_NO_NETWORK" in format_report(
            "NOT_INSTALLED_LOCAL_RUNNER"
        )
        denied += 1

        # Схема недоступного SDK не створює клієнта чи мережу.
        with patch(
            "tests.roadmap116.t116_39_demo_account_identity_preflight.find_spec",
            return_value=None,
        ):
            assert sdk_schema_preflight() == "NOT_INSTALLED_LOCAL_RUNNER"
        denied += 1

        # Спроба прямого TCP має блокуватись офлайн-контуром.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_probe:
            with pytest.raises(PermissionError):
                tcp_probe.connect(("192.0.2.17", 443))
        denied += 1

        for arguments in ([], ["--demo-network"], ["--live"]):
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                with pytest.raises(SystemExit):
                    main(arguments)
            denied += 1

        with patch(
            "tests.roadmap116.t116_39_demo_account_identity_preflight."
            "sdk_schema_preflight",
            return_value="VERIFIED_NO_EXTERNAL_NETWORK",
        ), redirect_stdout(StringIO()) as output:
            assert main(["--offline-preflight"]) == 0
        lines = output.getvalue().splitlines()
        assert lines.count(SUCCESS_MARKER) == 1
        assert "network_launch_authorized=NO" in lines
        assert "real_broker_requests=0" in lines
        assert "production_changes=0" in lines
        assert "sdk_client_constructor=NOT_CALLED" in lines
        assert "child_process=NOT_STARTED" in lines

        with patch(
            "tests.roadmap116.t116_39_demo_account_identity_preflight."
            "sdk_schema_preflight",
            return_value="SCHEMA_INCOMPATIBLE",
        ), redirect_stdout(StringIO()) as mismatch_output:
            assert main(["--offline-preflight"]) == 2
        assert "T116-39=NOT_READY_OFFLINE" in mismatch_output.getvalue()
        denied += 1

    print("T116-39 TEST_ONLY | DEMO account identity preflight OFFLINE")
    print(f"negative_scenarios_denied={denied}")
    print("identity_validator=SYNTHETIC_ACCOUNT_LIST_ONLY")
    print("real_identity_pair=NOT_QUERIED_NO_NETWORK")
    print("account_list_outbound=BLOCKED_PENDING_NEW_POLICY")
    print("sdk_client_constructor=NOT_CALLED")
    print("external_tcp=BLOCKED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print(SUCCESS_MARKER)
