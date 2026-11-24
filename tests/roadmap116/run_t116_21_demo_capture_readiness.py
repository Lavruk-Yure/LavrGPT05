"""T116-21 TEST_ONLY — офлайн-перевірка запуску DEMO-телеметрії.

Не підключається до брокера, не запускає LGE та не викликає --live.
"""

from __future__ import annotations

import os
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
TELEMETRY_FILE = (
    ROOT / "tests" / "roadmap116" / "run_t116_19_ctrader_raw_spot_telemetry.py"
)


def test_t116_21_demo_capture_readiness() -> None:
    """Перевірити заборонені входи та межі дочірнього процесу без мережі."""
    source = TELEMETRY_FILE.read_text(encoding="utf-8")
    scope = runpy.run_path(str(TELEMETRY_FILE), run_name="t116_21_offline")
    checks: dict[str, bool] = {
        "exact_demo_account": (
            scope["AUTHORIZED_DEMO_API_ID"] == 46368962
            and '"DEMO"' in source
            and "нецільовий DEMO API ID" in source
        ),
        "bounded_capture": (
            scope["LIVE_QT_TIMEOUT_SECONDS"] == 60
            and scope["LIVE_PROCESS_TIMEOUT_SECONDS"] == 75
        ),
        "bounded_jsonl": (
            scope["MAX_LIVE_EVENTS"] == 3000
            and scope["MAX_LIVE_JSONL_BYTES"] == 2 * 1024 * 1024
        ),
        "trade_and_ib_guards_wired": all(
            token in source
            for token in (
                "install_ib_network_guard(",
                "isolate_ctrader_outbound_protobuf():",
                "ctrader_trade_methods=BLOCKED",
            )
        ),
        "config_guard_before_lge_import": (
            source.index(
                "with isolate_real_config_writes(ConfigManager, ROOT_CONF_PATH):"
            )
            < source.index("            import LGE")
        ),
        "disconnect_wraps_lge": (
            source.index("with ctrader_disconnect_guard():")
            < source.index("                    LGE.main()")
        ),
    }

    worker_key = scope["LIVE_WORKER_ENV"]
    blocked_env = dict(os.environ)
    blocked_env.pop(worker_key, None)
    blocked_env["PYTHONIOENCODING"] = "utf-8"
    blocked = subprocess.run(
        [sys.executable, str(TELEMETRY_FILE), "--live-worker"],
        cwd=ROOT,
        env=blocked_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )
    checks["unsupervised_worker_denied"] = (
        blocked.returncode != 0
        and "без supervisor заборонений" in blocked.stdout + blocked.stderr
    )
    if not checks["unsupervised_worker_denied"]:
        print(f"worker_exit_code={blocked.returncode}")
        print(f"worker_stdout_tail={blocked.stdout[-500:]!r}")
        print(f"worker_stderr_tail={blocked.stderr[-500:]!r}")

    calls: list[dict[str, object]] = []

    def fake_supervised_run(
        command: list[str],
        *,
        cwd: str,
        env: dict[str, str],
        timeout: int,
        check: bool,
    ) -> SimpleNamespace:
        calls.append(
            {
                "command": command,
                "cwd": cwd,
                "env": env,
                "timeout": timeout,
                "check": check,
            }
        )
        return SimpleNamespace(returncode=0)

    supervisor = scope["launch_live_supervised"]
    supervisor_result = supervisor(run_process=fake_supervised_run)
    assert len(calls) == 1
    call = calls[0]
    call_env = call["env"]
    assert isinstance(call_env, dict)
    checks["supervisor_contract"] = (
        supervisor_result == 0
        and call["command"] == [sys.executable, str(TELEMETRY_FILE), "--live-worker"]
        and call["cwd"] == str(ROOT)
        and call["timeout"] == 75
        and call["check"] is False
        and call_env.get(worker_key) == "1"
    )

    def fake_hung_process(command: list[str], **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd=command, timeout=75)

    checks["supervisor_timeout"] = supervisor(run_process=fake_hung_process) == 124

    # Офлайн-аудит не підтверджує повну ізоляцію LGE від усіх мережевих API.
    assert "import LGE" in source and "LGE.main()" in source
    failures = [name for name, passed in checks.items() if not passed]
    for name, passed in checks.items():
        print(f"case={name} result={'OK' if passed else 'FAIL'}")
    print(f"readiness_cases={len(checks)}")
    print(f"readiness_mismatches={len(failures)}")
    print("actual_ctrader_sdk=NOT_STARTED_IN_THIS_TEST")
    print("full_lge_bootstrap=USED_BY_CURRENT_LIVE_SCRIPT")
    print("independent_process_network_isolation=NOT_PROVEN")
    print("real_quote_events=NOT_CAPTURED")
    print("real_broker_requests=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    print("live_launch_authorized=NO")
    if failures:
        print("T116-21=RED_OFFLINE_CAPTURE_READINESS")
        raise AssertionError("T116-21: порушення: " + ", ".join(failures))
    print("T116-21=GREEN_OFFLINE_CAPTURE_READINESS")
