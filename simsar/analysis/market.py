"""Per-item market table: prices, volume, fees, history statistics, flip opportunity."""

import time
from collections import defaultdict

from . import fees as feemod
from . import stats
from .. import groups as groupmod

LABELS = {
    "fast_profitable": "Fast and profitable",
    "fast_thin": "Fast, thin margin",
    "slow_profitable": "Profitable but slow",
    "avoid": "Avoid",
    "unknown": "Not enough data",
}

FLAGS = {
    "stale": "TSM data is older than the stale limit",
    "no_volume": "No recorded sales in the region",
    "thin_volume": "Sells less than once a day on your realm",
    "bubble": "Market value far above its long-term average",
    "cheap": "Cheapest listing well below the reference price",
    "possible_misprice": "Cheapest listing is far below market value; may be a mistake or bait",
    "not_live": "No recent scan price; using TSM data",
    "low_confidence": "Too few price points for volatility",
    "no_vendor_price": "Vendor price unknown, deposit not included",
}


HISTORY_KEYS = ("period_min", "period_max", "period_median", "n_points", "n_days", "volatility", "trend")


def _latest(conn, table, cols):
    sql = f"SELECT item_id, MAX(updated_at) AS updated_at, {', '.join(cols)} FROM {table} GROUP BY item_id"
    return {r["item_id"]: dict(r) for r in conn.execute(sql)}


def load_history(conn, since):
    """Daily price points per item from TSM realm minimum buyouts and Auctionator daily lows."""
    obs = defaultdict(list)
    for item_id, ts, price in conn.execute(
            "SELECT item_id, updated_at, min_buyout FROM tsm_realm WHERE updated_at >= ? AND min_buyout > 0",
            (since,)):
        obs[item_id].append((ts, price))
    for item_id, ts, price in conn.execute(
            "SELECT item_id, day_ts, low FROM ato_daily WHERE day_ts >= ? AND low > 0", (since,)):
        obs[item_id].append((ts, price))
    return obs


def history_stats(points, now, cfg):
    a = cfg["analysis"]
    if not points:
        return {}
    prices = [p for _, p in points]
    by_day = defaultdict(list)
    for ts, p in points:
        by_day[int(ts // 86400)].append(p)
    days = sorted(by_day)
    daily = [stats.median(by_day[d]) for d in days]
    out = {
        "period_min": min(prices),
        "period_max": max(prices),
        "period_median": stats.median(prices),
        "n_points": len(prices),
        "n_days": len(days),
        "volatility": None,
        "trend": None,
    }
    if len(prices) >= a["min_points_volatility"]:
        out["volatility"] = stats.robust_cv(daily if len(daily) >= a["min_points_volatility"] else prices)
    if len(days) >= a["min_days_trend"]:
        out["trend"] = stats.daily_trend(days, daily)
    out["_prices"] = prices
    return out


def _positive(*values):
    for v in values:
        if v is not None and v > 0:
            return v
    return None


def build(conn, cfg, fees, groups=None, recipe_items=None, now=None):
    now = now or time.time()
    a, eco = cfg["analysis"], cfg["economy"]
    groups = groups if groups is not None else groupmod.load(cfg)

    realm = _latest(conn, "tsm_realm", ["market", "min_buyout", "recent", "historical"])
    region = _latest(conn, "tsm_region", ["market", "historical", "avg_sale", "sale_rate", "sold_per_day"])
    ato = {r["item_id"]: dict(r) for r in conn.execute("SELECT * FROM ato_current")}
    available = {r[0]: r[1] for r in conn.execute(
        "SELECT item_id, available FROM ato_daily d WHERE day_ts = "
        "(SELECT MAX(day_ts) FROM ato_daily WHERE item_id = d.item_id)")}
    info = {r["item_id"]: dict(r) for r in conn.execute("SELECT item_id, name, vendor_sell FROM items")}
    history = load_history(conn, now - a["history_days"] * 86400)

    ids = set(realm) | set(region) | set(ato)
    names = {i: (info.get(i) or {}).get("name") or f"Item {i}" for i in ids}
    membership = groupmod.assign(names, groups, recipe_items)
    realm_share, market_share = eco["realm_share"], eco["market_share"]

    items = []
    for item_id in ids:
        r, g, at = realm.get(item_id, {}), region.get(item_id, {}), ato.get(item_id)
        vendor = (info.get(item_id) or {}).get("vendor_sell")
        flags = []

        # The cheapest listing comes from whichever scan is newer: yours or TSM's.
        listings = []
        if at is not None and at["price"] and now - at["seen_ts"] <= a["live_price_hours"] * 3600:
            listings.append((at["seen_ts"], at["price"], "auctionator"))
        if _positive(r.get("min_buyout")):
            listings.append((r["updated_at"], r["min_buyout"], "tsm_min_buyout"))
        if listings:
            price_ts, price_now, price_src = max(listings)
        else:
            price_now = _positive(r.get("market"), g.get("market"))
            price_src = "tsm_market" if price_now else None
            price_ts = r.get("updated_at") or g.get("updated_at")
        if price_src != "auctionator" and (price_src != "tsm_min_buyout" or now - price_ts > a["stale_hours"] * 3600):
            flags.append("not_live")

        market = _positive(r.get("market"), g.get("market"))
        historical = _positive(r.get("historical"), g.get("historical"))
        reference = historical if a["reference_price"] == "historical" else market
        avg_sale = _positive(g.get("avg_sale"))
        if eco["sell_price"] == "market":
            sell_ref = market
        else:
            candidates = [v for v in (avg_sale, _positive(r.get("market"))) if v]
            sell_ref = min(candidates) if candidates else market
        # To sell now you have to match the cheapest listing.
        sell_price = min(sell_ref, price_now) if sell_ref and price_now else (sell_ref or price_now)

        sale_rate = g.get("sale_rate")
        spd_region = g.get("sold_per_day")
        realm_spd = spd_region * realm_share if spd_region is not None else None
        my_spd = realm_spd * market_share if realm_spd is not None else None

        dep = feemod.deposit(vendor, fees)
        if dep is None:
            flags.append("no_vendor_price")
        net_sell = feemod.net_per_sale(sell_price, vendor, sale_rate, fees)
        net_ref = feemod.net_per_sale(sell_ref, vendor, sale_rate, fees)

        flip_profit = net_ref - price_now if net_ref is not None and price_now else None
        flip_margin = flip_profit / price_now if flip_profit is not None else None
        flip_profit_day = max(flip_profit, 0) * my_spd if flip_profit is not None and my_spd is not None else None

        h = history_stats(history.get(item_id), now, cfg)
        pctile = stats.percentile_rank(h.pop("_prices", None), price_now)
        disc_ref = price_now / reference - 1 if price_now and reference else None
        disc_hist = price_now / historical - 1 if price_now and historical else None
        bubble_ratio = market / historical if market and historical else None

        data_ts = max([t for t in (r.get("updated_at"), g.get("updated_at")) if t] or [0]) or None
        age_h = (now - data_ts) / 3600 if data_ts else None
        if age_h is not None and age_h > a["stale_hours"]:
            flags.append("stale")
        if not spd_region:
            flags.append("no_volume")
        elif realm_spd < 1:
            flags.append("thin_volume")
        if bubble_ratio and bubble_ratio > a["bubble_ratio"]:
            flags.append("bubble")
        if disc_ref is not None and disc_ref < -cfg["alerts"]["cheap_below"]:
            flags.append("cheap")
        if price_now and market and price_now < 0.4 * market:
            flags.append("possible_misprice")
        if h and h.get("volatility") is None:
            flags.append("low_confidence")

        vol = h.get("volatility")
        confidence = 1 - min(max(vol, 0), 0.6) if vol is not None else 0.6
        if "stale" in flags:
            confidence *= 0.5
        if sale_rate is None:
            confidence *= 0.7
        bubble_penalty = 1 / (1 + max(0.0, disc_ref or 0.0))
        score = flip_profit_day * confidence * bubble_penalty if flip_profit_day is not None else None

        if flip_margin is None or my_spd is None:
            label = "unknown"
        else:
            fast = my_spd >= a["fast_sales_per_day"]
            good = flip_margin >= a["good_margin"]
            label = ("fast_profitable" if fast and good else "fast_thin" if fast and flip_margin > 0
                     else "slow_profitable" if good else "avoid")

        keys = membership.get(item_id, [])
        items.append({
            "item_id": item_id,
            "name": names[item_id],
            "groups": keys,
            "group": keys[0] if keys else None,
            "vendor_sell": vendor,
            "price_now": price_now,
            "price_src": price_src,
            "price_age_h": (now - price_ts) / 3600 if price_ts else None,
            "min_buyout": r.get("min_buyout"),
            "market": market,
            "market_realm": r.get("market"),
            "market_region": g.get("market"),
            "recent": r.get("recent"),
            "historical": historical,
            "avg_sale": avg_sale,
            "sell_ref": sell_ref,
            "sell_price": sell_price,
            "sale_rate": sale_rate,
            "sold_per_day_region": spd_region,
            "sold_per_day_realm": realm_spd,
            "my_sales_per_day": my_spd,
            "available": available.get(item_id),
            "deposit": dep,
            "listings_per_sale": feemod.listings_per_sale(sale_rate, fees),
            "net_sell": net_sell,
            "turnover_day": realm_spd * sell_ref if realm_spd is not None and sell_ref else None,
            "income_day": max(net_sell, 0) * my_spd if net_sell is not None and my_spd is not None else None,
            "flip_profit": flip_profit,
            "flip_margin": flip_margin,
            "flip_profit_day": flip_profit_day,
            **dict.fromkeys(HISTORY_KEYS),
            **h,
            "pctile": pctile,
            "reference": reference,
            "disc_ref": disc_ref,
            "disc_hist": disc_hist,
            "bubble_ratio": bubble_ratio,
            "confidence": confidence,
            "score": score,
            "label": label,
            "flags": flags,
            "data_age_h": age_h,
        })
    items.sort(key=lambda x: -(x["score"] or 0))
    return items
