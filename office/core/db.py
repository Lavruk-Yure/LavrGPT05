# db.py
# -*- coding: utf-8 -*-
"""
db — робота з SQLite для LGEOffice.

Поки що: тільки створення/ініціалізація office.db зі schema.sql.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QFile, QIODevice
from PySide6.QtSql import QSqlDatabase

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "4"


def _load_schema_sql() -> str:
    """Завантажити schema.sql з Qt resource."""
    qfile = QFile(":/sql/core/schema.sql")
    if not qfile.open(QIODevice.OpenModeFlag.ReadOnly):
        raise RuntimeError("schema.sql resource not found: :/sql/core/schema.sql")

    data = qfile.readAll()
    qfile.close()
    return data.data().decode("utf-8")


def get_db_path(office_root: Path) -> Path:
    return office_root / "office.db"


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1;",
        (name,),
    ).fetchone()
    return row is not None


def _get_schema_version(conn: sqlite3.Connection) -> str:
    if not _table_exists(conn, "meta"):
        return ""
    row = conn.execute(
        "SELECT value FROM meta WHERE key='schema_version' LIMIT 1;"
    ).fetchone()
    return str(row[0]) if row and row[0] is not None else ""


def _set_schema_version(conn: sqlite3.Connection, v: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?);",
        (v,),
    )


def _column_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table});").fetchall()
    return any(r[1] == col for r in rows)  # r[1] = name


def _close_all_qt_sql_connections() -> None:
    """
    Закриває всі QSqlDatabase конекшени, щоб Windows відпустив office.db.
    """
    for name in QSqlDatabase.connectionNames():
        db = QSqlDatabase.database(name, False)
        if db.isValid():
            db.close()
        QSqlDatabase.removeDatabase(name)


def init_db(office_root: Path) -> Path:
    db_path = get_db_path(office_root)
    schema = _load_schema_sql()

    db_path.parent.mkdir(parents=True, exist_ok=True)

    with connect(db_path) as conn:
        # 1) якщо чиста/стара БД без meta — просто застосувати schema.sql
        if not _table_exists(conn, "meta"):
            conn.executescript(schema)
            conn.commit()
            logger.info("DB created by schema.sql: %s", db_path)
            return db_path

        current = _get_schema_version(conn)
        if current == SCHEMA_VERSION:
            logger.debug("DB schema OK: %s", current)
            return db_path

        # 2) backup (не блокуємо init якщо backup не вийшов)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = db_path.with_name(f"office_v{current or 'unknown'}_bak_{ts}.db")
        try:
            shutil.copy2(db_path, bak)
            logger.warning("DB backup created: %s", bak)
        except Exception as exc:  # noqa: BLE001
            logger.warning("DB backup skipped: %s", exc)

        # 3) міграції
        if current == "1":
            # customers.note
            if _table_exists(conn, "customers") and not _column_exists(
                conn, "customers", "note"
            ):
                conn.execute(
                    "ALTER TABLE customers ADD COLUMN note TEXT NOT NULL DEFAULT '';"
                )
                logger.info("DB migrate v1->v2: customers.note added")

            _set_schema_version(conn, SCHEMA_VERSION)
            conn.commit()
            logger.info("DB schema_version updated: %s", SCHEMA_VERSION)
            return db_path

        # 4) невідомий schema_version — тоді вже критично
        raise RuntimeError(f"Unsupported schema_version: '{current}'")


# --- DB readiness check -------------------------------------------------


def is_db_ready(office_root: Path) -> bool:
    """
    БД вважається готовою, якщо:
    - файл існує
    - є всі потрібні таблиці
    - schema_version == SCHEMA_VERSION
    """
    db_path = get_db_path(office_root)
    if not db_path.exists():
        return False

    try:
        with connect(db_path) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()

            tables = {r[0] for r in rows}
            required = {
                "meta",
                "customers",
                "orders",
                "payments",
                "licenses",
            }

            if not required.issubset(tables):
                return False

            row = conn.execute(
                "SELECT value FROM meta WHERE key='schema_version' LIMIT 1;"
            ).fetchone()

            return bool(row and row[0] == SCHEMA_VERSION)

    except Exception:  # noqa
        logger.exception("DB readiness check failed")
        return False


def is_db_write_locked(db_path: Path) -> bool:
    """
    True якщо SQLite не може взяти write-lock (інший процес тримає транзакцію).
    Працює краще за WinAPI для DBeaver.
    """
    if not db_path.exists():
        return False

    try:
        conn = sqlite3.connect(str(db_path), timeout=0.05)
        try:
            conn.execute("PRAGMA busy_timeout=50;")
            conn.execute("BEGIN IMMEDIATE;")  # бере RESERVED lock
            conn.rollback()
            return False
        finally:
            conn.close()
    except sqlite3.OperationalError as e:
        msg = str(e).lower()
        return ("database is locked" in msg) or ("database is busy" in msg)
