"""Write SimsarForeverData.lua into the installed addon, for the advice shown in item tooltips.

The game reads addon files only on login or /reload, so the tooltips show the numbers of the last
/reload. One entry per item, positional to keep the file small:

    SimsarForeverData = { version = 1, built = <unix time>, items = {
      [itemID] = { keep, sales_per_day, advice, expected_change, horizon_days, craft_profit, price_now } } }

`advice` is "sell", "vendor", "hold" or "gradual" (see analysis/sellplan.py); missing values are nil.
"""

import math
import os
import time
from pathlib import Path

from . import auctionator

FILE = "SimsarForeverData.lua"
VERSION = 1


def target(cfg):
    folder = auctionator.addon_dir(cfg, "SimsarForever")
    return folder / FILE if folder and folder.is_dir() else None


def _num(v, digits=0):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "nil"
    if digits == 0:
        return str(int(round(v)))
    return f"{round(v, digits):g}"


def entries(result):
    craft = {}
    for c in result.get("crafts") or []:
        pid, profit = c.get("product_id"), c.get("profit")
        if pid and profit is not None and c.get("yield"):
            per_unit = profit / c["yield"]
            craft[pid] = max(craft.get(pid, -math.inf), per_unit)
    advice = result.get("advice") or {}
    out = {}
    for it in result["items"]:
        a = advice.get(it["item_id"]) or {}
        row = [it.get("net_sell"), it.get("my_sales_per_day"), a.get("advice"), a.get("expected_change"),
               a.get("horizon"), craft.get(it["item_id"]), it.get("price_now")]
        if any(v is not None for v in row):
            out[it["item_id"]] = row
    return out


def render(result, now=None):
    lines = [
        "-- Written by the Simsar Forever dashboard. Do not edit; it is replaced as prices change.",
        f"SimsarForeverData = {{ version = {VERSION}, built = {int(now or time.time())}, items = {{",
    ]
    for item_id, (keep, spd, advice, change, horizon, craft, price) in sorted(entries(result).items()):
        fields = [_num(keep), _num(spd, 1), f'"{advice}"' if advice else "nil", _num(change, 3),
                  _num(horizon), _num(craft), _num(price)]
        while fields and fields[-1] == "nil":
            fields.pop()
        lines.append(f"[{item_id}]={{{','.join(fields)}}},")
    lines.append("} }")
    return "\n".join(lines) + "\n"


def write(cfg, conn, result):
    path = target(cfg)
    if path is None:
        return None
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(render(result), encoding="utf-8")
    os.replace(tmp, path)
    return path
