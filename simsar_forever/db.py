import json
import sqlite3
import time
from pathlib import Path

SCHEMA_VERSION = 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS items(
  item_id INTEGER PRIMARY KEY,
  name TEXT,
  vendor_sell INTEGER,
  vendor_buy REAL,
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

-- Sold-auction mail invoices captured by the Simsar Forever addon.
CREATE TABLE IF NOT EXISTS ah_invoices(
  seen_at INTEGER, item_name TEXT, quantity INTEGER,
  bid INTEGER, buyout INTEGER, deposit INTEGER, consignment INTEGER,
  PRIMARY KEY(seen_at, item_name, bid)
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

-- Characters and what they carry, from the Simsar Forever addon. The bank is only known from the
-- last time it was opened.
CREATE TABLE IF NOT EXISTS characters(
  char_key TEXT PRIMARY KEY, name TEXT, realm TEXT, class TEXT, faction TEXT,
  money INTEGER, bags_at INTEGER, bank_at INTEGER
);

CREATE TABLE IF NOT EXISTS inventory(
  char_key TEXT, location TEXT, item_id INTEGER, count INTEGER, bound INTEGER,
  PRIMARY KEY(char_key, location, item_id)
) WITHOUT ROWID;

-- Auction mail other than sales: purchases ("bought"), expired and cancelled auctions.
CREATE TABLE IF NOT EXISTS mail_events(
  mail_key TEXT PRIMARY KEY, kind TEXT, seen_at INTEGER, char_key TEXT,
  item_name TEXT, item_id INTEGER, quantity INTEGER, amount INTEGER
);

-- Profession skill per character, and which recipes each character knows.
CREATE TABLE IF NOT EXISTS char_professions(
  char_key TEXT, profession TEXT, rank INTEGER, max_rank INTEGER, seen_at INTEGER,
  PRIMARY KEY(char_key, profession)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS char_recipes(
  char_key TEXT, recipe_key TEXT, learned INTEGER,
  PRIMARY KEY(char_key, recipe_key)
) WITHOUT ROWID;

-- Recipes vendors sell (often limited stock), seen while a vendor window was open.
CREATE TABLE IF NOT EXISTS vendor_recipes(
  item_id INTEGER PRIMARY KEY, name TEXT, price INTEGER, limited INTEGER, vendor TEXT, zone TEXT,
  seen_at INTEGER
);

-- Gold ledger: income and spending per character, day and category. `source` is 'simsar' (this
-- addon) or 'accountant' (imported from Accountant Classic); for a character and day the Simsar
-- rows win when both exist.
CREATE TABLE IF NOT EXISTS ledger_days(
  char_key TEXT, day INTEGER, category TEXT, source TEXT,
  income INTEGER, expense INTEGER, n INTEGER,
  PRIMARY KEY(char_key, day, category, source)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS ledger_tx(
  char_key TEXT, t INTEGER, amount INTEGER, category TEXT, source TEXT, zone TEXT,
  PRIMARY KEY(char_key, t, amount, category, source)
) WITHOUT ROWID;

-- Gold on hand at the end of each day.
CREATE TABLE IF NOT EXISTS balances(
  char_key TEXT, day INTEGER, source TEXT, balance INTEGER,
  PRIMARY KEY(char_key, day, source)
) WITHOUT ROWID;

-- Forecasts the sell advice made, scored once the real price is known.
CREATE TABLE IF NOT EXISTS forecasts(
  item_id INTEGER, made_day INTEGER, horizon INTEGER, base REAL, predicted REAL, low REAL, high REAL,
  advice TEXT, actual REAL,
  PRIMARY KEY(item_id, made_day, horizon)
) WITHOUT ROWID;

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
    migrate(conn)
    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    return conn


MIGRATIONS = {
    "items": (("vendor_buy", "REAL"), ("quality", "INTEGER"), ("icon_id", "INTEGER")),
    "recipes": (("trainer_cost", "INTEGER"), ("skill_req", "INTEGER")),
    "characters": (("money_at", "INTEGER"),),
    "ah_invoices": (("char_key", "TEXT"),),
}


def migrate(conn):
    for table, columns in MIGRATIONS.items():
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, kind in columns:
            if col not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {kind}")
    conn.commit()


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


def upsert_item_looks(conn, looks):
    """looks: {item_id: (quality, icon_id)}"""
    conn.executemany(
        "INSERT INTO items(item_id, quality, icon_id) VALUES(?, ?, ?) "
        "ON CONFLICT(item_id) DO UPDATE SET quality = COALESCE(excluded.quality, items.quality), "
        "icon_id = COALESCE(excluded.icon_id, items.icon_id)",
        [(i, q, ic) for i, (q, ic) in looks.items()],
    )


def upsert_vendor_prices(conn, prices):
    conn.executemany(
        "INSERT INTO items(item_id, vendor_sell) VALUES(?, ?) "
        "ON CONFLICT(item_id) DO UPDATE SET vendor_sell = excluded.vendor_sell",
        list(prices.items()),
    )


def upsert_vendor_buy(conn, prices):
    conn.executemany(
        "INSERT INTO items(item_id, name, vendor_buy) VALUES(?, ?, ?) "
        "ON CONFLICT(item_id) DO UPDATE SET vendor_buy = excluded.vendor_buy, "
        "name = COALESCE(items.name, excluded.name)",
        [(i, n, p) for i, (n, p) in prices.items()],
    )


def prune(conn, retain_days, now=None):
    cutoff = int((now or time.time()) - retain_days * 86400)
    for table, col in (("tsm_realm", "updated_at"), ("tsm_region", "updated_at"), ("ato_daily", "day_ts")):
        conn.execute(f"DELETE FROM {table} WHERE {col} < ?", (cutoff,))
    conn.commit()
