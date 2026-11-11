"""Drives addon/SimsarExport against a fake WoW API and imports what it saves."""

from pathlib import Path

import pytest

from simsar import addon_import, db

lupa = pytest.importorskip("lupa.lua51")

ROOT = Path(__file__).resolve().parents[1]
ADDON = (ROOT / "addon" / "SimsarExport" / "SimsarExport.lua").read_text(encoding="utf-8")
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
    f = tmp_path / "SimsarExport.lua"
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


def test_legacy_posting_records_deposit(tmp_path):
    api = """
    items[2318] = { name = "Light Leather", vendor = 15 }
    function GetAuctionSellItemInfo() return "Light Leather", "tex", 20, 1, true, 300, 15, 20, 20, 2318 end
    function CalculateAuctionDeposit(runTime, stackSize, numStacks) return ({ 1, 2, 6 })[runTime] * stackSize * numStacks end
    function PostAuction() end
    """
    lua = run(api, 'fire("NEW_AUCTION_UPDATE"); PostAuction(100, 200, 3, 20, 1)')
    conn, rep = import_saved(lua, tmp_path)
    assert rep["deposits"] == 1
    row = conn.execute("SELECT item_id, quantity, hours, deposit FROM ah_deposits").fetchone()
    assert tuple(row) == (2318, 20, 24, 120)
    assert addon_import.measured_fees(conn)["deposit_rates"][24]["rate"] == pytest.approx(0.4)


def test_slash_command_and_diag_do_not_error(tmp_path):
    lua = run(CLASSIC_TRADESKILL, 'SlashCmdList.SIMSAR("diag"); SlashCmdList.SIMSAR("")')
    printed = list(lua.eval("printed").values())
    assert any("TradeSkill API: yes" in p for p in printed)
    assert any("recipes" in p for p in printed)
