"""Drives addon/SimsarForever against a fake WoW API and imports what it saves."""

from pathlib import Path

import pytest

from simsar_forever import addon_import, db

lupa = pytest.importorskip("lupa.lua51")

ROOT = Path(__file__).resolve().parents[1]
ADDON_DIR = ROOT / "addon" / "SimsarForever"
STUB = (Path(__file__).parent / "wowstub.lua").read_text(encoding="utf-8")


def toc_files():
    lines = (ADDON_DIR / "SimsarForever.toc").read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def load_addon(lua):
    """Load the addon's files in .toc order, sharing one namespace table like the game does."""
    lua.execute("ADDON_NS = {}")
    for name in toc_files():
        chunk = lua.eval("function(src, name) return assert(loadstring(src, name)) end")(
            (ADDON_DIR / name).read_text(encoding="utf-8"), name)
        chunk("SimsarForever", lua.eval("ADDON_NS"))


def run(api_lua, actions_lua, login=True):
    lua = lupa.LuaRuntime()
    lua.execute(STUB)
    lua.execute(api_lua)
    load_addon(lua)
    if login:
        lua.execute('fire("PLAYER_LOGIN"); fire("PLAYER_ENTERING_WORLD")')
    lua.execute(actions_lua)
    return lua


def import_saved(lua, tmp_path):
    f = tmp_path / "SimsarForever.lua"
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
    lua.execute('SimsarForeverDB = { recipes = { ["|Kit"] = { name = "Kit" }, '
                '["Leatherworking|Kit"] = { prof = "Leatherworking", name = "Kit" } } }')
    load_addon(lua)
    lua.execute('fire("PLAYER_LOGIN")')
    assert list(lua.eval("SimsarForeverDB.recipes").keys()) == ["Leatherworking|Kit"]


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


def reminders(lua):
    shown = list(lua.eval("errorsShown").values())
    return [t for t in shown if "/reload" in t]


def test_bank_visit_reminds_to_reload_once():
    lua = run(BAGS_AND_BANK, 'fire("BANKFRAME_OPENED"); fire("BANKFRAME_CLOSED")')
    assert reminders(lua) == ["Simsar Forever: new bank data. Type /reload to send it to the dashboard."]
    assert any("Type /reload" in p for p in lua.eval("printed").values())
    lua.execute('fire("BANKFRAME_OPENED"); fire("BANKFRAME_CLOSED")')
    assert len(reminders(lua)) == 1                                  # not again within ten minutes


def test_addon_never_reloads_the_interface():
    lua = run(BAGS_AND_BANK + FOREVER_MODERN,
              'fire("BANKFRAME_OPENED"); fire("BANKFRAME_CLOSED"); fire("TRADE_SKILL_SHOW"); fire("TRADE_SKILL_CLOSE");'
              'SlashCmdList.SIMSARFOREVER("save"); SlashCmdList.SIMSARFOREVER("")')
    assert lua.eval("reloads") == 0
    assert lua.eval("SimsarForeverSavePrompt") is None
    assert any("Type /reload" in p for p in lua.eval("printed").values())


def test_reload_reminder_can_be_turned_off():
    lua = run(BAGS_AND_BANK, 'SlashCmdList.SIMSARFOREVER("prompt off"); fire("BANKFRAME_OPENED"); fire("BANKFRAME_CLOSED")')
    assert reminders(lua) == []


def test_addon_never_touches_blizzard_popups():
    # The stub's StaticPopupDialogs and StaticPopup_Show raise if used; writing to them from an addon
    # taints Blizzard's popups ("blocked from an action only available to the Blizzard UI").
    lua = run(BAGS_AND_BANK + FOREVER_MODERN,
              'fire("BANKFRAME_OPENED"); fire("BANKFRAME_CLOSED"); fire("TRADE_SKILL_SHOW"); fire("TRADE_SKILL_CLOSE")')
    assert len(reminders(lua)) == 1


def test_closing_a_profession_window_with_new_recipes_reminds_to_reload():
    lua = run(FOREVER_MODERN, 'fire("TRADE_SKILL_SHOW"); fire("TRADE_SKILL_CLOSE")')
    assert "new recipes" in reminders(lua)[0]


def test_logout_keeps_the_last_bags_bank_and_gold(tmp_path):
    # On logout or a character switch the client has emptied the bags and reports 0 gold. The data
    # saved earlier must survive so the dashboard still shows characters you are not logged in with.
    lua = run(BAGS_AND_BANK, 'fire("BANKFRAME_OPENED"); fire("BANKFRAME_CLOSED")')
    lua.execute('money = 0; C_Container.GetContainerNumSlots = function() return 0 end;'
                'fire("PLAYER_MONEY"); fire("BAG_UPDATE_DELAYED"); fire("PLAYER_LOGOUT")')
    conn, _ = import_saved(lua, tmp_path)
    assert conn.execute("SELECT money FROM characters").fetchone()[0] == 123456
    held = {(r["location"], r["item_id"]): r["count"] for r in conn.execute("SELECT * FROM inventory")}
    assert held == {("bags", 2318): 25, ("bags", 6948): 1, ("bank", 2318): 40}


def test_gold_follows_money_changes(tmp_path):
    lua = run(BAGS_AND_BANK, 'money = 500; fire("PLAYER_MONEY")')
    conn, _ = import_saved(lua, tmp_path)
    assert conn.execute("SELECT money FROM characters").fetchone()[0] == 500


# Professions ---------------------------------------------------------------------------------------

def test_skill_levels_per_character(tmp_path):
    api = """
    local profs = { { "Leatherworking", 150, 225 }, { "Skinning", 160, 225 }, { "Cooking", 40, 75 } }
    function GetProfessions() return 1, 2, nil, nil, 3 end
    function GetProfessionInfo(i) local p = profs[i]; return p[1], "icon", p[2], p[3] end
    """
    lua = run(api, 'fire("SKILL_LINES_CHANGED")')
    conn, _ = import_saved(lua, tmp_path)
    skills = {r["profession"]: (r["rank"], r["max_rank"]) for r in conn.execute("SELECT * FROM char_professions")}
    assert skills == {"Leatherworking": (150, 225), "Skinning": (160, 225), "Cooking": (40, 75)}


def test_classic_skill_lines_skip_weapons_and_languages(tmp_path):
    api = """
    local lines = { { "Professions", true }, { "Tailoring", false, nil, 75, nil, nil, 150 },
                    { "Weapon Skills", true }, { "Swords", false, nil, 60, nil, nil, 60 },
                    { "Languages", true }, { "Common", false, nil, 300, nil, nil, 300 } }
    function GetNumSkillLines() return #lines end
    function GetSkillLineInfo(i) return unpack(lines[i]) end
    """
    lua = run(api, "")
    conn, _ = import_saved(lua, tmp_path)
    assert [tuple(r) for r in conn.execute("SELECT profession, rank, max_rank FROM char_professions")] == [
        ("Tailoring", 75, 150)]


def test_known_recipes_are_kept_per_character(tmp_path):
    lua = run(FOREVER_MODERN, 'fire("TRADE_SKILL_SHOW")')
    # An alt with the same profession who has learned nothing
    lua.execute('function UnitName() return "Alt" end')
    lua.execute('C_TradeSkillUI.GetRecipeInfo = function(id) if id == 3 then return nil end '
                'return { name = id == 1 and "Light Armor Kit" or "Handstitched Leather Belt", learned = false } end')
    lua.execute('fire("TRADE_SKILL_SHOW")')
    conn, _ = import_saved(lua, tmp_path)
    known = {(r["char_key"].split("-")[0], r["recipe_key"].split("|")[1]): r["learned"]
             for r in conn.execute("SELECT * FROM char_recipes")}
    assert known[("Tester", "Light Armor Kit")] == 1 and known[("Alt", "Light Armor Kit")] == 0
    # The recipe list says "learned" when any of your characters knows it.
    learned = dict(conn.execute("SELECT name, learned FROM recipes").fetchall())
    assert learned == {"Light Armor Kit": 1, "Handstitched Leather Belt": 0}


def test_trainer_cost_survives_the_profession_window(tmp_path):
    api = CLASSIC_TRADESKILL + """
    trainerTooltips = { [1] = { "Light Armor Kit", "Reagents: Light Leather" } }
    function GetNumTrainerServices() return 1 end
    function GetTrainerServiceInfo(i) return "Light Armor Kit", "", "available" end
    function GetTrainerServiceItemLink(i) return "|Hitem:2304::|h" end
    function GetTrainerServiceSkillLine(i) return "Leatherworking" end
    function GetTrainerServiceSkillReq(i) return "Leatherworking", 25, true end
    function GetTrainerServiceCost(i) return 250 end
    """
    lua = run(api, 'fire("TRAINER_SHOW"); fire("TRADE_SKILL_SHOW")')
    conn, _ = import_saved(lua, tmp_path)
    r = conn.execute("SELECT * FROM recipes WHERE name = 'Light Armor Kit'").fetchone()
    assert (r["source"], r["trainer_cost"], r["skill_req"]) == ("addon-window", 250, 25)


def test_recipe_item_tooltip_gives_required_skill(tmp_path):
    api = """
    items[5000] = { name = "Pattern: Dark Leather Boots", class = 9 }
    tip = { GetItem = function() return nil, "|Hitem:5000::|h" end, NumLines = function() return 3 end,
            GetName = function() return "TT" end }
    local text = { "Pattern: Dark Leather Boots", "Requires Leatherworking (100)",
                   "Reagents: Dark Leather (4), Fine Thread (2)" }
    for i, t in ipairs(text) do _G["TTTextLeft" .. i] = { GetText = function() return t end } end
    """
    lua = run(api, 'GameTooltip.hooks.OnTooltipSetItem(tip)')
    conn, _ = import_saved(lua, tmp_path)
    r = conn.execute("SELECT * FROM recipes WHERE recipe_key = 'recipe-item:5000'").fetchone()
    assert (r["profession"], r["skill_req"], r["name"]) == ("Leatherworking", 100, "Dark Leather Boots")


def test_vendor_recipes_are_saved_even_in_limited_stock(tmp_path):
    api = """
    local goods = { { "Pattern: Rare Thing", "tex", 5000, 1, 1, true, false, false, 9999 } }
    function GetMerchantNumItems() return #goods end
    function GetMerchantItemInfo(i) local g = goods[i]; return g[1], g[2], g[3], g[4], g[5], g[6], g[7], g[8] end
    function GetMerchantItemLink(i) return "|Hitem:" .. goods[i][9] .. "::|h" end
    """
    lua = run(api, 'fire("MERCHANT_SHOW")')
    conn, rep = import_saved(lua, tmp_path)
    assert rep["merchant_prices"] == 0 and rep["vendor_recipes"] == 1
    r = conn.execute("SELECT * FROM vendor_recipes").fetchone()
    assert (r["item_id"], r["price"], r["limited"], r["zone"]) == (9999, 5000, 1, "Stormwind City")


# Auction mail --------------------------------------------------------------------------------------

def test_purchases_and_expired_auctions_from_mail(tmp_path):
    api = """
    local mails = {
      { invoice = { "buyer", "Silk Cloth", "Seller", 900, 900, 0, 0, 0, 0, 0, 20 }, subject = "Auction won: Silk Cloth" },
      { subject = "Auction expired: Light Leather", item = { "Light Leather", 2318, "tex", 15 } },
      { subject = "Auction cancelled: Wool Cloth", item = { "Wool Cloth", 2592, "tex", 5 } },
      { subject = "Hello from a friend" },
    }
    function GetInboxNumItems() return #mails end
    function GetInboxInvoiceInfo(i) if mails[i].invoice then return unpack(mails[i].invoice) end end
    function GetInboxHeaderInfo(i) return nil, nil, "Auction House", mails[i].subject, 0, 0, 29.5 end
    function GetInboxItem(i) if mails[i].item then return unpack(mails[i].item) end end
    """
    lua = run(api, 'fire("MAIL_INBOX_UPDATE"); fire("MAIL_INBOX_UPDATE")')
    conn, rep = import_saved(lua, tmp_path)
    assert rep["mail_events"] == 3
    rows = {r["kind"]: r for r in conn.execute("SELECT * FROM mail_events")}
    assert (rows["bought"]["item_name"], rows["bought"]["amount"], rows["bought"]["quantity"]) == ("Silk Cloth", 900, 20)
    assert (rows["expired"]["item_id"], rows["expired"]["quantity"]) == (2318, 15)
    assert rows["cancelled"]["item_name"] == "Wool Cloth"


# Gold ledger ---------------------------------------------------------------------------------------

LEDGER = BAGS_AND_BANK + """
money = 10000
repairing = false
function InRepairMode() return repairing end
inbox = { { money = 2000, invoice = "seller" } }
function GetInboxHeaderInfo(i) return nil, nil, "Auction House", "Sold", inbox[i].money, 0, 29 end
function GetInboxInvoiceInfo(i) return inbox[i].invoice end
function TakeInboxMoney(i) end
function SendMail(to) end
function TakeTaxiNode() end
C_AuctionHouse = { PostItem = function() end }
function change(by) money = money + by; fire("PLAYER_MONEY") end
"""


def ledger(conn):
    return {(r["category"]): (r["income"], r["expense"], r["n"]) for r in conn.execute(
        "SELECT category, SUM(income) AS income, SUM(expense) AS expense, SUM(n) AS n FROM ledger_days "
        "GROUP BY category")}


def test_gold_changes_are_booked_by_what_you_were_doing(tmp_path):
    lua = run(LEDGER, """
      fire("MERCHANT_SHOW"); change(500); repairing = true; change(-100); repairing = false; fire("MERCHANT_CLOSED")
      clock = clock + 10
      fire("MAIL_SHOW"); TakeInboxMoney(1); change(2000); fire("MAIL_CLOSED")
      clock = clock + 10
      fire("AUCTION_HOUSE_SHOW"); C_AuctionHouse.PostItem(); change(-60); change(-5000); fire("AUCTION_HOUSE_CLOSED")
      clock = clock + 10
      fire("TAXIMAP_OPENED"); fire("TAXIMAP_CLOSED"); clock = clock + 1; change(-50)
      clock = clock + 10
      change(-7)
      fire("QUEST_TURNED_IN", 1, 100, 300); change(300)
    """)
    conn, _ = import_saved(lua, tmp_path)
    assert ledger(conn) == {
        "VENDOR": (500, 0, 1), "REPAIR": (0, 100, 1), "AH_SALE": (2000, 0, 1), "AH_DEPOSIT": (0, 60, 1),
        "AH": (0, 5000, 1), "TAXI": (0, 50, 1), "OTHER": (0, 7, 1), "QUEST": (300, 0, 1)}
    assert conn.execute("SELECT COUNT(*) FROM ledger_tx").fetchone()[0] == 8
    [(balance,)] = conn.execute("SELECT balance FROM balances").fetchall()
    assert balance == 10000 + 500 - 100 + 2000 - 60 - 5000 - 50 - 7 + 300


def test_gold_sent_to_your_own_alt_is_a_transfer(tmp_path):
    lua = run(LEDGER, """
      SimsarForeverDB.characters["Alt-Normal"] = { name = "Alt" }
      fire("MAIL_SHOW"); SendMail("Alt"); change(-1000); SendMail("Stranger"); change(-30)
    """)
    conn, _ = import_saved(lua, tmp_path)
    assert ledger(conn) == {"TRANSFER": (0, 1000, 1), "MAIL": (0, 30, 1)}


def test_gold_changed_while_away_is_booked_once_at_login(tmp_path):
    lua = lupa.LuaRuntime()
    lua.execute(STUB)
    lua.execute(LEDGER)
    lua.execute('SimsarForeverDB = { version = 1, characters = { ["Tester-Normal"] = { money = 9000, moneyTime = 1 }, '
                '["Old-Normal"] = { money = 0 } } }')
    load_addon(lua)
    lua.execute('fire("PLAYER_LOGIN"); fire("PLAYER_ENTERING_WORLD"); fire("PLAYER_ENTERING_WORLD")')
    conn, _ = import_saved(lua, tmp_path)
    assert ledger(conn) == {"UNTRACKED": (1000, 0, 1)}


def test_no_untracked_entry_without_a_trusted_previous_balance(tmp_path):
    # Characters saved by addon 0.1.x have no moneyTime and their gold may be a wrong 0.
    lua = lupa.LuaRuntime()
    lua.execute(STUB)
    lua.execute(LEDGER)
    lua.execute('SimsarForeverDB = { version = 1, characters = { ["Tester-Normal"] = { money = 0 } } }')
    load_addon(lua)
    lua.execute('fire("PLAYER_LOGIN"); fire("PLAYER_ENTERING_WORLD")')
    conn, _ = import_saved(lua, tmp_path)
    assert ledger(conn) == {}


# Tooltip -------------------------------------------------------------------------------------------

TOOLTIP_DATA = """
SimsarForeverData = { version = 1, built = now, items = {
  [2318] = { 950, 2.5, "hold", 0.08, 3, 120, 1000 },
  [6948] = { nil, nil, "vendor" },
} }
"""


def test_tooltip_shows_the_dashboards_advice():
    lua = run("", TOOLTIP_DATA)
    lines = list(lua.eval("ADDON_NS.tooltipLines(2318)").values())
    text = "\n".join(lines)
    assert "you keep" in text and "2.5 sold per day" in text
    assert "Hold" in text and "+8% expected in 3 days" in text
    assert "crafting it makes" in text
    assert any("vendor" in line for line in lua.eval("ADDON_NS.tooltipLines(6948)").values())
    assert lua.eval("ADDON_NS.tooltipLines(1)") is None


def test_tooltip_lines_are_added_and_can_be_turned_off():
    lua = run("", TOOLTIP_DATA + 'GameTooltip.link = "|Hitem:2318::|h"; GameTooltip.hooks.OnTooltipSetItem(GameTooltip)')
    assert len(lua.eval("GameTooltip.added")) >= 3
    lua.execute('GameTooltip.added = nil; SlashCmdList.SIMSARFOREVER("tooltip off"); '
                'GameTooltip.hooks.OnTooltipSetItem(GameTooltip)')
    assert lua.eval("GameTooltip.added") is None


def test_tooltip_without_data_does_nothing():
    lua = run("", 'GameTooltip.link = "|Hitem:2318::|h"; GameTooltip.hooks.OnTooltipSetItem(GameTooltip)')
    assert lua.eval("GameTooltip.added") is None
    assert "no data yet" in lua.eval("ADDON_NS.tooltipStatus()")
