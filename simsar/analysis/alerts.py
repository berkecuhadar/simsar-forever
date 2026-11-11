import time

from ..money import fmt


def generate(items, crafts, cfg, now=None):
    """Alert candidates for tracked items. The caller stores them; dedupe keys make each one fire
    at most once per day."""
    a = cfg["alerts"]
    if not a["enabled"]:
        return []
    day = int((now or time.time()) // 86400)
    out = []
    for it in items:
        if not it["groups"] or "below_historical" not in it["flags"]:
            continue
        fresh = it["price_src"] == "auctionator" or (it["price_age_h"] or 99) <= cfg["analysis"]["stale_hours"]
        if not fresh or (it["my_sales_per_day"] or 0) < a["min_sales_per_day"]:
            continue
        out.append({
            "kind": "below_historical", "item_id": it["item_id"],
            "dedupe_key": f"below:{it['item_id']}:{day}",
            "title": f"{it['name']} is cheap",
            "message": f"{fmt(it['price_now'])}, {abs(it['disc_hist']):.0%} below its average of {fmt(it['historical'])}.",
        })
    min_profit = a["min_craft_profit_gold"] * 10000
    for c in crafts:
        if c["verdict"] == "craft" and (c["profit"] or 0) >= min_profit and \
                (c["product_sales_per_day"] or 0) >= a["min_sales_per_day"]:
            out.append({
                "kind": "craft", "item_id": c["product_id"],
                "dedupe_key": f"craft:{c['recipe_key']}:{day}",
                "title": f"Craft {c['name']}",
                "message": f"About {fmt(c['profit'])} per craft after fees, buying all materials.",
            })
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
