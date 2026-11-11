# Metrics

Every number Simsar Forever shows, how it is computed, and when it can mislead. All prices are in copper
(1 gold = 100 silver = 10,000 copper). Code: `simsar/analysis/`.

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
| `vendor_sell` | Auctionator vendor cache, SimsarExport | What a vendor pays you. Drives the deposit. |
| `vendor_buy` | SimsarExport (merchant windows) | What a vendor charges. Only unlimited-stock items. |
| AH cut, deposit rate | SimsarExport (sale mails, posting) | Fall back to `economy.ah_cut` and `economy.deposit_rate`. |

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

**Deposit per listing**: `vendor_sell * deposit_rate`. Refunded when the item sells, lost when the
listing expires or is cancelled. Unknown vendor price means the deposit is left out and the item
is flagged `no_vendor_price`.

**Listings per sale**: `min(1 / sale_rate, economy.max_relists)`. A 25% sale rate means one listing
in four sells, so four listings per sale. A missing or zero sale rate uses the cap.

**You keep per sale** (`net_sell`):

```
net_per_sale(p) = p * (1 - ah_cut) - deposit * (listings_per_sale - 1)
net_sell        = net_per_sale(sell_price)
```

The last listing's deposit is refunded, so only `listings_per_sale - 1` deposits are lost.

Failure modes: TSM's sale rate is region-wide and averages over all sellers; underpricing sells
faster than this suggests, overpricing slower. The deposit formula for Forever is unverified until
SimsarExport has recorded posts; the default rate is a guess.

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
| `no_vendor_price` | deposit not included |

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

## Alerts

After each data update:

- **Cheap**: a tracked item flagged `cheap`, not `possible_misprice`, priced from a fresh scan,
  selling at least `alerts.min_sales_per_day`, with at least `analysis.min_days_trend` days of
  history and a trend no worse than -2% per day. The last two conditions stop alerts on prices that
  are simply sliding. At most five per update, ranked by `|disc_ref| * reference * my_sales_per_day`.
- **Craft**: verdict Craft with `profit >= alerts.min_craft_profit_gold` and enough product sales.
  At most five per update.

Each alert fires at most once per item (or recipe) per day.
