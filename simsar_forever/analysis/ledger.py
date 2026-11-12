"""Gold ledger: what each character earned and spent, by day and category, and gold over time.

Two sources fill the same tables: the Simsar Forever addon ('simsar') and Accountant Classic
('accountant'). For one character and day the addon's numbers win when both exist; Accountant
Classic only fills days the addon did not record (typically before it was installed).
"""

from collections import defaultdict

# Category -> (label, kind). Transfers move gold between your own characters and are left out of
# profit; "untracked" is gold that changed while no addon was recording.
CATEGORIES = {
    "AH_SALE": ("Auction sales", "trade"),
    "AH_BUY": ("Auction purchases", "trade"),
    "AH_DEPOSIT": ("Auction deposits", "trade"),
    "AH": ("Auction house, other", "trade"),
    "VENDOR": ("Vendors", "trade"),
    "REPAIR": ("Repairs", "cost"),
    "TRAINING": ("Training", "cost"),
    "TAXI": ("Flights", "cost"),
    "BARBER": ("Barber", "cost"),
    "QUEST": ("Quests", "earn"),
    "LOOT": ("Loot", "earn"),
    "MAIL": ("Mail", "other"),
    "TRADE": ("Trade window", "other"),
    "BANK": ("Bank", "other"),
    "GUILD": ("Guild bank", "other"),
    "OTHER": ("Other", "other"),
    "UNTRACKED": ("While not recording", "other"),
    "TRANSFER": ("Between your characters", "transfer"),
}


def _preferred(rows, key):
    """Keep the 'simsar' rows of a (character, day) when it has any, else the 'accountant' rows."""
    have_simsar = {key(r) for r in rows if r["source"] == "simsar"}
    return [r for r in rows if r["source"] == "simsar" or key(r) not in have_simsar]


def days(conn):
    rows = [dict(r) for r in conn.execute(
        "SELECT char_key, day, category, source, income, expense, n FROM ledger_days")]
    return [{k: r[k] for k in ("char_key", "day", "category", "income", "expense", "n")}
            for r in _preferred(rows, lambda r: (r["char_key"], r["day"]))]


def balances(conn, characters):
    """Gold at the end of each day per character, carried forward over days without a record, with
    today's balance from the latest bag scan."""
    rows = [dict(r) for r in conn.execute("SELECT char_key, day, source, balance FROM balances")]
    by_char = defaultdict(dict)
    for r in _preferred(rows, lambda r: (r["char_key"], r["day"])):
        by_char[r["char_key"]][r["day"]] = r["balance"]
    return {k: sorted(v.items()) for k, v in by_char.items()}


def transactions(conn, limit=500):
    rows = [dict(r) for r in conn.execute(
        "SELECT char_key, t, amount, category, source, zone FROM ledger_tx ORDER BY t DESC LIMIT ?", (limit * 2,))]
    # The same gold change can be in both sources; a simsar record within a minute wins.
    simsar = defaultdict(list)
    for r in rows:
        if r["source"] == "simsar":
            simsar[(r["char_key"], r["amount"])].append(r["t"])
    out = [r for r in rows if r["source"] == "simsar"
           or not any(abs(t - r["t"]) <= 60 for t in simsar.get((r["char_key"], r["amount"]), []))]
    return out[:limit]


def auction_items(conn):
    """Per item: what sold, what the auction house kept, what you bought, and how often listings failed."""
    out = defaultdict(lambda: {"sold": 0, "sales": 0, "gross": 0, "cut": 0, "net": 0, "bought": 0, "purchases": 0,
                               "spent": 0, "expired": 0, "cancelled": 0, "last": 0})
    for r in conn.execute("SELECT item_name, quantity, bid, consignment, seen_at FROM ah_invoices"):
        e = out[r["item_name"]]
        e["sales"] += 1
        e["sold"] += r["quantity"] or 1
        e["gross"] += r["bid"] or 0
        e["cut"] += r["consignment"] or 0
        e["net"] += (r["bid"] or 0) - (r["consignment"] or 0)
        e["last"] = max(e["last"], r["seen_at"] or 0)
    for r in conn.execute("SELECT kind, item_name, quantity, amount, seen_at FROM mail_events"):
        e = out[r["item_name"]]
        if r["kind"] == "bought":
            e["purchases"] += 1
            e["bought"] += r["quantity"] or 1
            e["spent"] += r["amount"] or 0
        else:
            e[r["kind"]] += 1
        e["last"] = max(e["last"], r["seen_at"] or 0)
    names = {r["name"]: dict(r) for r in conn.execute("SELECT item_id, name, quality, icon_id FROM items")}
    rows = []
    for name, e in out.items():
        listings = e["sales"] + e["expired"] + e["cancelled"]
        meta = names.get(name) or {}
        rows.append({
            "name": name, "item_id": meta.get("item_id"), "quality": meta.get("quality"),
            "icon_id": meta.get("icon_id"), **e,
            "avg_sale": e["net"] / e["sold"] if e["sold"] else None,
            "avg_buy": e["spent"] / e["bought"] if e["bought"] else None,
            # Sold auctions out of all that ended; cancelled ones count as not sold.
            "sell_through": e["sales"] / listings if listings and (e["expired"] or e["cancelled"]) else
                            (1.0 if e["sales"] else None),
            "margin": e["net"] - e["spent"],
        })
    rows.sort(key=lambda r: -(r["net"] + r["spent"]))
    return rows


def build(conn):
    chars = [dict(r) for r in conn.execute(
        "SELECT char_key, name, realm, class, faction, money, money_at FROM characters ORDER BY name")]
    known = {c["char_key"] for c in chars}
    day_rows = days(conn)
    bal = balances(conn, chars)
    # Characters only Accountant Classic knows about still belong in the ledger.
    for key in sorted({r["char_key"] for r in day_rows} | set(bal)):
        if key not in known:
            chars.append({"char_key": key, "name": key.split("-")[0], "realm": key.partition("-")[2], "class": None,
                          "faction": None, "money": (bal.get(key) or [(None, None)])[-1][1], "money_at": None})
    sources = {r[0] for r in conn.execute("SELECT DISTINCT source FROM ledger_days")}
    first = conn.execute("SELECT MIN(day) FROM ledger_days WHERE source = 'simsar'").fetchone()[0]
    return {
        "characters": chars,
        "categories": {k: {"label": label, "kind": kind} for k, (label, kind) in CATEGORIES.items()},
        "days": day_rows,
        "balances": bal,
        "transactions": transactions(conn),
        "auction_items": auction_items(conn),
        "sources": sorted(sources),
        "simsar_since": first,
    }
