# run_runtime_events_check.py
"""
RoadMap67 diagnostic script для перевірки SQLite runtime_events.

Перевіряє останні runtime events у data/demo.db після запуску:
    tests/runtime_manual/run_runtime_ctrader_connection.py

Без:
- Qt;
- broker API;
- UI;
- зміни БД.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def _format_payload(payload_json: str) -> str:
    """
    Повернути коротке читабельне представлення JSON payload.
    """

    try:
        payload = json.loads(payload_json or "{}")
    except json.JSONDecodeError:
        return payload_json

    if not payload:
        return "{}"

    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
    )


def main() -> int:
    """
    Показати останні runtime events із data/demo.db.
    """

    db_path = PROJECT_ROOT / "data" / "demo.db"
    if not db_path.exists():
        logger.error("DB file not found: %s", db_path)
        return 1

    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT
                id,
                event_type,
                message,
                payload_json,
                created_utc
            FROM runtime_events
            ORDER BY id DESC
            LIMIT 20
            """,
        ).fetchall()
    finally:
        connection.close()

    if not rows:
        logger.warning("runtime_events table is empty: %s", db_path)
        return 1

    print(f"DB: {db_path}")
    print("Last runtime_events:")

    for row in reversed(rows):
        event_id, event_type, message, payload_json, created_utc = row
        print(
            f"{event_id:>5} | {created_utc} | {event_type:<24} | "
            f"{message} | {_format_payload(payload_json)}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
