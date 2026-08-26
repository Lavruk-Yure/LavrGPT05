"""Canonical cTrader reconnect ownership regression check."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _read(relative_path: str) -> str:
    """Read one production source file for the static contract check."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def main() -> int:
    """Verify reconnect ownership stays in SessionManager/RuntimeService."""
    adapter_source = _read("engine/ctrader_adapter.py")
    manager_source = _read("engine/ctrader_session_manager.py")
    service_source = _read("engine/services/ctrader_runtime_service.py")

    checks = {
        "adapter_legacy_reconnect_removed": (
            "def reconnect(self) -> bool:" not in adapter_source
        ),
        "adapter_blind_reconnect_sleep_removed": (
            "time.sleep(1.0)" not in adapter_source
        ),
        "history_request_throttle_preserved": (
            "time.sleep(CTRADER_HISTORY_REQUEST_DELAY_SECONDS)" in adapter_source
        ),
        "session_manager_owns_reconnect": (
            "def reconnect(self) -> Optional[CTraderAdapter]:" in manager_source
            and "return self._connect(account_mode=account_mode)" in manager_source
        ),
        "runtime_service_uses_session_manager": (
            "adapter = self._session_manager.reconnect()" in service_source
        ),
    }

    print("cTrader adapter reconnect contract result")
    for name, value in checks.items():
        print(f"  {name}={value}")

    if not all(checks.values()):
        print("CTRADER_ADAPTER_RECONNECT_CONTRACT_CHECK=FAILED")
        return 1

    print("CTRADER_ADAPTER_RECONNECT_CONTRACT_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
