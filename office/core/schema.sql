PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_uid TEXT NOT NULL UNIQUE,              -- "LGE-20260206-1008-A991" (з листа/замовлення)
    customer_id INTEGER NOT NULL,
    edition TEXT NOT NULL,                       -- PRO / PRO_PLUS
    app_version TEXT NOT NULL DEFAULT '',
    payment_ref TEXT NOT NULL DEFAULT '',
    fingerprint_sha256 TEXT NOT NULL DEFAULT '',
    created_utc TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NULL,
    provider TEXT NOT NULL DEFAULT '',
    external_ref TEXT NOT NULL DEFAULT '',
    amount REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'USD',
    paid_utc TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_payments_external_ref ON payments(external_ref);

CREATE TABLE IF NOT EXISTS licenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL UNIQUE,            -- 1:1 (унікально)
    license_uid TEXT NOT NULL UNIQUE,            -- uuid4
    license_rel_path TEXT NOT NULL,              -- licenses/xxx.lic
    edition TEXT NOT NULL,
    issued_utc TEXT NOT NULL,
    sent_utc TEXT,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_licenses_license_uid ON licenses(license_uid);

---------------------------------------------------------------------
-- META (службова таблиця для контролю версії схеми)
---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Версія схеми (змінювати при зміні структури БД)
INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', '4');

-- Час ініціалізації БД (UTC)
INSERT OR REPLACE INTO meta(key, value)
VALUES ('db_initialized_utc', strftime('%Y-%m-%dT%H:%M:%fZ','now'));

