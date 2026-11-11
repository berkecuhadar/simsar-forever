import time

from ..money import fmt

MAX_PER_KIND = 5


def generate(items, crafts, cfg, now=None):
    """Alert candidates for tracked items. The caller stores them; dedupe keys make each one fire
    at most once per day."""
    a, an = cfg["alerts"], cfg["analysis"]
    if not a["enabled"]:
        return []
    day = int((now or time.time()) // 86400)

    cheap = []
    for it in items:
        if not it["groups"] or "cheap" not in it["flags"] or "possible_misprice" in it["flags"]:
            continue
        fresh = it["price_src"] == "auctionator" or (it["price_age_h"] or 99) <= an["stale_hours"]
        if not fresh or (it["my_sales_per_day"] or 0) < a["min_sales_per_day"]:
            continue
        # In a falling market "below the two-week value" is just the trend. Only alert once there is
        # enough history to see that the price is not simply sliding.
        if (it["n_days"] or 0) < an["min_days_trend"] or it["trend"] is None or it["trend"] < -0.02:
            continue
        cheap.append(it)
    cheap.sort(key=lambda i: -(abs(i["disc_ref"]) * (i["reference"] or 0) * (i["my_sales_per_day"] or 0)))
    out = [{
        "kind": "cheap", "item_id": it["item_id"],
        "dedupe_key": f"cheap:{it['item_id']}:{day}",
        "title": f"{it['name']} is cheap",
        "message": f"{fmt(it['price_now'])}, {abs(it['disc_ref']):.0%} below its usual {fmt(it['reference'])}.",
    } for it in cheap[:MAX_PER_KIND]]

    min_profit = a["min_craft_profit_gold"] * 10000
    good = [c for c in crafts if c["verdict"] == "craft" and (c["profit"] or 0) >= min_profit
            and (c["product_sales_per_day"] or 0) >= a["min_sales_per_day"]]
    good.sort(key=lambda c: -(c["profit_day"] or 0))
    out += [{
        "kind": "craft", "item_id": c["product_id"],
        "dedupe_key": f"craft:{c['recipe_key']}:{day}",
        "title": f"Craft {c['name']}",
        "message": f"About {fmt(c['profit'])} per craft after fees, buying all materials.",
    } for c in good[:MAX_PER_KIND]]
    return out


def store(conn, alerts, now=None):
    now = int(now or time.time())
    before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO alerts(created_at, kind, item_id, dedupe_key, title, message) VALUES(?,?,?,?,?,?)",
        [(now, a["kind"], a["item_id"], a["dedupe_key"], a["title"], a["message"]) for a in alerts])
    inserted = conn.total_changes - before
    conn.execute("DELETE FROM alerts WHERE created_at < ?", (now - 14 * 86400,))
    conn.commit()
    return inserted
