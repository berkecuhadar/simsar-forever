# Metrics

Every number Simsar Forever shows, how it is computed, and when it can mislead. All prices are in copper
(1 gold = 100 silver = 10,000 copper). Code: `simsar_forever/analysis/`.

Settings referred to below live in `config.yaml` (defaults in `config.example.yaml`).

## Inputs

| Name | Source | Notes |
|---|---|---|
| `min_buyout` | TSM realm file, latest scan | Cheapest listing at TSM's last scan of your realm. About every 3 hours. |
| `market` | TSM realm `marketValue`, falls back to region | TSM's weighted typical price over roughly the last 14 days. |
| `historical` | TSM realm `historical`, falls back to region | Roughly a 60-day average. |
| `avg_sale` | TSM region `avgSalePrice` | Average price items actually sold for, region-wide. |
| `sale_rate` | TSM region `saleRate` | Share of listings that sell, region-wide. 0 to 1. |
| `sold_per_day_region` | TSM region `soldPerDay` | Units sold per day, region-wide. |
| Auctionator price | `AUCTIONATOR_PRICE_DATABASE` `m` | Last minimum price your client saw. |
| Auctionator daily | `h`, `l`, `a` per scan day | Highest and lowest minimum price of the day, most units seen. |
| `vendor_sell` | Auctionator vendor cache, Simsar Forever addon | What a vendor pays you. |
| `vendor_buy` | Simsar Forever addon (merchant windows) | What a vendor charges. Only unlimited-stock items. |

## Prices

**Price now** (`price_now`): the cheapest listing from the newest of two scans: your Auctionator
scan (if younger than `analysis.live_price_hours`) and TSM's latest realm scan. If neither has a
listing, TSM market value is used and the item is flagged `not_live`.

**Usual price** (`sell_ref`): with `economy.sell_price: avg_sale` (default) the lower of the
region average sale price and the realm market value; with `market`, the realm market value.
Taking the lower of the two is deliberately conservative.

**Sell at** (`sell_price`): `min(sell_ref, price_now)`. To sell today you have to match the
cheapest competing listing, so you can not count on more than that.

**Reference price** (`reference`): what "cheap" and "expensive" are measured against.
`analysis.reference_price: market` (default) uses the two-week market value; `historical` uses the
60-day average. WoW Forever launched on 4 November 2026 and prices have been falling since, so the
60-day average still holds launch-week prices that will not return. Comparing to it would call
almost everything a bargain.

`disc_ref = price_now / reference - 1` and `disc_hist = price_now / historical - 1`. Negative means
cheaper than the reference.

## Fees

The auction house keeps a cut of every sale: **5% on the Alliance and Horde auction houses, 15% on
the neutral one** (`economy.auction_house`, chosen in Settings; `economy.ah_cut` overrides it).

```
net_per_sale(p) = p * (1 - ah_cut)
net_sell        = net_per_sale(sell_price)
```

Listing deposits are deliberately left out: they are refunded when an item sells, and Simsar
Forever does not try to guess how often your listings expire. Items with a low sale rate are flagged
in the commentary instead. The addon still records sale mails; when the cut they show
differs from the configured one, the data status page says so.

## Volume

```
sold_per_day_realm = sold_per_day_region * realm_share
my_sales_per_day   = sold_per_day_realm * market_share
turnover_day       = sold_per_day_realm * sell_ref      (market size on your realm)
income_day         = max(net_sell, 0) * my_sales_per_day
```

`realm_share` and `market_share` are settings, not measurements. TSM only publishes sales volume
for the whole region, and nothing in the public data says how it splits across realms or how much
of it you would win. **This is the largest unverified assumption in Simsar Forever**; treat every "per day"
figure as an order of magnitude.

## Flip (buy low, resell)

```
flip_profit     = net_per_sale(sell_ref) - price_now
flip_margin     = flip_profit / price_now
flip_profit_day = max(flip_profit, 0) * my_sales_per_day
```

This assumes the price returns to the usual price and that buyers turn up. A falling market
breaks both assumptions.

## History statistics

Price points in the window (`analysis.history_days`) are TSM realm minimum buyouts (one per scan)
and Auctionator daily lows. They are grouped by UTC day and each day reduced to its median.

**Volatility**: robust coefficient of variation of the daily medians:

```
volatility = 1.4826 * MAD(daily) / median(daily)
```

MAD is the median absolute deviation. The 1.4826 factor makes it equal to the usual
standard-deviation-over-mean for normally distributed prices, but a single absurd listing barely
moves it. Shown only with at least `analysis.min_points_volatility` points, otherwise the item is
flagged `low_confidence`.

**Trend**: Theil-Sen slope (median of all pairwise slopes) of the log of the daily medians,
converted to a percent change per day: `expm1(slope)`. Up to about 29% of wild points cannot move
it. Shown only with at least `analysis.min_days_trend` distinct days.

**Range and percentile**: lowest and highest raw points in the window, and the share of points at
or below today's price.

Failure modes: TSM scans and your own scans sample the market at different times; a day with only
one point is as heavy as a day with many. History starts empty and fills as Simsar Forever runs, which is
why the server should be left running.

## Confidence, score and labels

```
confidence = 1 - clip(volatility, 0, 0.6)     (0.6 when volatility is unknown)
             * 0.5 if the TSM data is stale
             * 0.7 if the sale rate is unknown
score      = flip_profit_day * confidence / (1 + max(0, disc_ref))
```

The last factor lowers the score of items priced above their reference, where the "it will come
back to normal" logic points the wrong way. The score exists only to sort the opportunity table;
its weights are judgement calls, not calibrated.

Labels use `analysis.fast_sales_per_day` and `analysis.good_margin`:

| Label | Rule |
|---|---|
| Fast and profitable | `my_sales_per_day >= fast` and `flip_margin >= good` |
| Fast, thin margin | fast and `0 < flip_margin < good` |
| Profitable but slow | not fast and `flip_margin >= good` |
| Avoid | otherwise |
| Not enough data | margin or volume missing |

Labels describe flipping. For items you gather, look at income per day instead.

## Flags

| Flag | Rule |
|---|---|
| `stale` | TSM data older than `analysis.stale_hours` |
| `no_volume` | no region sales |
| `thin_volume` | fewer than 1 sale per day on your realm |
| `bubble` | `market / historical > analysis.bubble_ratio` |
| `cheap` | `disc_ref < -alerts.cheap_below` |
| `possible_misprice` | `price_now < 0.4 * market` |
| `not_live` | price from TSM market value, or from a TSM scan older than the stale limit |
| `low_confidence` | too few points for volatility |

## Crafting

For each recipe, each reagent is priced at the cheaper of the auction house (`price_now`) and a
vendor (`vendor_buy`). Then:

```
cost_buy       = sum(count * buy_price)               buying every material
mats_value     = sum(count * net_sell(reagent))       selling the materials instead
yield          = (yield_min + yield_max) / 2
revenue        = yield * net_sell(product)
profit         = revenue - cost_buy
profit_vs_mats = revenue - mats_value                  opportunity cost check
roi            = profit / cost_buy
crafts_per_day = my_sales_per_day(product) / yield
profit_day     = max(profit, 0) * crafts_per_day
payback_days   = recipe_item_price / profit_day        when the recipe is sold on the AH
```

Verdicts:

| Verdict | Rule |
|---|---|
| Craft | `profit > 0` and `profit_vs_mats > 0` |
| Own mats only | `profit_vs_mats > 0` but `profit <= 0`: crafting beats selling mats you already own, but buying mats to craft loses money |
| Sell the mats | `profit_vs_mats <= 0` |
| Missing prices | a reagent or the product has no price |
| Not sold on AH | the recipe is an enchant (name starts with "Enchant ") |

A reagent with no AH data falls back to `price_now * (1 - ah_cut)` for its sale value.

Failure modes: recipes reported by the trainer or seen in tooltips are only as good as the game's
tooltip text; recipes from `recipes.yaml` are typed by hand. Selling many crafted items at once
pushes the price down; Simsar Forever treats prices as fixed.

## Bags and bank

The Simsar Forever addon saves every character's bags whenever they change and the bank whenever it
is opened (the game writes both to disk on `/reload` or logout). For each item held:

```
tradable = count - soulbound
unit_ah  = net_sell                                  (today's realistic price after the cut)
value    = tradable * max(unit_ah, vendor_sell) + soulbound * vendor_sell
days_to_sell = tradable / my_sales_per_day
```

"Sell at" says whether the auction house or a vendor pays more. The value is recomputed from the
latest prices every time the page loads, so it follows the market without a new scan of your bags.
It is what the items would fetch, not what you could sell at once: `days_to_sell` shows how long the
market needs to absorb them.

## Gold ledger

The addon watches the character's gold. Each change is booked under a category decided at that
moment, in this order:

1. **An exact amount it was told to expect.** Taking money from a mail books it as an auction sale
   when the mail is a sale invoice, as a transfer when the sender is one of your characters, as mail
   otherwise. A quest reward is announced with its amount by the game.
2. **An action seen in the last 10 seconds.** Posting an auction (deposit), buying on the auction
   house, repairing, taking a flight, sending mail (to one of your characters: transfer), group loot.
3. **The window that is open**, or was closed less than 3 seconds ago: vendor (repair mode counts as
   repair), auction house, mailbox, trainer, flight master, trade (with one of your characters:
   transfer), loot, quest, bank, guild bank, barber.
4. Otherwise **Other**.

Gold that changed while the addon was not running (another computer, an older addon version) is
booked once at the next login as **While not recording**, so the days still add up to the balance.
Characters saved by addon 0.1.x have no trusted balance and get no such entry.

Stored per character: daily totals per category (kept for good), single movements for the last 90
days (at most 1500), and the gold on hand at the end of each day.

```
net          = income - spending, without "Between your characters"
auction net  = auction sales - auction purchases - deposits - other auction house payments
```

**Accountant Classic.** When its SavedVariables file exists, its per-day history is imported. Its
categories are mapped to Simsar Forever's (its auction income is sale mail, so it becomes
"Auction sales"; its auction spending stays "Auction house, other" because it does not tell
deposits from purchases). For a character and day the addon's own record wins; Accountant Classic
fills only the days the addon did not record.

**Auction house, item by item** comes from mail, not from gold changes: sale invoices (received
after the cut), "auction won" mails (price paid) and expired or cancelled auctions.

```
sell_through = sold auctions / (sold + expired + cancelled)
```

Failure modes: a gold change while two things happen at once (looting while a vendor window is
open) goes to whichever rule matches first; mail opened by another addon in bulk can arrive faster
than the game reports gold, which the exact-amount match in step 1 is there to handle.

## Alerts

After each data update:

- **Cheap**: a tracked item flagged `cheap`, not `possible_misprice`, priced from a fresh scan,
  selling at least `alerts.min_sales_per_day`, with at least `analysis.min_days_trend` days of
  history and a trend no worse than -2% per day. The last two conditions stop alerts on prices that
  are simply sliding. At most five per update, ranked by `|disc_ref| * reference * my_sales_per_day`.
- **Craft**: verdict Craft with `profit >= alerts.min_craft_profit_gold` and enough product sales.
  At most five per update.

Each alert fires at most once per item (or recipe) per day.

## Advanced statistics (item page)

Computed on demand for one item from its stored history (`simsar_forever/analysis/econometrics.py`,
using NumPy, SciPy, pandas and statsmodels). Each part says what data it still needs instead of
showing a number built on too little.

**Mean reversion.** An AR(1) model on the log of TSM's cheapest-listing series (one point per
scan, about every 3 hours):

```
dy[t] = a + b * y[t-1] + e        phi = 1 + b
half_life = ln(0.5) / ln(phi) * scan_interval        (only when 0 < phi < 1)
equilibrium = exp(-a / b)
```

The augmented Dickey-Fuller test (`statsmodels.tsa.stattools.adfuller`) checks whether the series
really pulls back to a level (p < 0.05: "strong", p < 0.15: "weak") or wanders like a random walk
("none"). Needs 16 scans. A short half-life means cheap listings are bought up or the price
recovers quickly, which makes flips safer; "none" means "it will come back" is not a safe bet.

**Forecast.** Exponential smoothing with additive errors and a damped additive trend (ETS A,Ad,N,
`statsmodels.tsa.exponential_smoothing.ets.ETSModel`) on the log of daily median prices (TSM
minimum buyouts and Auctionator daily lows), missing days carried forward. Three days ahead with
an 80% prediction interval. Needs 7 days. The damped trend stops a short run from being projected
forever; the interval assumes the market keeps behaving as it has, which a patch or a new source of
supply breaks.

**Price elasticity of demand.** Ordinary least squares of `log(sold_per_day)` on `log(avg_sale)`
across region snapshots, with a 90% confidence interval for the slope. Needs 10 days with some
price movement. A slope of -2 means a 1% higher price goes with 2% fewer units sold. When the
interval contains zero there is no clear link. This is a correlation, not a causal estimate: shifts
in supply and demand move price and volume together, which can even make the slope positive.

**Timing.** Every scan's price divided by that day's median, grouped by three-hour block of local
time (and by weekday after 14 days). The block with the lowest median is the cheapest time to buy,
the highest the best time to sell. The Kruskal-Wallis test (`scipy.stats.kruskal`) says whether
the blocks differ by more than chance (p < 0.05). Needs 5 days.
