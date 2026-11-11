-- Simsar Forever Export
-- Writes what the game knows about recipes and auction fees to SavedVariables, so the
-- Simsar Forever dashboard can read it. It never posts, buys or clicks anything.
--
-- Data is only written to disk on /reload or logout.

local DB_VERSION = 1

SimsarForeverExportDB = SimsarForeverExportDB or {}

local function say(msg)
  print("|cff4fc3f7Simsar Forever|r " .. tostring(msg))
end

local function db()
  local d = SimsarForeverExportDB
  d.version = DB_VERSION
  d.recipes = d.recipes or {}
  d.invoices = d.invoices or {}
  d.characters = d.characters or {}
  d.items = d.items or {}
  d.stats = d.stats or {}
  return d
end

local function idFromLink(link)
  if type(link) ~= "string" then return nil end
  return tonumber(link:match("item:(%d+)"))
end

local function rememberItem(itemID)
  if not itemID then return end
  local name, _, quality, _, _, _, _, _, _, icon, sellPrice = GetItemInfo(itemID)
  if not icon and GetItemInfoInstant then icon = select(5, GetItemInfoInstant(itemID)) end
  if name then
    db().items[itemID] = { name = name, vendor = sellPrice, quality = quality, icon = icon }
  end
end

local function storeRecipe(r)
  local key = (r.prof or "?") .. "|" .. (r.name or "?")
  local old = db().recipes[key]
  -- A trainer or tooltip sighting must not downgrade a recipe read from the profession window.
  if old and old.source == "window" and r.source ~= "window" then
    old.trainerCost = old.trainerCost or r.trainerCost
    old.skill = old.skill or r.skill
    return false
  end
  r.updated = time()
  db().recipes[key] = r
  rememberItem(r.itemID)
  for _, reagent in ipairs(r.reagents or {}) do rememberItem(reagent.id) end
  return true
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
        prof = prof, name = ri.name, source = "window", learned = learned,
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

local function tooltipReagents(tip)
  for i = 1, tip:NumLines() do
    local line = _G[tip:GetName() .. "TextLeft" .. i]
    local text = line and line:GetText()
    local reagents = parseReagentLine(text)
    if reagents then return reagents end
    -- Some clients put the list on the line after a bare "Reagents:" label.
    if text and text:gsub("%s+$", "") == reagentPrefix then
      local nextLine = _G[tip:GetName() .. "TextLeft" .. (i + 1)]
      local body = nextLine and nextLine:GetText()
      if body then return parseReagentLine(reagentPrefix .. " " .. body) end
    end
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
  local itemName, _, _, _, _, _, _, _, _, _, _, classID = GetItemInfo(recipeItemID)
  if classID ~= RECIPE_CLASS or not itemName then return end
  local reagents = tooltipReagents(tip)
  if not reagents then return end
  local prof, product = itemName:match("^(%a+): (.+)$")
  if not product then return end
  db().recipeItems = db().recipeItems or {}
  db().recipeItems[recipeItemID] = {
    name = itemName, kind = prof, product = product, reagents = reagents, seen = time(),
  }
end

-- Auction fees
local function onMailUpdate()
  if not (GetInboxNumItems and GetInboxInvoiceInfo) then return end
  local d = db()
  for i = 1, GetInboxNumItems() do
    local kind, itemName, _, bid, buyout, deposit, consignment, _, _, _, count = GetInboxInvoiceInfo(i)
    if kind == "seller" and itemName and bid and bid > 0 then
      local daysLeft = select(7, GetInboxHeaderInfo(i)) or 0
      -- The same mail shows up on every inbox refresh; key it on its content and expiry hour.
      local expires = math.floor((time() + daysLeft * 86400) / 3600)
      local key = table.concat({ itemName, bid, deposit or 0, consignment or 0, expires }, "|")
      if not d.invoices[key] then
        d.invoices[key] = {
          item = itemName, count = count, bid = bid, buyout = buyout,
          deposit = deposit, consignment = consignment, seen = time(),
        }
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

local function onMerchantShow()
  if not GetMerchantNumItems then return end
  local d = db()
  d.merchant = d.merchant or {}
  local n = 0
  for i = 1, GetMerchantNumItems() do
    local name, price, quantity, numAvailable, extendedCost = merchantItem(i)
    local itemID = (GetMerchantItemID and GetMerchantItemID(i))
      or idFromLink(GetMerchantItemLink and GetMerchantItemLink(i))
    if itemID and name and price and price > 0 and numAvailable == -1 and not extendedCost then
      d.merchant[itemID] = { name = name, price = price / math.max(quantity or 1, 1), seen = time() }
      n = n + 1
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

local function character()
  local d = db()
  d.characters = d.characters or {}
  local name, realm = UnitName("player"), GetRealmName()
  local key = tostring(name) .. "-" .. tostring(realm)
  local c = d.characters[key] or {}
  d.characters[key] = c
  c.name, c.realm, c.faction = name, realm, UnitFactionGroup("player")
  c.class = select(2, UnitClass("player"))
  c.money = GetMoney and GetMoney() or c.money
  return c
end

local function scanBags()
  local c = character()
  c.bags = readContainers(bagIDs())
  c.bagsTime = time()
end

local function scanBank()
  if not bankOpen then return end
  local c = character()
  c.bank = readContainers(bankIDs())
  c.bankTime = time()
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
  say(recipes .. " recipes (" .. learned .. " learned), " .. invoices .. " sale invoices, bags of "
    .. chars .. " characters. Type /reload to write them to disk.")
end

local frame = CreateFrame("Frame")
for _, event in ipairs({ "PLAYER_LOGIN", "TRADE_SKILL_SHOW", "TRADE_SKILL_UPDATE", "TRADE_SKILL_LIST_UPDATE",
  "TRADE_SKILL_DATA_SOURCE_CHANGED", "CRAFT_SHOW", "CRAFT_UPDATE", "TRAINER_SHOW", "TRAINER_UPDATE",
  "MAIL_INBOX_UPDATE", "MERCHANT_SHOW", "MERCHANT_UPDATE", "BAG_UPDATE_DELAYED", "PLAYER_MONEY",
  "BANKFRAME_OPENED", "BANKFRAME_CLOSED", "PLAYERBANKSLOTS_CHANGED", "PLAYERBANKBAGSLOTS_CHANGED",
  "PLAYER_LOGOUT" }) do
  pcall(frame.RegisterEvent, frame, event)
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

frame:SetScript("OnEvent", function(_, event)
  if event == "PLAYER_LOGIN" then
    -- Early builds saved some recipes without a profession name ("|<recipe>"); drop them.
    for key in pairs(db().recipes) do
      if key:sub(1, 1) == "|" then db().recipes[key] = nil end
    end
    db().build = select(4, GetBuildInfo())
    db().realm = GetRealmName()
    db().faction = UnitFactionGroup("player")
    later("bags", scanBags)
    if GameTooltip and GameTooltip.HookScript then
      pcall(GameTooltip.HookScript, GameTooltip, "OnTooltipSetItem", function(tip) pcall(onItemTooltip, tip) end)
    end
  elseif event == "TRAINER_SHOW" or event == "TRAINER_UPDATE" then
    later("trainer", readTrainer)
  elseif event == "MAIL_INBOX_UPDATE" then
    later("mail", onMailUpdate)
  elseif event == "BAG_UPDATE_DELAYED" then
    later("bags", scanBags)
  elseif event == "PLAYER_MONEY" then
    later("money", character)
  elseif event == "BANKFRAME_OPENED" then
    bankOpen = true
    later("bank", function() scanBank(); scanBags() end)
  elseif event == "BANKFRAME_CLOSED" then
    bankOpen = false
  elseif event == "PLAYERBANKSLOTS_CHANGED" or event == "PLAYERBANKBAGSLOTS_CHANGED" then
    later("bank", scanBank)
  elseif event == "PLAYER_LOGOUT" then
    pcall(scanBags)
  elseif event == "MERCHANT_SHOW" or event == "MERCHANT_UPDATE" then
    later("merchant", onMerchantShow)
  else
    if event:find("SHOW") then announced = false end
    later("window", function()
      local n = readProfessionWindow()
      -- The modern profession window fills in after it opens, so announce on the first update with data.
      if n > 0 and not announced then
        announced = true
        say(n .. " recipes saved. /reload to write them to disk.")
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
  elseif arg == "reset" then
    SimsarForeverExportDB = {}
    say("cleared. /reload to write the empty file.")
  else
    local n = readProfessionWindow()
    if n > 0 then say(n .. " recipes read from the open profession window.") end
    status()
  end
end
