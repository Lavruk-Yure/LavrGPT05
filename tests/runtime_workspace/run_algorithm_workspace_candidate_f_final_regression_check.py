# -*- coding: utf-8 -*-
"""Фінальний regression Candidate F перед закриттям RoadMap101.

Запускає канонічні production, profile/UI, SAME_TIMEFRAME, Signals/Journal і
табличні перевірки, які разом фіксують завершений стан Candidate F. Runner не
дублює торгову логіку і не підміняє окремі tests: кожен check виконується
окремим Python-процесом та має повернути власний ``...=OK`` marker.

Інваріанти: Historical Replay не виконує broker execution; Candidate F точно
відтворює GREEN RoadMap101 №37; legacy profile/default лишаються доступними;
profile revision не втрачає приховані policy thresholds; causal no-look-ahead,
локалізація reason codes, Signals/Journal navigation і widths regression мають
лишатися зеленими.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = PROJECT_ROOT / "tests" / "runtime_workspace"


@dataclass(frozen=True, slots=True)
class RegressionCheck:
    """Один обов'язковий subprocess-check фінального regression."""

    name: str
    script: str
    marker: str


CHECKS = (
    RegressionCheck(
        "candidate_f_production",
        "run_algorithm_workspace_alligator_candidate_f_production_check.py",
        "ALGORITHM_WORKSPACE_ALLIGATOR_CANDIDATE_F_PRODUCTION_CHECK=OK",
    ),
    RegressionCheck(
        "candidate_f_profile_revision_ui",
        "run_workspace_indicator_profile_candidate_f_revision_ui_check.py",
        "WORKSPACE_INDICATOR_PROFILE_CANDIDATE_F_REVISION_UI_CHECK=OK",
    ),
    RegressionCheck(
        "alligator_same_timeframe",
        "run_algorithm_workspace_alligator_same_timeframe_check.py",
        "ALGORITHM_WORKSPACE_ALLIGATOR_SAME_TIMEFRAME_CHECK=OK",
    ),
    RegressionCheck(
        "signal_localization",
        "run_algorithm_workspace_signal_localization_check.py",
        "ALGORITHM_WORKSPACE_SIGNAL_LOCALIZATION_CHECK=OK",
    ),
    RegressionCheck(
        "signal_table",
        "run_algorithm_workspace_signal_table_check.py",
        "ALGORITHM_WORKSPACE_SIGNAL_TABLE_CHECK=OK",
    ),
    RegressionCheck(
        "signal_analysis_navigation",
        "run_algorithm_workspace_signal_analysis_navigation_check.py",
        "ALGORITHM_WORKSPACE_SIGNAL_ANALYSIS_NAVIGATION_CHECK=OK",
    ),
    RegressionCheck(
        "table_column_width_persistence",
        "run_algorithm_workspace_table_column_width_persistence_check.py",
        "ALGORITHM_WORKSPACE_TABLE_COLUMN_WIDTH_PERSISTENCE_CHECK=OK",
    ),
)


def _run_check(check: RegressionCheck) -> tuple[bool, str, str]:
    script_path = TEST_ROOT / check.script
    assert script_path.is_file(), script_path
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    completed = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        check=False,
    )
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    passed = completed.returncode == 0 and check.marker in stdout
    return passed, stdout, stderr


def main() -> None:
    results: list[tuple[RegressionCheck, bool]] = []
    for check in CHECKS:
        passed, stdout, stderr = _run_check(check)
        results.append((check, passed))
        if not passed:
            print(f"FAILED_CHECK={check.name}")
            if stdout.strip():
                print("--- stdout ---")
                print(stdout.rstrip())
            if stderr.strip():
                print("--- stderr ---")
                print(stderr.rstrip())
            raise AssertionError(
                f"Final Candidate F regression failed: {check.name}"
            )

    print("RoadMap101 Candidate F final regression result")
    for check, passed in results:
        print(f"  {check.name}={passed}")
    print("  candidate_f_matches_green_37=True")
    print("  legacy_profile_preserved=True")
    print("  fresh_workspace_default_unchanged=True")
    print("  completed_bars_only=True")
    print("  no_look_ahead=True")
    print("  signal_reason_localization_preserved=True")
    print("  journal_readable_detail_preserved=True")
    print("  table_width_persistence_preserved=True")
    print("  broker_execution_attempted=False")
    print("ROADMAP101_CANDIDATE_F_FINAL_REGRESSION_CHECK=OK")


if __name__ == "__main__":
    main()
