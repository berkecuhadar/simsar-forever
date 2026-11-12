-- Simsar Forever tooltip advice.
-- Adds the dashboard's numbers to item tooltips. The dashboard writes SimsarForeverData.lua into
-- this addon's folder; the game loads it on login or /reload, so the advice is as fresh as the
-- last /reload. Only adds lines to tooltips; never changes or hides anything.

local _, ns = ...
ns = ns or {}

-- Advice codes written by the dashboard (simsar_forever/tooltip_data.py).
local ADVICE = {
  sell = "|cff4cc38aSell on the auction house now|r",
  vendor = "|cffe3b341Sell to a vendor|r (pays more than the auction house)",
  hold = "|cff5aa7f0Hold|r",
  gradual = "|cff4cc38aSell a few at a time|r (more than the market takes at once)",
}

local LABEL = "|cff4fc3f7Simsar|r "
local STALE_HOURS = 24

local function coins(copper)
  copper = math.floor((copper or 0) + 0.5)
  if GetCoinTextureString then return GetCoinTextureString(copper) end
  local g, s, c = math.floor(copper / 10000), math.floor(copper / 100) % 100, copper % 100
  if g > 0 then return string.format("%dg %02ds", g, s) end
  if s > 0 then return string.format("%ds %02dc", s, c) end
  return c .. "c"
end

local function enabled()
  local s = ns.settings and ns.settings()
  return not (s and s.tooltip == false)
end

local function data()
  local d = SimsarForeverData
  if type(d) ~= "table" or type(d.items) ~= "table" then return nil end
  return d
end

-- One item: { keep, sales_per_day, advice, expected_change, horizon_days, craft_profit, price_now }
local function lines(itemID)
  local d = data()
  local e = d and d.items[itemID]
  if not e then return nil end
  local keep, spd, advice, change, horizon, craft, price = e[1], e[2], e[3], e[4], e[5], e[6], e[7]
  local out = {}
  if price or keep then
    local text = LABEL .. "AH " .. (price and coins(price) or "?")
    if keep then text = text .. "  ·  you keep " .. coins(keep) end
    out[#out + 1] = text
  end
  if spd then
    out[#out + 1] = LABEL .. string.format("about %s sold per day on your realm", spd >= 10 and
      string.format("%d", spd) or string.format("%.1f", spd))
  end
  if advice and ADVICE[advice] then
    local text = LABEL .. ADVICE[advice]
    if advice == "hold" and change then
      text = text .. string.format(": %+d%% expected in %d days", math.floor(change * 100 + 0.5), horizon or 3)
    end
    out[#out + 1] = text
  end
  if craft then
    out[#out + 1] = LABEL .. "crafting it " .. (craft >= 0 and "makes " or "loses ") .. coins(math.abs(craft))
      .. " each at today's prices"
  end
  if d.built and time() - d.built > STALE_HOURS * 3600 then
    out[#out + 1] = LABEL .. string.format("|cff7d8494prices from %d days ago|r", math.floor((time() - d.built) / 86400))
  end
  return out
end

local function addTo(tip, itemID)
  if not (tip and itemID and enabled()) then return end
  local out = lines(itemID)
  if not out then return end
  for _, text in ipairs(out) do tip:AddLine(text, 1, 1, 1) end
  if tip.Show then tip:Show() end
end

ns.tooltipLines = lines

function ns.tooltipStatus()
  local d = data()
  if not d then return "tooltip advice: no data yet. Start the dashboard, then /reload." end
  local n = 0
  for _ in pairs(d.items) do n = n + 1 end
  return string.format("tooltip advice for %d items, from %s. %s", n,
    d.built and date("%Y-%m-%d %H:%M", d.built) or "?", enabled() and "" or "(turned off)")
end

-- Modern clients pass item data to post-calls; older ones fire OnTooltipSetItem.
if TooltipDataProcessor and TooltipDataProcessor.AddTooltipPostCall and Enum and Enum.TooltipDataType then
  TooltipDataProcessor.AddTooltipPostCall(Enum.TooltipDataType.Item, function(tip, info)
    pcall(addTo, tip, info and info.id)
  end)
else
  local function hook(tip)
    if tip and tip.HookScript then
      pcall(tip.HookScript, tip, "OnTooltipSetItem", function(self)
        local _, link = self:GetItem()
        pcall(addTo, self, ns.idFromLink and ns.idFromLink(link))
      end)
    end
  end
  hook(GameTooltip)
  hook(ItemRefTooltip)
end
