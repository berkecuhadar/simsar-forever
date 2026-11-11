"""Import SimsarForeverExport.lua written by the in-game addon in addon/SimsarForeverExport."""

import statistics
import time
from pathlib import Path

from . import db, lua

SUPPORTED_VERSIONS = {1}
DURATIONS = (2, 8, 24)


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

    names, vendor = {}, {}
    for item_id, info in _items(data.get("items")):
        if isinstance(info, dict) and _int(item_id):
            if info.get("name"):
                names[int(item_id)] = info["name"]
            if _int(info.get("vendor")) is not None:
                vendor[int(item_id)] = int(info["vendor"])
    db.upsert_names(conn, names)
    db.upsert_vendor_prices(conn, vendor)
    merchant = {}
    for item_id, m in _items(data.get("merchant")):
        if isinstance(m, dict) and _int(item_id) and isinstance(m.get("price"), (int, float)) and m["price"] > 0:
            merchant[int(item_id)] = (m.get("name"), float(m["price"]))
    db.upsert_vendor_buy(conn, merchant)

    recipes = 0
    for key, r in _items(data.get("recipes")):
        if not isinstance(r, dict) or not r.get("name"):
            continue
        product_id = _int(r.get("itemID"))
        _store_recipe(
            conn, f"addon:{key}", r.get("prof") or "?", r["name"], product_id,
            names.get(product_id) if product_id else None,
            r.get("yieldMin") or 1, r.get("yieldMax") or r.get("yieldMin") or 1,
            1 if r.get("learned") else 0, f"addon-{r.get('source') or 'window'}", _reagents(r.get("reagents")))
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

    by_name = {n.lower(): i for i, n in conn.execute("SELECT item_id, name FROM items WHERE name IS NOT NULL")}
    deposits = []
    for _, d in _items(data.get("deposits")):
        if not isinstance(d, dict):
            continue
        item = d.get("item")
        item_id = _int(item) if not isinstance(item, str) else by_name.get(item.lower())
        if item_id and _int(d.get("deposit")) is not None:
            deposits.append((_int(d.get("seen")) or 0, item_id, _int(d.get("quantity")) or 1,
                             _int(d.get("hours")), _int(d["deposit"]), _int(d.get("vendor"))))
    conn.executemany("INSERT OR IGNORE INTO ah_deposits VALUES(?,?,?,?,?,?)", deposits)
    conn.commit()

    return {
        "recipes": recipes,
        "recipe_items": recipe_items,
        "invoices": len(invoices),
        "deposits": len(deposits),
        "items": len(names),
        "merchant_prices": len(merchant),
        "build": data.get("build"),
        "realm": data.get("realm"),
        "faction": data.get("faction"),
        "last_error": (data.get("stats") or {}).get("lastError"),
    }


def measured_fees(conn):
    """AH cut and deposit rates observed in game. Values are None until there is data."""
    cuts = [r["consignment"] / r["bid"] for r in conn.execute(
        "SELECT bid, consignment FROM ah_invoices WHERE bid > 0 AND consignment IS NOT NULL")]
    rates = {}
    for hours in DURATIONS:
        samples = []
        for r in conn.execute(
                "SELECT d.deposit, d.quantity, COALESCE(d.vendor_sell, i.vendor_sell) AS vendor "
                "FROM ah_deposits d LEFT JOIN items i ON i.item_id = d.item_id WHERE d.hours = ?", (hours,)):
            if r["vendor"] and r["quantity"]:
                samples.append(r["deposit"] / (r["vendor"] * r["quantity"]))
        if samples:
            rates[hours] = {"rate": statistics.median(samples), "samples": len(samples)}
    return {
        "ah_cut": round(statistics.median(cuts), 4) if cuts else None,
        "ah_cut_samples": len(cuts),
        "deposit_rates": rates,
    }
