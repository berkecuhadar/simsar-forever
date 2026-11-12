# Changelog

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
