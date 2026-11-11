"""Drives addon/SimsarForeverExport against a fake WoW API and imports what it saves."""

from pathlib import Path

import pytest

from simsar_forever import addon_import, db

lupa = pytest.importorskip("lupa.lua51")

ROOT = Path(__file__).resolve().parents[1]
ADDON = (ROOT / "addon" / "SimsarForeverExport" / "SimsarForeverExport.lua").read_text(encoding="utf-8")
STUB = (Path(__file__).parent / "wowstub.lua").read_text(encoding="utf-8")


def run(api_lua, actions_lua):
    lua = lupa.LuaRuntime()
    lua.execute(STUB)
    lua.execute(api_lua)
    lua.execute(ADDON)
    lua.execute('fire("PLAYER_LOGIN")')
    lua.execute(actions_lua)
    return lua


def import_saved(lua, tmp_path):
    f = tmp_path / "SimsarForeverExport.lua"
    f.write_text(lua.eval("savedVariables()"), encoding="utf-8")
    conn = db.connect(":memory:")
    return conn, addon_import.import_file(conn, f)


CLASSIC_TRADESKILL = """
items[2318] = { name = "Light Leather", vendor = 15 }
items[2320] = { name = "Coarse Thread", vendor = 2 }
items[2304] = { name = "Light Armor Kit", vendor = 25 }
local recipes = {
  { "Leatherworking", "header" },
  { "Light Armor Kit", "easy", item = 2304, reagents = { { "Light Leather", 1, 2318 } } },
  { "Cured Light Hide", "trivial", item = 4231, made = { 1, 1 },
    reagents = { { "Light Hide", 1, 783 }, { "Salt", 1, 4289 } } },
}
function GetTradeSkillLine() return "Leatherworking", 75, 150 end
function GetNumTradeSkills() return #recipes end
function GetTradeSkillInfo(i) return recipes[i][1], recipes[i][2] end
function GetTradeSkillItemLink(i) return recipes[i].item and ("|Hitem:" .. recipes[i].item .. "::|h[x]|h") end
function GetTradeSkillNumMade(i) return 1, 1 end
function GetTradeSkillNumReagents(i) return #(recipes[i].reagents or {}) end
function GetTradeSkillReagentInfo(i, j) local r = recipes[i].reagents[j]; return r[1], "tex", r[2], 0 end
function GetTradeSkillReagentItemLink(i, j) return "|Hitem:" .. recipes[i].reagents[j][3] .. "::|h" end
"""


def test_classic_tradeskill_window(tmp_path):
    lua = run(CLASSIC_TRADESKILL, 'fire("TRADE_SKILL_SHOW")')
    conn, rep = import_saved(lua, tmp_path)
    assert rep["recipes"] == 2
    kit = conn.execute("SELECT * FROM recipes WHERE name = 'Light Armor Kit'").fetchone()
    assert kit["product_id"] == 2304 and kit["learned"] == 1 and kit["source"] == "addon-window"
    reagents = conn.execute("SELECT item_id, count FROM recipe_reagents WHERE recipe_key = ?",
                            (kit["recipe_key"],)).fetchall()
    assert [tuple(r) for r in reagents] == [(2318, 1)]
    assert conn.execute("SELECT vendor_sell FROM items WHERE item_id = 2318").fetchone()[0] == 15


def test_classic_craft_window_for_enchanting(tmp_path):
    api = """
    function GetCraftDisplaySkillLine() return "Enchanting", 50, 75 end
    function GetNumCrafts() return 1 end
    function GetCraftInfo(i) return "Enchant Bracer - Minor Health", "", "optimal" end
    function GetCraftItemLink(i) return "|Henchant:7418|h[Enchant]|h" end
    function GetCraftNumReagents(i) return 1 end
    function GetCraftReagentInfo(i, j) return "Strange Dust", "tex", 1, 0 end
    function GetCraftReagentItemLink(i, j) return "|Hitem:10940::|h" end
    """
    lua = run(api, 'fire("CRAFT_SHOW")')
    conn, rep = import_saved(lua, tmp_path)
    r = conn.execute("SELECT profession, product_id FROM recipes").fetchone()
    assert tuple(r) == ("Enchanting", None)


def test_modern_api_lists_unlearned_recipes(tmp_path):
    api = """
    items[4000] = { name = "Bolt of Linen Cloth", vendor = 40 }
    C_TradeSkillUI = {
      GetBaseProfessionInfo = function() return { professionName = "Tailoring" } end,
      GetAllRecipeIDs = function() return { 10, 11 } end,
      GetRecipeInfo = function(id) return { name = id == 10 and "Bolt of Linen Cloth" or "Linen Bag", learned = id == 10 } end,
      GetRecipeSchematic = function(id) return {
        outputItemID = id == 10 and 4000 or 4001, quantityMin = 1, quantityMax = 1,
        reagentSlotSchematics = { { quantityRequired = 2, reagents = { { itemID = 2589 } } } } } end,
    }
    """
    lua = run(api, 'fire("TRADE_SKILL_SHOW")')
    conn, rep = import_saved(lua, tmp_path)
    learned = dict(conn.execute("SELECT name, learned FROM recipes").fetchall())
    assert learned == {"Bolt of Linen Cloth": 1, "Linen Bag": 0}


def test_trainer_reagents_from_tooltip(tmp_path):
    api = """
    trainerTooltips = { [1] = { "Heavy Armor Kit", "Reagents: Medium Leather (5), Coarse Thread" } }
    function GetNumTrainerServices() return 1 end
    function GetTrainerServiceInfo(i) return "Heavy Armor Kit", "", "available" end
    function GetTrainerServiceItemLink(i) return "|Hitem:4265::|h" end
    function GetTrainerServiceSkillLine(i) return "Leatherworking" end
    function GetTrainerServiceSkillReq(i) return "Leatherworking", 100, true end
    function GetTrainerServiceCost(i) return 1500 end
    """
    lua = run(api, 'fire("TRAINER_SHOW")')
    conn, _ = import_saved(lua, tmp_path)
    r = conn.execute("SELECT * FROM recipes").fetchone()
    assert (r["name"], r["learned"], r["source"]) == ("Heavy Armor Kit", 0, "addon-trainer")
    reagents = {row["name"]: row["count"] for row in conn.execute("SELECT * FROM recipe_reagents")}
    assert reagents == {"Medium Leather": 5, "Coarse Thread": 1}


def test_trainer_does_not_overwrite_window_recipe(tmp_path):
    api = CLASSIC_TRADESKILL + """
    trainerTooltips = { [1] = { "Light Armor Kit", "Reagents: Light Leather" } }
    function GetNumTrainerServices() return 1 end
    function GetTrainerServiceInfo(i) return "Light Armor Kit", "", "used" end
    function GetTrainerServiceItemLink(i) return "|Hitem:2304::|h" end
    function GetTrainerServiceSkillLine(i) return "Leatherworking" end
    """
    lua = run(api, 'fire("TRADE_SKILL_SHOW"); fire("TRAINER_SHOW")')
    conn, _ = import_saved(lua, tmp_path)
    assert conn.execute("SELECT source FROM recipes WHERE name = 'Light Armor Kit'").fetchone()[0] == "addon-window"


def test_invoices_are_deduplicated_and_give_ah_cut(tmp_path):
    api = """
    local mails = {
      { "seller", "Light Leather", "Buyer", 2000, 2000, 30, 100, 0, 0, 0, 20 },
      { "seller", "Wool Cloth", "Buyer", 1000, 1000, 10, 50, 0, 0, 0, 5 },
      { "buyer", "Silk Cloth", "Seller", 900, 900, 0, 0 },
    }
    function GetInboxNumItems() return #mails end
    function GetInboxInvoiceInfo(i) return unpack(mails[i]) end
    function GetInboxHeaderInfo(i) return nil, nil, "Auction House", "Sold", 0, 0, 29.5 end
    """
    lua = run(api, 'fire("MAIL_INBOX_UPDATE"); fire("MAIL_INBOX_UPDATE")')
    conn, rep = import_saved(lua, tmp_path)
    assert rep["invoices"] == 2
    assert addon_import.measured_fees(conn)["ah_cut"] == 0.05


BAGS_AND_BANK = """
items[2318] = { name = "Light Leather", vendor = 15, icon = 134252, quality = 1 }
items[6948] = { name = "Hearthstone", vendor = 0 }
local slots = {
  [0] = { { itemID = 2318, stackCount = 20 }, { itemID = 6948, stackCount = 1, isBound = true } },
  [1] = { { itemID = 2318, stackCount = 5 } },
  [-1] = { { itemID = 2318, stackCount = 40 } },
}
C_Container = {
  GetContainerNumSlots = function(bag) return slots[bag] and #slots[bag] or 0 end,
  GetContainerItemInfo = function(bag, slot) return slots[bag] and slots[bag][slot] end,
}
"""


def test_bags_and_bank_are_saved_per_character(tmp_path):
    lua = run(BAGS_AND_BANK, 'fire("BAG_UPDATE_DELAYED"); fire("BANKFRAME_OPENED"); fire("BANKFRAME_CLOSED")')
    conn, rep = import_saved(lua, tmp_path)
    assert rep["characters"] == 1
    c = conn.execute("SELECT * FROM characters").fetchone()
    assert (c["name"], c["class"], c["money"]) == ("Tester", "HUNTER", 123456)
    held = {(r["location"], r["item_id"]): (r["count"], r["bound"]) for r in conn.execute("SELECT * FROM inventory")}
    assert held == {("bags", 2318): (25, 0), ("bags", 6948): (1, 1), ("bank", 2318): (40, 0)}
    assert tuple(conn.execute("SELECT quality, icon_id FROM items WHERE item_id = 2318").fetchone()) == (1, 134252)


def test_bank_is_not_read_while_closed(tmp_path):
    lua = run(BAGS_AND_BANK, 'fire("PLAYERBANKSLOTS_CHANGED")')
    conn, _ = import_saved(lua, tmp_path)
    assert conn.execute("SELECT COUNT(*) FROM inventory WHERE location = 'bank'").fetchone()[0] == 0


def test_slash_command_and_diag_do_not_error(tmp_path):
    lua = run(CLASSIC_TRADESKILL, 'SlashCmdList.SIMSARFOREVER("diag"); SlashCmdList.SIMSARFOREVER("")')
    printed = list(lua.eval("printed").values())
    assert any("TradeSkill API: yes" in p for p in printed)
    assert any("recipes" in p for p in printed)


def test_merchant_prices_for_unlimited_stock(tmp_path):
    api = """
    local goods = {
      { "Coarse Thread", "tex", 10, 1, -1, true, false, false, 2320 },
      { "Salt", "tex", 50, 5, -1, true, false, false, 4289 },
      { "Pattern: Rare Thing", "tex", 5000, 1, 1, true, false, false, 9999 },
    }
    function GetMerchantNumItems() return #goods end
    function GetMerchantItemInfo(i) local g = goods[i]; return g[1], g[2], g[3], g[4], g[5], g[6], g[7], g[8] end
    function GetMerchantItemLink(i) return "|Hitem:" .. goods[i][9] .. "::|h" end
    """
    lua = run(api, 'fire("MERCHANT_SHOW")')
    conn, rep = import_saved(lua, tmp_path)
    assert rep["merchant_prices"] == 2
    prices = dict(conn.execute("SELECT item_id, vendor_buy FROM items WHERE vendor_buy IS NOT NULL").fetchall())
    assert prices == {2320: 10, 4289: 10}


FOREVER_MODERN = """
items[2318] = { name = "Light Leather", vendor = 15 }
C_TradeSkillUI = {
  GetBaseProfessionInfo = function() return { professionName = "Leatherworking" } end,
  GetChildProfessionInfo = function() return { professionName = "Classic Leatherworking", parentProfessionName = "Leatherworking" } end,
  IsTradeSkillLinked = function() return linked end,
  GetAllRecipeIDs = function() return { 1, 2, 3 } end,
  GetRecipeInfo = function(id)
    if id == 3 then error("broken recipe") end
    return { name = id == 1 and "Light Armor Kit" or "Handstitched Leather Belt", learned = id == 1 }
  end,
  GetRecipeSchematic = function(id) return {
    outputItemID = 2303 + id, quantityMin = 1, quantityMax = 1,
    reagentSlotSchematics = {
      { quantityRequired = 1, reagentType = 1, reagents = { { itemID = 2318 } } },
      { quantityRequired = 1, reagentType = 0, required = false, reagents = { { itemID = 9999 } } },
    } } end,
}
"""


def test_forever_profession_window(tmp_path):
    lua = run(FOREVER_MODERN, 'fire("TRADE_SKILL_SHOW"); fire("TRADE_SKILL_LIST_UPDATE")')
    conn, rep = import_saved(lua, tmp_path)
    rows = {r["name"]: r for r in conn.execute("SELECT * FROM recipes")}
    assert set(rows) == {"Light Armor Kit", "Handstitched Leather Belt"}
    assert rows["Light Armor Kit"]["profession"] == "Leatherworking"
    assert rows["Light Armor Kit"]["learned"] == 1 and rows["Handstitched Leather Belt"]["learned"] == 0
    reagents = conn.execute("SELECT item_id FROM recipe_reagents WHERE recipe_key = ?",
                            (rows["Light Armor Kit"]["recipe_key"],)).fetchall()
    assert [r[0] for r in reagents] == [2318]                       # the optional slot is left out
    assert "broken recipe" in rep["last_error"]                    # one bad recipe does not stop the rest
    printed = list(lua.eval("printed").values())
    assert sum("recipes saved" in p for p in printed) == 1


def test_linked_profession_does_not_claim_recipes(tmp_path):
    lua = run("linked = true\n" + FOREVER_MODERN, 'fire("TRADE_SKILL_SHOW")')
    conn, _ = import_saved(lua, tmp_path)
    assert {r[0] for r in conn.execute("SELECT learned FROM recipes")} == {None}


def test_trainer_reagents_on_the_next_line(tmp_path):
    api = """
    trainerTooltips = { [1] = { "Light Armor Kit", "Reagents:", "Light Leather (2)" } }
    function GetNumTrainerServices() return 1 end
    function GetTrainerServiceInfo(i) return "Light Armor Kit", "", "available" end
    function GetTrainerServiceItemLink(i) return "|Hitem:2304::|h" end
    function GetTrainerServiceSkillLine(i) return "Leatherworking" end
    """
    lua = run(api, 'fire("TRAINER_SHOW")')
    conn, _ = import_saved(lua, tmp_path)
    assert [tuple(r) for r in conn.execute("SELECT name, count FROM recipe_reagents")] == [("Light Leather", 2)]


def test_profession_name_normalised():
    assert addon_import.profession_name("Classic Leatherworking") == "Leatherworking"
    assert addon_import.profession_name("first aid") == "First Aid"
    assert addon_import.profession_name(None) == "Unknown"


def test_empty_profession_duplicates_are_dropped(tmp_path):
    f = tmp_path / "SimsarForeverExport.lua"
    f.write_text("""SimsarForeverExportDB = { ["version"] = 1, ["recipes"] = {
      ["|Light Armor Kit"] = { ["prof"] = "", ["name"] = "Light Armor Kit", ["reagents"] = {} },
      ["Leatherworking|Light Armor Kit"] = { ["prof"] = "Leatherworking", ["name"] = "Light Armor Kit", ["reagents"] = {} },
      ["|Mystery Item"] = { ["prof"] = "", ["name"] = "Mystery Item", ["reagents"] = {} },
    } }""")
    conn = db.connect(":memory:")
    rep = addon_import.import_file(conn, f)
    assert rep["recipes"] == 2
    assert dict(conn.execute("SELECT name, profession FROM recipes").fetchall()) == {
        "Light Armor Kit": "Leatherworking", "Mystery Item": "Unknown"}


def test_empty_profession_name_is_skipped_in_game(tmp_path):
    lua = run(FOREVER_MODERN.replace('professionName = "Leatherworking"', 'professionName = ""')
              .replace('parentProfessionName = "Leatherworking"', 'parentProfessionName = ""')
              .replace('professionName = "Classic Leatherworking"', 'professionName = ""'),
              'fire("TRADE_SKILL_SHOW")')
    conn, rep = import_saved(lua, tmp_path)
    assert rep["recipes"] == 0


def test_login_drops_recipes_without_a_profession(tmp_path):
    lua = lupa.LuaRuntime()
    lua.execute(STUB)
    lua.execute('SimsarForeverExportDB = { recipes = { ["|Kit"] = { name = "Kit" }, '
                '["Leatherworking|Kit"] = { prof = "Leatherworking", name = "Kit" } } }')
    lua.execute(ADDON)
    lua.execute('fire("PLAYER_LOGIN")')
    assert list(lua.eval("SimsarForeverExportDB.recipes").keys()) == ["Leatherworking|Kit"]


def test_merchant_prices_with_the_forever_api(tmp_path):
    api = """
    local goods = {
      { name = "Coarse Thread", price = 10, stackCount = 1, numAvailable = -1, id = 2320 },
      { name = "Medal", price = 0, stackCount = 1, numAvailable = -1, hasExtendedCost = true, id = 1 },
      { name = "Salt", price = 50, stackCount = 5, numAvailable = -1, id = 4289 },
    }
    C_MerchantFrame = { GetItemInfo = function(i) return goods[i] end }
    function GetMerchantNumItems() return #goods end
    function GetMerchantItemID(i) return goods[i].id end
    """
    lua = run(api, 'fire("MERCHANT_SHOW")')
    conn, rep = import_saved(lua, tmp_path)
    assert rep["merchant_prices"] == 2
    prices = dict(conn.execute("SELECT item_id, vendor_buy FROM items WHERE vendor_buy IS NOT NULL").fetchall())
    assert prices == {2320: 10, 4289: 10}
