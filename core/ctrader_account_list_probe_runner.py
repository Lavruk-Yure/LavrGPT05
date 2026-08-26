# ctrader_account_list_probe_runner.py
"""
Subprocess runner для одноразового отримання списку cTrader-рахунків.

Призначення:
- запускатися окремим Python-процесом;
- ізолювати Twisted reactor від PySide6 GUI event loop;
- приймати параметри через stdin JSON;
- повертати результат через stdout JSON.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import traceback

from core.ctrader_account_list_probe import CTraderAccountListProbe
from core.token_manager import refresh_if_needed


def _read_input() -> dict:
    """
    Читає JSON-параметри зі stdin.
    """
    raw_text = sys.stdin.read().strip()

    if not raw_text:
        raise RuntimeError("Порожній stdin для cTrader probe runner.")

    data = json.loads(raw_text)

    if not isinstance(data, dict):
        raise RuntimeError("stdin JSON має бути object/dict.")

    return data


def _write_json(data: dict) -> None:
    """
    Пише JSON у stdout.
    """
    sys.stdout.write(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        )
    )
    sys.stdout.flush()


def main() -> int:
    """
    Entry point runner.
    """
    try:
        data = _read_input()

        with contextlib.redirect_stdout(io.StringIO()):
            refresh_if_needed()

        probe = CTraderAccountListProbe(
            host=str(data.get("host", "")).strip(),
            port=int(data.get("port", 5035)),
            client_id=str(data.get("client_id", "")).strip(),
            client_secret=str(data.get("client_secret", "")).strip(),
        )

        accounts = probe.run()

        _write_json(
            {
                "ok": True,
                "accounts": accounts,
                "error": "",
            }
        )

        return 0

    except Exception as exc:
        _write_json(
            {
                "ok": False,
                "accounts": [],
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
