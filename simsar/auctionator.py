"""Import Auctionator's SavedVariables.

Layout verified against Auctionator 345 on the WoW Forever client (November 2026):

    AUCTIONATOR_PRICE_DATABASE = {
      __dbversion = 8,
      [realmKey] = <CBOR string> or <table>,   -- current realm may be left deserialized
    }
    realm table = { version = 2, [dbKey] = { m = price, h = {[day] = p}, l = {[day] = p}, a = {[day] = n} } }

dbKey is a plain item id, "g:<id>:<ilvl>" or "gr:<id>:<suffix>" for gear, "p:<species>" for pets.
Day keys count days since 2020-01-01 00:00 local time (Auctionator.Constants.SCAN_DAY_0).
h is the highest minimum price seen that day, l the lowest (only stored when it differs from h),
a the most units seen on sale that day.
"""

import hashlib
import os
import re
import time
from pathlib import Path

import cbor2

from . import db, lua

SUPPORTED_DB_VERSIONS = {8}
KNOWN_ENTRY_FIELDS = {"m", "h", "l", "a"}
SCAN_DAY_0 = int(time.mktime((2020, 1, 1, 0, 0, 0, 0, 0, -1)))


class AuctionatorFormatError(ValueError):
    pass


def day_to_ts(day):
    return SCAN_DAY_0 + int(day) * 86400


def ts_to_day(ts):
    return (int(ts) - SCAN_DAY_0) // 86400


def saved_variables_dir(cfg):
    game_dir = cfg["wow"].get("game_dir")
    if not game_dir:
        return None
    accounts = Path(game_dir) / "WTF" / "Account"
    if cfg["wow"].get("account"):
        return accounts / cfg["wow"]["account"] / "SavedVariables"
    if not accounts.is_dir():
        return None
    found = [p / "SavedVariables" for p in accounts.iterdir() if (p / "SavedVariables").is_dir()]
    if len(found) == 1:
        return found[0]
    with_ato = [p for p in found if (p / "Auctionator.lua").exists()]
    if len(with_ato) == 1:
        return with_ato[0]
    return None


def addon_dir(cfg, name="Auctionator"):
    game_dir = cfg["wow"].get("game_dir")
    return Path(game_dir) / "Interface" / "AddOns" / name if game_dir else None


def read_toc(path):
    """Return the ## fields of an addon .toc file."""
    fields = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"##\s*([^:]+):\s*(.*)", line.strip())
                if m:
                    fields[m.group(1).strip()] = m.group(2).strip()
    except OSError:
        return {}
    return fields


def find_files(root, max_depth=7):
    hits = []
    root = os.path.abspath(root)
    base = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        if dirpath.count(os.sep) - base >= max_depth:
            dirnames[:] = []
        if "Auctionator.lua" in filenames and os.path.basename(dirpath) == "SavedVariables":
            hits.append(os.path.join(dirpath, "Auctionator.lua"))
    return hits


def _norm(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", "surrogateescape")
    if isinstance(value, dict):
        return {_norm(k): _norm(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_norm(v) for v in value]
    return value


def _as_day_map(value):
    # Lua serialises empty tables as CBOR arrays.
    if isinstance(value, dict):
        return value
    return {}


def decode_realm(raw):
    if isinstance(raw, str):
        try:
            raw = cbor2.loads(lua.to_bytes(raw))
        except Exception as e:
            raise AuctionatorFormatError(f"realm data is not valid CBOR: {e}") from e
    raw = _norm(raw)
    if not isinstance(raw, dict):
        raise AuctionatorFormatError(f"realm data decoded to {type(raw).__name__}, expected a table")
    return raw


def read_price_database(saved):
    root = saved.get("AUCTIONATOR_PRICE_DATABASE")
    if not isinstance(root, dict):
        raise AuctionatorFormatError("AUCTIONATOR_PRICE_DATABASE is missing; is this Auctionator's file?")
    version = root.get("__dbversion")
    if version not in SUPPORTED_DB_VERSIONS:
        raise AuctionatorFormatError(
            f"Auctionator price database version {version!r} is not supported "
            f"(known: {sorted(SUPPORTED_DB_VERSIONS)}). The addon probably changed its format.")
    realms = {}
    for key, raw in root.items():
        if key == "__dbversion":
            continue
        realms[str(key)] = decode_realm(raw)
    if not realms:
        raise AuctionatorFormatError("the price database has no realms yet; scan the auction house first")
    return version, realms


def base_item_id(db_key):
    s = str(db_key)
    if s.isdigit():
        return int(s), True
    m = re.fullmatch(r"gr?:(\d+):.*", s)
    if m:
        return int(m.group(1)), False
    return None, False


def extract(realm_data):
    """Turn one realm table into current prices and daily rows keyed by item id."""
    current, daily, fields = {}, {}, set()
    skipped = 0
    exact = set()
    for key, entry in realm_data.items():
        if not isinstance(entry, dict):
            continue
        item_id, is_plain = base_item_id(key)
        if item_id is None:
            skipped += 1
            continue
        if not is_plain and item_id in exact:
            continue
        fields.update(entry.keys())
        highs, lows, avail = (_as_day_map(entry.get(f)) for f in ("h", "l", "a"))
        days = {}
        for day, high in highs.items():
            if not str(day).lstrip("-").isdigit() or not isinstance(high, (int, float)):
                continue
            low = lows.get(day, high)
            days[int(day)] = (int(low), int(high), avail.get(day))
        price = entry.get("m")
        if is_plain:
            exact.add(item_id)
            current[item_id] = (price, days)
        elif item_id not in current or (price and price < (current[item_id][0] or float("inf"))):
            current[item_id] = (price, days)
    for item_id, (price, days) in current.items():
        daily[item_id] = days
    prices = {i: int(p) for i, (p, _) in current.items() if isinstance(p, (int, float)) and p > 0}
    return prices, daily, fields, skipped


def fingerprint(version, fields, realm_keys):
    text = f"{version}|{','.join(sorted(map(str, fields)))}|{len(realm_keys)}"
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def choose_realm(realms, hint=None):
    if hint and hint in realms:
        return hint
    return max(realms, key=lambda r: sum(isinstance(v, dict) for v in realms[r].values()))


def import_file(conn, path, cfg):
    path = Path(path)
    saved = lua.load(path)
    version, realms = read_price_database(saved)
    realm = choose_realm(realms, cfg["wow"].get("auctionator_realm"))
    prices, daily, fields, skipped = extract(realms[realm])
    if not daily:
        raise AuctionatorFormatError(f"realm {realm!r} has no recognisable item entries")

    mtime = int(path.stat().st_mtime)
    last_scan = (saved.get("AUCTIONATOR_SAVEDVARS") or {}).get("TimeOfLastBrowseScan")
    current_rows, daily_rows = [], []
    for item_id, days in daily.items():
        for day, (low, high, available) in days.items():
            daily_rows.append((item_id, day_to_ts(day), low, high, available))
        if item_id in prices and days:
            latest = max(days)
            seen = min(mtime, day_to_ts(latest) + 86399)
            current_rows.append((item_id, prices[item_id], seen))

    conn.executemany("INSERT OR REPLACE INTO ato_daily VALUES(?, ?, ?, ?, ?)", daily_rows)
    conn.executemany("INSERT OR REPLACE INTO ato_current VALUES(?, ?, ?)", current_rows)

    postings = import_postings(conn, saved.get("AUCTIONATOR_POSTING_HISTORY"))
    vendor = saved.get("AUCTIONATOR_VENDOR_PRICE_CACHE")
    vendor_prices = {}
    if isinstance(vendor, dict):
        for k, v in vendor.items():
            if str(k).isdigit() and isinstance(v, (int, float)) and v >= 0:
                vendor_prices[int(k)] = int(v)
        db.upsert_vendor_prices(conn, vendor_prices)
    conn.commit()

    unknown = sorted(str(f) for f in fields - KNOWN_ENTRY_FIELDS)
    return {
        "realm": realm,
        "realms": sorted(realms),
        "db_version": version,
        "items": len(daily),
        "current_prices": len(current_rows),
        "daily_rows": len(daily_rows),
        "skipped_keys": skipped,
        "postings": postings,
        "vendor_prices": len(vendor_prices),
        "unknown_fields": unknown,
        "fingerprint": fingerprint(version, fields & KNOWN_ENTRY_FIELDS | set(unknown), realms),
        "file_mtime": mtime,
        "last_full_scan": int(last_scan) if isinstance(last_scan, (int, float)) else None,
    }


def import_postings(conn, history):
    if not isinstance(history, dict):
        return 0
    rows = []
    for key, posts in history.items():
        if not str(key).isdigit() or not isinstance(posts, list):
            continue
        for p in posts:
            if isinstance(p, dict) and all(isinstance(p.get(f), (int, float)) for f in ("price", "quantity", "time")):
                rows.append((int(key), int(p["time"]), int(p["price"]), int(p["quantity"])))
    conn.executemany("INSERT OR IGNORE INTO my_postings VALUES(?, ?, ?, ?)", rows)
    return len(rows)


def inspect(path):
    """Human-readable description of an Auctionator.lua file, for troubleshooting."""
    path = Path(path)
    lines = [f"File: {path}", f"Size: {path.stat().st_size:,} bytes"]
    saved = lua.load(path)
    lines.append(f"Globals: {', '.join(sorted(saved))}")
    root = saved.get("AUCTIONATOR_PRICE_DATABASE")
    if not isinstance(root, dict):
        lines.append("AUCTIONATOR_PRICE_DATABASE not found.")
        return "\n".join(lines)
    lines.append(f"__dbversion: {root.get('__dbversion')!r} (supported: {sorted(SUPPORTED_DB_VERSIONS)})")
    for key, raw in root.items():
        if key == "__dbversion":
            continue
        kind = "CBOR string" if isinstance(raw, str) else type(raw).__name__
        try:
            data = decode_realm(raw)
        except AuctionatorFormatError as e:
            lines.append(f"realm {key!r}: {kind}, cannot decode: {e}")
            continue
        prices, daily, fields, skipped = extract(data)
        all_days = sorted({d for days in daily.values() for d in days})
        span = ""
        if all_days:
            first = time.strftime("%Y-%m-%d", time.localtime(day_to_ts(all_days[0])))
            last = time.strftime("%Y-%m-%d", time.localtime(day_to_ts(all_days[-1])))
            span = f", days {first} .. {last}"
        lines.append(f"realm {key!r}: {kind}, {len(daily)} items, {len(prices)} with a current price, "
                     f"fields {sorted(map(str, fields))}, {skipped} non-item keys{span}")
        sample = next(iter(daily.items()), None)
        if sample:
            item_id, days = sample
            lines.append(f"  sample item {item_id}: m={prices.get(item_id)} days={dict(list(days.items())[:3])}")
    last_scan = (saved.get("AUCTIONATOR_SAVEDVARS") or {}).get("TimeOfLastBrowseScan")
    if last_scan:
        lines.append(f"Last full scan: {time.strftime('%Y-%m-%d %H:%M', time.localtime(last_scan))}")
    return "\n".join(lines)
