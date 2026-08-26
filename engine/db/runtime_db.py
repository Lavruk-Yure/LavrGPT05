# runtime_db.py
"""
Канонічний SQLite bootstrap для runtime ATS LGE.

Поточний етап:
- SQLite connect;
- WAL;
- PRAGMA;
- schema version;
- auto-create runtime tables.

Без:
- Qt
- broker API
- UI
"""

import sqlite3
from pathlib import Path

from core.app_paths import BASE_DIR

SCHEMA_VERSION = 8


RUNTIME_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    runtime_state TEXT NOT NULL,
    broker TEXT NOT NULL,
    account_mode TEXT NOT NULL,
    execution_mode TEXT NOT NULL,
    created_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS broker_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    broker TEXT NOT NULL,
    account_id TEXT NOT NULL,
    account_mode TEXT NOT NULL,
    created_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings_runtime (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setting_key TEXT NOT NULL UNIQUE,
    setting_value TEXT NOT NULL,
    updated_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_uid TEXT NOT NULL UNIQUE,
    broker TEXT NOT NULL,
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    volume REAL NOT NULL,
    created_utc TEXT NOT NULL,
    source TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS order_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_plan_uid TEXT NOT NULL UNIQUE,
    trade_uid TEXT NOT NULL,
    order_type TEXT NOT NULL,
    side TEXT NOT NULL,
    volume REAL NOT NULL,
    created_utc TEXT NOT NULL,
    source TEXT NOT NULL,
    FOREIGN KEY (trade_uid) REFERENCES trades (trade_uid)
);

CREATE TABLE IF NOT EXISTS broker_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    broker_order_uid TEXT NOT NULL UNIQUE,
    trade_uid TEXT NOT NULL,
    order_plan_uid TEXT NOT NULL,
    broker TEXT NOT NULL,
    broker_order_id TEXT,
    execution_status TEXT NOT NULL,
    broker_timestamp TEXT,
    created_utc TEXT NOT NULL,
    source TEXT NOT NULL,
    broker_comment TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (trade_uid) REFERENCES trades (trade_uid),
    FOREIGN KEY (order_plan_uid) REFERENCES order_plans (order_plan_uid)
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_uid TEXT NOT NULL UNIQUE,
    trade_uid TEXT NOT NULL,
    broker_order_uid TEXT NOT NULL,
    broker TEXT NOT NULL,
    broker_position_id TEXT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    volume REAL NOT NULL,
    open_price REAL,
    opened_utc TEXT,
    state TEXT NOT NULL,
    created_utc TEXT NOT NULL,
    source TEXT NOT NULL,
    FOREIGN KEY (trade_uid) REFERENCES trades (trade_uid),
    FOREIGN KEY (broker_order_uid)
        REFERENCES broker_orders (broker_order_uid)
);

CREATE TABLE IF NOT EXISTS ib_virtual_position_legs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_uid TEXT NOT NULL UNIQUE,
    trade_uid TEXT NOT NULL UNIQUE,
    broker_position_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    initial_volume REAL NOT NULL,
    remaining_volume REAL NOT NULL,
    entry_price REAL,
    opened_utc TEXT,
    source TEXT NOT NULL,
    parent_order_id TEXT,
    stop_loss_order_id TEXT,
    take_profit_order_id TEXT,
    stop_loss REAL,
    take_profit REAL,
    oca_group TEXT NOT NULL DEFAULT '',
    leg_status TEXT NOT NULL,
    protection_status TEXT NOT NULL,
    reconciliation_status TEXT NOT NULL,
    reconciliation_messages_json TEXT NOT NULL DEFAULT '[]',
    closed_utc TEXT,
    created_utc TEXT NOT NULL,
    updated_utc TEXT NOT NULL,
    FOREIGN KEY (position_uid) REFERENCES positions (position_uid),
    FOREIGN KEY (trade_uid) REFERENCES trades (trade_uid)
);

CREATE TABLE IF NOT EXISTS ib_virtual_position_leg_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_uid TEXT NOT NULL,
    order_role TEXT NOT NULL,
    broker_order_id TEXT NOT NULL,
    parent_order_id TEXT,
    perm_id TEXT,
    client_id INTEGER,
    action TEXT,
    order_type TEXT,
    quantity REAL,
    price REAL,
    oca_group TEXT NOT NULL DEFAULT '',
    oca_type INTEGER,
    order_ref TEXT NOT NULL DEFAULT '',
    execution_status TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_utc TEXT NOT NULL,
    updated_utc TEXT NOT NULL,
    FOREIGN KEY (position_uid)
        REFERENCES ib_virtual_position_legs (position_uid),
    UNIQUE (position_uid, broker_order_id)
);

CREATE TABLE IF NOT EXISTS ib_fx_external_exposures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    broker_position_id TEXT NOT NULL UNIQUE,
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    signed_volume REAL NOT NULL,
    evidence_status TEXT NOT NULL,
    last_confirmed_utc TEXT,
    last_observed_utc TEXT NOT NULL,
    cleared_utc TEXT,
    updated_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ib_pending_open_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_uid TEXT NOT NULL UNIQUE,
    order_plan_uid TEXT NOT NULL,
    broker_order_uid TEXT NOT NULL UNIQUE,
    broker_order_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    stop_loss_order_id TEXT,
    take_profit_order_id TEXT,
    stop_loss REAL,
    take_profit REAL,
    client_id INTEGER,
    comment TEXT NOT NULL DEFAULT '',
    execution_status TEXT NOT NULL,
    last_error TEXT NOT NULL DEFAULT '',
    recovery_attempts INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_utc TEXT NOT NULL,
    updated_utc TEXT NOT NULL,
    resolved_utc TEXT,
    FOREIGN KEY (trade_uid) REFERENCES trades (trade_uid),
    FOREIGN KEY (order_plan_uid)
        REFERENCES order_plans (order_plan_uid),
    FOREIGN KEY (broker_order_uid)
        REFERENCES broker_orders (broker_order_uid),
    UNIQUE (account_id, client_id, broker_order_id)
);

CREATE INDEX IF NOT EXISTS idx_ib_virtual_legs_broker_position
ON ib_virtual_position_legs (broker_position_id);

CREATE INDEX IF NOT EXISTS idx_ib_virtual_legs_status
ON ib_virtual_position_legs (leg_status, reconciliation_status);

CREATE INDEX IF NOT EXISTS idx_ib_virtual_leg_orders_position
ON ib_virtual_position_leg_orders (position_uid, order_role);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ib_virtual_leg_orders_active_role
ON ib_virtual_position_leg_orders (position_uid, order_role)
WHERE is_active = 1;

CREATE INDEX IF NOT EXISTS idx_ib_fx_external_exposures_active
ON ib_fx_external_exposures (account_id, symbol, evidence_status);

CREATE INDEX IF NOT EXISTS idx_ib_pending_open_orders_active
ON ib_pending_open_orders (is_active, execution_status);
"""


def get_runtime_database_path(account_mode: str = "DEMO") -> Path:
    mode = str(account_mode).strip().upper()

    if mode == "DEMO":
        filename = "demo.db"
    elif mode == "LIVE":
        filename = "live.db"
    elif mode == "TEST":
        filename = "test.db"
    else:
        raise ValueError(f"Unsupported runtime database mode: {account_mode}")

    return BASE_DIR / "data" / filename


def ensure_parent_dir(db_path: Path) -> None:
    """
    Створити батьківську директорію для SQLite DB.
    """

    db_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )


def apply_pragmas(connection: sqlite3.Connection) -> None:
    """
    Застосувати canonical SQLite PRAGMA.
    """

    connection.execute("PRAGMA journal_mode=WAL;")

    connection.execute("PRAGMA foreign_keys=ON;")

    connection.execute("PRAGMA synchronous=NORMAL;")

    connection.execute("PRAGMA temp_store=MEMORY;")


def create_runtime_tables(
    connection: sqlite3.Connection,
) -> None:
    """
    Створити runtime tables.
    """

    connection.executescript(RUNTIME_TABLES_SQL)

    connection.commit()


def _table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    """Return existing SQLite column names for one runtime table."""
    rows = connection.execute(
        f"PRAGMA table_info({table_name});"
    ).fetchall()
    return {str(row[1]) for row in rows}


def _ensure_runtime_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    declaration: str,
) -> None:
    """Add one backward-compatible runtime column when it is absent."""
    if column_name in _table_columns(connection, table_name):
        return

    connection.execute(
        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {declaration};"
    )


def migrate_runtime_schema(
    connection: sqlite3.Connection,
) -> None:
    """Apply additive Runtime schema migrations through schema v8."""
    _ensure_runtime_column(
        connection,
        "trades",
        "comment",
        "TEXT NOT NULL DEFAULT ''",
    )
    _ensure_runtime_column(
        connection,
        "broker_orders",
        "broker_comment",
        "TEXT NOT NULL DEFAULT ''",
    )
    _ensure_runtime_column(
        connection,
        "ib_virtual_position_leg_orders",
        "order_ref",
        "TEXT NOT NULL DEFAULT ''",
    )

    # Recover exact delayed-Open comments already persisted by schema v6.
    connection.execute(
        """
        UPDATE broker_orders
        SET broker_comment = COALESCE((
            SELECT pending.comment
            FROM ib_pending_open_orders pending
            WHERE pending.broker_order_uid = broker_orders.broker_order_uid
            ORDER BY pending.id DESC
            LIMIT 1
        ), broker_comment)
        WHERE broker_comment = ''
          AND EXISTS (
              SELECT 1
              FROM ib_pending_open_orders pending
              WHERE pending.broker_order_uid = broker_orders.broker_order_uid
          )
        """
    )
    connection.execute(
        """
        UPDATE trades
        SET comment = COALESCE((
            SELECT CASE
                WHEN pending.comment LIKE '[LGE:M] %'
                    THEN SUBSTR(pending.comment, 9)
                WHEN pending.comment LIKE '[LGE:S] %'
                    THEN SUBSTR(pending.comment, 9)
                WHEN pending.comment LIKE '[LGE:A] %'
                    THEN SUBSTR(pending.comment, 9)
                ELSE pending.comment
            END
            FROM ib_pending_open_orders pending
            WHERE pending.trade_uid = trades.trade_uid
            ORDER BY pending.id DESC
            LIMIT 1
        ), comment)
        WHERE comment = ''
          AND EXISTS (
              SELECT 1
              FROM ib_pending_open_orders pending
              WHERE pending.trade_uid = trades.trade_uid
          )
        """
    )
    connection.execute(
        """
        UPDATE ib_virtual_position_leg_orders
        SET order_ref = COALESCE((
            SELECT broker_orders.broker_comment
            FROM ib_virtual_position_legs legs
            INNER JOIN broker_orders
                ON broker_orders.trade_uid = legs.trade_uid
            WHERE legs.position_uid
                = ib_virtual_position_leg_orders.position_uid
              AND broker_orders.broker_order_id
                = ib_virtual_position_leg_orders.broker_order_id
              AND broker_orders.broker_comment != ''
            ORDER BY broker_orders.id DESC
            LIMIT 1
        ), order_ref)
        WHERE order_ref = ''
        """
    )
    connection.commit()


def set_schema_version(
    connection: sqlite3.Connection,
    schema_version: int,
) -> None:
    """
    Встановити schema version.
    """

    connection.execute(f"PRAGMA user_version={schema_version};")


def get_schema_version(
    connection: sqlite3.Connection,
) -> int:
    """
    Отримати schema version.
    """

    cursor = connection.execute("PRAGMA user_version;")

    row = cursor.fetchone()

    if row is None:
        return 0

    return int(row[0])


def connect_runtime_db(
    db_path: str | Path,
) -> sqlite3.Connection:
    """
    Відкрити та підготувати runtime SQLite DB.
    """

    db_file = Path(db_path)

    ensure_parent_dir(db_file)

    connection = sqlite3.connect(
        db_file,
    )

    apply_pragmas(connection)

    create_runtime_tables(connection)
    migrate_runtime_schema(connection)

    current_version = get_schema_version(connection)

    if current_version != SCHEMA_VERSION:
        set_schema_version(
            connection,
            SCHEMA_VERSION,
        )

        connection.commit()

    return connection


def insert_runtime_event(
    connection: sqlite3.Connection,
    runtime_event_type: str,
    message: str,
    payload_json: str,
    created_utc: str,
) -> None:
    """
    Додати runtime event у SQLite.
    """

    connection.execute(
        """
        INSERT INTO runtime_events (
            event_type,
            message,
            payload_json,
            created_utc
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            runtime_event_type,
            message,
            payload_json,
            created_utc,
        ),
    )

    connection.commit()


def insert_session(
    connection: sqlite3.Connection,
    session_id: str,
    runtime_state: str,
    broker: str,
    account_mode: str,
    execution_mode: str,
    created_utc: str,
) -> None:
    """
    Додати runtime session у SQLite.
    """

    connection.execute(
        """
        INSERT INTO sessions (
            session_id,
            runtime_state,
            broker,
            account_mode,
            execution_mode,
            created_utc
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            runtime_state,
            broker,
            account_mode,
            execution_mode,
            created_utc,
        ),
    )

    connection.commit()
