-- Simsar Export
-- Writes what the game knows about recipes and auction fees to SavedVariables, so the
-- Simsar dashboard can read it. It never posts, buys or clicks anything.
--
-- Data is only written to disk on /reload or logout.

local DB_VERSION = 1
local DURATION_HOURS = { 2, 8, 24 }

SimsarExportDB = SimsarExportDB or {}

local function say(msg)
  print("|cff4fc3f7Simsar|r " .. tostring(msg))
end

local function db()
  local d = SimsarExportDB
  d.version = DB_VERSION
  d.recipes = d.recipes or {}
  d.invoices = d.invoices or {}
  d.deposits = d.deposits or {}
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
  local name, _, _, _, _, _, _, _, _, _, sellPrice = GetItemInfo(itemID)
  if name then
    db().items[itemID] = { name = name, vendor = sellPrice }
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
local function readModern()
  local T = C_TradeSkillUI
  if not (T and T.GetAllRecipeIDs and T.GetRecipeSchematic and T.GetRecipeInfo) then return 0 end
  local info = (T.GetChildProfessionInfo and T.GetChildProfessionInfo())
    or (T.GetBaseProfessionInfo and T.GetBaseProfessionInfo())
  local prof = (info and (info.parentProfessionName or info.professionName)) or "?"
  local n = 0
  for _, recipeID in ipairs(T.GetAllRecipeIDs() or {}) do
    local ri = T.GetRecipeInfo(recipeID)
    local sch = ri and T.GetRecipeSchematic(recipeID, false)
    if sch then
      local reagents = {}
      for _, slot in ipairs(sch.reagentSlotSchematics or {}) do
        local r = slot.reagents and slot.reagents[1]
        if r and r.itemID then
          reagents[#reagents + 1] = {
            id = r.itemID, name = GetItemInfo(r.itemID), count = slot.quantityRequired,
          }
        end
      end
      storeRecipe({
        prof = prof, name = ri.name, source = "window", learned = ri.learned and true or false,
        itemID = sch.outputItemID, spellID = recipeID,
        yieldMin = sch.quantityMin or 1, yieldMax = sch.quantityMax or sch.quantityMin or 1,
        reagents = reagents,
      })
      n = n + 1
    end
  end
  return n
end

local function readProfessionWindow()
  local total = 0
  for _, fn in ipairs({ readTradeSkills, readCrafts, readModern }) do
    local ok, n = pcall(fn)
    if ok and type(n) == "number" then total = total + n end
  end
  db().stats.lastWindow = { time = time(), recipes = total }
  return total
end

-- Tooltip helpers: the trainer and recipe items only expose reagents through tooltip text.
local scanner = CreateFrame("GameTooltip", "SimsarScanTooltip", nil, "GameTooltipTemplate")
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
    local reagents = parseReagentLine(line and line:GetText())
    if reagents then return reagents end
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

local function recordDeposit(itemID, quantity, hours, deposit, vendor)
  if not (itemID and deposit) then return end
  local d = db()
  d.deposits[#d.deposits + 1] = {
    item = itemID, quantity = quantity, hours = hours, deposit = deposit, vendor = vendor, seen = time(),
  }
  while #d.deposits > 500 do table.remove(d.deposits, 1) end
end

local function guarded(fn)
  local ok, err = pcall(fn)
  if not ok then db().stats.lastError = tostring(err) end
end

-- Post hooks run after the item has left the sell slot, so the deposit is quoted while the
-- item is still there and remembered until the post goes through.
local sellSlot

local function hookLegacyPosting()
  if not (PostAuction and GetAuctionSellItemInfo and CalculateAuctionDeposit) then return false end
  local f = CreateFrame("Frame")
  f:RegisterEvent("NEW_AUCTION_UPDATE")
  f:SetScript("OnEvent", function()
    guarded(function()
      local name, _, count, _, _, _, unitVendor, _, _, itemID = GetAuctionSellItemInfo()
      if not name then sellSlot = nil; return end
      local perUnit = {}
      for runTime = 1, 3 do
        local deposit = CalculateAuctionDeposit(runTime, 1, 1)
        if deposit then perUnit[runTime] = deposit end
      end
      sellSlot = { name = name, itemID = itemID, count = count, vendor = unitVendor, perUnit = perUnit }
    end)
  end)
  hooksecurefunc("PostAuction", function(_, _, runTime, stackSize, numStacks)
    guarded(function()
      local s = sellSlot
      if not (s and s.perUnit[runTime]) then return end
      local quantity = (stackSize or s.count or 1) * (numStacks or 1)
      recordDeposit(s.itemID or s.name, quantity, DURATION_HOURS[runTime] or runTime,
        s.perUnit[runTime] * quantity, s.vendor)
    end)
  end)
  return true
end

local function hookModernPosting()
  local AH = C_AuctionHouse
  if not (AH and AH.PostItem and AH.CalculateItemDeposit) then return false end
  local quote, quoting
  local function remember(fnName, a, duration, quantity)
    if quoting then return end
    quoting = true
    guarded(function()
      local itemID = fnName == "CalculateItemDeposit" and C_Item.GetItemID(a) or a
      quote = { itemID = itemID, duration = duration, quantity = quantity, deposit = AH[fnName](a, duration, quantity) }
    end)
    quoting = false
  end
  hooksecurefunc(AH, "CalculateItemDeposit", function(...) remember("CalculateItemDeposit", ...) end)
  if AH.CalculateCommodityDeposit then
    hooksecurefunc(AH, "CalculateCommodityDeposit", function(...) remember("CalculateCommodityDeposit", ...) end)
  end
  local function posted(_, duration, quantity)
    guarded(function()
      if quote and quote.duration == duration and quote.quantity == quantity then
        recordDeposit(quote.itemID, quantity, DURATION_HOURS[duration] or duration, quote.deposit,
          select(11, GetItemInfo(quote.itemID)))
      end
    end)
  end
  hooksecurefunc(AH, "PostItem", posted)
  if AH.PostCommodity then hooksecurefunc(AH, "PostCommodity", posted) end
  return true
end

local function diag()
  local function has(x) return x and "yes" or "no" end
  local version, build, _, interface = GetBuildInfo()
  say("client " .. tostring(version) .. " build " .. tostring(build) .. ", interface " .. tostring(interface))
  say("TradeSkill API: " .. has(GetNumTradeSkills) .. ", Craft API: " .. has(GetNumCrafts)
    .. ", C_TradeSkillUI: " .. has(C_TradeSkillUI and C_TradeSkillUI.GetAllRecipeIDs))
  say("Trainer API: " .. has(GetNumTrainerServices) .. ", reagent label: '" .. reagentPrefix .. "'")
  say("Legacy AH: " .. has(PostAuction) .. ", modern AH: " .. has(C_AuctionHouse and C_AuctionHouse.PostItem)
    .. ", invoices: " .. has(GetInboxInvoiceInfo))
  if db().stats.lastError then say("last error: " .. db().stats.lastError) end
end

local function status()
  local d, recipes, learned, invoices = db(), 0, 0, 0
  for _, r in pairs(d.recipes) do
    recipes = recipes + 1
    if r.learned then learned = learned + 1 end
  end
  for _ in pairs(d.invoices) do invoices = invoices + 1 end
  say(recipes .. " recipes (" .. learned .. " learned), " .. invoices .. " sale invoices, "
    .. #d.deposits .. " deposits. Type /reload to write them to disk.")
end

local frame = CreateFrame("Frame")
for _, event in ipairs({ "PLAYER_LOGIN", "TRADE_SKILL_SHOW", "TRADE_SKILL_UPDATE", "CRAFT_SHOW", "CRAFT_UPDATE",
  "TRAINER_SHOW", "TRAINER_UPDATE", "MAIL_INBOX_UPDATE" }) do
  pcall(frame.RegisterEvent, frame, event)
end

local pending = {}
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
    db().build = select(4, GetBuildInfo())
    db().realm = GetRealmName()
    db().faction = UnitFactionGroup("player")
    if not hookModernPosting() then hookLegacyPosting() end
    if GameTooltip and GameTooltip.HookScript then
      pcall(GameTooltip.HookScript, GameTooltip, "OnTooltipSetItem", function(tip) pcall(onItemTooltip, tip) end)
    end
  elseif event == "TRAINER_SHOW" or event == "TRAINER_UPDATE" then
    later("trainer", readTrainer)
  elseif event == "MAIL_INBOX_UPDATE" then
    later("mail", onMailUpdate)
  else
    later("window", function()
      local n = readProfessionWindow()
      if n > 0 and event:find("SHOW") then say(n .. " recipes saved. /reload to write them to disk.") end
    end)
  end
end)

SLASH_SIMSAR1 = "/simsar"
SlashCmdList.SIMSAR = function(arg)
  arg = (arg or ""):lower()
  if arg == "diag" then
    diag()
  elseif arg == "reset" then
    SimsarExportDB = {}
    say("cleared. /reload to write the empty file.")
  else
    local n = readProfessionWindow()
    if n > 0 then say(n .. " recipes read from the open profession window.") end
    status()
  end
end
