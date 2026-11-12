"""SavedVariables imports around the addon: the old addon name, Accountant Classic, tooltip data."""

from simsar_forever import accountant, config, db, lua, refresh, tooltip_data


def game(tmp_path):
    sv = tmp_path / "WTF" / "Account" / "ACC" / "SavedVariables"
    sv.mkdir(parents=True)
    (tmp_path / "Interface" / "AddOns" / "SimsarForever").mkdir(parents=True)
    cfg = config.load(tmp_path / "config.yaml")
    cfg["wow"]["game_dir"] = str(tmp_path)
    cfg["wow"]["account"] = "ACC"
    return cfg, sv


def recipe(name):
    return (f'["Leatherworking|{name}"] = {{ ["prof"] = "Leatherworking", ["name"] = "{name}", '
            '["source"] = "window", ["learned"] = true, ["reagents"] = {} }')


def test_old_and_new_addon_files_are_both_imported(tmp_path):
    cfg, sv = game(tmp_path)
    (sv / "SimsarForeverExport.lua").write_text(
        'SimsarForeverExportDB = { ["version"] = 1, ["recipes"] = { ' + recipe("Old Kit") + " } }")
    (sv / "SimsarForever.lua").write_text(
        'SimsarForeverDB = { ["version"] = 1, ["recipes"] = { ' + recipe("New Kit") + " } }")
    conn = db.connect(":memory:")
    rep = refresh.import_addon(cfg, conn)
    assert rep["ok"] and rep["file"] == "SimsarForever.lua"
    assert {r[0] for r in conn.execute("SELECT name FROM recipes")} == {"Old Kit", "New Kit"}
    assert refresh.import_addon(cfg, conn) == {"ok": True, "unchanged": True}


ACCOUNTANT = """
Accountant_ClassicHistory = {
  ["schema"] = 1,
  ["chars"] = {
    ["Realm One|Bolulu-Karahaci"] = {
      ["name"] = "Bolulu-Karahaci", ["money"] = 86991,
      ["days"] = {
        [20261110] = {
          ["AH"] = { ["i"] = 5000, ["o"] = 776, ["ni"] = 1, ["no"] = 1 },
          ["MERCH"] = { ["i"] = 301, ["o"] = 200, ["ni"] = 1, ["no"] = 2 },
          ["s"] = { [1413] = { ["Ratchet"] = { ["MERCH"] = { ["i"] = 301 } } } },
          ["bal"] = 90000,
        },
      },
    },
  },
  ["recent"] = {
    { ["a"] = -120, ["c"] = "Realm One|Bolulu-Karahaci", ["t"] = 1794319893, ["k"] = "MAIL", ["s"] = "Ratchet" },
    { ["a"] = 5000, ["c"] = "Realm One|Bolulu-Karahaci", ["t"] = 1794319999, ["k"] = "AH" },
    { ["a"] = 10, ["c"] = "Somebody|Unknown", ["t"] = 1794319999, ["k"] = "LOOT" },
  },
}
"""


def test_accountant_classic_history_is_imported(tmp_path):
    cfg, sv = game(tmp_path)
    (sv / accountant.FILE).write_text(ACCOUNTANT)
    conn = db.connect(":memory:")
    rep = refresh.import_accountant(cfg, conn)
    assert rep == {"ok": True, "characters": 1, "days": 1, "transactions": 2}
    rows = {(r["char_key"], r["category"]): (r["income"], r["expense"], r["n"]) for r in conn.execute(
        "SELECT * FROM ledger_days WHERE source = 'accountant'")}
    assert rows == {("Bolulu-Realm One", "AH_SALE"): (5000, 0, 1), ("Bolulu-Realm One", "AH"): (0, 776, 1),
                    ("Bolulu-Realm One", "VENDOR"): (301, 200, 3)}
    assert conn.execute("SELECT balance FROM balances").fetchone()[0] == 90000
    tx = sorted((r["amount"], r["category"]) for r in conn.execute("SELECT * FROM ledger_tx"))
    assert tx == [(-120, "MAIL"), (5000, "AH_SALE")]
    assert refresh.import_accountant(cfg, conn) == {"ok": True, "unchanged": True}


def test_no_accountant_file_is_fine(tmp_path):
    cfg, _ = game(tmp_path)
    assert refresh.import_accountant(cfg, db.connect(":memory:")) == {"ok": False, "missing": True}


def test_tooltip_data_file_is_valid_lua(tmp_path):
    cfg, _ = game(tmp_path)
    result = {
        "items": [
            {"item_id": 2318, "net_sell": 950.4, "my_sales_per_day": 2.53, "price_now": 1000},
            {"item_id": 2319, "net_sell": None, "my_sales_per_day": None, "price_now": None},
        ],
        "crafts": [{"product_id": 2318, "profit": 300, "yield": 2}, {"product_id": 2318, "profit": 100, "yield": 1}],
        "advice": {2318: {"advice": "hold", "expected_change": 0.0812, "horizon": 3}},
    }
    path = tooltip_data.write(cfg, None, result)
    data = lua.load(path)["SimsarForeverData"]
    assert data["version"] == 1 and data["built"] > 0
    assert data["items"][2318] == [950, 2.5, "hold", 0.081, 3, 150, 1000]
    assert 2319 not in data["items"]


def test_tooltip_data_is_skipped_without_the_addon(tmp_path):
    cfg = config.load(tmp_path / "config.yaml")
    cfg["wow"]["game_dir"] = str(tmp_path)
    assert tooltip_data.write(cfg, None, {"items": []}) is None


def test_ledger_prefers_the_addon_over_accountant_for_the_same_day():
    from simsar_forever.analysis import ledger
    conn = db.connect(":memory:")
    conn.executemany("INSERT INTO ledger_days VALUES(?,?,?,?,?,?,?)", [
        ("A-R", 20261110, "VENDOR", "accountant", 100, 0, 1),     # only Accountant knows this day
        ("A-R", 20261111, "VENDOR", "accountant", 999, 0, 1),     # both know this day: the addon wins
        ("A-R", 20261111, "VENDOR", "simsar", 50, 0, 1),
        ("A-R", 20261111, "REPAIR", "simsar", 0, 20, 1),
    ])
    conn.executemany("INSERT INTO balances VALUES(?,?,?,?)", [
        ("A-R", 20261110, "accountant", 1000), ("A-R", 20261111, "accountant", 1999), ("A-R", 20261111, "simsar", 1030)])
    out = ledger.build(conn)
    assert sorted((r["day"], r["category"], r["income"]) for r in out["days"]) == [
        (20261110, "VENDOR", 100), (20261111, "REPAIR", 0), (20261111, "VENDOR", 50)]
    assert out["balances"]["A-R"] == [(20261110, 1000), (20261111, 1030)]
    assert [c["char_key"] for c in out["characters"]] == ["A-R"]      # known only from the ledger
