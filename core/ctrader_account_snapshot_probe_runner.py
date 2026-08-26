# ctrader_account_snapshot_probe_runner.py
"""
Subprocess runner для одноразового отримання snapshot cTrader-рахунку.

Призначення:
- прийняти JSON із stdin;
- запустити CTraderAccountSnapshotProbe;
- повернути тільки JSON у stdout;
- усі службові повідомлення писати у stderr;
- ізолювати Twisted reactor від GUI.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import traceback
from typing import Any

from core.ctrader_account_snapshot_probe import CTraderAccountSnapshotProbe
from core.token_manager import refresh_if_needed


def _print_error(message: str) -> None:
    """
    Пише службову помилку у stderr.
    """
    print(message, file=sys.stderr)


def _read_input() -> dict[str, Any]:
    """
    Читає JSON-параметри зі stdin.
    """
    raw_text = sys.stdin.read().strip()
    if not raw_text:
        raise ValueError("Input JSON is empty.")

    data = json.loads(raw_text)
    if not isinstance(data, dict):
        raise ValueError("Input JSON must be an object.")

    return data


def main() -> int:
    """
    Точка входу subprocess runner.
    """
    try:
        data = _read_input()

        host = str(data.get("host", "")).strip()
        port = int(data.get("port", 0))
        client_id = str(data.get("client_id", "")).strip()
        client_secret = str(data.get("client_secret", "")).strip()
        account_id = str(data.get("account_id", "")).strip()

        with contextlib.redirect_stdout(io.StringIO()):
            refresh_if_needed()

        probe = CTraderAccountSnapshotProbe(
            host=host,
            port=port,
            client_id=client_id,
            client_secret=client_secret,
            account_id=account_id,
        )

        snapshot = probe.run()

        result = {
            "ok": True,
            "snapshot": snapshot,
            "error": "",
            "traceback": "",
        }

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    except Exception as exc:
        _print_error(f"cTrader snapshot probe error: {exc}")

        result = {
            "ok": False,
            "snapshot": {},
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
