"""T116-34 TEST_ONLY — перевірка готовності до DEMO мережі без запуску.

Не передає credentials, не створює SDK Client, не запускає child або WSP.
Справжній T116-33 мережевий режим вимагає окремого рішення оператора.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_30_offline_symbol_preparation import (
    external_tcp_denied,
)
from tests.roadmap116.t116_32_demo_network_readonly_discovery import (
    CREDENTIAL_VARIABLES,
    NETWORK_APPROVAL_VARIABLE,
)
from tests.roadmap116.t116_33_supervised_demo_readonly_discovery import (
    sdk_offline_preflight,
)

SDK_READY = "VERIFIED_NO_EXTERNAL_NETWORK"
SDK_ABSENT = "NOT_INSTALLED_LOCAL_RUNNER"


@dataclass(frozen=True, slots=True)
class Readiness:
    """Лише агреговані безпечні ознаки, жодних credentials."""

    sdk_status: str
    credentials_count: int
    approval_env_present: bool

    @property
    def ready_for_approval(self) -> bool:
        """Готовність до окремого рішення, а не дозвіл на мережу."""
        return (
            self.sdk_status == SDK_READY
            and self.credentials_count == len(CREDENTIAL_VARIABLES)
            and not self.approval_env_present
        )


def inspect_readiness(
    *,
    environment: Mapping[str, str],
    check_sdk: Callable[[], str] = sdk_offline_preflight,
) -> Readiness:
    """Оглянути SDK у TCP-забороні та лише наявність секретних полів."""
    with external_tcp_denied():
        try:
            result = check_sdk()
        except Exception:  # noqa
            result = "SDK_PREFLIGHT_FAILED"
    sdk_status = result if result in {SDK_READY, SDK_ABSENT} else "SDK_PREFLIGHT_FAILED"
    count = sum(
        bool(environment.get(name, "").strip()) for name in CREDENTIAL_VARIABLES
    )
    return Readiness(
        sdk_status=sdk_status,
        credentials_count=count,
        approval_env_present=NETWORK_APPROVAL_VARIABLE in environment,
    )


def format_report(readiness: Readiness) -> str:
    """Сформувати звіт без доступу до значень credentials."""
    verdict = (
        "READY_FOR_SEPARATE_APPROVAL"
        if readiness.ready_for_approval
        else "NOT_READY_OFFLINE"
    )
    approval = (
        "PRESENT_CLEAR_BEFORE_NEXT_STEP" if readiness.approval_env_present else "UNSET"
    )
    return "\n".join(
        (
            "T116-34 TEST_ONLY | local DEMO connection readiness NO NETWORK",
            f"demo_api_account_id={DEMO_API_ACCOUNT_ID}",
            f"sdk_offline_preflight={readiness.sdk_status}",
            f"credential_fields_present={readiness.credentials_count}/3",
            f"network_approval_env={approval}",
            "orders_off=NOT_VERIFIED_OPERATOR_REQUIRED",
            "wsp_stopped=NOT_VERIFIED_OPERATOR_REQUIRED",
            "sdk_client_constructor=NOT_CALLED",
            "external_tcp=BLOCKED",
            "real_broker_requests=0",
            "production_changes=0",
            "network_launch_authorized=NO",
            f"T116-34={verdict}",
        )
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    environment: Mapping[str, str] | None = None,
    check_sdk: Callable[[], str] = sdk_offline_preflight,
) -> int:
    """Єдина команда --check-machine; інших режимів немає."""
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--check-machine", action="store_true", required=True)
    parser.parse_args(argv)
    env = os.environ if environment is None else environment
    readiness = inspect_readiness(environment=env, check_sdk=check_sdk)
    print(format_report(readiness))
    return 0 if readiness.ready_for_approval else 2


if __name__ == "__main__":
    raise SystemExit(main())
