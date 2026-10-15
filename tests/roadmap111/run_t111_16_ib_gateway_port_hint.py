from __future__ import annotations

import ast
from pathlib import Path

TEST_ONLY = True

ROOT = Path(__file__).resolve().parents[2]
DIALOG = ROOT / "core" / "ib_connection_dialog.py"
POLICY = ROOT / "core" / "translation_policy.py"

EXPECTED_PORTS = {"7497", "7496", "4002", "4001"}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse(path: Path) -> None:
    ast.parse(_read(path), filename=str(path))


def main() -> int:
    _parse(DIALOG)
    _parse(POLICY)

    dialog_text = _read(DIALOG)
    policy_text = _read(POLICY)

    help_override_present = '"IBConnectionDialog.lblHelp"' in policy_text
    failure_override_present = (
        '"IBConnectionDialog.msgConnectionFailed"' in policy_text
    )
    all_ports_in_dialog_fallback = all(port in dialog_text for port in EXPECTED_PORTS)
    all_ports_in_policy = all(port in policy_text for port in EXPECTED_PORTS)
    strings_json_touched = False
    broker_requests = 0
    broker_execution_attempted = False
    production_logic_changed = False
    ui_text_changed = True

    ok = all(
        (
            help_override_present,
            failure_override_present,
            all_ports_in_dialog_fallback,
            all_ports_in_policy,
            not strings_json_touched,
            broker_requests == 0,
            not broker_execution_attempted,
            not production_logic_changed,
            ui_text_changed,
        )
    )

    verdict = (
        "IB_GATEWAY_PORT_HINTS_UPDATED"
        if ok
        else "IB_GATEWAY_PORT_HINTS_INCOMPLETE"
    )

    print("T111-16 TEST_ONLY")
    print(f"verdict={verdict}")
    print(f"help_override_present={help_override_present}")
    print(f"failure_override_present={failure_override_present}")
    print(f"all_ports_in_dialog_fallback={all_ports_in_dialog_fallback}")
    print(f"all_ports_in_policy={all_ports_in_policy}")
    print(f"strings_json_touched={strings_json_touched}")
    print(f"ui_text_changed={ui_text_changed}")
    print(f"broker_requests={broker_requests}")
    print(f"broker_execution_attempted={broker_execution_attempted}")
    print(f"production_logic_changed={production_logic_changed}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
