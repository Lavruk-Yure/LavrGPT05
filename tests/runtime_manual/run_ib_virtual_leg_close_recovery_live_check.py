"""Console launcher for confirmed IB virtual-leg Close recovery."""

from __future__ import annotations

import sys
from pathlib import Path


def _add_project_root_to_sys_path() -> None:
    project_root_text = str(Path(__file__).resolve().parents[2])

    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)


def main() -> int:
    _add_project_root_to_sys_path()

    from tests.runtime_manual.ib_virtual_leg_close_recovery_live_check_impl import (
        main as run_check,
    )

    return run_check()


if __name__ == "__main__":
    raise SystemExit(main())
