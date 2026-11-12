# Changelog

## Unreleased

### Addon

- **One addon: Simsar Forever.** SimsarForeverExport is now part of a single addon called Simsar
  Forever (folder `SimsarForever`). Installing or updating removes the old folder; the old addon's
  saved data is still imported, so nothing is lost.
- **Tooltip advice.** Item tooltips show what one sale on the auction house leaves you, how many sell
  per day on your realm, whether to sell now, vendor or hold, and what crafting the item makes. The
  dashboard writes this data into the addon folder; the game loads it on login or `/reload`.
  `/sfe tooltip off` hides it.
- **Gold ledger.** Every change of gold is booked under what you were doing: auction sales, auction
  purchases, deposits, vendor, repairs, mail, gold moved between your own characters, quests, loot,
  trainer, taxi and more. The gold on hand at the end of each day is saved too.
- **Professions.** Each character's skill levels and the recipes that character knows are saved
  separately, so an alt opening a profession window no longer hides what your main has learned.
  Trainer costs and required skill survive a later profession window read; recipe items record
  their required skill, and recipes sold by vendors are saved even in limited stock.
- **Auction mail.** Purchases (with the price paid) and expired or cancelled auctions are saved
  next to sale invoices.
- Bags, bank and gold of characters you are not logged in with are no longer wiped. The addon
  scanned bags at logout, when the game has already emptied them and reports 0 gold, so every
  character but the current one showed up empty. It now skips any scan while the bags are not
  loaded and keeps each character's last good data.
- The addon no longer reloads the interface. The "Reload now" window is gone and `/sfe save` only
  tells you to type `/reload`; after a bank visit or new recipes the addon prints a reminder to
  type `/reload` in chat and on screen.

### Dashboard

- **Gold ledger page.** Income and spending per character and category for today, yesterday, this
  and last week, month, year or all time; net per day with gold on hand; gold over time per
  character; every auction item with what it sold for, what you paid, the cut and how often your
  listings sold; and the single gold movements of the last 90 days. Gold moved between your own
  characters is shown but left out of profit.
- Imports the gold history of Accountant Classic when that addon is installed, so the ledger
  reaches back to before the Simsar Forever addon was installed.
- **Sell plan page.** For everything your characters hold: sell on the auction house now, sell a
  few at a time (you hold more than the market buys in a few days), sell to a vendor, or hold
  because the price is expected to rise, each with the reason.
- **Forecast accuracy page.** Price forecasts for 1, 3 and 7 days from a mean-reversion model
  fitted on all items at once, with an 80% range and a calibrated chance of a rise. A rolling
  backtest compares them with "no change", with a significance test, and every day's forecasts are
  stored and scored as their day arrives. "Hold" is only advised when the backtest shows the
  forecasts beating "no change"; until then the page says why.
- **Shopping list page.** Pick recipes and how many to craft; Simsar adds up the materials, takes
  off what your characters already hold, and shows what is left to buy, whether the auction house
  or a vendor is cheaper, materials that are cheaper to craft than to buy, and the batch's expected
  profit. Recipes can be added from the Crafts page.
- **Navigation** moved to a side menu grouped into Market, Crafting, Your characters and About the
  data.

## 0.1.2 (2026-11-12)

- Fixed the game message "SimsarForeverExport has been blocked from an action only available to the
  Blizzard UI". The save prompt borrowed Blizzard's popup system, which taints it so that the game
  then blocks Blizzard's own popups. The prompt is now the addon's own small window, and the addon no
  longer writes any Blizzard global.

## 0.1.1 (2026-11-12)

- Installing no longer needs a C compiler on new Python versions. PyYAML had no Windows build for
  Python 3.15 and failed with "Microsoft Visual C++ 14.0 or greater is required"; YAML is now read
  with pure-Python ruamel.yaml, and every dependency installs from ready-made builds on Python 3.12
  to 3.15.
- `start.bat` explains Python version and package install problems in plain words.

## 0.1.0 (2026-11-12)

First version.

- Downloads TSM's public WoW Forever price files for any region, realm and faction, and keeps a
  growing price history per realm in SQLite.
- Imports Auctionator scans (price database version 8, CBOR) whenever the game writes them, and
  warns when Auctionator changes its format.
- SimsarForeverExport addon: recipes (profession windows, trainers, recipe tooltips), vendor prices,
  bags and bank of every character, gold, item icons and sale invoices. Verified on the WoW Forever
  client 1.60.1.
- Analysis for every profession: price now, usual price, what you keep after the auction house
  cut (5% faction, 15% neutral), sales per day, flip profit, robust volatility and trend, warnings, alerts.
- Crafting: profit buying all materials, the comparison with selling the materials, ROI, profit per
  day, recipe payback time.
- Item statistics: mean reversion half-life (AR(1) and ADF), three-day ETS forecast with an 80%
  interval, price elasticity of demand, cheapest time of day and weekday.
- Bags and bank page: every item your characters hold, valued at today's prices.
- Item and coin icons from Blizzard's render CDN, cached locally.
- Web dashboard: overview, opportunities, crafts, what to sell, market map, item pages, data status,
  glossary, first-run setup with install detection and one-click addon install. Synthetic demo mode.
