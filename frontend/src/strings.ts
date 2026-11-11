// Every user-facing explanation lives here so the UI can be translated in one place.

import type { Flag, Label, Verdict } from "./api";

export const LABELS: Record<Label, string> = {
  fast_profitable: "Fast and profitable",
  fast_thin: "Fast, thin margin",
  slow_profitable: "Profitable but slow",
  avoid: "Avoid",
  unknown: "Not enough data",
};

export const LABEL_HINTS: Record<Label, string> = {
  fast_profitable: "Sells often and buying to resell clears your margin target.",
  fast_thin: "Sells often, but the resale margin is small. Fine for volume, little room for error.",
  slow_profitable: "Good margin, but few sales per day. Money can sit on the auction house for a while.",
  avoid: "Buying to resell loses money at current prices.",
  unknown: "Missing price or sales data.",
};

export const FLAGS: Record<Flag, string> = {
  stale: "Old data",
  no_volume: "No sales",
  thin_volume: "Thin volume",
  bubble: "Bubble?",
  cheap: "Cheap now",
  possible_misprice: "Odd listing",
  not_live: "Not live",
  low_confidence: "Few points",
  no_vendor_price: "No deposit",
};

export const FLAG_HINTS: Record<Flag, string> = {
  stale: "TSM data is older than the stale limit in your settings.",
  no_volume: "TSM has no recorded sales for this item in the region. Hard to sell.",
  thin_volume: "Sells less than once a day on your realm.",
  bubble: "Market value (last two weeks) is far above the 60-day average. Prices like this tend to fall back.",
  cheap: "The cheapest listing is well below the item's usual price (see the reference price setting).",
  possible_misprice: "The cheapest listing is far below market value: a mistake, a bait listing, or a single cheap unit.",
  not_live: "No recent Auctionator scan for this item, so 'price now' comes from TSM's last scan.",
  low_confidence: "Too few price points to judge volatility yet. History builds up as Simsar runs.",
  no_vendor_price: "Vendor price unknown, so the listing deposit is not included in the fees.",
};

export const VERDICTS: Record<Verdict, string> = {
  craft: "Craft",
  own_mats: "Own mats only",
  sell_mats: "Sell the mats",
  missing: "Missing prices",
  no_product: "Not sold on AH",
};

export const VERDICT_HINTS: Record<Verdict, string> = {
  craft: "Profitable even if you buy every material at today's price.",
  own_mats: "Crafting beats selling the materials you already have, but buying materials to craft it loses money.",
  sell_mats: "Selling the materials brings in more than selling the crafted item.",
  missing: "At least one price is missing, so profit cannot be worked out.",
  no_product: "The result is an enchant or a service, not an item you can list.",
};

export const PRICE_SOURCES: Record<string, string> = {
  auctionator: "Your Auctionator scan",
  tsm_min_buyout: "TSM's latest realm scan",
  tsm_market: "TSM market value (no listing seen)",
};

export const COLUMNS: Record<string, { title: string; hint: string }> = {
  name: { title: "Item", hint: "Click a row to open the item page." },
  group: { title: "Group", hint: "Profession group the item belongs to." },
  price_now: { title: "Price now", hint: "Cheapest listing right now: from your Auctionator scan if it is recent, otherwise TSM's latest scan." },
  market: { title: "Market value", hint: "TSM's typical price on your realm over the last two weeks." },
  historical: { title: "Historical", hint: "TSM's long-term (60 day) average price. On a new server it still includes launch-week prices, so Simsar compares against the two-week market value by default." },
  sell_ref: { title: "Usual price", hint: "Price this item normally sells for: the lower of TSM's average sale price and the realm market value." },
  sell_price: { title: "Sell at", hint: "Price you can realistically sell at today: the usual price, but never above the cheapest competing listing." },
  net_sell: { title: "You keep", hint: "What one sale leaves you after the auction house cut and the deposits you lose on listings that expire first." },
  sale_rate: { title: "Sale rate", hint: "Share of listings that actually sell (region-wide). 25% means about four listings per sale." },
  sold_per_day_region: { title: "Sold/day (region)", hint: "Units sold per day across the whole region, from TSM." },
  my_sales_per_day: { title: "Your sales/day", hint: "Region sales x your realm's share x your share of that realm. Both shares are settings." },
  available: { title: "On AH", hint: "Most units seen on sale on the latest Auctionator scan day. Many units means many competitors." },
  turnover_day: { title: "Market size/day", hint: "Money that changes hands for this item on your realm per day (realm sales x usual price)." },
  income_day: { title: "Income/day", hint: "What you could earn per day selling your own stock: 'You keep' x your sales per day." },
  flip_profit: { title: "Flip profit", hint: "Buy at the cheapest listing, resell at the usual price: profit per unit after fees." },
  flip_margin: { title: "Flip margin", hint: "Flip profit as a share of the buy price." },
  flip_profit_day: { title: "Flip/day", hint: "Flip profit x your sales per day: the most this flip can make per day." },
  volatility: { title: "Volatility", hint: "How much the daily price swings, as a share of the typical price (robust: one odd listing barely moves it). Under 8% is calm, over 20% is wild." },
  trend: { title: "Trend", hint: "Typical price change per day over the analysis window, fitted so that a single spike does not decide it." },
  disc_ref: { title: "vs usual", hint: "How far the cheapest listing is from the reference price (by default TSM market value over the last two weeks). Negative = cheaper than usual." },
  disc_hist: { title: "vs 60-day", hint: "How far the cheapest listing is from TSM's 60-day average. On a new server this average still contains launch-week prices." },
  confidence: { title: "Confidence", hint: "How much to trust the numbers: lower when the price swings a lot, data is old, or sales data is missing." },
  score: { title: "Score", hint: "Flip/day x confidence, reduced when the price is above its long-term average. Used for ranking only." },
  label: { title: "Verdict", hint: "Quick class based on resale margin and how fast it sells." },
  flags: { title: "Warnings", hint: "Things to check before acting. Hover a warning for details." },
  period_min: { title: "Low", hint: "Lowest price seen in the analysis window." },
  period_max: { title: "High", hint: "Highest price seen in the analysis window." },
  deposit: { title: "Deposit", hint: "Deposit for listing one unit. You get it back when the item sells and lose it when the listing expires." },
};

export const CRAFT_COLUMNS: Record<string, { title: string; hint: string }> = {
  name: { title: "Recipe", hint: "Recipe name. A dimmed name means your character has not learned it." },
  verdict: { title: "Verdict", hint: "What to do with this recipe at today's prices." },
  cost_buy: { title: "Mats cost", hint: "Cost of buying every material at the cheapest listing." },
  mats_value: { title: "Mats value", hint: "What the materials would bring in if you sold them instead (after fees). This is the real cost of crafting with materials you already own." },
  revenue: { title: "Revenue", hint: "What you keep from selling the crafted result (all units if the recipe makes several), after fees." },
  profit: { title: "Profit", hint: "Revenue minus the cost of buying the materials." },
  profit_vs_mats: { title: "vs selling mats", hint: "Revenue minus what the materials would fetch. Positive means crafting beats selling the materials." },
  roi: { title: "ROI", hint: "Return on investment: profit divided by the materials cost." },
  product_sales_per_day: { title: "Sales/day", hint: "How many of the result you can expect to sell per day." },
  profit_day: { title: "Profit/day", hint: "Profit per craft x crafts you can sell per day." },
  payback_days: { title: "Recipe payback", hint: "Days of crafting needed to earn back the recipe's auction price." },
};

export const GLOSSARY: { term: string; text: string }[] = [
  { term: "Copper, silver, gold", text: "All prices are stored in copper. 100 copper = 1 silver, 100 silver = 1 gold." },
  { term: "Auction house cut", text: "Share of the sale price the auction house keeps when something sells. Vanilla used 5% on faction auction houses and 15% on the neutral one. Simsar measures the real value from your sale mails once the SimsarExport addon has seen some." },
  { term: "Deposit", text: "A fee paid when you post an auction, based on the item's vendor price and the duration. It is refunded if the item sells and lost if the listing expires or you cancel it. Items that rarely sell therefore cost you deposits again and again." },
  { term: "Sale rate", text: "The share of listings that end in a sale. With a 20% sale rate you list an item five times on average before it sells, losing four deposits on the way." },
  { term: "Market value", text: "TSM's estimate of the normal price on your realm, based on the last two weeks of scans." },
  { term: "Historical price", text: "TSM's long-term average (about 60 days). On an established server it is a good yardstick for 'cheap' or 'expensive'. WoW Forever launched in November 2026, so for now this average is pulled up by launch-week prices that are not coming back; Simsar therefore measures cheapness against the two-week market value unless you change analysis.reference_price." },
  { term: "Mean reversion", text: "Prices that move far from their usual level tend to come back. That makes items far below it candidates for buying, and items far above it risky to buy. It is a tendency, not a rule: a price can also be low because supply grew for good." },
  { term: "Flip", text: "Buying an item cheaply on the auction house and listing it again at the usual price. Profit depends on the price returning to normal and on buyers showing up." },
  { term: "Liquidity", text: "How easily something sells. High liquidity means many sales per day, so stock turns into gold quickly." },
  { term: "Turnover (market size)", text: "Total money spent on an item per day. A big market can absorb your listings; a tiny one cannot." },
  { term: "Volatility", text: "How much the price swings from day to day. Simsar uses the median absolute deviation, which ignores single absurd listings. High volatility means today's profit can vanish tomorrow." },
  { term: "Trend", text: "The typical daily price change, fitted with the Theil-Sen method so one spike cannot decide it." },
  { term: "Opportunity cost", text: "The value of the best thing you give up. Crafting with your own leather costs you the gold you could have made by selling that leather, even though you paid nothing for it." },
  { term: "ROI", text: "Return on investment: profit divided by what you spent. 50% ROI means 50 gold back for every 100 gold spent, on top of the 100." },
  { term: "Payback time", text: "How long it takes for a recipe to earn back what it cost to buy." },
  { term: "Bubble", text: "A price far above its long-term average, often from a short supply or a rush. Buying into one is risky." },
  { term: "Market share", text: "Your guess of how many of the daily sales you win against other sellers. Set in config.yaml; Simsar cannot measure it." },
  { term: "Realm share", text: "TSM's sales numbers cover the whole region. Simsar multiplies them by this share to estimate sales on your realm alone. It is a guess and is set in config.yaml." },
  { term: "Confidence", text: "A 0 to 1 weight Simsar uses for ranking: lower when prices swing, data is old, or sales data is missing. It is not a probability of profit." },
];
