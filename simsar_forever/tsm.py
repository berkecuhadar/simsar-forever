"""TSM public CSV files: download, parse, store as snapshots.

Docs: https://tradeskillmaster.com/public-data (no key, no login, no rate limit)
"""

import csv
import io
import time
from datetime import datetime

import requests

from . import __version__, db

BASE_URL = "https://public-data.tradeskillmaster.com"
HEADERS = {"User-Agent": f"simsar-forever/{__version__} (personal market dashboard)"}

REALM_COLUMNS = ("itemid", "name", "marketvalue", "minbuyout", "recent", "historical", "updatedat")
REGION_COLUMNS = ("itemid", "name", "marketvalue", "historical", "avgsaleprice", "salerate",
                  "soldperday", "updatedat")


class TsmError(RuntimeError):
    pass


def urls(cfg):
    t = cfg["tsm"]
    base = f"{BASE_URL}/{t['game_type']}/{t['region']}"
    out = {"region": f"{base}/region/items.csv"}
    if t.get("realm"):
        out["realm"] = f"{base}/realm/{t['realm']}/items.csv"
    return out


def iso_to_ts(value):
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return int(datetime.fromisoformat(value).timestamp())


def _int(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _float(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse(kind, text):
    """Parse a realm or region CSV. Returns (rows, names, updated_at)."""
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    try:
        header = [h.strip().lower() for h in next(reader)]
    except StopIteration:
        raise TsmError("file is empty")
    expected = REALM_COLUMNS if kind == "realm" else REGION_COLUMNS
    missing = [c for c in expected if c not in header]
    if missing:
        raise TsmError(f"unexpected columns, missing {missing}; got {header}")
    col = {name: header.index(name) for name in expected}

    rows, names, stamps = [], {}, set()
    for record in reader:
        if not record or len(record) < len(header):
            continue
        item_id = _int(record[col["itemid"]])
        updated = record[col["updatedat"]].strip()
        if item_id is None or not updated:
            continue
        ts = iso_to_ts(updated)
        stamps.add(ts)
        names[item_id] = record[col["name"]].strip()
        if kind == "realm":
            rows.append((item_id, ts, _int(record[col["marketvalue"]]), _int(record[col["minbuyout"]]),
                         _int(record[col["recent"]]), _int(record[col["historical"]])))
        else:
            rows.append((item_id, ts, _int(record[col["marketvalue"]]), _int(record[col["historical"]]),
                         _int(record[col["avgsaleprice"]]), _float(record[col["salerate"]]),
                         _float(record[col["soldperday"]])))
    if not rows:
        raise TsmError("file has a header but no rows")
    return rows, names, max(stamps)


def store(conn, kind, rows, names):
    table = "tsm_realm" if kind == "realm" else "tsm_region"
    placeholders = ",".join("?" * len(rows[0]))
    before = conn.total_changes
    conn.executemany(f"INSERT OR IGNORE INTO {table} VALUES({placeholders})", rows)
    inserted = conn.total_changes - before
    db.upsert_names(conn, names)
    conn.commit()
    return inserted


def download(url, timeout, etag=None, attempts=3, session=None):
    """GET with retries. Returns (status, text, etag). status 304 means unchanged."""
    http = session or requests
    headers = dict(HEADERS)
    if etag:
        headers["If-None-Match"] = etag
    last_error = None
    for attempt in range(attempts):
        wait = 2 ** attempt * 2
        try:
            r = http.get(url, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            last_error = e
        else:
            if r.status_code == 304:
                return 304, None, etag
            if r.status_code == 200:
                return 200, r.content.decode("utf-8-sig"), r.headers.get("ETag")
            if r.status_code in (404, 403, 410):
                return r.status_code, None, None
            if r.status_code == 429:
                # The files are public but the host does rate limit bursts of requests.
                last_error = TsmError("rate limited by TSM (HTTP 429); will try again on the next check")
                wait = _retry_after(r.headers.get("Retry-After"), wait)
            else:
                last_error = TsmError(f"HTTP {r.status_code}")
        if attempt + 1 < attempts:
            time.sleep(wait)
    raise TsmError(f"download failed after {attempts} attempts: {last_error}")


def _retry_after(value, default):
    try:
        return min(max(float(value), 1), 120)
    except (TypeError, ValueError):
        return default


def fetch(cfg, conn, session=None):
    """Fetch every configured TSM file. Returns one report dict per file."""
    reports = []
    for kind, url in urls(cfg).items():
        rep = {"source": f"tsm_{kind}", "url": url, "ok": False}
        etag_key, stamp_key = f"tsm_{kind}_etag", f"tsm_{kind}_updated_at"
        try:
            status, text, etag = download(url, cfg["tsm"]["timeout_seconds"],
                                          db.get_meta(conn, etag_key), session=session)
            rep["http"] = status
            if status == 304:
                rep.update(ok=True, unchanged=True, updated_at=db.get_meta(conn, stamp_key))
            elif status != 200:
                rep["error"] = (f"TSM has no {kind} file at this address (HTTP {status}). "
                                "Check tsm.game_type, tsm.region and tsm.realm.")
            else:
                rows, names, updated_at = parse(kind, text)
                rep.update(ok=True, rows=len(rows), updated_at=updated_at)
                if updated_at == db.get_meta(conn, stamp_key):
                    rep["unchanged"] = True
                else:
                    rep["new_rows"] = store(conn, kind, rows, names)
                    db.set_meta(conn, stamp_key, updated_at)
                if etag:
                    db.set_meta(conn, etag_key, etag)
            db.set_meta(conn, f"tsm_{kind}_checked_at", int(time.time()))
        except (TsmError, ValueError) as e:
            rep["error"] = str(e)
        db.log_fetch(conn, rep["source"], rep["ok"], rep)
        reports.append(rep)
    return reports
