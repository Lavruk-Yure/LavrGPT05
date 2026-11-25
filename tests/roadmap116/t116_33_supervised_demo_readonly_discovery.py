"""T116-33 TEST_ONLY — контроль першої DEMO read-only мережевої спроби.

Повторно використовує T116-32 у дочірньому Python-процесі та незалежний
T116-26 supervisor. Звичайний offline-preflight ніколи не відкриває мережу.
Production, GUI, WSP, RuntimeEngine та конфігурації LGE не змінюються.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Mapping, Sequence
from importlib import import_module
from importlib.util import find_spec

from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_23_sdk_offline_bridge import (
    load_real_sdk_types,
    sdk_client_spec,
    sdk_message_type,
)
from tests.roadmap116.t116_26_process_watchdog import (
    SUPERVISOR_TIMEOUT_SECONDS,
    SupervisedResult,
    supervise_process,
)
from tests.roadmap116.t116_29_sdk_outbound_guard import guarded_sdk_outbound
from tests.roadmap116.t116_30_offline_symbol_preparation import (
    external_tcp_denied,
)
from tests.roadmap116.t116_31_demo_readonly_discovery_session import (
    INBOUND_RESPONSE_NAMES,
)
from tests.roadmap116.t116_32_demo_network_readonly_discovery import (
    NETWORK_CONFIRMATION,
    authorized_credentials,
)

CHILD_MODULE = "tests.roadmap116.t116_32_demo_network_readonly_discovery"
CHILD_GREEN = "T116-32=GREEN_DEMO_READONLY_SYMBOL_DISCOVERY"
RESULT_GREEN = "T116-33=GREEN_DEMO_READONLY_SYMBOL_DISCOVERY_SUPERVISED"
RESULT_OFFLINE = "T116-33=GREEN_OFFLINE_SUPERVISED_NETWORK_PREFLIGHT"
SYMBOL_PATTERN = re.compile(r"real_eurusd_symbol_id=([1-9][0-9]*)")
ERROR_PATTERN = re.compile(r"failure_code=([A-Z][A-Z0-9_]*)")


def sdk_offline_preflight() -> str:
    """Перевірити реальний SDK та outbound guard без створення Client()."""
    if find_spec("ctrader_open_api") is None:
        return "NOT_INSTALLED_LOCAL_RUNNER"

    with external_tcp_denied():
        endpoints, client_type, protocol_type, messages, common = load_real_sdk_types()
        spec = sdk_client_spec(endpoints, protocol_type)
        if spec.demo_host == spec.live_host:
            raise PermissionError("T116-33: DEMO та LIVE endpoint однакові")
        for name in (
            "setConnectedCallback",
            "setDisconnectedCallback",
            "setMessageReceivedCallback",
            "send",
            "startService",
            "stopService",
        ):
            if not callable(getattr(client_type, name, None)):
                raise RuntimeError("T116-33: SDK Client API несумісний")
        names = (
            "ProtoOAApplicationAuthReq",
            "ProtoOAAccountAuthReq",
            "ProtoOASymbolsListReq",
            *INBOUND_RESPONSE_NAMES,
        )
        payload_ids = []
        for name in names:
            message_type = sdk_message_type(messages, name)
            payload_ids.append(int(getattr(message_type(), "payloadType")))
        if len(payload_ids) != len(set(payload_ids)):
            raise RuntimeError("T116-33: payloadType неунікальні")

        frame_sender_type = getattr(
            import_module("twisted.protocols.basic"), "Int32StringReceiver"
        )
        with guarded_sdk_outbound(
            client_type=client_type,
            tcp_protocol_type=protocol_type,
            frame_sender_type=frame_sender_type,
            request_messages=messages,
            common_messages=common,
        ):
            pass
    return "VERIFIED_NO_EXTERNAL_NETWORK"


def summarize_child(result: SupervisedResult) -> int:
    """Показати лише безпечні коди та EURUSD ID, не друкуючи raw логи."""
    print(f"child_return_code={result.returncode}")
    print(f"child_reaped={'YES' if result.reaped else 'NO'}")
    if result.hard_timeout:
        print("failure_code=HARD_PROCESS_TIMEOUT")
        print("T116-33=FAILED_DEMO_READONLY_DISCOVERY")
        return 1
    if not result.reaped or result.returncode != 0:
        match = ERROR_PATTERN.search(result.stdout)
        print(f"failure_code={match.group(1) if match else 'CHILD_PROCESS_FAILED'}")
        print("T116-33=FAILED_DEMO_READONLY_DISCOVERY")
        return 1

    lines = result.stdout.splitlines()
    symbol_lines = [line for line in lines if SYMBOL_PATTERN.fullmatch(line)]
    if lines.count(CHILD_GREEN) != 1 or len(symbol_lines) != 1:
        print("failure_code=INVALID_CHILD_RESULT")
        print("T116-33=FAILED_DEMO_READONLY_DISCOVERY")
        return 1
    match = SYMBOL_PATTERN.fullmatch(symbol_lines[0])
    if match is None:
        print("failure_code=INVALID_SYMBOL_ID")
        print("T116-33=FAILED_DEMO_READONLY_DISCOVERY")
        return 1
    if lines.count(f"demo_api_account_id={DEMO_API_ACCOUNT_ID}") != 1:
        print("failure_code=ACCOUNT_ID_MISMATCH")
        print("T116-33=FAILED_DEMO_READONLY_DISCOVERY")
        return 1
    print(f"demo_api_account_id={DEMO_API_ACCOUNT_ID}")
    print(f"real_eurusd_symbol_id={int(match.group(1))}")
    print("request_policy=APPLICATION_ACCOUNT_SYMBOLS_HEARTBEAT_ONLY")
    print("production_changes=0")
    print(RESULT_GREEN)
    return 0


def run_supervised_network() -> int:
    """Один DEMO child, без повторних спроб і без shell."""
    command = [
        sys.executable,
        "-m",
        CHILD_MODULE,
        "--demo-network",
        "--confirm",
        NETWORK_CONFIRMATION,
    ]
    result = supervise_process(
        command,
        hard_timeout_seconds=SUPERVISOR_TIMEOUT_SECONDS,
    )
    return summarize_child(result)


def main(
    argv: Sequence[str] | None = None,
    *,
    environment: Mapping[str, str] | None = None,
) -> int:
    """Без двох підтверджень ніколи не запускати дочірній Client."""
    parser = argparse.ArgumentParser(allow_abbrev=False)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--offline-preflight", action="store_true")
    modes.add_argument("--demo-network", action="store_true")
    parser.add_argument("--confirm", default=None)
    args = parser.parse_args(argv)
    env = os.environ if environment is None else environment

    if args.offline_preflight:
        if args.confirm is not None:
            parser.error("T116-33: offline-preflight не приймає --confirm")
        status = sdk_offline_preflight()
        print("T116-33 TEST_ONLY | first DEMO network attempt OFFLINE")
        print(f"demo_api_account_id={DEMO_API_ACCOUNT_ID}")
        print(f"actual_ctrader_sdk={status}")
        print("child_process=NOT_STARTED")
        print("sdk_client_constructor=NOT_CALLED")
        print("real_broker_requests=0")
        print("production_changes=0")
        print("network_launch_authorized=NO")
        print(RESULT_OFFLINE)
        return 0

    # Підтвердження та наявність credentials перевіряються до SDK і child.
    # Самі секрети не передаються у CLI та ніколи не виводяться.
    authorized_credentials(confirmation=args.confirm, environment=env)
    status = sdk_offline_preflight()
    if status != "VERIFIED_NO_EXTERNAL_NETWORK":
        raise RuntimeError("T116-33: реальний SDK недоступний")
    # T116-32 повторно перевіряє обидва дозволи всередині child.
    if env is not os.environ:
        raise PermissionError("T116-33: DEMO child потребує реальне environment")
    return run_supervised_network()


if __name__ == "__main__":
    raise SystemExit(main())
