"""Builds the full analysis and caches it until the data or the config changes."""

import threading
import time

from .. import addon_import, db
from .. import groups as groupmod
from . import crafts as craftmod
from . import fees as feemod
from . import market


def bump_data_version(conn):
    db.set_meta(conn, "data_version", (db.get_meta(conn, "data_version", 0) or 0) + 1)


class Engine:
    def __init__(self, cfg, conn):
        self.cfg = cfg
        self.conn = conn
        self.groups = groupmod.load(cfg)
        self._lock = threading.Lock()
        self._cache = None
        self._version = None

    def result(self):
        with self._lock:
            version = db.get_meta(self.conn, "data_version", 0)
            if self._cache is None or version != self._version:
                self._cache = self._build()
                self._version = version
            return self._cache

    def _build(self):
        started = time.time()
        measured = addon_import.measured_fees(self.conn)
        fees = feemod.from_config(self.cfg, measured)
        recipes = craftmod.load_recipes(self.conn, self.cfg)
        recipe_items = craftmod.product_items_by_profession(recipes)
        items = market.build(self.conn, self.cfg, fees, self.groups, recipe_items)
        crafts = craftmod.analyse(recipes, items, fees)
        return {
            "items": items,
            "by_id": {i["item_id"]: i for i in items},
            "crafts": crafts,
            "fees": fees,
            "measured_fees": measured,
            "overview": overview(items, crafts, self.groups),
            "built_at": time.time(),
            "build_seconds": round(time.time() - started, 2),
        }


def overview(items, crafts, groups):
    out = []
    for g in groups:
        members = [i for i in items if g["key"] in i["groups"]]
        with_volume = [i for i in members if i["sold_per_day_region"]]
        top = sorted((i for i in members if i["score"]), key=lambda i: -i["score"])[:5]
        top_income = sorted((i for i in members if i["income_day"]), key=lambda i: -i["income_day"])[:5]
        prof_crafts = [c for c in crafts if c["profession"].lower() == g["profession"].lower()]
        best_crafts = [c for c in prof_crafts if c["verdict"] == "craft"][:5]
        out.append({
            **groupmod.public([g])[0],
            "items": len(members),
            "with_volume": len(with_volume),
            "turnover_day": sum(i["turnover_day"] or 0 for i in with_volume),
            "recipes": len(prof_crafts),
            "profitable_crafts": sum(c["verdict"] == "craft" for c in prof_crafts),
            "top_flips": [_brief(i, "score") for i in top],
            "top_sellers": [_brief(i, "income_day") for i in top_income],
            "top_crafts": [{"recipe_key": c["recipe_key"], "name": c["name"], "profit": c["profit"],
                            "profit_day": c["profit_day"], "product_id": c["product_id"]} for c in best_crafts],
        })
    return out


def _brief(i, key):
    return {"item_id": i["item_id"], "name": i["name"], "value": i[key], "label": i["label"],
            "price_now": i["price_now"], "flags": i["flags"]}
