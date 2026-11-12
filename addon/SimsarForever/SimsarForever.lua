-- Simsar Forever
-- Writes what the game knows about recipes, professions, bags, gold and auction mail to
-- SavedVariables, so the Simsar Forever dashboard can read it, and shows the dashboard's advice in
-- item tooltips (Tooltip.lua). It never posts, buys or clicks anything, and it never reloads the
-- interface.
--
-- Data is only written to disk on /reload or logout.

local _, ns = ...
ns = ns or {}

local DB_VERSION = 1

SimsarForeverDB = SimsarForeverDB or {}

local function say(msg)
  print("|cff4fc3f7Simsar Forever|r " .. tostring(msg))
end

local function db()
  local d = SimsarForeverDB
  d.version = DB_VERSION
  d.recipes = d.recipes or {}
  d.invoices = d.invoices or {}
  d.mail = d.mail or {}
  d.characters = d.characters or {}
  d.items = d.items or {}
  d.stats = d.stats or {}
  return d
end

local function idFromLink(link)
  if type(link) ~= "string" then return nil end
  return tonumber(link:match("item:(%d+)"))
end

local function settings()
  local d = db()
  d.settings = d.settings or {}
  return d.settings
end

ns.say, ns.db, ns.settings, ns.idFromLink = say, db, settings, idFromLink

local function rememberItem(itemID)
  if not itemID then return end
  local name, _, quality, _, _, _, _, _, _, icon, sellPrice = GetItemInfo(itemID)
  if not icon and GetItemInfoInstant then icon = select(5, GetItemInfoInstant(itemID)) end
  if name then
    db().items[itemID] = { name = name, vendor = sellPrice, quality = quality, icon = icon }
  end
end

local function today()
  return tonumber(date("%Y%m%d"))
end

-- The character that is logged in. Its key matches the dashboard's: "Name-Realm".
local function charKey()
  return tostring(UnitName("player")) .. "-" .. tostring(GetRealmName())
end

local function character()
  local d = db()
  local key = charKey()
  local c = d.characters[key] or {}
  d.characters[key] = c
  c.name, c.realm, c.faction = UnitName("player"), GetRealmName(), UnitFactionGroup("player")
  c.class = select(2, UnitClass("player"))
  return c
end

-- Recipes are shared by every character in d.recipes; which character knows which one is kept
-- per character, so an alt opening a profession window does not hide what the main has learned.
local function markKnown(prof, name, learned)
  if learned == nil or not prof or not name then return end
  local c = character()
  c.known = c.known or {}
  c.known[prof .. "|" .. name] = learned and true or false
end

local function storeRecipe(r)
  local key = (r.prof or "?") .. "|" .. (r.name or "?")
  local old = db().recipes[key]
  if r.source == "window" or r.source == "trainer" then markKnown(r.prof, r.name, r.learned) end
  -- A trainer or tooltip sighting must not downgrade a recipe read from the profession window.
  if old and old.source == "window" and r.source ~= "window" then
    old.trainerCost = old.trainerCost or r.trainerCost
    old.skill = old.skill or r.skill
    return false
  end
  -- The profession window does not show what a trainer charges; keep what the trainer said.
  if old then
    r.trainerCost = r.trainerCost or old.trainerCost
    r.skill = r.skill or old.skill
  end
  r.updated = time()
  db().recipes[key] = r
  rememberItem(r.itemID)
  for _, reagent in ipairs(r.reagents or {}) do rememberItem(reagent.id) end
  return true
end

-- Profession skill levels ---------------------------------------------------------------------

-- Skill lines that are professions. Classic clients list weapon skills and languages in the same
-- list, so anything else is ignored.
local PROFESSION_NAMES = {
  Alchemy = true, Blacksmithing = true, Cooking = true, Enchanting = true, Engineering = true,
  ["First Aid"] = true, Fishing = true, Herbalism = true, Inscription = true, Jewelcrafting = true,
  Leatherworking = true, Mining = true, Skinning = true, Tailoring = true,
}

local function storeSkill(name, rank, max)
  if not name or name == "" or name == "UNKNOWN" or not tonumber(rank) then return false end
  local c = character()
  c.professions = c.professions or {}
  c.professions[name] = { rank = tonumber(rank), max = tonumber(max), seen = time() }
  return true
end

local function readSkills()
  local n = 0
  -- Modern clients
  if GetProfessions and GetProfessionInfo then
    for _, index in pairs({ GetProfessions() }) do
      if index then
        local name, _, rank, max = GetProfessionInfo(index)
        if storeSkill(name, rank, max) then n = n + 1 end
      end
    end
  end
  -- Classic skill list
  if n == 0 and GetNumSkillLines and GetSkillLineInfo then
    for i = 1, GetNumSkillLines() do
      local name, isHeader, _, rank, _, _, max = GetSkillLineInfo(i)
      if not isHeader and PROFESSION_NAMES[name] and storeSkill(name, rank, max) then n = n + 1 end
    end
  end
  return n
end

-- The open profession window also reports the skill of that profession.
local function readWindowSkill()
  if GetTradeSkillLine then
    local name, rank, max = GetTradeSkillLine()
    if name and name ~= "UNKNOWN" and tonumber(rank) and tonumber(rank) > 0 then storeSkill(name, rank, max) end
  end
  local T = C_TradeSkillUI
  if T and T.GetBaseProfessionInfo then
    local base = T.GetBaseProfessionInfo()
    local foreign = (T.IsTradeSkillLinked and T.IsTradeSkillLinked()) or (T.IsTradeSkillGuild and T.IsTradeSkillGuild())
      or (T.IsNPCCrafting and T.IsNPCCrafting())
    if base and not foreign and base.professionName and base.professionName ~= "" and base.skillLevel then
      storeSkill(base.professionName, base.skillLevel, base.maxSkillLevel)
    end
  end
end

-- Profession window, classic TradeSkill API
local function readTradeSkills()
  if not (GetNumTradeSkills and GetTradeSkillLine and GetTradeSkillInfo) then return 0 end
  local prof = GetTradeSkillLine()
  if not prof or prof == "UNKNOWN" then return 0 end
  local n = 0
  for i = 1, GetNumTradeSkills() do
    local name, kind = GetTradeSkillInfo(i)
    if name and kind ~= "header" and kind ~= "subheader" then
      local lo, hi = 1, 1
      if GetTradeSkillNumMade then lo, hi = GetTradeSkillNumMade(i) end
      local reagents = {}
      for j = 1, (GetTradeSkillNumReagents(i) or 0) do
        local rname, _, count = GetTradeSkillReagentInfo(i, j)
        local rlink = GetTradeSkillReagentItemLink and GetTradeSkillReagentItemLink(i, j)
        reagents[#reagents + 1] = { id = idFromLink(rlink), name = rname, count = count }
      end
      local recipeLink = GetTradeSkillRecipeLink and GetTradeSkillRecipeLink(i)
      storeRecipe({
        prof = prof, name = name, source = "window", learned = true,
        itemID = idFromLink(GetTradeSkillItemLink and GetTradeSkillItemLink(i)),
        spellID = recipeLink and tonumber(recipeLink:match("enchant:(%d+)")),
        yieldMin = lo or 1, yieldMax = hi or lo or 1, reagents = reagents,
      })
      n = n + 1
    end
  end
  return n
end

-- Profession window, classic Craft API (Enchanting on Vanilla-style clients)
local function readCrafts()
  if not (GetNumCrafts and GetCraftDisplaySkillLine and GetCraftInfo) then return 0 end
  local prof = GetCraftDisplaySkillLine()
  if not prof or prof == "UNKNOWN" then return 0 end
  local n = 0
  for i = 1, GetNumCrafts() do
    local name, _, kind = GetCraftInfo(i)
    if name and kind ~= "header" then
      local reagents = {}
      for j = 1, (GetCraftNumReagents(i) or 0) do
        local rname, _, count = GetCraftReagentInfo(i, j)
        local rlink = GetCraftReagentItemLink and GetCraftReagentItemLink(i, j)
        reagents[#reagents + 1] = { id = idFromLink(rlink), name = rname, count = count }
      end
      local link = GetCraftItemLink and GetCraftItemLink(i)
      storeRecipe({
        prof = prof, name = name, source = "window", learned = true,
        itemID = idFromLink(link),
        spellID = link and tonumber(link:match("enchant:(%d+)")),
        yieldMin = 1, yieldMax = 1, reagents = reagents,
      })
      n = n + 1
    end
  end
  return n
end

-- Profession window, modern API. Also lists recipes the character has not learned.
local BASIC_REAGENT = Enum and Enum.CraftingReagentType and Enum.CraftingReagentType.Basic or 1

local function itemName(itemID)
  return GetItemInfo(itemID) or (C_Item and C_Item.GetItemNameByID and C_Item.GetItemNameByID(itemID))
end

-- Profession window on the WoW Forever client (checked with /sfe diag on build 1.60.1).
-- Lists every recipe of the open profession, learned or not.
local function readModern()
  local T = C_TradeSkillUI
  if not (T and T.GetAllRecipeIDs and T.GetRecipeSchematic and T.GetRecipeInfo) then return 0 end
  local base = T.GetBaseProfessionInfo and T.GetBaseProfessionInfo()
  local child = T.GetChildProfessionInfo and T.GetChildProfessionInfo()
  local function named(s) return s and s ~= "" and s or nil end
  -- While the window opens or switches profession the client briefly reports an empty name. Skip
  -- that read; the next TRADE_SKILL_LIST_UPDATE carries the name.
  local prof = named(base and base.professionName) or named(child and child.parentProfessionName)
    or named(child and child.professionName)
  if not prof then return 0 end
  -- A profession linked by another player or an NPC crafter says nothing about what you know.
  local foreign = (T.IsTradeSkillLinked and T.IsTradeSkillLinked()) or (T.IsTradeSkillGuild and T.IsTradeSkillGuild())
    or (T.IsNPCCrafting and T.IsNPCCrafting())
  local n, failed = 0, 0
  for _, recipeID in ipairs(T.GetAllRecipeIDs() or {}) do
    local ok, err = pcall(function()
      local ri = T.GetRecipeInfo(recipeID)
      if not ri or ri.isDummyRecipe then return end
      local sch = T.GetRecipeSchematic(recipeID, false)
      if not sch then return end
      local reagents = {}
      for _, slot in ipairs(sch.reagentSlotSchematics or {}) do
        local r = slot.reagents and slot.reagents[1]
        local basic = slot.reagentType == nil or slot.reagentType == BASIC_REAGENT
        if r and r.itemID and basic and slot.required ~= false then
          reagents[#reagents + 1] = { id = r.itemID, name = itemName(r.itemID), count = slot.quantityRequired }
        end
      end
      local learned = ri.learned and true or false
      if foreign then learned = nil end
      local existing = db().recipes[prof .. "|" .. ri.name]
      if foreign and existing then learned = existing.learned end
      storeRecipe({
        prof = prof, name = ri.name, source = foreign and "linked" or "window", learned = learned,
        itemID = sch.outputItemID, spellID = recipeID,
        yieldMin = sch.quantityMin or 1, yieldMax = sch.quantityMax or sch.quantityMin or 1,
        reagents = reagents,
      })
      n = n + 1
    end)
    if not ok then
      failed = failed + 1
      db().stats.lastError = "recipe " .. tostring(recipeID) .. ": " .. tostring(err)
    end
  end
  db().stats.lastModern = { time = time(), prof = prof, recipes = n, failed = failed, foreign = foreign and true or false }
  return n
end

local function readProfessionWindow()
  local total = 0
  pcall(readWindowSkill)
  for _, fn in ipairs({ readTradeSkills, readCrafts, readModern }) do
    local ok, n = pcall(fn)
    if ok and type(n) == "number" then
      total = total + n
    elseif not ok then
      db().stats.lastError = tostring(n)
    end
  end
  db().stats.lastWindow = { time = time(), recipes = total }
  return total
end

-- Tooltip helpers: the trainer and recipe items only expose reagents through tooltip text.
local scanner = CreateFrame("GameTooltip", "SimsarForeverScanTooltip", nil, "GameTooltipTemplate")
scanner:SetOwner(WorldFrame, "ANCHOR_NONE")

local reagentPrefix = (SPELL_REAGENTS or "Reagents: "):gsub("|n", ""):gsub("%s+$", "")
local reagentPattern = "^" .. reagentPrefix:gsub("%p", "%%%0") .. "%s*(.+)$"
-- "Requires Leatherworking (225)"
local requiresPattern = "^" .. (ITEM_MIN_SKILL or "Requires %s (%d)"):gsub("%p", "%%%0")
  :gsub("%%%%s", "(.-)"):gsub("%%%%d", "(%%d+)") .. "$"

local function parseReagentLine(text)
  if not text then return nil end
  local body = text:match(reagentPattern)
  if not body then return nil end
  local reagents = {}
  for part in body:gmatch("[^,]+") do
    part = part:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):match("^%s*(.-)%s*$")
    local name, count = part:match("^(.-)%s*%((%d+)%)$")
    reagents[#reagents + 1] = { name = name or part, count = tonumber(count) or 1 }
  end
  return reagents
end

local function tooltipLines(tip)
  local out = {}
  for i = 1, tip:NumLines() do
    local line = _G[tip:GetName() .. "TextLeft" .. i]
    out[i] = line and line:GetText()
  end
  return out
end

local function tooltipReagents(tip)
  local lines = tooltipLines(tip)
  for i = 1, #lines do
    local text = lines[i]
    local reagents = parseReagentLine(text)
    if reagents then return reagents end
    -- Some clients put the list on the line after a bare "Reagents:" label.
    if text and text:gsub("%s+$", "") == reagentPrefix and lines[i + 1] then
      return parseReagentLine(reagentPrefix .. " " .. lines[i + 1])
    end
  end
  return nil
end

local function tooltipRequires(tip)
  for _, text in ipairs(tooltipLines(tip)) do
    local prof, skill = (text or ""):gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):match(requiresPattern)
    if prof and PROFESSION_NAMES[prof] then return prof, tonumber(skill) end
  end
  return nil
end

local function readTrainer()
  if not (GetNumTrainerServices and GetTrainerServiceInfo) then return 0 end
  local n = 0
  for i = 1, GetNumTrainerServices() do
    local name, _, category = GetTrainerServiceInfo(i)
    if name and category ~= "header" then
      local link = GetTrainerServiceItemLink and GetTrainerServiceItemLink(i)
      local itemID = idFromLink(link)
      scanner:ClearLines()
      local reagents
      if pcall(scanner.SetTrainerService, scanner, i) then
        reagents = tooltipReagents(scanner)
      end
      if itemID or reagents then
        local skill = GetTrainerServiceSkillReq and select(2, GetTrainerServiceSkillReq(i))
        local cost = GetTrainerServiceCost and GetTrainerServiceCost(i)
        local thisProf = (GetTrainerServiceSkillLine and GetTrainerServiceSkillLine(i)) or "?"
        storeRecipe({
          prof = thisProf, name = name, source = "trainer",
          learned = category == "used", itemID = itemID,
          yieldMin = 1, yieldMax = 1, reagents = reagents or {},
          skill = tonumber(skill), trainerCost = cost,
        })
        n = n + 1
      end
    end
  end
  db().stats.lastTrainer = { time = time(), recipes = n }
  return n
end

-- Recipe items (Pattern:, Formula: ...) seen in any tooltip
local RECIPE_CLASS = (Enum and Enum.ItemClass and Enum.ItemClass.Recipe) or 9

local function onItemTooltip(tip)
  local _, link = tip:GetItem()
  local recipeItemID = idFromLink(link)
  if not recipeItemID then return end
  local name, _, _, _, _, _, _, _, _, _, _, classID = GetItemInfo(recipeItemID)
  if classID ~= RECIPE_CLASS or not name then return end
  local reagents = tooltipReagents(tip)
  if not reagents then return end
  local kind, product = name:match("^(%a+): (.+)$")
  if not product then return end
  local reqProf, reqSkill = tooltipRequires(tip)
  db().recipeItems = db().recipeItems or {}
  db().recipeItems[recipeItemID] = {
    name = name, kind = kind, product = product, reagents = reagents, seen = time(),
    prof = reqProf, skill = reqSkill,
  }
end

-- Auction mail ----------------------------------------------------------------------------------
-- Sale invoices give the real auction house cut and deposit; purchase invoices give what you
-- really paid; expired and cancelled auctions show how often a listing fails.

local function subjectPattern(fmt, fallback)
  return "^" .. (fmt or fallback):gsub("%p", "%%%0"):gsub("%%%%s", "(.+)") .. "$"
end
local EXPIRED = subjectPattern(AUCTION_EXPIRED_MAIL_SUBJECT, "Auction expired: %s")
local CANCELLED = subjectPattern(AUCTION_REMOVED_MAIL_SUBJECT, "Auction cancelled: %s")

local function mailItem(i)
  if not GetInboxItem then return nil, nil end
  local name, itemID, _, count = GetInboxItem(i, 1)
  return itemID, count
end

local function onMailUpdate()
  if not GetInboxNumItems then return end
  local d = db()
  for i = 1, GetInboxNumItems() do
    local _, _, sender, subject, _, _, daysLeft = GetInboxHeaderInfo(i)
    -- The same mail shows up on every inbox refresh; key it on its content and expiry hour.
    local expires = math.floor((time() + (daysLeft or 0) * 86400) / 3600)
    local kind, item, _, bid, buyout, deposit, consignment, _, _, _, count
    if GetInboxInvoiceInfo then
      kind, item, _, bid, buyout, deposit, consignment, _, _, _, count = GetInboxInvoiceInfo(i)
    end
    if kind == "seller" and item and bid and bid > 0 then
      local key = table.concat({ item, bid, deposit or 0, consignment or 0, expires }, "|")
      if not d.invoices[key] then
        d.invoices[key] = {
          item = item, count = count, bid = bid, buyout = buyout,
          deposit = deposit, consignment = consignment, seen = time(), char = charKey(),
        }
      end
    elseif kind == "buyer" and item and bid and bid > 0 then
      local key = table.concat({ "buy", item, bid, expires }, "|")
      if not d.mail[key] then
        d.mail[key] = { kind = "bought", item = item, count = count, amount = bid, seen = time(), char = charKey() }
      end
    elseif subject then
      local expired, cancelled = subject:match(EXPIRED), subject:match(CANCELLED)
      local what = expired or cancelled
      if what then
        local itemID, n = mailItem(i)
        local key = table.concat({ expired and "expired" or "cancelled", what, n or 0, expires }, "|")
        if not d.mail[key] then
          d.mail[key] = { kind = expired and "expired" or "cancelled", item = what, itemID = itemID,
            count = n, seen = time(), char = charKey() }
        end
      end
    end
  end
end

-- Vendor prices for reagents like thread, salt and dyes. Only unlimited stock counts.
-- The Forever client has C_MerchantFrame.GetItemInfo instead of GetMerchantItemInfo.
local function merchantItem(i)
  if C_MerchantFrame and C_MerchantFrame.GetItemInfo then
    local info = C_MerchantFrame.GetItemInfo(i)
    if info then
      return info.name, info.price, info.stackCount, info.numAvailable, info.hasExtendedCost or info.currencyID
    end
    return nil
  end
  if GetMerchantItemInfo then
    local name, _, price, quantity, numAvailable, _, _, extendedCost = GetMerchantItemInfo(i)
    return name, price, quantity, numAvailable, extendedCost
  end
end

local RECIPE_NAME = { Pattern = true, Formula = true, Plans = true, Recipe = true, Schematic = true,
  Design = true, Manual = true, Technique = true }

local function onMerchantShow()
  if not GetMerchantNumItems then return end
  local d = db()
  d.merchant = d.merchant or {}
  d.merchantRecipes = d.merchantRecipes or {}
  local n = 0
  for i = 1, GetMerchantNumItems() do
    local name, price, quantity, numAvailable, extendedCost = merchantItem(i)
    local itemID = (GetMerchantItemID and GetMerchantItemID(i))
      or idFromLink(GetMerchantItemLink and GetMerchantItemLink(i))
    if itemID and name and price and price > 0 and not extendedCost then
      if numAvailable == -1 then
        d.merchant[itemID] = { name = name, price = price / math.max(quantity or 1, 1), seen = time() }
        n = n + 1
      end
      -- Recipes sold by vendors, often in limited stock.
      local prefix = name:match("^(%a+):")
      if prefix and RECIPE_NAME[prefix] then
        d.merchantRecipes[itemID] = { name = name, price = price, limited = numAvailable ~= -1 or nil,
          vendor = UnitName and UnitName("npc") or nil, zone = GetZoneText and GetZoneText() or nil, seen = time() }
        rememberItem(itemID)
      end
    end
  end
  d.stats.lastMerchant = { time = time(), items = n }
end

-- Bags and bank of every character you log in with. The bank can only be read while it is open.
local NUM_BAGS = NUM_BAG_SLOTS or 4
local NUM_BANK_BAGS = NUM_BANKBAGSLOTS or 7
local bankOpen = false

local function numSlots(bag)
  if C_Container and C_Container.GetContainerNumSlots then return C_Container.GetContainerNumSlots(bag) or 0 end
  return GetContainerNumSlots and GetContainerNumSlots(bag) or 0
end

local function slotItem(bag, slot)
  if C_Container and C_Container.GetContainerItemInfo then
    local info = C_Container.GetContainerItemInfo(bag, slot)
    if info then return info.itemID, info.stackCount, info.isBound end
    return nil
  end
  if GetContainerItemInfo then
    local _, count, _, _, _, _, link = GetContainerItemInfo(bag, slot)
    return idFromLink(link), count, nil
  end
end

local function readContainers(bags)
  local items, seen = {}, {}
  for _, bag in ipairs(bags) do
    if not seen[bag] then
      seen[bag] = true
      for slot = 1, numSlots(bag) do
        local itemID, count, bound = slotItem(bag, slot)
        if itemID then
          local e = items[itemID] or { count = 0, bound = 0 }
          e.count = e.count + (count or 1)
          if bound then e.bound = e.bound + (count or 1) end
          items[itemID] = e
          rememberItem(itemID)
        end
      end
    end
  end
  return items
end

local function bagIDs()
  local ids = {}
  for bag = 0, NUM_BAGS do ids[#ids + 1] = bag end
  local B = Enum and Enum.BagIndex
  if B and B.ReagentBag then ids[#ids + 1] = B.ReagentBag end
  return ids
end

local function bankIDs()
  local ids = { BANK_CONTAINER or -1 }
  for bag = NUM_BAGS + 1, NUM_BAGS + NUM_BANK_BAGS do ids[#ids + 1] = bag end
  local B = Enum and Enum.BagIndex
  if B then
    if B.Reagentbank then ids[#ids + 1] = B.Reagentbank end
    for i = 1, 6 do
      if B["CharacterBankTab_" .. i] then ids[#ids + 1] = B["CharacterBankTab_" .. i] end
    end
  end
  return ids
end

-- While logging out or switching characters the client has already emptied the bags and reports
-- 0 gold. A scan then would overwrite the character's last good data, so every write checks that
-- the backpack is readable first.
local function bagsLoaded()
  return numSlots(0) > 0
end

local ledgerLogin

local function scanMoney()
  if not (GetMoney and bagsLoaded()) then return end
  -- The first reading of a session must compare against the saved balance before replacing it.
  if ledgerLogin and ledgerLogin() then return end
  local c = character()
  c.money = GetMoney()
  c.moneyTime = time()
  c.balance = c.balance or {}
  c.balance[today()] = c.money
end

local function scanBags()
  if not bagsLoaded() then return end
  local c = character()
  c.bags = readContainers(bagIDs())
  c.bagsTime = time()
  scanMoney()
end

local function scanBank()
  if not (bankOpen and bagsLoaded()) then return end
  local c = character()
  c.bank = readContainers(bankIDs())
  c.bankTime = time()
end

-- Gold ledger -----------------------------------------------------------------------------------
-- Every change of the character's gold is booked under a category, decided by what the player is
-- doing at that moment: the window that is open (vendor, auction house, mailbox, trainer, ...) or
-- an action seen just before (taking money from a sale mail, posting an auction, repairing).
--
--   c.ledger.days[YYYYMMDD][category] = { i = income, o = spent, n = count }
--   c.ledger.recent = { { t, a = signed amount, k = category, z = zone }, ... }  (last 90 days)
--   c.balance[YYYYMMDD] = gold at the end of that day

local RECENT_MAX = 1500
local RECENT_DAYS = 90
local CONTEXT_LINGER = 3      -- seconds a closed window still counts (taxi fares are paid after closing)
local HINT_SECONDS = 10

local context, contextUntil = nil, nil
local hints = {}              -- { cat, amount (optional, exact match), expires }
local lastMoney = nil

local function setContext(cat)
  context, contextUntil = cat, nil
end

local function closeContext(cat)
  if context == cat then contextUntil = GetTime() + CONTEXT_LINGER end
end

local function hint(cat, amount)
  hints[#hints + 1] = { cat = cat, amount = amount, expires = GetTime() + HINT_SECONDS }
end

local function ownCharacter(name)
  if not name or name == "" then return false end
  name = name:match("^([^%-]+)") or name
  for _, c in pairs(db().characters) do
    if c.name == name then return true end
  end
  return false
end

local function categoryFor(diff)
  local now = GetTime()
  -- An exact amount we were told to expect (a sale mail, a quest reward) wins.
  for i, h in ipairs(hints) do
    if h.expires >= now and h.amount and h.amount == diff then
      table.remove(hints, i)
      return h.cat
    end
  end
  for i = #hints, 1, -1 do
    local h = hints[i]
    if h.expires < now then
      table.remove(hints, i)
    elseif not h.amount and ((h.cat == "AH_DEPOSIT" or h.cat == "AH_BUY" or h.cat == "REPAIR" or h.cat == "TAXI")
        and diff < 0 or h.cat == "LOOT" and diff > 0 or h.cat == "TRANSFER") then
      table.remove(hints, i)
      return h.cat
    end
  end
  if context and (not contextUntil or now <= contextUntil) then
    if context == "VENDOR" and diff < 0 and InRepairMode and InRepairMode() then return "REPAIR" end
    return context
  end
  return "OTHER"
end

local function book(cat, amount)
  local c = character()
  c.ledger = c.ledger or {}
  local L = c.ledger
  L.days = L.days or {}
  L.recent = L.recent or {}
  local day = today()
  local bucket = L.days[day] or {}
  L.days[day] = bucket
  local e = bucket[cat] or { i = 0, o = 0, n = 0 }
  bucket[cat] = e
  if amount > 0 then e.i = e.i + amount else e.o = e.o - amount end
  e.n = e.n + 1
  L.recent[#L.recent + 1] = { t = time(), a = amount, k = cat, z = GetZoneText and GetZoneText() or nil }
  if #L.recent > RECENT_MAX + 100 then
    local cutoff, keep = time() - RECENT_DAYS * 86400, {}
    for i = math.max(1, #L.recent - RECENT_MAX + 1), #L.recent do
      if L.recent[i].t >= cutoff then keep[#keep + 1] = L.recent[i] end
    end
    L.recent = keep
  end
end

local function onMoney()
  if not (GetMoney and bagsLoaded()) then return end
  if ledgerLogin() then return end
  local now = GetMoney()
  local diff = now - lastMoney
  lastMoney = now
  if diff ~= 0 then book(categoryFor(diff), diff) end
  scanMoney()
end

-- Gold that changed while the addon was not running (played on another computer, or before this
-- version) is booked once at login so the totals still add up.
-- Returns true when it ran (and saved the balance itself).
function ledgerLogin()
  if lastMoney ~= nil or not (GetMoney and bagsLoaded()) then return false end
  local c = character()
  local now = GetMoney()
  if c.moneyTime and c.money and now ~= c.money then book("UNTRACKED", now - c.money) end
  lastMoney = now
  scanMoney()
  return true
end

local function mailMoneyHint(i)
  if not GetInboxHeaderInfo then return end
  local _, _, sender, _, money, cod = GetInboxHeaderInfo(i)
  local kind = GetInboxInvoiceInfo and GetInboxInvoiceInfo(i)
  if money and money > 0 then
    hint(kind == "seller" and "AH_SALE" or ownCharacter(sender) and "TRANSFER" or "MAIL", money)
  end
  if cod and cod > 0 then hint("MAIL", -cod) end
end

local hooked = false
local function hookActions()
  if hooked or not hooksecurefunc then return end
  hooked = true
  local function try(tbl, name, fn)
    if tbl and type(tbl[name]) == "function" then pcall(hooksecurefunc, tbl, name, fn) end
  end
  try(_G, "TakeInboxMoney", function(i) pcall(mailMoneyHint, i) end)
  try(_G, "AutoLootMailItem", function(i) pcall(mailMoneyHint, i) end)
  try(_G, "TakeInboxItem", function(i) pcall(mailMoneyHint, i) end)
  try(_G, "SendMail", function(to) hint(ownCharacter(to) and "TRANSFER" or "MAIL") end)
  try(_G, "RepairAllItems", function(guild) if not guild then hint("REPAIR") end end)
  try(_G, "TakeTaxiNode", function() hint("TAXI") end)
  try(_G, "PostAuction", function() hint("AH_DEPOSIT") end)
  try(_G, "StartAuction", function() hint("AH_DEPOSIT") end)
  try(_G, "PlaceAuctionBid", function() hint("AH_BUY") end)
  try(C_AuctionHouse, "PostItem", function() hint("AH_DEPOSIT") end)
  try(C_AuctionHouse, "PostCommodity", function() hint("AH_DEPOSIT") end)
  try(C_AuctionHouse, "PlaceBid", function() hint("AH_BUY") end)
  try(C_AuctionHouse, "ConfirmCommoditiesPurchase", function() hint("AH_BUY") end)
end

local CONTEXT_OPEN = {
  MERCHANT_SHOW = "VENDOR", AUCTION_HOUSE_SHOW = "AH", MAIL_SHOW = "MAIL", TRAINER_SHOW = "TRAINING",
  TAXIMAP_OPENED = "TAXI", TRADE_SHOW = "TRADE", LOOT_OPENED = "LOOT", QUEST_DETAIL = "QUEST",
  QUEST_PROGRESS = "QUEST", QUEST_COMPLETE = "QUEST", BANKFRAME_OPENED = "BANK", GUILDBANKFRAME_OPENED = "GUILD",
  BARBER_SHOP_OPEN = "BARBER", CONFIRM_TALENT_WIPE = "TRAINING",
}
local CONTEXT_CLOSE = {
  MERCHANT_CLOSED = "VENDOR", AUCTION_HOUSE_CLOSED = "AH", MAIL_CLOSED = "MAIL", TRAINER_CLOSED = "TRAINING",
  TAXIMAP_CLOSED = "TAXI", TRADE_CLOSED = "TRADE", LOOT_CLOSED = "LOOT", QUEST_FINISHED = "QUEST",
  BANKFRAME_CLOSED = "BANK", GUILDBANKFRAME_CLOSED = "GUILD", BARBER_SHOP_CLOSE = "BARBER",
}

local function onLedgerEvent(event, ...)
  if CONTEXT_OPEN[event] then
    local cat = CONTEXT_OPEN[event]
    -- Trading with one of your own characters moves gold between pockets; it is not income.
    if cat == "TRADE" and UnitName and ownCharacter(UnitName("npc")) then cat = "TRANSFER" end
    setContext(cat)
  elseif CONTEXT_CLOSE[event] then
    closeContext(CONTEXT_CLOSE[event] == "TRADE" and context == "TRANSFER" and "TRANSFER" or CONTEXT_CLOSE[event])
  elseif event == "QUEST_TURNED_IN" then
    local _, _, money = ...
    if money and money > 0 then hint("QUEST", money) end
  elseif event == "CHAT_MSG_MONEY" then
    hint("LOOT")
  end
end

-- Icon file ids of every item the client knows, so the dashboard can show item icons.
-- GetItemInfoInstant answers from local data without asking the server; the scan runs once per
-- client build, a few thousand ids per frame.
local ICON_SCAN_MAX_ID = 300000
local ICON_SCAN_STEP = 4000

local function scanIcons()
  if not GetItemInfoInstant then return end
  local d = db()
  local build = select(2, GetBuildInfo())
  if d.iconsBuild == build and d.icons then return end
  local icons, nextID = {}, 1
  local function step()
    local last = math.min(nextID + ICON_SCAN_STEP - 1, ICON_SCAN_MAX_ID)
    for id = nextID, last do
      local _, _, _, _, icon = GetItemInfoInstant(id)
      if icon then icons[id] = icon end
    end
    nextID = last + 1
    if nextID <= ICON_SCAN_MAX_ID then
      C_Timer.After(0, step)
    else
      d.icons, d.iconsBuild = icons, build
    end
  end
  step()
end

local function diag()
  local function has(x) return x and "yes" or "no" end
  local version, build, _, interface = GetBuildInfo()
  say("client " .. tostring(version) .. " build " .. tostring(build) .. ", interface " .. tostring(interface))
  say("TradeSkill API: " .. has(GetNumTradeSkills) .. ", Craft API: " .. has(GetNumCrafts)
    .. ", C_TradeSkillUI: " .. has(C_TradeSkillUI and C_TradeSkillUI.GetAllRecipeIDs))
  say("Trainer API: " .. has(GetNumTrainerServices) .. ", reagent label: '" .. reagentPrefix .. "'")
  say("Merchant API: " .. has(C_MerchantFrame and C_MerchantFrame.GetItemInfo) .. " (modern), "
    .. has(GetMerchantItemInfo) .. " (classic)")
  say("Bags API: " .. has(C_Container and C_Container.GetContainerItemInfo) .. " (modern), "
    .. has(GetContainerItemInfo) .. " (classic), invoices: " .. has(GetInboxInvoiceInfo))
  say("Skills API: " .. has(GetProfessions) .. " (modern), " .. has(GetSkillLineInfo) .. " (classic), AH API: "
    .. has(C_AuctionHouse and C_AuctionHouse.PostItem) .. " (modern), " .. has(PostAuction or StartAuction) .. " (classic)")
  if db().stats.lastError then say("last error: " .. db().stats.lastError) end
end

local function status()
  local d, recipes, learned, invoices, chars = db(), 0, 0, 0, 0
  for _, r in pairs(d.recipes) do
    recipes = recipes + 1
    if r.learned then learned = learned + 1 end
  end
  for _ in pairs(d.invoices) do invoices = invoices + 1 end
  for _ in pairs(d.characters) do chars = chars + 1 end
  say(recipes .. " recipes (" .. learned .. " learned), " .. invoices .. " sale invoices, bags and gold of "
    .. chars .. " characters. Type /reload to write them to disk.")
end

-- The game only writes SavedVariables on /reload, logout or a character switch, and no addon can
-- force it. After a bank visit or new recipes we remind the player to type /reload, at most every
-- ten minutes. The addon never reloads the interface itself and creates no dialogs or buttons: it
-- only prints text, which cannot taint anything Blizzard's UI does.
local REMINDER_INTERVAL = 600
local RELOAD_HINT = "Type /reload to send it to the dashboard."
local lastReminder = 0

local function remindReload(what)
  local d = db()
  d.settings = d.settings or {}
  if d.settings.prompt == false then return end
  if time() - lastReminder < REMINDER_INTERVAL then return end
  lastReminder = time()
  say("new " .. what .. ". |cffffd100" .. RELOAD_HINT .. "|r")
  if UIErrorsFrame and UIErrorsFrame.AddMessage then
    pcall(UIErrorsFrame.AddMessage, UIErrorsFrame, "Simsar Forever: new " .. what .. ". " .. RELOAD_HINT, 1, 0.82, 0)
  end
end

local frame = CreateFrame("Frame")
local EVENTS = { "PLAYER_LOGIN", "TRADE_SKILL_SHOW", "TRADE_SKILL_UPDATE", "TRADE_SKILL_LIST_UPDATE",
  "TRADE_SKILL_DATA_SOURCE_CHANGED", "CRAFT_SHOW", "CRAFT_UPDATE", "TRAINER_SHOW", "TRAINER_UPDATE",
  "MAIL_INBOX_UPDATE", "MERCHANT_SHOW", "MERCHANT_UPDATE", "BAG_UPDATE_DELAYED", "PLAYER_MONEY",
  "BANKFRAME_OPENED", "BANKFRAME_CLOSED", "PLAYERBANKSLOTS_CHANGED", "PLAYERBANKBAGSLOTS_CHANGED",
  "PLAYER_ENTERING_WORLD", "TRADE_SKILL_CLOSE", "CRAFT_CLOSE", "SKILL_LINES_CHANGED",
  "QUEST_TURNED_IN", "CHAT_MSG_MONEY" }
for event in pairs(CONTEXT_OPEN) do EVENTS[#EVENTS + 1] = event end
for event in pairs(CONTEXT_CLOSE) do EVENTS[#EVENTS + 1] = event end
local registered = {}
for _, event in ipairs(EVENTS) do
  if not registered[event] then
    registered[event] = true
    pcall(frame.RegisterEvent, frame, event)
  end
end

local pending = {}
local announced = false
local function later(name, fn)
  if pending[name] then return end
  pending[name] = true
  C_Timer.After(0.5, function()
    pending[name] = nil
    local ok, err = pcall(fn)
    if not ok then db().stats.lastError = tostring(err) end
  end)
end

local PROFESSION_WINDOW = { TRADE_SKILL_SHOW = true, TRADE_SKILL_UPDATE = true, TRADE_SKILL_LIST_UPDATE = true,
  TRADE_SKILL_DATA_SOURCE_CHANGED = true, CRAFT_SHOW = true, CRAFT_UPDATE = true }

frame:SetScript("OnEvent", function(_, event, ...)
  -- The ledger runs first and synchronously: the open window decides the category of a gold change.
  local ok, err = pcall(onLedgerEvent, event, ...)
  if not ok then db().stats.lastError = "ledger: " .. tostring(err) end

  if event == "PLAYER_LOGIN" then
    -- Early builds saved some recipes without a profession name ("|<recipe>"); drop them.
    for key in pairs(db().recipes) do
      if key:sub(1, 1) == "|" then db().recipes[key] = nil end
    end
    db().build = select(4, GetBuildInfo())
    db().realm = GetRealmName()
    db().faction = UnitFactionGroup("player")
    pcall(hookActions)
    later("bags", scanBags)
    later("icons", scanIcons)
    later("skills", readSkills)
    if GameTooltip and GameTooltip.HookScript then
      pcall(GameTooltip.HookScript, GameTooltip, "OnTooltipSetItem", function(tip) pcall(onItemTooltip, tip) end)
    end
  elseif event == "PLAYER_ENTERING_WORLD" then
    pcall(ledgerLogin)
    later("bags", scanBags)
    later("skills", readSkills)
  elseif event == "PLAYER_MONEY" then
    local ok2, err2 = pcall(onMoney)
    if not ok2 then db().stats.lastError = "money: " .. tostring(err2) end
  elseif event == "SKILL_LINES_CHANGED" then
    later("skills", readSkills)
  elseif event == "TRAINER_SHOW" or event == "TRAINER_UPDATE" then
    later("trainer", readTrainer)
  elseif event == "MAIL_INBOX_UPDATE" then
    later("mail", onMailUpdate)
  elseif event == "BAG_UPDATE_DELAYED" then
    later("bags", scanBags)
  elseif event == "BANKFRAME_OPENED" then
    bankOpen = true
    later("bank", function() scanBank(); scanBags() end)
  elseif event == "BANKFRAME_CLOSED" then
    if bankOpen then remindReload("bank data") end
    bankOpen = false
  elseif event == "PLAYERBANKSLOTS_CHANGED" or event == "PLAYERBANKBAGSLOTS_CHANGED" then
    later("bank", scanBank)
  elseif event == "TRADE_SKILL_CLOSE" or event == "CRAFT_CLOSE" then
    if announced then remindReload("recipes") end
  elseif event == "MERCHANT_SHOW" or event == "MERCHANT_UPDATE" then
    later("merchant", onMerchantShow)
  elseif PROFESSION_WINDOW[event] then
    if event:find("SHOW") then announced = false end
    later("window", function()
      local n = readProfessionWindow()
      -- The modern profession window fills in after it opens, so announce on the first update with data.
      if n > 0 and not announced then
        announced = true
        say(n .. " recipes saved. Type /reload (or log out) to send them to the dashboard.")
      end
    end)
  end
end)

SLASH_SIMSARFOREVER1 = "/simsarforever"
SLASH_SIMSARFOREVER2 = "/sfe"
SlashCmdList.SIMSARFOREVER = function(arg)
  arg = (arg or ""):lower()
  if arg == "diag" then
    diag()
  elseif arg == "save" then
    -- The addon does not reload the interface for you; the player types it.
    say("|cffffd100Type /reload|r to write everything to disk for the dashboard.")
  elseif arg == "prompt off" or arg == "prompt on" then
    settings().prompt = arg == "prompt on"
    say("/reload reminder " .. (settings().prompt and "on" or "off") .. ".")
  elseif arg == "tooltip off" or arg == "tooltip on" then
    settings().tooltip = arg == "tooltip on"
    say("tooltip advice " .. (settings().tooltip and "on" or "off") .. ".")
  elseif arg == "reset" then
    SimsarForeverDB = {}
    say("cleared. /reload to write the empty file.")
  else
    local n = readProfessionWindow()
    if n > 0 then say(n .. " recipes read from the open profession window.") end
    status()
    if ns.tooltipStatus then say(ns.tooltipStatus()) end
    say("Type /reload to write everything to disk. /sfe prompt off|on (reload reminder), "
      .. "/sfe tooltip off|on, /sfe diag.")
  end
end
