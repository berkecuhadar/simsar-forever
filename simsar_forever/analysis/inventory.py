"""What the items in your characters' bags and banks are worth at today's prices, and what to do with them."""

from . import sellplan


def build(conn, result, cfg=None):
    by_id, fees = result["by_id"], result["fees"]
    fc = result.get("forecast") or {"items": {}, "backtest": {}}
    allowed = sellplan.hold_allowed(fc, cfg) if cfg else False
    info = {r["item_id"]: dict(r) for r in conn.execute(
        "SELECT item_id, name, vendor_sell, quality, icon_id FROM items")}
    chars = {r["char_key"]: dict(r) for r in conn.execute("SELECT * FROM characters ORDER BY name")}

    held = {}
    for r in conn.execute("SELECT char_key, location, item_id, count, bound FROM inventory"):
        e = held.setdefault((r["char_key"], r["item_id"]), {"bags": 0, "bank": 0, "bound": 0})
        e[r["location"]] += r["count"]
        e["bound"] += r["bound"]

    rows = []
    totals = {k: {"ah_value": 0.0, "vendor_value": 0.0, "value": 0.0, "items": 0} for k in chars}
    for (char_key, item_id), e in held.items():
        it = by_id.get(item_id) or {}
        meta = info.get(item_id) or {}
        count = e["bags"] + e["bank"]
        bound = min(e["bound"], count)
        tradable = count - bound
        unit_ah = it.get("net_sell")
        vendor = meta.get("vendor_sell") or 0
        ah_value = tradable * unit_ah if unit_ah else None
        # Sell each unit wherever it fetches more; bound units can only go to a vendor.
        best_unit = max(unit_ah or 0, vendor)
        value = tradable * best_unit + bound * vendor
        spd = it.get("my_sales_per_day")
        rows.append({
            "char_key": char_key,
            "item_id": item_id,
            "name": it.get("name") or meta.get("name") or f"Item {item_id}",
            "quality": meta.get("quality"),
            "icon_id": meta.get("icon_id"),
            "group": it.get("group"),
            "bags": e["bags"],
            "bank": e["bank"],
            "count": count,
            "bound": bound,
            "price_now": it.get("price_now"),
            "sell_price": it.get("sell_price"),
            "unit_ah": unit_ah,
            "vendor_sell": vendor or None,
            "ah_value": ah_value,
            "vendor_value": count * vendor if vendor else None,
            "value": value,
            "sell_where": "bound" if tradable == 0 else "auction" if (unit_ah or 0) >= vendor and unit_ah else
                          "vendor" if vendor else "unknown",
            "my_sales_per_day": spd,
            "days_to_sell": tradable / spd if spd and tradable else None,
            "flags": it.get("flags", []),
            **({"plan": sellplan.advise({**it, "vendor_sell": vendor}, fc["items"].get(item_id), cfg, allowed,
                                        quantity=count, bound=bound)} if cfg else {}),
        })
        t = totals.setdefault(char_key, {"ah_value": 0.0, "vendor_value": 0.0, "value": 0.0, "items": 0})
        t["ah_value"] += ah_value or 0
        t["vendor_value"] += count * vendor
        t["value"] += value
        t["items"] += count

    characters = []
    for key, c in chars.items():
        characters.append({**c, **totals.get(key, {})})
    return {
        "characters": characters,
        "items": sorted(rows, key=lambda r: -r["value"]),
        "ah_cut": fees.ah_cut,
        "auction_house": fees.auction_house,
    }
