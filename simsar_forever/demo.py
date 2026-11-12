"""Synthetic demo data. It does not describe any real market; it exists so the dashboard can be
tried without network access or a game install. Every name carries "(demo)" and every id is in
the 990000 range so it can never be mistaken for real data."""

import math
import random
import time

from . import db
from .analysis.engine import bump_data_version

ID_BASE = 990000

# name, base price (copper), region sales/day, volatility, sale rate, vendor sell
ITEMS = [
    ("Light Leather", 60, 6000, 0.08, 0.55, 15), ("Medium Leather", 150, 2400, 0.08, 0.5, 25),
    ("Heavy Leather", 450, 2100, 0.10, 0.45, 50), ("Thick Leather", 900, 900, 0.12, 0.4, 75),
    ("Rugged Leather", 2400, 250, 0.14, 0.35, 100), ("Light Hide", 220, 600, 0.12, 0.3, 50),
    ("Medium Hide", 500, 1100, 0.12, 0.3, 75), ("Heavy Hide", 1800, 240, 0.15, 0.25, 100),
    ("Scorpid Scale", 1200, 60, 0.2, 0.2, 100),
    ("Salt", 40, 150, 0.05, 0.6, 12), ("Cured Medium Hide", 900, 950, 0.1, 0.4, 100),
    ("Cured Heavy Hide", 2600, 130, 0.12, 0.3, 125), ("Medium Armor Kit", 450, 160, 0.1, 0.35, 75),
    ("Heavy Armor Kit", 1500, 120, 0.12, 0.3, 125), ("Thick Armor Kit", 3200, 70, 0.15, 0.25, 175),
    ("Linen Cloth", 25, 16000, 0.06, 0.6, 13), ("Wool Cloth", 100, 7000, 0.07, 0.55, 33),
    ("Silk Cloth", 260, 9000, 0.08, 0.5, 38), ("Mageweave Cloth", 1000, 2200, 0.1, 0.45, 25),
    ("Bolt of Linen Cloth", 70, 1000, 0.1, 0.4, 40), ("Bolt of Woolen Cloth", 420, 760, 0.12, 0.35, 100),
    ("Bolt of Silk Cloth", 1150, 490, 0.12, 0.3, 150), ("Coarse Thread", 20, 700, 0.05, 0.6, 2),
    ("Fine Thread", 140, 460, 0.06, 0.55, 25), ("Linen Bag", 260, 360, 0.15, 0.3, 50),
    ("Woolen Bag", 900, 130, 0.18, 0.25, 125),
    ("Strange Dust", 90, 1450, 0.08, 0.5, 0), ("Soul Dust", 700, 480, 0.1, 0.45, 0),
    ("Vision Dust", 2600, 270, 0.12, 0.4, 0), ("Lesser Magic Essence", 130, 700, 0.1, 0.4, 0),
    ("Greater Magic Essence", 330, 500, 0.1, 0.4, 0), ("Small Glimmering Shard", 550, 200, 0.15, 0.3, 0),
    ("Minor Wizard Oil", 300, 110, 0.15, 0.3, 50), ("Lesser Magic Wand", 200, 670, 0.15, 0.35, 100),
    ("Raw Rockscale Cod", 30, 1000, 0.08, 0.5, 4), ("Oily Blackmouth", 100, 1800, 0.08, 0.5, 4),
    ("Firefin Snapper", 150, 1050, 0.1, 0.45, 4), ("Stonescale Eel", 450, 600, 0.12, 0.4, 10),
    ("Raw Sagefish", 130, 680, 0.1, 0.4, 2), ("Deviate Fish", 190, 430, 0.15, 0.35, 1),
    ("Pattern: Heavy Armor Kit", 25000, 2, 0.3, 0.08, 250), ("Formula: Minor Wizard Oil", 9000, 1, 0.35, 0.06, 100),
]

RECIPES = [
    ("Leatherworking", "Cured Medium Hide", 1, {"Medium Hide": 1, "Salt": 1}),
    ("Leatherworking", "Cured Heavy Hide", 1, {"Heavy Hide": 1, "Salt": 3}),
    ("Leatherworking", "Medium Armor Kit", 1, {"Medium Leather": 4, "Coarse Thread": 1}),
    ("Leatherworking", "Heavy Armor Kit", 1, {"Heavy Leather": 5, "Coarse Thread": 1}),
    ("Leatherworking", "Thick Armor Kit", 1, {"Thick Leather": 5, "Fine Thread": 1}),
    ("Tailoring", "Bolt of Linen Cloth", 1, {"Linen Cloth": 2}),
    ("Tailoring", "Bolt of Woolen Cloth", 1, {"Wool Cloth": 3}),
    ("Tailoring", "Bolt of Silk Cloth", 1, {"Silk Cloth": 4}),
    ("Tailoring", "Linen Bag", 1, {"Linen Cloth": 3, "Coarse Thread": 3}),
    ("Tailoring", "Woolen Bag", 1, {"Wool Cloth": 4, "Coarse Thread": 1}),
    ("Enchanting", "Minor Wizard Oil", 1, {"Strange Dust": 2}),
    ("Enchanting", "Lesser Magic Wand", 1, {"Lesser Magic Essence": 1}),
    ("Enchanting", "Enchant Bracer - Minor Health", 1, {"Strange Dust": 1}),
]


def label(name):
    return f"{name} (demo)"


def build(conn, days=14, seed=7, now=None):
    rnd = random.Random(seed)
    now = int(now or time.time())
    step = 3 * 3600
    n = days * 24 // 3
    stamps = [now - (n - 1 - i) * step for i in range(n)]
    dips = set(rnd.sample(range(len(ITEMS)), 4))
    spikes = set(rnd.sample(sorted(set(range(len(ITEMS))) - dips), 2))
    ids = {}
    realm_rows, region_rows, daily_rows, current_rows = [], [], [], []

    for idx, (name, base, spd, vol, sale_rate, vendor) in enumerate(ITEMS):
        item_id = ID_BASE + idx
        ids[name] = item_id
        conn.execute("INSERT INTO items(item_id, name, vendor_sell, updated_at) VALUES(?, ?, ?, ?)",
                     (item_id, label(name), vendor, now))
        x, series = 0.0, []
        for _ in range(n):
            x = 0.9 * x + rnd.gauss(0, vol / 2.2)
            series.append(x)
        if idx in dips:
            series[-6:] = [s - 0.35 for s in series[-6:]]
        if idx in spikes:
            series[-8:] = [s + 0.9 for s in series[-8:]]
        market = [base * math.exp(s) for s in series]
        min_buyout = [m * rnd.uniform(0.84, 0.99) for m in market]
        historical = sum(market) / n
        for i, ts in enumerate(stamps):
            realm_rows.append((item_id, ts, round(market[i]), round(min_buyout[i]), round(market[i] * 0.97),
                               round(historical)))
        for j in range(0, n, 8):
            region_rows.append((item_id, stamps[j], round(market[j]), round(historical * 0.99),
                                round(market[j] * rnd.uniform(0.95, 1.05)),
                                min(0.95, sale_rate * rnd.uniform(0.85, 1.15)), spd * rnd.uniform(0.8, 1.2)))
        region_rows.append((item_id, stamps[-1], round(market[-1]), round(historical * 0.99),
                            round(market[-1] * rnd.uniform(0.97, 1.03)), sale_rate, float(spd)))
        for d in range(days):
            j = min(n - 1, d * 8 + 7)
            day_ts = stamps[j] - stamps[j] % 86400
            low = round(min_buyout[j])
            daily_rows.append((item_id, day_ts, low, round(low * rnd.uniform(1.0, 1.3)), rnd.randint(5, 400)))
        if rnd.random() < 0.8:
            current_rows.append((item_id, round(min_buyout[-1] * rnd.uniform(0.97, 1.02)), now - 1800))

    conn.executemany("INSERT OR IGNORE INTO tsm_realm VALUES(?,?,?,?,?,?)", realm_rows)
    conn.executemany("INSERT OR IGNORE INTO tsm_region VALUES(?,?,?,?,?,?,?)", region_rows)
    conn.executemany("INSERT OR REPLACE INTO ato_daily VALUES(?,?,?,?,?)", daily_rows)
    conn.executemany("INSERT OR REPLACE INTO ato_current VALUES(?,?,?)", current_rows)

    for prof, product, yield_, reagents in RECIPES:
        key = f"demo:{prof}|{product}"
        conn.execute(
            "INSERT INTO recipes(recipe_key, profession, name, product_id, product_name, yield_min, yield_max, "
            "learned, source, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (key, prof, label(product), ids.get(product), label(product), yield_, yield_, 1, "demo", now))
        conn.executemany("INSERT INTO recipe_reagents VALUES(?,?,?,?)",
                         [(key, ids[r], label(r), c) for r, c in reagents.items()])

    chars = [("Leatherhand-Demo", "Leatherhand (demo)", "HUNTER", 1_234_500),
             ("Threadbare-Demo", "Threadbare (demo)", "MAGE", 87_650)]
    for key, name, cls, money in chars:
        conn.execute("INSERT INTO characters(char_key, name, realm, class, faction, money, bags_at, bank_at) "
                     "VALUES(?,?,?,?,?,?,?,?)",
                     (key, name, "Demo Realm", cls, "Alliance", money, now - 600, now - 86400))
    holdings = [
        ("Leatherhand-Demo", "bags", "Light Leather", 60), ("Leatherhand-Demo", "bags", "Medium Leather", 35),
        ("Leatherhand-Demo", "bank", "Heavy Leather", 120), ("Leatherhand-Demo", "bank", "Medium Hide", 12),
        ("Leatherhand-Demo", "bags", "Heavy Armor Kit", 4), ("Threadbare-Demo", "bags", "Linen Cloth", 140),
        ("Threadbare-Demo", "bags", "Wool Cloth", 80), ("Threadbare-Demo", "bank", "Silk Cloth", 200),
        ("Threadbare-Demo", "bank", "Strange Dust", 45), ("Leatherhand-Demo", "bank", "Silk Cloth", 20),
    ]
    conn.executemany("INSERT INTO inventory VALUES(?,?,?,?,0)",
                     [(k, loc, ids[name], n) for k, loc, name, n in holdings])
    build_ledger(conn, rnd, now, chars, ids)
    build_professions(conn, now, ids)

    db.set_meta(conn, "demo", True)
    db.set_meta(conn, "tsm_realm_updated_at", stamps[-1])
    db.set_meta(conn, "tsm_region_updated_at", stamps[-1])
    bump_data_version(conn)
    conn.commit()
    return {"items": len(ITEMS), "snapshots": n, "recipes": len(RECIPES)}


def build_ledger(conn, rnd, now, chars, ids):
    """Thirty days of made-up gold movements for the demo characters."""
    day_rows, balance_rows, tx_rows = [], [], []
    for key, _, _, money in chars:
        # Scaled to the character's gold so the history ends at the gold it has now.
        scale = max(money // 400, 100)
        balance = money
        for back in range(30):
            t = now - back * 86400
            day = int(time.strftime("%Y%m%d", time.localtime(t)))
            balance_rows.append((key, day, "simsar", max(balance, 0)))
            moves = {
                "AH_SALE": rnd.randint(2, 30) * scale, "AH_BUY": -rnd.randint(0, 14) * scale,
                "AH_DEPOSIT": -rnd.randint(1, 20) * scale // 50, "VENDOR": rnd.randint(1, 80) * scale // 20,
                "REPAIR": -rnd.randint(0, 30) * scale // 20, "QUEST": rnd.randint(0, 3) * scale // 2,
                "LOOT": rnd.randint(0, 40) * scale // 20,
            }
            if back % 7 == 3:
                moves["TRAINING"] = -rnd.randint(1, 5) * scale
            for cat, amount in moves.items():
                if amount:
                    day_rows.append((key, day, cat, "simsar", max(amount, 0), max(-amount, 0), 1))
                    tx_rows.append((key, t - rnd.randint(0, 80000), amount, cat, "simsar", "Demo Zone"))
                    balance -= amount
    conn.executemany("INSERT OR REPLACE INTO ledger_days VALUES(?,?,?,?,?,?,?)", day_rows)
    conn.executemany("INSERT OR REPLACE INTO balances VALUES(?,?,?,?)", balance_rows)
    conn.executemany("INSERT OR IGNORE INTO ledger_tx VALUES(?,?,?,?,?,?)", tx_rows)
    sold = [("Heavy Armor Kit", 1, 16000), ("Cured Heavy Hide", 5, 13000), ("Bolt of Silk Cloth", 10, 11500),
            ("Heavy Armor Kit", 1, 15500), ("Silk Cloth", 20, 5200)]
    conn.executemany(
        "INSERT OR IGNORE INTO ah_invoices(seen_at, item_name, quantity, bid, buyout, deposit, consignment, char_key) "
        "VALUES(?,?,?,?,?,?,?,?)",
        [(now - i * 40000, label(n), q, p, p, 0, round(p * 0.05), chars[0][0]) for i, (n, q, p) in enumerate(sold)])
    conn.executemany(
        "INSERT OR IGNORE INTO mail_events VALUES(?,?,?,?,?,?,?,?)",
        [("demo-buy-1", "bought", now - 90000, chars[0][0], label("Heavy Leather"), ids["Heavy Leather"], 20, 8400),
         ("demo-exp-1", "expired", now - 50000, chars[0][0], label("Heavy Armor Kit"), ids["Heavy Armor Kit"], 1, None)])


def build_professions(conn, now, ids):
    """Skills, known recipes, trainer costs and a vendor recipe for the demo characters."""
    skills = [("Leatherhand-Demo", "Leatherworking", 175, 225), ("Leatherhand-Demo", "Skinning", 190, 225),
              ("Threadbare-Demo", "Tailoring", 140, 150), ("Threadbare-Demo", "Enchanting", 90, 150)]
    conn.executemany("INSERT INTO char_professions VALUES(?,?,?,?,?)", [(*s, now - 3600) for s in skills])
    unknown = {("Leatherhand-Demo", "Thick Armor Kit"), ("Leatherhand-Demo", "Cured Heavy Hide"),
               ("Threadbare-Demo", "Woolen Bag"), ("Threadbare-Demo", "Bolt of Silk Cloth"),
               ("Threadbare-Demo", "Lesser Magic Wand")}
    owners = {"Leatherworking": "Leatherhand-Demo", "Tailoring": "Threadbare-Demo", "Enchanting": "Threadbare-Demo"}
    skill_req = {"Cured Medium Hide": 115, "Cured Heavy Hide": 160, "Medium Armor Kit": 100, "Heavy Armor Kit": 150,
                 "Thick Armor Kit": 200, "Bolt of Linen Cloth": 1, "Bolt of Woolen Cloth": 75, "Bolt of Silk Cloth": 125,
                 "Linen Bag": 45, "Woolen Bag": 80, "Minor Wizard Oil": 45, "Lesser Magic Wand": 70}
    for prof, product, _, _ in RECIPES:
        key = f"demo:{prof}|{product}"
        cost = None if product in ("Heavy Armor Kit", "Minor Wizard Oil") else skill_req.get(product, 50) * 50
        conn.execute("UPDATE recipes SET skill_req = ?, trainer_cost = ?, learned = ? WHERE recipe_key = ?",
                     (skill_req.get(product), cost, int((owners[prof], product) not in unknown), key))
        conn.execute("INSERT INTO char_recipes VALUES(?,?,?)",
                     (owners[prof], key, int((owners[prof], product) not in unknown)))
    conn.execute("INSERT INTO vendor_recipes VALUES(?,?,?,?,?,?,?)",
                 (ids["Formula: Minor Wizard Oil"], label("Formula: Minor Wizard Oil"), 2500, 1,
                  "Demo Supplier", "Demo Zone", now - 86400))
