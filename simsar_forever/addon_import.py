"""Import the SavedVariables written by the in-game Simsar Forever addon (addon/SimsarForever).

Before 0.2.0 the addon was called SimsarForeverExport and saved `SimsarForeverExportDB` to
SimsarForeverExport.lua; both files are read, so nothing recorded by the old addon is lost.
"""

import statistics
import time
from pathlib import Path

from . import db, lua

SUPPORTED_VERSIONS = {1}
VARIABLES = ("SimsarForeverDB", "SimsarForeverExportDB")
PROFESSIONS = ("Alchemy", "Blacksmithing", "Cooking", "Enchanting", "Engineering", "First Aid", "Fishing",
               "Herbalism", "Inscription", "Jewelcrafting", "Leatherworking", "Mining", "Skinning", "Tailoring")


def profession_name(raw):
    """'Classic Leatherworking' -> 'Leatherworking'. Unknown names are kept as they are."""
    text = (raw or "").lower()
    for p in PROFESSIONS:
        if p.lower() in text:
            return p
    return raw or "Unknown"


class AddonFormatError(ValueError):
    pass


def _items(table):
    if isinstance(table, dict):
        return table.items()
    if isinstance(table, list):
        return enumerate(table, 1)
    return ()


def _int(v):
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _reagents(raw):
    out = []
    for _, r in _items(raw):
        if not isinstance(r, dict) or not (r.get("id") or r.get("name")):
            continue
        out.append({"id": _int(r.get("id")), "name": r.get("name"), "count": r.get("count") or 1})
    return out


def recipe_key(prof, name):
    return f"addon:{profession_name(prof)}|{name}"


def _store_recipe(conn, key, prof, name, product_id, product_name, ymin, ymax, learned, source,
                  reagents, recipe_item_id=None, trainer_cost=None, skill_req=None):
    conn.execute(
        "INSERT OR REPLACE INTO recipes(recipe_key, profession, name, product_id, product_name, yield_min, "
        "yield_max, learned, recipe_item_id, source, updated_at, trainer_cost, skill_req) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (key, prof, name, product_id, product_name, ymin, ymax, learned, recipe_item_id, source, int(time.time()),
         trainer_cost, skill_req))
    conn.execute("DELETE FROM recipe_reagents WHERE recipe_key = ?", (key,))
    merged = {}
    for r in reagents:
        k = (r["id"], r["name"] if r["id"] is None else None)
        merged.setdefault(k, {**r, "count": 0})["count"] += r["count"]
    conn.executemany("INSERT INTO recipe_reagents(recipe_key, item_id, name, count) VALUES(?,?,?,?)",
                     [(key, r["id"], r["name"], r["count"]) for r in merged.values()])


def load_saved(path):
    saved = lua.load(Path(path))
    for name in VARIABLES:
        if isinstance(saved.get(name), dict):
            return saved[name]
    raise AddonFormatError("SimsarForeverDB is missing; has the addon run and have you used /reload?")


def import_file(conn, path):
    data = load_saved(path)
    if data.get("version") not in SUPPORTED_VERSIONS:
        raise AddonFormatError(f"Simsar Forever addon data version {data.get('version')!r} is not supported")

    names, vendor, looks = {}, {}, {}
    for item_id, info in _items(data.get("items")):
        if isinstance(info, dict) and _int(item_id):
            if info.get("name"):
                names[int(item_id)] = info["name"]
            if _int(info.get("vendor")) is not None:
                vendor[int(item_id)] = int(info["vendor"])
            if _int(info.get("quality")) is not None or _int(info.get("icon")) is not None:
                looks[int(item_id)] = (_int(info.get("quality")), _int(info.get("icon")))
    db.upsert_names(conn, names)
    db.upsert_vendor_prices(conn, vendor)
    for item_id, icon in _items(data.get("icons")):
        if _int(item_id) and _int(icon) and int(item_id) not in looks:
            looks[int(item_id)] = (None, int(icon))
    db.upsert_item_looks(conn, looks)
    merchant = {}
    for item_id, m in _items(data.get("merchant")):
        if isinstance(m, dict) and _int(item_id) and isinstance(m.get("price"), (int, float)) and m["price"] > 0:
            merchant[int(item_id)] = (m.get("name"), float(m["price"]))
    db.upsert_vendor_buy(conn, merchant)
    vendor_recipes = import_vendor_recipes(conn, data.get("merchantRecipes"))

    known = _known_by_any_character(data.get("characters"))
    recipes = 0
    # Addon 0.1.0 sometimes saved recipes while the client reported an empty profession name; they
    # are duplicates of a named entry.
    named = {r.get("name") for _, r in _items(data.get("recipes")) if isinstance(r, dict) and r.get("prof")}
    for _, r in _items(data.get("recipes")):
        if not isinstance(r, dict) or not r.get("name"):
            continue
        if not r.get("prof") and r["name"] in named:
            continue
        product_id = _int(r.get("itemID"))
        key = recipe_key(r.get("prof"), r["name"])
        learned = None if r.get("learned") is None else int(bool(r.get("learned")))
        if key in known:
            learned = int(known[key])
        _store_recipe(
            conn, key, profession_name(r.get("prof")), r["name"], product_id,
            names.get(product_id) if product_id else None,
            r.get("yieldMin") or 1, r.get("yieldMax") or r.get("yieldMin") or 1,
            learned, f"addon-{r.get('source') or 'window'}", _reagents(r.get("reagents")),
            trainer_cost=_int(r.get("trainerCost")), skill_req=_int(r.get("skill")))
        recipes += 1

    recipe_items = 0
    for item_id, r in _items(data.get("recipeItems")):
        if not isinstance(r, dict) or not r.get("product"):
            continue
        prof = profession_name(r["prof"]) if r.get("prof") else r.get("kind") or "?"
        _store_recipe(conn, f"recipe-item:{item_id}", prof, r["product"], None, r["product"],
                      1, 1, None, "addon-recipe-item", _reagents(r.get("reagents")), _int(item_id),
                      skill_req=_int(r.get("skill")))
        recipe_items += 1

    invoices = []
    for _, inv in _items(data.get("invoices")):
        if isinstance(inv, dict) and _int(inv.get("bid")):
            invoices.append((_int(inv.get("seen")) or 0, inv.get("item"), _int(inv.get("count")),
                             _int(inv["bid"]), _int(inv.get("buyout")), _int(inv.get("deposit")),
                             _int(inv.get("consignment")), inv.get("char")))
    conn.executemany("INSERT OR IGNORE INTO ah_invoices(seen_at, item_name, quantity, bid, buyout, deposit, "
                     "consignment, char_key) VALUES(?,?,?,?,?,?,?,?)", invoices)
    mail = import_mail(conn, data.get("mail"))

    characters = import_characters(conn, data.get("characters"))
    conn.commit()

    return {
        "recipes": recipes,
        "recipe_items": recipe_items,
        "invoices": len(invoices),
        "mail_events": mail,
        "items": len(names),
        "merchant_prices": len(merchant),
        "vendor_recipes": vendor_recipes,
        "characters": characters,
        "build": data.get("build"),
        "realm": data.get("realm"),
        "faction": data.get("faction"),
        "last_error": (data.get("stats") or {}).get("lastError"),
    }


def _known_by_any_character(chars):
    """recipe_key -> True when any character has learned it, False when characters only saw it unlearned."""
    out = {}
    for _, c in _items(chars):
        if not isinstance(c, dict):
            continue
        for key, learned in _items(c.get("known")):
            prof, _, name = str(key).partition("|")
            k = recipe_key(prof, name)
            out[k] = out.get(k, False) or bool(learned)
    return out


def import_vendor_recipes(conn, raw):
    rows = []
    for item_id, r in _items(raw):
        if isinstance(r, dict) and _int(item_id) and _int(r.get("price")):
            rows.append((int(item_id), r.get("name"), _int(r["price"]), int(bool(r.get("limited"))),
                         r.get("vendor"), r.get("zone"), _int(r.get("seen"))))
    conn.executemany("INSERT OR REPLACE INTO vendor_recipes VALUES(?,?,?,?,?,?,?)", rows)
    return len(rows)


def import_mail(conn, raw):
    rows = []
    for key, m in _items(raw):
        if isinstance(m, dict) and m.get("kind") in ("bought", "expired", "cancelled"):
            rows.append((str(key), m["kind"], _int(m.get("seen")) or 0, m.get("char"), m.get("item"),
                         _int(m.get("itemID")), _int(m.get("count")), _int(m.get("amount"))))
    conn.executemany("INSERT OR IGNORE INTO mail_events VALUES(?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def import_characters(conn, chars):
    count = 0
    for key, c in _items(chars):
        if not isinstance(c, dict):
            continue
        key = str(key)
        conn.execute(
            "INSERT INTO characters(char_key, name, realm, class, faction, money, bags_at, bank_at, money_at) "
            "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(char_key) DO UPDATE SET "
            "name = excluded.name, realm = excluded.realm, class = excluded.class, faction = excluded.faction, "
            "money = COALESCE(excluded.money, characters.money), bags_at = excluded.bags_at, "
            "bank_at = COALESCE(excluded.bank_at, characters.bank_at), "
            "money_at = COALESCE(excluded.money_at, characters.money_at)",
            (key, c.get("name"), c.get("realm"), c.get("class"), c.get("faction"), _int(c.get("money")),
             _int(c.get("bagsTime")), _int(c.get("bankTime")), _int(c.get("moneyTime"))))
        for location in ("bags", "bank"):
            items = c.get(location)
            if items is None:
                continue  # never seen; keep whatever was stored before
            conn.execute("DELETE FROM inventory WHERE char_key = ? AND location = ?", (key, location))
            rows = []
            for item_id, e in _items(items):
                if _int(item_id) and isinstance(e, dict) and _int(e.get("count")):
                    rows.append((key, location, int(item_id), int(e["count"]), _int(e.get("bound")) or 0))
            conn.executemany("INSERT INTO inventory VALUES(?,?,?,?,?)", rows)
        for prof, p in _items(c.get("professions")):
            if isinstance(p, dict) and _int(p.get("rank")) is not None:
                conn.execute("INSERT OR REPLACE INTO char_professions VALUES(?,?,?,?,?)",
                             (key, profession_name(str(prof)), _int(p["rank"]), _int(p.get("max")),
                              _int(p.get("seen"))))
        for rkey, learned in _items(c.get("known")):
            prof, _, name = str(rkey).partition("|")
            conn.execute("INSERT OR REPLACE INTO char_recipes VALUES(?,?,?)",
                         (key, recipe_key(prof, name), int(bool(learned))))
        import_ledger(conn, key, c.get("ledger"), c.get("balance"), "simsar")
        count += 1
    return count


def import_ledger(conn, char_key, ledger, balance, source):
    """Daily buckets replace what was stored for those days; transactions are only ever added."""
    ledger = ledger if isinstance(ledger, dict) else {}
    for day, cats in _items(ledger.get("days")):
        if not _int(day) or not isinstance(cats, dict):
            continue
        conn.execute("DELETE FROM ledger_days WHERE char_key = ? AND day = ? AND source = ?",
                     (char_key, int(day), source))
        conn.executemany(
            "INSERT INTO ledger_days VALUES(?,?,?,?,?,?,?)",
            [(char_key, int(day), str(cat), source, _int(e.get("i")) or 0, _int(e.get("o")) or 0,
              _int(e.get("n")) or 0)
             for cat, e in cats.items() if isinstance(e, dict)])
    conn.executemany(
        "INSERT OR IGNORE INTO ledger_tx VALUES(?,?,?,?,?,?)",
        [(char_key, _int(r.get("t")), _int(r.get("a")), str(r.get("k") or "OTHER"), source, r.get("z"))
         for _, r in _items(ledger.get("recent"))
         if isinstance(r, dict) and _int(r.get("t")) and _int(r.get("a"))])
    conn.executemany("INSERT OR REPLACE INTO balances VALUES(?,?,?,?)",
                     [(char_key, int(day), source, int(v)) for day, v in _items(balance)
                      if _int(day) and _int(v) is not None])


def measured_fees(conn):
    """Auction house cut seen in your sale mails, for comparison with the configured cut."""
    cuts = [r["consignment"] / r["bid"] for r in conn.execute(
        "SELECT bid, consignment FROM ah_invoices WHERE bid > 0 AND consignment IS NOT NULL")]
    return {
        "ah_cut": round(statistics.median(cuts), 4) if cuts else None,
        "ah_cut_samples": len(cuts),
    }
