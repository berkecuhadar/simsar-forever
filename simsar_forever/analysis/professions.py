"""Professions: each character's skill, the recipes it knows, and the ones it could learn.

A recipe can be learned from a trainer (cost from the trainer window), bought from a vendor
(recipes seen in vendor windows) or bought on the auction house (the recipe item's price). The
cheapest of those is the cost to learn; with the recipe's profit per day it gives the payback time.
"""

import re
from collections import defaultdict

from ..addon_import import profession_name

RECIPE_PREFIX = re.compile(r"^(Pattern|Formula|Plans|Recipe|Schematic|Design|Manual|Technique): (.+)$")


def _strip(name):
    m = RECIPE_PREFIX.match(name or "")
    return m.group(2) if m else name


def build(conn, result):
    crafts = result["crafts"]
    by_id = result["by_id"]
    extra = {r["recipe_key"]: dict(r) for r in conn.execute(
        "SELECT recipe_key, trainer_cost, skill_req, recipe_item_id, source FROM recipes")}
    chars = {r["char_key"]: dict(r) for r in conn.execute("SELECT char_key, name, class FROM characters ORDER BY name")}
    skills = defaultdict(list)
    for r in conn.execute("SELECT * FROM char_professions ORDER BY profession"):
        skills[r["char_key"]].append(dict(r))
    known = defaultdict(dict)
    for r in conn.execute("SELECT char_key, recipe_key, learned FROM char_recipes"):
        known[r["char_key"]][r["recipe_key"]] = bool(r["learned"])

    vendor_rows = [dict(r) for r in conn.execute("SELECT * FROM vendor_recipes")]
    vendor_by_name = {}
    for v in vendor_rows:
        vendor_by_name.setdefault(_strip(v["name"]).lower(), v)

    # Recipes seen only as a recipe item in a tooltip duplicate the profession window's entry.
    window_names = {(c["profession"].lower(), c["name"].lower()) for c in crafts
                    if not c["recipe_key"].startswith("recipe-item:")}
    item_info = {}
    for c in crafts:
        if c["recipe_key"].startswith("recipe-item:"):
            e = extra.get(c["recipe_key"]) or {}
            item_info[(c["profession"].lower(), c["name"].lower())] = e

    recipes, matched_vendor = [], set()
    for c in crafts:
        key = c["recipe_key"]
        if key.startswith("recipe-item:") and (c["profession"].lower(), c["name"].lower()) in window_names:
            continue
        e = extra.get(key) or {}
        via = item_info.get((c["profession"].lower(), c["name"].lower())) or {}
        skill_req = e.get("skill_req") or via.get("skill_req")
        recipe_item_id = e.get("recipe_item_id") or via.get("recipe_item_id")
        ah = None
        if c.get("recipe_item") and c["recipe_item"].get("price"):
            ah = {"item_id": c["recipe_item"]["item_id"], "name": c["recipe_item"]["name"],
                  "price": c["recipe_item"]["price"]}
        elif recipe_item_id and (by_id.get(recipe_item_id) or {}).get("price_now"):
            it = by_id[recipe_item_id]
            ah = {"item_id": recipe_item_id, "name": it["name"], "price": it["price_now"]}
        vendor = vendor_by_name.get(c["name"].lower()) or vendor_by_name.get((c.get("product_name") or "").lower())
        if vendor:
            matched_vendor.add(vendor["item_id"])
        ways = []
        if e.get("trainer_cost") is not None:
            ways.append(("trainer", e["trainer_cost"]))
        if vendor:
            ways.append(("vendor", vendor["price"]))
        if ah:
            ways.append(("auction", ah["price"]))
        learn_via, learn_cost = min(ways, key=lambda w: w[1]) if ways else (None, None)
        profit_day = c.get("profit_day")
        recipes.append({
            "recipe_key": key, "profession": c["profession"], "name": c["name"],
            "product_id": c.get("product_id"), "product_name": c.get("product_name"),
            "product_icon": c.get("product_icon"), "product_quality": c.get("product_quality"),
            "verdict": c["verdict"], "profit": c.get("profit"), "profit_day": profit_day,
            "product_sales_per_day": c.get("product_sales_per_day"),
            "skill_req": skill_req, "trainer_cost": e.get("trainer_cost"),
            "vendor": {k: vendor[k] for k in ("item_id", "name", "price", "limited", "vendor", "zone")} if vendor else None,
            "auction": ah, "learn_via": learn_via, "learn_cost": learn_cost,
            "payback_days": learn_cost / profit_day if learn_cost and profit_day and profit_day > 0 else None,
            "learned_any": c.get("learned"),
            "known_by": sorted(k for k, m in known.items() if m.get(key) is True),
            "unknown_by": sorted(k for k, m in known.items() if m.get(key) is False),
        })

    characters = []
    for key, c in chars.items():
        profs = []
        for s in skills.get(key, []):
            mine = [r for r in recipes if r["profession"].lower() == s["profession"].lower()]
            seen = [r for r in mine if key in r["known_by"] or key in r["unknown_by"]]
            profs.append({**{k: s[k] for k in ("profession", "rank", "max_rank", "seen_at")},
                          "known": sum(key in r["known_by"] for r in mine), "recipes": len(mine),
                          "window_seen": bool(seen)})
        characters.append({**c, "professions": profs})

    vendor_only = []
    for v in vendor_rows:
        if v["item_id"] in matched_vendor:
            continue
        it = by_id.get(v["item_id"]) or {}
        vendor_only.append({**v, "product": _strip(v["name"]), "auction_price": it.get("price_now")})
    vendor_only.sort(key=lambda v: v["name"])
    return {"characters": characters, "recipes": recipes, "vendor_recipes": vendor_only,
            "professions": sorted({profession_name(r["profession"]) for r in recipes})}
