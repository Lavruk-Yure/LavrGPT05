# run_ib_virtual_leg_group_snapshot_check.py
"""
Console launcher for the RoadMap90 IB position group snapshot check.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT_TEXT = str(PROJECT_ROOT)

if PROJECT_ROOT_TEXT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_TEXT)


if __name__ == "__main__":
    runpy.run_module(
        "tests.runtime_ib.ib_virtual_leg_group_snapshot_check_impl",
        run_name="__main__",
    )
