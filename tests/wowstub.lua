-- Minimal stand-in for the WoW client API, enough to load and drive the Simsar Forever addon.
-- Each test defines the profession/AH functions it needs before loading the addon.

frames = {}
printed = {}
now = 1794000000

function print(...)
  local parts = {}
  for i = 1, select("#", ...) do parts[#parts + 1] = tostring(select(i, ...)) end
  printed[#printed + 1] = table.concat(parts, " ")
end

function time() return now end
clock = 100
function GetTime() return clock end
function date(fmt, t) return os.date(fmt, t or now) end
zone = "Stormwind City"
function GetZoneText() return zone end
function GetBuildInfo() return "1.60.1", "60001", "Nov 1 2026", 16001 end
function GetRealmName() return "Normal" end
function UnitFactionGroup() return "Alliance" end
function UnitName() return "Tester" end
function UnitClass() return "Hunter", "HUNTER" end
money = 123456
function GetMoney() return money end
reloads, inCombat = 0, false
function ReloadUI() reloads = reloads + 1 end
C_UI = { Reload = ReloadUI }
errorsShown = {}
UIErrorsFrame = { AddMessage = function(_, text) errorsShown[#errorsShown + 1] = text end }
-- Blizzard's popup system; the addon must leave it alone (see test_addon_never_touches_blizzard_popups).
StaticPopupDialogs = setmetatable({}, { __newindex = function() error("addon wrote to StaticPopupDialogs") end })
function StaticPopup_Show() error("addon used StaticPopup_Show") end
function InCombatLockdown() return inCombat end
WorldFrame = {}
SlashCmdList = {}
C_Timer = { After = function(_, fn) fn() end }

items = {}
function GetItemInfo(id)
  local i = items[id]
  if not i then return nil end
  return i.name, "link", i.quality or 1, 1, 1, "Type", "Sub", 20, "", i.icon, i.vendor, i.class
end

local newFrame
function newFrame(name)
  local f = { events = {}, lines = {}, hooks = {}, scripts = {}, shown = true }
  function f:RegisterEvent(e) self.events[e] = true end
  function f:SetScript(what, fn)
    self.scripts[what] = fn
    if what == "OnEvent" then self.handler = fn end
  end
  function f:Click() if self.scripts.OnClick then self.scripts.OnClick(self) end end
  function f:Show() self.shown = true end
  function f:Hide() self.shown = false end
  function f:IsShown() return self.shown end
  function f:SetText(t) self.text_value = t end
  function f:GetText() return self.text_value end
  function f:CreateFontString() return newFrame() end
  function f:SetSize() end
  function f:SetWidth() end
  function f:SetPoint() end
  function f:SetFrameStrata() end
  function f:HookScript(what, fn)
    local prev = self.hooks[what]
    self.hooks[what] = prev and function(...) prev(...); fn(...) end or fn
  end
  function f:AddLine(text) self.added = self.added or {}; self.added[#self.added + 1] = text end
  function f:SetOwner() end
  function f:ClearLines() self.lines = {} end
  function f:NumLines() return #self.lines end
  function f:GetName() return name end
  function f:SetTrainerService(i)
    self.lines = trainerTooltips and trainerTooltips[i] or {}
    for n, text in ipairs(self.lines) do
      _G[name .. "TextLeft" .. n] = { GetText = function() return text end }
    end
  end
  function f:GetItem() return nil, self.link end
  frames[#frames + 1] = f
  return f
end

function CreateFrame(_, name)
  local f = newFrame(name or "anon")
  if name then _G[name] = f end
  return f
end
UIParent = newFrame("UIParent")
GameTooltip = newFrame("GameTooltip")

function hooksecurefunc(a, b, c)
  local tbl, key, fn = _G, a, b
  if type(a) == "table" then tbl, key, fn = a, b, c end
  local orig = tbl[key]
  tbl[key] = function(...)
    local r = { orig(...) }
    fn(...)
    return unpack(r)
  end
end

function fire(event, ...)
  for _, f in ipairs(frames) do
    if f.events[event] and f.handler then f.handler(f, event, ...) end
  end
end

local function serialize(v, indent)
  local t = type(v)
  if t == "string" then return string.format("%q", v) end
  if t ~= "table" then return tostring(v) end
  local out = { "{\n" }
  for k, val in pairs(v) do
    local key = type(k) == "string" and string.format("[%q]", k) or "[" .. tostring(k) .. "]"
    out[#out + 1] = key .. " = " .. serialize(val) .. ",\n"
  end
  out[#out + 1] = "}"
  return table.concat(out)
end

function savedVariables()
  return "SimsarForeverDB = " .. serialize(SimsarForeverDB) .. "\n"
end
