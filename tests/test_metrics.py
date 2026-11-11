"""Metric tests. Expected values are worked out by hand in the comments."""

import pytest

from simsar_forever import config, db
from simsar_forever.analysis import crafts, fees, market, stats

NOW = 1_800_000_000


def cfg(**eco):
    c = config.load("does-not-exist.yaml")
    c["economy"].update(eco)
    return c


FEES = fees.Fees(ah_cut=0.05)


def test_net_per_sale():
    assert fees.net_per_sale(1000, FEES) == pytest.approx(950)
    assert fees.net_per_sale(None, FEES) is None


@pytest.mark.parametrize("house, cut", [("faction", 0.05), ("neutral", 0.15)])
def test_cut_follows_the_auction_house(house, cut):
    f = fees.from_config(cfg(auction_house=house))
    assert (f.ah_cut, f.auction_house) == (cut, house)


def test_configured_cut_overrides_the_house_rule():
    assert fees.from_config(cfg(ah_cut=0.1)).ah_cut == 0.1


def test_robust_stats_ignore_outliers():
    prices = [100, 102, 98, 101, 99, 5000]
    assert stats.median(prices) == 100.5
    assert stats.robust_cv(prices) < 0.05
    assert stats.robust_cv([100, 100, 100]) == 0


def test_trend_is_percent_per_day():
    days = list(range(10))
    prices = [100 * 1.02 ** d for d in days]
    prices[4] = 1000  # one wild point does not move Theil-Sen
    assert stats.daily_trend(days, prices) == pytest.approx(0.02, abs=1e-9)


def test_percentile_rank():
    assert stats.percentile_rank([1, 2, 3, 4], 2) == 0.5


def _db_with_item(**over):
    conn = db.connect(":memory:")
    v = dict(market=1200, min_buyout=1000, historical=1100, avg_sale=1150, sale_rate=0.5, spd=100, vendor=100)
    v.update(over)
    conn.execute("INSERT INTO items(item_id, name, vendor_sell) VALUES(1, 'Light Leather', ?)", (v["vendor"],))
    conn.execute("INSERT INTO tsm_realm VALUES(1, ?, ?, ?, ?, ?)",
                 (NOW - 3600, v["market"], v["min_buyout"], v["market"], v["historical"]))
    conn.execute("INSERT INTO tsm_region VALUES(1, ?, ?, ?, ?, ?, ?)",
                 (NOW - 3600, v["market"], v["historical"], v["avg_sale"], v["sale_rate"], v["spd"]))
    return conn


def test_market_row_hand_computed():
    c = cfg(realm_share=0.25, market_share=0.2)
    [it] = market.build(_db_with_item(), c, FEES, now=NOW)
    assert it["group"] == "skinning"
    assert it["price_now"] == 1000 and it["price_src"] == "tsm_min_buyout"
    assert it["sell_ref"] == 1150                       # min(avg_sale 1150, realm market 1200)
    assert it["sell_price"] == 1000                     # must match the cheapest listing to sell now
    assert it["net_sell"] == pytest.approx(950)         # 1000 * 0.95
    assert it["flip_profit"] == pytest.approx(92.5)     # 1150 * 0.95 - 1000
    assert it["my_sales_per_day"] == pytest.approx(5)   # 100 * 0.25 * 0.2
    assert it["flip_profit_day"] == pytest.approx(462.5)
    assert it["income_day"] == pytest.approx(4750)      # 950 * 5
    assert it["turnover_day"] == pytest.approx(28750)   # 25 * 1150
    assert it["disc_hist"] == pytest.approx(1000 / 1100 - 1)
    assert it["reference"] == 1200 and it["disc_ref"] == pytest.approx(1000 / 1200 - 1)
    assert it["label"] == "fast_thin"                   # 5/day is fast, 9.25% < 15% margin
    assert "not_live" not in it["flags"]                # TSM scan is an hour old


def test_market_flags():
    c = cfg()
    [it] = market.build(_db_with_item(market=5000, historical=1000, min_buyout=1000, spd=0.5), c, FEES,
                        now=NOW + 13 * 3600)
    assert {"stale", "thin_volume", "bubble", "possible_misprice"} <= set(it["flags"])


def test_live_auctionator_price_wins():
    conn = _db_with_item()
    conn.execute("INSERT INTO ato_current VALUES(1, 900, ?)", (NOW - 600,))
    [it] = market.build(conn, cfg(), FEES, now=NOW)
    assert (it["price_now"], it["price_src"]) == (900, "auctionator")
    assert "not_live" not in it["flags"]


def test_newer_tsm_scan_beats_older_auctionator_scan():
    conn = _db_with_item()
    conn.execute("INSERT INTO ato_current VALUES(1, 900, ?)", (NOW - 2 * 86400,))
    [it] = market.build(conn, cfg(), FEES, now=NOW)
    assert (it["price_now"], it["price_src"]) == (1000, "tsm_min_buyout")


def test_volatility_needs_enough_points():
    conn = _db_with_item()
    for d in range(3):
        conn.execute("INSERT INTO tsm_realm VALUES(1, ?, 1200, 1000, 1200, 1100)", (NOW - (d + 1) * 86400,))
    [it] = market.build(conn, cfg(), FEES, now=NOW)
    assert it["volatility"] is None and "low_confidence" in it["flags"]
    assert it["confidence"] == 0.6


def _items(**prices):
    rows = []
    for i, (name, (buy, net, spd)) in enumerate(prices.items(), 1):
        rows.append({"item_id": i, "name": name, "price_now": buy, "net_sell": net, "sell_price": buy,
                     "my_sales_per_day": spd, "flags": [], "volatility": None})
    return rows


def _recipe(product, reagents, yield_=1, name=None):
    return {"recipe_key": f"t:{name or product}", "profession": "Leatherworking", "name": name or product,
            "product_id": None, "product_name": product, "yield_min": yield_, "yield_max": yield_,
            "learned": 1, "recipe_item_id": None, "source": "test",
            "reagents": [{"item_id": None, "name": n, "count": c} for n, c in reagents.items()]}


def test_craft_profit_and_verdicts():
    items = _items(**{
        "Light Leather": (100, 90, 50),
        "Light Armor Kit": (500, 450, 4),
        "Cheap Kit": (150, 130, 4),
        "Odd Kit": (230, 190, 4),
    })
    recipes = [
        _recipe("Light Armor Kit", {"Light Leather": 2}),
        _recipe("Cheap Kit", {"Light Leather": 2}),
        _recipe("Odd Kit", {"Light Leather": 2}),
        _recipe("Unknown Kit", {"Light Leather": 1}),
        _recipe("Enchant Boots - Speed", {"Light Leather": 1}),
    ]
    rows = {r["name"]: r for r in crafts.analyse(recipes, items, FEES)}

    kit = rows["Light Armor Kit"]
    assert kit["cost_buy"] == 200 and kit["mats_value"] == 180
    assert kit["profit"] == 250 and kit["profit_vs_mats"] == 270
    assert kit["roi"] == pytest.approx(1.25)
    assert kit["profit_day"] == pytest.approx(1000)     # 250 * 4 crafts a day
    assert kit["verdict"] == "craft"

    assert rows["Cheap Kit"]["verdict"] == "sell_mats"    # 130 < 180 the mats would fetch
    assert rows["Odd Kit"]["verdict"] == "own_mats"       # 190 beats the 180 the mats fetch, but buying them costs 200
    assert rows["Unknown Kit"]["verdict"] == "missing"
    assert rows["Enchant Boots - Speed"]["verdict"] == "no_product"


def test_craft_with_multi_yield_and_missing_reagent():
    items = _items(**{"Wool Cloth": (50, 45, 100), "Bolt of Woolen Cloth": (180, 160, 10)})
    r = _recipe("Bolt of Woolen Cloth", {"Wool Cloth": 3}, yield_=2)
    [row] = crafts.analyse([r], items, FEES)
    assert row["revenue"] == 320 and row["profit"] == 170
    assert row["crafts_per_day"] == 5

    r = _recipe("Bolt of Woolen Cloth", {"Wool Cloth": 3, "Mystery Dye": 1})
    [row] = crafts.analyse([r], items, FEES)
    assert row["missing"] == ["Mystery Dye"] and row["verdict"] == "missing" and row["profit"] is None


def test_recipe_payback():
    items = _items(**{"Light Leather": (100, 90, 50), "Light Armor Kit": (500, 450, 4),
                      "Pattern: Light Armor Kit": (5000, 4500, 1)})
    [row] = crafts.analyse([_recipe("Light Armor Kit", {"Light Leather": 2})], items, FEES)
    assert row["recipe_item"]["price"] == 5000
    assert row["payback_days"] == pytest.approx(5)      # 5000 / 1000 per day


def test_money_format():
    from simsar_forever.money import fmt
    assert fmt(12345) == "1g 23s 45c"
    assert fmt(10000) == "1g"
    assert fmt(10005) == "1g 0s 5c"
    assert fmt(-250) == "-2s 50c"
    assert fmt(0) == "0c"


def test_cheap_flag_and_alert():
    from simsar_forever.analysis import alerts
    c = cfg()
    conn = _db_with_item(market=2000, min_buyout=1000)
    items = market.build(conn, c, FEES, now=NOW)
    assert "cheap" in items[0]["flags"] and "possible_misprice" not in items[0]["flags"]
    assert alerts.generate(items, [], c, now=NOW) == []     # no history yet: could be a falling market

    for d in range(1, 5):
        conn.execute("INSERT INTO tsm_realm VALUES(1, ?, 2000, 1000, 2000, 1100)", (NOW - d * 86400,))
    items = market.build(conn, c, FEES, now=NOW)
    [alert] = alerts.generate(items, [], c, now=NOW)
    assert alert["kind"] == "cheap" and "50% below" in alert["message"]

    for d in range(1, 5):
        conn.execute("UPDATE tsm_realm SET min_buyout = ? WHERE updated_at = ?", (1000 * 1.1 ** d, NOW - d * 86400))
    items = market.build(conn, c, FEES, now=NOW)
    assert items[0]["trend"] < -0.05
    assert alerts.generate(items, [], c, now=NOW) == []     # sliding price, not a bargain
    c["analysis"]["reference_price"] = "historical"
    [it] = market.build(_db_with_item(market=2000, min_buyout=1000, historical=1100), c, FEES, now=NOW)
    assert it["reference"] == 1100


def test_vendor_reagent_is_used_when_cheaper():
    items = _items(**{"Light Leather": (100, 90, 50), "Light Armor Kit": (500, 450, 4), "Coarse Thread": (80, 70, 9)})
    items[2]["vendor_buy"] = 10
    [row] = crafts.analyse([_recipe("Light Armor Kit", {"Light Leather": 2, "Coarse Thread": 1})], items, FEES)
    thread = row["reagents"][1]
    assert (thread["unit_price"], thread["price_src"]) == (10, "vendor")
    assert row["cost_buy"] == 210


def test_inventory_values_at_todays_prices():
    from simsar_forever.analysis import inventory
    conn = _db_with_item()                                   # Light Leather: you keep 950 per sale
    conn.execute("INSERT INTO items(item_id, name, vendor_sell) VALUES(2, 'Hearthstone', 0)")
    conn.execute("INSERT INTO items(item_id, name, vendor_sell) VALUES(3, 'Grey Junk', 40)")
    conn.execute("INSERT INTO characters VALUES('Tester-Realm', 'Tester', 'Realm', 'HUNTER', 'Alliance', 5000, 1, 2)")
    conn.executemany("INSERT INTO inventory VALUES('Tester-Realm', ?, ?, ?, ?)",
                     [("bags", 1, 10, 0), ("bank", 1, 5, 2), ("bags", 2, 1, 1), ("bags", 3, 3, 0)])
    items = market.build(conn, cfg(), FEES, now=NOW)
    result = {"by_id": {i["item_id"]: i for i in items}, "fees": FEES}
    inv = inventory.build(conn, result)
    rows = {r["item_id"]: r for r in inv["items"]}
    leather = rows[1]
    assert (leather["bags"], leather["bank"], leather["bound"]) == (10, 5, 2)
    assert leather["ah_value"] == pytest.approx(13 * 950)    # bound units cannot be auctioned
    assert leather["value"] == pytest.approx(13 * 950 + 2 * 100)
    assert leather["days_to_sell"] == pytest.approx(13 / 5)
    assert rows[3]["sell_where"] == "vendor" and rows[3]["value"] == 120
    assert rows[2]["sell_where"] == "bound" and rows[2]["value"] == 0
    [char] = inv["characters"]
    assert char["money"] == 5000 and char["value"] == pytest.approx(13 * 950 + 200 + 120)
