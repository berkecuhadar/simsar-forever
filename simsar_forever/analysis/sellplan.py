"""Sell now, sell to a vendor, sell a few at a time, or hold: one piece of advice per item.

    vendor   a vendor pays at least what one auction sale leaves you after the cut
    hold     the forecast expects at least advice.hold_min_gain more within advice.horizon_days, with
             at least advice.hold_min_probability chance of a rise, AND the backtest shows the
             forecasts beat "no change" with statistical evidence (otherwise hold is never advised)
    gradual  you hold more than the market buys in advice.gradual_days: list a few at a time
    sell     otherwise: the auction house now

Listing deposits are not part of any calculation (they are refunded when an item sells).
"""

ADVICE = {
    "sell": "Sell on the auction house now",
    "vendor": "Sell to a vendor",
    "hold": "Hold",
    "gradual": "Sell a few at a time",
    "bound": "Soulbound: vendor only",
    "none": "No price known",
}


def hold_allowed(fc, cfg):
    bt = (fc.get("backtest") or {}).get(cfg["advice"]["horizon_days"]) or {}
    return bool(bt.get("ok") and bt.get("beats_naive"))


def advise(item, fc_item, cfg, allowed, quantity=None, bound=0):
    """item: a row of the market table; fc_item: forecast.build()['items'][item_id] or None."""
    a = cfg["advice"]
    H = a["horizon_days"]
    net, vendor = item.get("net_sell"), item.get("vendor_sell") or 0
    spd = item.get("my_sales_per_day")
    f = (fc_item or {}).get(H)
    out = {"advice": None, "horizon": H, "expected_change": None, "p_up": None, "low": None, "high": None,
           "hold_allowed": allowed, "days_to_sell": None}
    if f:
        out.update(expected_change=f["change"], p_up=f["p_up"], low=f["low"], high=f["high"])
    tradable = (quantity - bound) if quantity is not None else None
    if quantity is not None and tradable <= 0:
        out["advice"] = "bound"
        return out
    if not net:
        out["advice"] = "vendor" if vendor else ("none" if quantity is not None else None)
        return out
    if vendor and vendor >= net:
        out["advice"] = "vendor"
        return out
    if allowed and f and f["change"] >= a["hold_min_gain"] and f["p_up"] >= a["hold_min_probability"]:
        out["advice"] = "hold"
        return out
    if tradable is not None and spd:
        out["days_to_sell"] = tradable / spd
        if out["days_to_sell"] > a["gradual_days"]:
            out["advice"] = "gradual"
            return out
    if not spd and quantity is None:
        return out                           # nothing sells; no advice in tooltips
    out["advice"] = "sell"
    return out


def advice_all(items, fc, cfg):
    """Advice for every item, without a quantity (used for tooltips)."""
    allowed = hold_allowed(fc, cfg)
    out = {}
    for it in items:
        r = advise(it, fc["items"].get(it["item_id"]), cfg, allowed)
        if r["advice"]:
            out[it["item_id"]] = r
    return out
