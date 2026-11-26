"""T116-42 TEST_ONLY — supervised AccountList, лише синтетична офлайн-сесія.

Поєднує T116-36/37 (ізольоване середовище й watchdog), T116-40
(scoped outbound guard) і T116-41 (callback + перевірка DEMO-ідентичності).
Навіть із доданими мережевими прапорцями жоден режим не запускає SDK Client.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_26_process_watchdog import (
    SUPERVISOR_TIMEOUT_SECONDS,
    SupervisedResult,
)
from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied
from tests.roadmap116.t116_32_demo_network_readonly_discovery import (
    CREDENTIAL_VARIABLES,
    NETWORK_APPROVAL_VARIABLE,
)
from tests.roadmap116.t116_36_lge_credentials_launcher_bridge import (
    BridgedCredentials,
    make_launcher_environment,
)
from tests.roadmap116.t116_37_lge_supervised_offline_bridge import (
    assert_offline_environment,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHILD_MODULE = "tests.roadmap116.t116_42_supervised_account_list_offline"
CHILD_MARKER = "T116-42=GREEN_SYNTHETIC_ACCOUNT_LIST_CHILD"
READY_MARKER = "T116-42=GREEN_OFFLINE_SUPERVISED_ACCOUNT_LIST_PREFLIGHT"
SYNTHETIC_CREDENTIALS = BridgedCredentials(
    client_id="T11642_SYNTHETIC_CLIENT_ID",
    client_secret="T11642_SYNTHETIC_CLIENT_SECRET",
    access_token="T11642_SYNTHETIC_ACCESS_TOKEN",
)
CHILD_LINES = (
    f"demo_api_account_id={DEMO_API_ACCOUNT_ID}",
    "account_identity=SYNTHETIC_DEMO_ONLY",
    "request_order=APPLICATION_AUTH_ACCOUNT_LIST",
    "credentials_values=NOT_LOGGED",
    "real_broker_requests=0",
    "network_launch_authorized=NO",
    CHILD_MARKER,
)
SYSTEM_ENV_KEYS = (
    "SystemRoot",
    "WINDIR",
    "PATH",
    "PATHEXT",
    "TEMP",
    "TMP",
    "VIRTUAL_ENV",
    "PYTHONIOENCODING",
)


def prepare_synthetic_child_environment(
    source: Mapping[str, str],
) -> dict[str, str]:
    """У child передавати лише системні змінні та синтетичні credentials."""
    if NETWORK_APPROVAL_VARIABLE in source:
        raise PermissionError("T116-42: approval змінна заборонена")
    safe_env = {
        key: value
        for key in SYSTEM_ENV_KEYS
        if isinstance((value := source.get(key)), str) and value
    }
    if os.name == "nt" and not safe_env.get("SystemRoot"):
        raise RuntimeError("T116-42: відсутній SystemRoot для Windows")
    child_env = make_launcher_environment(
        SYNTHETIC_CREDENTIALS,
        environment=safe_env,
    )
    assert_offline_environment(child_env)
    return child_env


def child_result_valid(result: SupervisedResult) -> bool:
    """Приймати лише точний безпечний звіт штатно завершеного child."""
    return (
        not result.hard_timeout
        and result.reaped
        and result.returncode == 0
        and not result.stderr
        and result.stdout.splitlines() == list(CHILD_LINES)
    )


def run_offline_child(
    environment: Mapping[str, str],
    *,
    popen: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
) -> SupervisedResult:
    """Запустити один офлайн-child; timeout і reap, без raw-log у консолі."""
    assert_offline_environment(environment)
    if any(
        environment.get(name) != value
        for name, value in zip(
            CREDENTIAL_VARIABLES,
            (
                SYNTHETIC_CREDENTIALS.client_id,
                SYNTHETIC_CREDENTIALS.client_secret,
                SYNTHETIC_CREDENTIALS.access_token,
            ),
            strict=True,
        )
    ):
        raise PermissionError("T116-42: дозволені лише synthetic credentials")
    process = popen(
        [sys.executable, "-m", CHILD_MODULE, "--offline-child"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        cwd=str(PROJECT_ROOT),
        env=dict(environment),
    )
    try:
        try:
            stdout, stderr = process.communicate(timeout=SUPERVISOR_TIMEOUT_SECONDS)
            return SupervisedResult(
                returncode=process.wait(),
                hard_timeout=False,
                reaped=process.poll() is not None,
                stdout=stdout,
                stderr=stderr,
            )
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5.0)
            return SupervisedResult(
                returncode=124,
                hard_timeout=True,
                reaped=process.poll() is not None,
                stdout=stdout,
                stderr=stderr,
            )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5.0)


def run_synthetic_account_list() -> None:
    """У повністю заблокованій мережі відтворити два SDK request кадри."""
    from tests.roadmap116 import t116_29_sdk_outbound_guard as outbound
    from tests.roadmap116.run_t116_29_sdk_outbound_transport_guard import (
        FakeClient,
        FakeFrameSender,
        FakeTcpProtocol,
    )
    from tests.roadmap116.run_t116_41_demo_account_list_session_preflight import (
        RESPONSE_IDS,
        account_list,
        make_envelope,
        synthetic_sdk,
    )
    from tests.roadmap116.t116_40_demo_account_list_scoped_policy import (
        guarded_scoped_account_list,
    )
    from tests.roadmap116.t116_41_demo_account_list_session import (
        RESPONSE_NAMES,
        OfflineAccountListSession,
    )

    sdk_messages, common_messages = synthetic_sdk()
    protocol = FakeTcpProtocol()
    protocol.envelope_class = getattr(common_messages, "ProtoMessage")
    client = FakeClient(protocol)
    shutdowns: list[str] = []
    baseline = outbound.PERMITTED_REQUEST_NAMES

    with external_tcp_denied(), guarded_scoped_account_list(
        client_type=FakeClient,
        tcp_protocol_type=FakeTcpProtocol,
        frame_sender_type=FakeFrameSender,
        request_messages=sdk_messages,
        common_messages=common_messages,
        expected_token=SYNTHETIC_CREDENTIALS.access_token,
    ):
        session = OfflineAccountListSession(
            sdk_messages=sdk_messages,
            envelope_type=getattr(common_messages, "ProtoMessage"),
            response_payload_types=RESPONSE_IDS,
            sender=client.send,
            disconnect=lambda: shutdowns.append("CLOSED"),
            clock=lambda: 100.0,
        )
        session.on_connected(
            client_id=SYNTHETIC_CREDENTIALS.client_id,
            client_secret=SYNTHETIC_CREDENTIALS.client_secret,
            access_token=SYNTHETIC_CREDENTIALS.access_token,
        )
        response = getattr(sdk_messages, RESPONSE_NAMES[0])()
        if session.on_envelope(make_envelope(sdk_messages, response)) is not None:
            raise PermissionError("T116-42: ApplicationAuth завершив сесію")
        response = account_list(sdk_messages)
        matched = session.on_envelope(make_envelope(sdk_messages, response))
        if matched is None or not matched.matched:
            raise PermissionError("T116-42: DEMO рахунок не підтверджений")
        if session.phase != "CLOSED" or shutdowns != ["CLOSED"]:
            raise PermissionError("T116-42: дочірня сесія не закрита")
        expected_names = (
            "ProtoOAApplicationAuthReq",
            "ProtoOAGetAccountListByAccessTokenReq",
        )
        if len(protocol.transport.writes) != len(expected_names):
            raise PermissionError("T116-42: неправильна кількість кадрів")
        for wire, expected_name in zip(
            protocol.transport.writes, expected_names, strict=True
        ):
            if len(wire) - 4 != int.from_bytes(wire[:4], "big"):
                raise PermissionError("T116-42: невірна довжина кадру")
            envelope = getattr(common_messages, "ProtoMessage")()
            envelope.ParseFromString(wire[4:])
            expected_type = getattr(sdk_messages, expected_name)
            if envelope.payloadType != expected_type().payloadType:
                raise PermissionError("T116-42: порушено порядок запитів")
    if outbound.PERMITTED_REQUEST_NAMES != baseline:
        raise PermissionError("T116-42: baseline outbound guard не відновлено")


def offline_child() -> int:
    """Відхилити будь-які чужі credentials, прапорці й реальні запити."""
    expected = (
        SYNTHETIC_CREDENTIALS.client_id,
        SYNTHETIC_CREDENTIALS.client_secret,
        SYNTHETIC_CREDENTIALS.access_token,
    )
    if NETWORK_APPROVAL_VARIABLE in os.environ or any(
        os.environ.get(name) != value
        for name, value in zip(CREDENTIAL_VARIABLES, expected, strict=True)
    ):
        print("T116-42=OFFLINE_CHILD_REJECTED")
        return 2
    try:
        with external_tcp_denied():
            run_synthetic_account_list()
    # noinspection PyBroadException
    except Exception:  # noqa
        print("T116-42=OFFLINE_CHILD_FAILED")
        return 2
    print("\n".join(CHILD_LINES))
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    environment: Mapping[str, str] | None = None,
    runner: Callable[[Mapping[str, str]], SupervisedResult] = run_offline_child,
) -> int:
    """Публічний CLI має тільки офлайн-режими, DEMO-network не існує."""
    parser = argparse.ArgumentParser(allow_abbrev=False)
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--offline-preflight", action="store_true")
    options.add_argument("--offline-child", action="store_true")
    args = parser.parse_args(argv)
    if args.offline_child:
        return offline_child()

    source = os.environ if environment is None else environment
    try:
        child_env = prepare_synthetic_child_environment(source)
        result = runner(child_env)
        passed = child_result_valid(result)
    # noinspection PyBroadException
    except Exception:  # noqa
        passed = False
    print("T116-42 TEST_ONLY | supervised AccountList OFFLINE")
    print(f"demo_api_account_id={DEMO_API_ACCOUNT_ID}")
    print("account_identity=SYNTHETIC_DEMO_ONLY")
    print(
        "child_process="
        + ("SYNTHETIC_STARTED_AND_REAPED" if passed else "FAILED_OR_NOT_STARTED")
    )
    print(f"supervisor_timeout_seconds={int(SUPERVISOR_TIMEOUT_SECONDS)}")
    print("credentials_values=NOT_LOGGED")
    print("sdk_client_constructor=NOT_CALLED")
    print("real_identity_pair=NOT_QUERIED_NO_NETWORK")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print(READY_MARKER if passed else "T116-42=NOT_READY_OFFLINE")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
