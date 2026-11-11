import json
import sqlite3
import time
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS items(
  item_id INTEGER PRIMARY KEY,
  name TEXT,
  vendor_sell INTEGER,
  updated_at INTEGER
);

-- One row per item per TSM scan. Prices in copper.
CREATE TABLE IF NOT EXISTS tsm_realm(
  item_id INTEGER, updated_at INTEGER,
  market INTEGER, min_buyout INTEGER, recent INTEGER, historical INTEGER,
  PRIMARY KEY(item_id, updated_at)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS tsm_region(
  item_id INTEGER, updated_at INTEGER,
  market INTEGER, historical INTEGER, avg_sale INTEGER,
  sale_rate REAL, sold_per_day REAL,
  PRIMARY KEY(item_id, updated_at)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS ix_tsm_realm_time ON tsm_realm(updated_at);
CREATE INDEX IF NOT EXISTS ix_tsm_region_time ON tsm_region(updated_at);

-- Auctionator keeps one row per item per scan day: the lowest and highest minimum price seen
-- that day and the most units seen on sale.
CREATE TABLE IF NOT EXISTS ato_daily(
  item_id INTEGER, day_ts INTEGER,
  low INTEGER, high INTEGER, available INTEGER,
  PRIMARY KEY(item_id, day_ts)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS ato_current(
  item_id INTEGER PRIMARY KEY,
  price INTEGER,
  seen_ts INTEGER
);

CREATE TABLE IF NOT EXISTS my_postings(
  item_id INTEGER, posted_at INTEGER, price INTEGER, quantity INTEGER,
  PRIMARY KEY(item_id, posted_at, price, quantity)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS recipes(
  recipe_key TEXT PRIMARY KEY,
  profession TEXT NOT NULL,
  name TEXT NOT NULL,
  product_id INTEGER,
  product_name TEXT,
  yield_min REAL DEFAULT 1,
  yield_max REAL DEFAULT 1,
  learned INTEGER,
  recipe_item_id INTEGER,
  source TEXT NOT NULL,
  updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS recipe_reagents(
  recipe_key TEXT,
  item_id INTEGER,
  name TEXT,
  count REAL,
  PRIMARY KEY(recipe_key, item_id, name)
);

-- Sold-auction mail invoices captured by the SimsarExport addon.
CREATE TABLE IF NOT EXISTS ah_invoices(
  seen_at INTEGER, item_name TEXT, quantity INTEGER,
  bid INTEGER, buyout INTEGER, deposit INTEGER, consignment INTEGER,
  PRIMARY KEY(seen_at, item_name, bid)
);

-- Deposits quoted by the game when posting, captured by the addon.
CREATE TABLE IF NOT EXISTS ah_deposits(
  seen_at INTEGER, item_id INTEGER, quantity INTEGER, hours INTEGER,
  deposit INTEGER, vendor_sell INTEGER,
  PRIMARY KEY(seen_at, item_id)
);

CREATE TABLE IF NOT EXISTS fetch_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT, at INTEGER, ok INTEGER, details TEXT
);

CREATE TABLE IF NOT EXISTS alerts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at INTEGER, kind TEXT, item_id INTEGER, dedupe_key TEXT UNIQUE,
  title TEXT, message TEXT, seen INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""


def connect(path):
    path = Path(path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    return conn


def set_meta(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)", (key, json.dumps(value)))
    conn.commit()


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def log_fetch(conn, source, ok, details):
    conn.execute("INSERT INTO fetch_log(source, at, ok, details) VALUES(?, ?, ?, ?)",
                 (source, int(time.time()), int(bool(ok)), json.dumps(details)))
    conn.execute("DELETE FROM fetch_log WHERE id NOT IN (SELECT id FROM fetch_log ORDER BY id DESC LIMIT 500)")
    conn.commit()


def upsert_names(conn, names, now=None):
    now = int(now or time.time())
    conn.executemany(
        "INSERT INTO items(item_id, name, updated_at) VALUES(?, ?, ?) "
        "ON CONFLICT(item_id) DO UPDATE SET name = excluded.name, updated_at = excluded.updated_at "
        "WHERE excluded.name IS NOT NULL AND excluded.name != ''",
        [(i, n, now) for i, n in names.items() if n],
    )


def upsert_vendor_prices(conn, prices):
    conn.executemany(
        "INSERT INTO items(item_id, vendor_sell) VALUES(?, ?) "
        "ON CONFLICT(item_id) DO UPDATE SET vendor_sell = excluded.vendor_sell",
        list(prices.items()),
    )


def prune(conn, retain_days, now=None):
    cutoff = int((now or time.time()) - retain_days * 86400)
    for table, col in (("tsm_realm", "updated_at"), ("tsm_region", "updated_at"), ("ato_daily", "day_ts")):
        conn.execute(f"DELETE FROM {table} WHERE {col} < ?", (cutoff,))
    conn.commit()
