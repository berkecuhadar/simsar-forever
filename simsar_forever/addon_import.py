"""Import SimsarForeverExport.lua written by the in-game addon in addon/SimsarForeverExport."""

import statistics
import time
from pathlib import Path

from . import db, lua

SUPPORTED_VERSIONS = {1}
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


def _store_recipe(conn, key, prof, name, product_id, product_name, ymin, ymax, learned, source,
                  reagents, recipe_item_id=None):
    conn.execute(
        "INSERT OR REPLACE INTO recipes(recipe_key, profession, name, product_id, product_name, yield_min, "
        "yield_max, learned, recipe_item_id, source, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (key, prof, name, product_id, product_name, ymin, ymax, learned, recipe_item_id, source, int(time.time())))
    conn.execute("DELETE FROM recipe_reagents WHERE recipe_key = ?", (key,))
    merged = {}
    for r in reagents:
        k = (r["id"], r["name"] if r["id"] is None else None)
        merged.setdefault(k, {**r, "count": 0})["count"] += r["count"]
    conn.executemany("INSERT INTO recipe_reagents(recipe_key, item_id, name, count) VALUES(?,?,?,?)",
                     [(key, r["id"], r["name"], r["count"]) for r in merged.values()])


def import_file(conn, path):
    saved = lua.load(Path(path))
    data = saved.get("SimsarForeverExportDB")
    if not isinstance(data, dict):
        raise AddonFormatError("SimsarForeverExportDB is missing; has the addon run and have you used /reload?")
    if data.get("version") not in SUPPORTED_VERSIONS:
        raise AddonFormatError(f"SimsarForeverExport data version {data.get('version')!r} is not supported")

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

    recipes = 0
    # Addon 0.1.0 sometimes saved recipes while the client reported an empty profession name; they
    # are duplicates of a named entry.
    named = {r.get("name") for _, r in _items(data.get("recipes")) if isinstance(r, dict) and r.get("prof")}
    for key, r in _items(data.get("recipes")):
        if not isinstance(r, dict) or not r.get("name"):
            continue
        if not r.get("prof") and r["name"] in named:
            continue
        product_id = _int(r.get("itemID"))
        _store_recipe(
            conn, f"addon:{profession_name(r.get('prof'))}|{r['name']}", profession_name(r.get("prof")), r["name"], product_id,
            names.get(product_id) if product_id else None,
            r.get("yieldMin") or 1, r.get("yieldMax") or r.get("yieldMin") or 1,
            None if r.get("learned") is None else int(bool(r.get("learned"))),
            f"addon-{r.get('source') or 'window'}", _reagents(r.get("reagents")))
        recipes += 1

    recipe_items = 0
    for item_id, r in _items(data.get("recipeItems")):
        if not isinstance(r, dict) or not r.get("product"):
            continue
        _store_recipe(conn, f"recipe-item:{item_id}", r.get("kind") or "?", r["product"], None, r["product"],
                      1, 1, None, "addon-recipe-item", _reagents(r.get("reagents")), _int(item_id))
        recipe_items += 1

    invoices = []
    for _, inv in _items(data.get("invoices")):
        if isinstance(inv, dict) and _int(inv.get("bid")):
            invoices.append((_int(inv.get("seen")) or 0, inv.get("item"), _int(inv.get("count")),
                             _int(inv["bid"]), _int(inv.get("buyout")), _int(inv.get("deposit")),
                             _int(inv.get("consignment"))))
    conn.executemany("INSERT OR IGNORE INTO ah_invoices VALUES(?,?,?,?,?,?,?)", invoices)

    characters = import_characters(conn, data.get("characters"))
    conn.commit()

    return {
        "recipes": recipes,
        "recipe_items": recipe_items,
        "invoices": len(invoices),
        "items": len(names),
        "merchant_prices": len(merchant),
        "characters": characters,
        "build": data.get("build"),
        "realm": data.get("realm"),
        "faction": data.get("faction"),
        "last_error": (data.get("stats") or {}).get("lastError"),
    }


def import_characters(conn, chars):
    count = 0
    for key, c in _items(chars):
        if not isinstance(c, dict):
            continue
        key = str(key)
        conn.execute(
            "INSERT INTO characters VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(char_key) DO UPDATE SET "
            "name = excluded.name, realm = excluded.realm, class = excluded.class, faction = excluded.faction, "
            "money = excluded.money, bags_at = excluded.bags_at, bank_at = excluded.bank_at",
            (key, c.get("name"), c.get("realm"), c.get("class"), c.get("faction"), _int(c.get("money")),
             _int(c.get("bagsTime")), _int(c.get("bankTime"))))
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
        count += 1
    return count


def measured_fees(conn):
    """Auction house cut seen in your sale mails, for comparison with the configured cut."""
    cuts = [r["consignment"] / r["bid"] for r in conn.execute(
        "SELECT bid, consignment FROM ah_invoices WHERE bid > 0 AND consignment IS NOT NULL")]
    return {
        "ah_cut": round(statistics.median(cuts), 4) if cuts else None,
        "ah_cut_samples": len(cuts),
    }
