# run_runtime_db_bootstrap.py
"""
Ручний тест bootstrap runtime SQLite DB.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.db.runtime_db import (
    connect_runtime_db,
    get_runtime_database_path,
    get_schema_version,
)

DB_LIST = [
    get_runtime_database_path("DEMO"),
    get_runtime_database_path("LIVE"),
    get_runtime_database_path("TEST"),
]


def main() -> None:
    """
    Точка входу manual runtime DB bootstrap test.
    """

    for db_path in DB_LIST:

        print("\n====================")
        print(f"DB PATH: {db_path}")

        connection = connect_runtime_db(
            db_path=db_path,
        )

        print("SQLite connection: OK")

        schema_version = get_schema_version(connection)

        print(f"Schema version: {schema_version}")

        cursor = connection.execute(
            "SELECT name FROM sqlite_master " "WHERE type='table' " "ORDER BY name;"
        )

        tables = [row[0] for row in cursor.fetchall()]

        print("Tables:")

        for table_name in tables:
            print(f"  - {table_name}")

        connection.close()

        print("Connection closed.")


if __name__ == "__main__":
    main()
