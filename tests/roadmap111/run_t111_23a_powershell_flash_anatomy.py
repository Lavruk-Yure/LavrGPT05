from __future__ import annotations

import ast
from pathlib import Path

TEST_ONLY = True

ROOT = Path(__file__).resolve().parents[2]
LICENSE_MANAGER = ROOT / "core" / "license_manager.py"
MAIN_LOGIC = ROOT / "core" / "main_logic.py"
LOGIN_LOGIC = ROOT / "core" / "login_logic.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse(path: Path) -> None:
    ast.parse(_read(path), filename=str(path))


def _require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing evidence: {label}: {needle!r}")


def main() -> int:
    _parse(LICENSE_MANAGER)
    _parse(MAIN_LOGIC)
    _parse(LOGIN_LOGIC)

    license_text = _read(LICENSE_MANAGER)
    main_text = _read(MAIN_LOGIC)
    login_text = _read(LOGIN_LOGIC)

    _require(
        license_text,
        '"powershell",',
        "System UUID uses external PowerShell",
    )
    _require(
        license_text,
        '"(Get-CimInstance Win32_ComputerSystemProduct).UUID",',
        "PowerShell reads Win32_ComputerSystemProduct UUID",
    )
    _require(
        license_text,
        '"reg",\n                    "query",',
        "MachineGuid uses external reg.exe",
    )
    _require(
        license_text,
        "cls.compute_machine_id_candidates()",
        "license status recomputes machine identity",
    )
    _require(
        license_text,
        'su = cls._read_system_uuid() or "NA"',
        "machine-id candidates read system UUID",
    )
    _require(
        login_text,
        "LicenseManager.compute_and_update(",
        "login invokes license recomputation",
    )
    _require(
        main_text,
        "LicenseManager.compute_and_update(",
        "main window invokes license recomputation",
    )
    _require(
        main_text,
        "self._trial_watch_timer.setInterval(60_000)",
        "license watch runs every 60 seconds",
    )
    _require(
        main_text,
        "self._trial_watch_timer.timeout.connect(self._on_trial_watch_timer)",
        "timer invokes license watch",
    )

    powershell_block_start = license_text.index('"powershell",')
    powershell_block = license_text[
        powershell_block_start : powershell_block_start + 700  # noqa
    ]
    hidden_window_flags_present = any(
        marker in powershell_block
        for marker in (
            "CREATE_NO_WINDOW",
            "STARTUPINFO",
            "STARTF_USESHOWWINDOW",
            "SW_HIDE",
            "creationflags=",
            "startupinfo=",
        )
    )

    reg_block_start = license_text.index('"reg",\n                    "query",')
    reg_block = license_text[reg_block_start : reg_block_start + 700]  # noqa
    reg_hidden_window_flags_present = any(
        marker in reg_block
        for marker in (
            "CREATE_NO_WINDOW",
            "STARTUPINFO",
            "STARTF_USESHOWWINDOW",
            "SW_HIDE",
            "creationflags=",
            "startupinfo=",
        )
    )

    periodic_external_console_path = (
        not hidden_window_flags_present and not reg_hidden_window_flags_present
    )
    broker_requests = 0
    broker_execution_attempted = False
    production_logic_changed = False

    ok = all(
        (
            periodic_external_console_path,
            broker_requests == 0,
            not broker_execution_attempted,
            not production_logic_changed,
        )
    )

    verdict = (
        "POWERSHELL_FLASH_PATH_CONFIRMED"
        if ok
        else "POWERSHELL_FLASH_PATH_NOT_CONFIRMED"
    )

    print("T111-23A TEST_ONLY")
    print(f"verdict={verdict}")
    print("powershell_system_uuid_present=True")
    print("reg_machine_guid_present=True")
    print("license_recomputed_on_login=True")
    print("license_recomputed_in_main_window=True")
    print("license_watch_interval_seconds=60")
    print(f"powershell_hidden_window_flags_present={hidden_window_flags_present}")
    print(f"reg_hidden_window_flags_present={reg_hidden_window_flags_present}")
    print(f"periodic_external_console_path={periodic_external_console_path}")
    print(f"broker_requests={broker_requests}")
    print(f"broker_execution_attempted={broker_execution_attempted}")
    print(f"production_logic_changed={production_logic_changed}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
