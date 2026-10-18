# -*- coding: utf-8 -*-
"""
T111-35 v2 — Cryptography collect-binaries probe — TEST_ONLY.

Виправлення v2:
- результат frozen probe є головною ознакою працездатності;
- archive path не вважаємо наперед відомим;
- друкуємо всі фактичні ознаки до verdict;
- production не змінюється;
- broker requests = 0.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

TEST_ONLY = True
BROKER_REQUESTS = 0
BROKER_EXECUTION_ATTEMPTED = False
PRODUCTION_LOGIC_CHANGED = False

CANDIDATE_ARGUMENT = "--collect-binaries=cryptography"


def _run(
    command: list[str],
    cwd: Path,
    timeout: int = 240,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def main() -> int:
    scripts_dir = Path(sys.executable).resolve().parent
    archive_viewer = scripts_dir / "pyi-archive_viewer.exe"

    if not archive_viewer.is_file():
        raise AssertionError(f"archive viewer missing: {archive_viewer}")

    try:
        import cryptography.hazmat.bindings._rust as rust_binding
    except Exception as exc:
        raise AssertionError(f"source _rust import failed: {exc}") from exc

    source_rust_path = Path(rust_binding.__file__).resolve()
    source_rust_binding_present = source_rust_path.is_file()

    with tempfile.TemporaryDirectory(prefix="t111_35_") as temp_name:
        temp_dir = Path(temp_name)
        probe_py = temp_dir / "cryptography_probe.py"
        dist_dir = temp_dir / "dist"
        work_dir = temp_dir / "build"
        spec_dir = temp_dir / "spec"

        probe_py.write_text(
            "\n".join(
                (
                    "import pyAesCrypt",
                    "from cryptography.hazmat.bindings import _rust",
                    "print('FROZEN_CRYPTOGRAPHY_IMPORT_OK')",
                    "",
                )
            ),
            encoding="utf-8",
        )

        build_command = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--console",
            CANDIDATE_ARGUMENT,
            "--distpath",
            str(dist_dir),
            "--workpath",
            str(work_dir),
            "--specpath",
            str(spec_dir),
            str(probe_py),
        ]

        build_result = _run(build_command, temp_dir)
        frozen_exe = dist_dir / "cryptography_probe.exe"

        pyinstaller_probe_build_ok = (
            build_result.returncode == 0 and frozen_exe.is_file()
        )

        if pyinstaller_probe_build_ok:
            archive_result = _run(
                [str(archive_viewer), "-l", "-r", str(frozen_exe)],
                temp_dir,
                timeout=120,
            )
            archive_text = archive_result.stdout + "\n" + archive_result.stderr

            archive_viewer_returncode = archive_result.returncode
            archive_contains_rust_name = "_rust" in archive_text
            archive_contains_rust_pyd = (
                r"cryptography\hazmat\bindings\_rust.pyd" in archive_text
                or "cryptography/hazmat/bindings/_rust.pyd" in archive_text
            )

            frozen_result = _run([str(frozen_exe)], temp_dir, timeout=120)
            frozen_output = frozen_result.stdout + "\n" + frozen_result.stderr
            frozen_probe_returncode = frozen_result.returncode
            frozen_probe_import_ok = (
                frozen_probe_returncode == 0
                and "FROZEN_CRYPTOGRAPHY_IMPORT_OK" in frozen_output
            )
            frozen_probe_missing_rust = (
                "No module named 'cryptography.hazmat.bindings._rust'" in frozen_output
            )
        else:
            archive_viewer_returncode = -1
            archive_contains_rust_name = False
            archive_contains_rust_pyd = False
            frozen_probe_returncode = -1
            frozen_probe_import_ok = False
            frozen_probe_missing_rust = False

    if frozen_probe_import_ok:
        verdict = "COLLECT_BINARIES_CRYPTOGRAPHY_PROVEN"
    elif pyinstaller_probe_build_ok and frozen_probe_missing_rust:
        verdict = "COLLECT_BINARIES_CRYPTOGRAPHY_INSUFFICIENT"
    else:
        verdict = "COLLECT_BINARIES_CRYPTOGRAPHY_UNRESOLVED"

    print("T111-35 TEST_ONLY")
    print(f"verdict={verdict}")
    print(f"candidate_argument={CANDIDATE_ARGUMENT}")
    print(f"source_rust_binding_present={source_rust_binding_present}")
    print(f"pyinstaller_probe_build_ok={pyinstaller_probe_build_ok}")
    print(f"archive_viewer_returncode={archive_viewer_returncode}")
    print(f"archive_contains_rust_name={archive_contains_rust_name}")
    print(f"archive_contains_rust_pyd={archive_contains_rust_pyd}")
    print(f"frozen_probe_returncode={frozen_probe_returncode}")
    print(f"frozen_probe_import_ok={frozen_probe_import_ok}")
    print(f"frozen_probe_missing_rust={frozen_probe_missing_rust}")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"broker_execution_attempted={BROKER_EXECUTION_ATTEMPTED}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")

    if not source_rust_binding_present:
        return 2
    if not pyinstaller_probe_build_ok:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
