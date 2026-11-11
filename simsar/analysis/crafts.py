"""Craft profitability: is a recipe worth crafting, and with whose materials?"""

import re
from pathlib import Path

import yaml

VERDICTS = {
    "craft": "Craft and sell, even when buying the materials",
    "own_mats": "Craft only with materials you already have",
    "sell_mats": "Selling the materials makes more",
    "missing": "Some prices are missing",
    "no_product": "Product is not tradeable (an enchant or a service)",
}

RECIPE_PREFIX = {"Leatherworking": "Pattern", "Tailoring": "Pattern", "Enchanting": "Formula"}


def load_recipes(conn, cfg=None):
    """Recipes from the database (addon), then the YAML file for anything the addon has not seen."""
    recipes = {}
    for r in conn.execute("SELECT * FROM recipes"):
        reagents = [dict(x) for x in conn.execute(
            "SELECT item_id, name, count FROM recipe_reagents WHERE recipe_key = ?", (r["recipe_key"],))]
        recipes[r["recipe_key"]] = {**dict(r), "reagents": reagents}

    seen = {(r["profession"].lower(), (r["product_name"] or r["name"]).lower()) for r in recipes.values()}
    for path in _yaml_sources(cfg):
        with path.open(encoding="utf-8") as f:
            spec = yaml.safe_load(f) or {}
        for i, r in enumerate(spec.get("recipes") or []):
            product = r.get("product") or r["name"]
            if (r["profession"].lower(), product.lower()) in seen:
                continue
            key = f"yaml:{r['profession']}|{r.get('name', product)}"
            recipes[key] = {
                "recipe_key": key, "profession": r["profession"], "name": r.get("name", product),
                "product_id": r.get("product_id"), "product_name": product,
                "yield_min": r.get("yield", 1), "yield_max": r.get("yield", 1), "learned": None,
                "recipe_item_id": None, "source": "yaml" if r.get("verified") else "yaml-unverified",
                "reagents": [{"item_id": None, "name": n, "count": c} for n, c in r["reagents"].items()],
            }
    return list(recipes.values())


def _yaml_sources(cfg):
    if cfg:
        user = Path(cfg["_base_dir"]) / "recipes.yaml"
        if user.exists():
            yield user


def product_items_by_profession(recipes):
    out = {}
    for r in recipes:
        ids = out.setdefault(r["profession"], set())
        if r.get("product_id"):
            ids.add(r["product_id"])
        ids.update(x["item_id"] for x in r["reagents"] if x["item_id"])
    return out


def _resolve(spec_id, spec_name, by_id, by_name):
    if spec_id and spec_id in by_id:
        return by_id[spec_id]
    if spec_name:
        return by_name.get(spec_name.lower())
    return None


def analyse(recipes, items, fees, profession=None):
    by_id = {i["item_id"]: i for i in items}
    by_name = {}
    for i in items:
        by_name.setdefault(i["name"].lower(), i)

    rows = []
    for r in recipes:
        if profession and r["profession"].lower() != profession.lower():
            continue
        product = _resolve(r.get("product_id"), r.get("product_name"), by_id, by_name)
        ymin, ymax = r.get("yield_min") or 1, r.get("yield_max") or r.get("yield_min") or 1
        yield_avg = (ymin + ymax) / 2

        missing, reagents = [], []
        cost_buy = mats_value = 0.0
        for x in r["reagents"]:
            it = _resolve(x["item_id"], x["name"], by_id, by_name)
            name = (it or {}).get("name") or x["name"] or f"Item {x['item_id']}"
            buy = it and it.get("price_now")
            sell = it and it.get("net_sell")
            reagents.append({"item_id": (it or {}).get("item_id") or x["item_id"], "name": name,
                             "count": x["count"], "unit_price": buy, "unit_net_sell": sell})
            if not buy:
                missing.append(name)
                continue
            cost_buy += x["count"] * buy
            mats_value += x["count"] * (sell if sell is not None else buy * (1 - fees.ah_cut))

        row = {
            "recipe_key": r["recipe_key"], "profession": r["profession"], "name": r["name"],
            "source": r["source"], "learned": r.get("learned"),
            "product_id": (product or {}).get("item_id") or r.get("product_id"),
            "product_name": (product or {}).get("name") or r.get("product_name") or r["name"],
            "yield": yield_avg, "reagents": reagents, "missing": missing,
            "cost_buy": cost_buy if not missing else None,
            "mats_value": mats_value if not missing else None,
            "revenue": None, "profit": None, "profit_vs_mats": None, "roi": None,
            "crafts_per_day": None, "profit_day": None,
            "product_sales_per_day": None, "product_price": None, "product_flags": [],
        }
        if product:
            unit_net = product.get("net_sell")
            row.update(product_price=product.get("sell_price"), product_sales_per_day=product.get("my_sales_per_day"),
                       product_flags=product.get("flags", []), product_volatility=product.get("volatility"))
            if unit_net is not None and not missing:
                revenue = unit_net * yield_avg
                profit = revenue - cost_buy
                spd = product.get("my_sales_per_day")
                crafts_per_day = spd / yield_avg if spd is not None else None
                row.update(
                    revenue=revenue, profit=profit, profit_vs_mats=revenue - mats_value,
                    roi=profit / cost_buy if cost_buy else None,
                    crafts_per_day=crafts_per_day,
                    profit_day=max(profit, 0) * crafts_per_day if crafts_per_day is not None else None,
                )

        recipe_item = _recipe_item(r, by_id, by_name)
        if recipe_item:
            row["recipe_item"] = {"item_id": recipe_item["item_id"], "name": recipe_item["name"],
                                  "price": recipe_item.get("price_now")}
            if recipe_item.get("price_now") and row["profit_day"]:
                row["payback_days"] = recipe_item["price_now"] / row["profit_day"]

        row["verdict"] = verdict(row, product)
        rows.append(row)
    rows.sort(key=lambda x: (x["profit_day"] is None, -(x["profit_day"] or 0), -(x["profit"] or float("-inf"))))
    return rows


def _recipe_item(r, by_id, by_name):
    if r.get("recipe_item_id") and r["recipe_item_id"] in by_id:
        return by_id[r["recipe_item_id"]]
    prefix = RECIPE_PREFIX.get(r["profession"])
    if not prefix:
        return None
    for name in {r["name"], r.get("product_name") or r["name"]}:
        hit = by_name.get(f"{prefix}: {name}".lower())
        if hit:
            return hit
    return None


def verdict(row, product):
    if product is None:
        return "no_product" if is_enchant(row["name"]) else "missing"
    if row["missing"] or row["profit"] is None:
        return "missing"
    if row["profit_vs_mats"] <= 0:
        return "sell_mats"
    if row["profit"] > 0:
        return "craft"
    return "own_mats"


def is_enchant(name):
    return bool(re.match(r"^Enchant ", name or ""))
