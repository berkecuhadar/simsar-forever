# Simsar Forever

Simsar Forever ("simsar" is Turkish for "broker") is a local auction house analysis dashboard for **WoW Forever**. It
combines TradeSkillMaster's public price files with your own Auctionator scans, keeps a growing
price history in SQLite, and answers practical questions in a web page on your own machine:

- What sells, how fast, and for how much after the auction house cut and deposits?
- Which of my gathered materials earn the most per day, for every profession?
- Which recipes are worth crafting, and is crafting better than selling the materials?
- How long does a recipe take to pay for itself?
- What is cheap right now, and is it cheap or just falling?
- Does this price snap back, where is it heading, how sensitive are buyers to it, and when in the
  day is it cheapest? (econometric statistics with statsmodels and SciPy)

It is a decision-support tool. It reads data; it never touches the game, posts, buys or clicks
anything, and it cannot promise a profit.

## Requirements

- Windows (other systems work but the start script is PowerShell)
- Python 3.12 or newer
- Node.js 20 or newer, only when running from source (release archives include the built UI)
- WoW Forever with [Auctionator](https://www.curseforge.com/wow/addons/auctionator) for your own scans (optional but recommended)

## Quick start

Download `simsar-forever-<version>.zip` from the releases page, extract it anywhere, and double-click
`start.bat`. The release already contains the built web UI, so only Python is needed.

From source instead (needs Node.js to build the UI on the first run):

```powershell
git clone <this repository> simsar-forever
cd simsar-forever
.\start.bat
```

To stop the dashboard, close its console window or press Ctrl+C in it.

The first run creates a virtual environment, installs the Python packages, builds the UI and opens
the dashboard at <http://127.0.0.1:8765/> on its **setup page**:

1. pick your region (US, EU, TW, KR), realm type (Normal, PvP, Roleplay, Roleplay PvP; TW and KR
   have Normal and PvP) and faction. Simsar Forever checks that TSM publishes data for that
   auction house;
2. pick your game folder. Installs are found automatically from the Windows registry, the
   Battle.net settings and the usual folders on every drive; you can also type a path. If the
   folder has several accounts or Auctionator realms, choose one;
3. tick your professions. They are shown first; every profession is analysed either way.

The choices are saved to `config.yaml` and can be changed any time under **Settings**. Each realm
keeps its own database in `data/`, so switching realms never mixes price histories.

After that, `start.bat` just starts the dashboard. Leave it running: it fetches new TSM data as it
appears and picks up your Auctionator scans by itself, and price history only grows while it runs.

### Demo mode

```powershell
.\start.bat -Demo
```

Starts the dashboard on synthetic data, without network access or a game install. A red banner
marks every page, item names end in "(demo)" and item ids are in the 990000 range, so demo data
cannot be mistaken for the real market.

## In game

1. **Auctionator full scan.** Open the auction house and run a full scan. To scan automatically
   whenever you open the auction house, enable *Start autoscan when the auction house is opened*
   under `/auctionator config` → Basic.
2. **Install SimsarForeverExport** (once, and again after updating Simsar Forever):

   ```powershell
   .venv\Scripts\python -m simsar_forever install-addon
   ```

   It records, into its own SavedVariables file:
   - all recipes of the profession window you open (on clients with the modern profession API this
     includes recipes you have not learned yet), trainer recipes, and recipes shown in tooltips;
   - sale invoices from your mailbox, from which Simsar Forever measures the real auction house cut;
   - the deposit the game quotes when you post, from which Simsar Forever measures the deposit rate;
   - vendor prices of unlimited items (thread, salt, dyes) when you open a vendor.

   Type `/sfe` for a summary and `/sfe diag` to see which game APIs are available.
3. **`/reload` or log out.** The game only writes SavedVariables to disk at that moment. Simsar Forever
   notices the new files within seconds.

## Data sources

| Source | What | How often |
|---|---|---|
| TSM auction house file `forever/<region>/realm/<realm>-<faction>` | cheapest listing, market value, historical | about every 3 hours |
| TSM region file `forever/<region>/region` | average sale price, sale rate, sales per day | about daily |
| `Auctionator.lua` | your scans: cheapest price, daily low/high, units on sale, your posts, vendor prices | when you scan and `/reload` |
| `SimsarForeverExport.lua` | recipes, invoices, deposits, vendor buy prices | when you `/reload` |

TSM's files are public and need no key: <https://tradeskillmaster.com/public-data>. They are
rate limited, though: a burst of a few dozen requests gets HTTP 429 for a while. Simsar Forever
checks at most twice an hour by default and backs off as the server asks.

## Configuration

Everything has a default; `config.example.yaml` documents each setting. The ones worth a look:

| Setting | Default | Meaning |
|---|---|---|
| `tsm.region`, `tsm.realm` | `eu`, `normal-alliance` | Set on the setup page. `realm: null` is region-only mode. |
| `player.professions` | all | Shown first in the dashboard. |
| `economy.realm_share` | 0.25 | Share of region-wide sales that happen on your realm. |
| `economy.market_share` | 0.20 | Share of your realm's sales you expect to win. |
| `economy.ah_cut` | 0.05 | Used until SimsarForeverExport has measured the real cut. |
| `economy.deposit_rate` | 0.15 | Deposit as a share of vendor price, until measured. |
| `analysis.reference_price` | `market` | What "cheap" is measured against; see below. |
| `alerts.*` |  | When to raise cheap-item and craft alerts. |

`groups.yaml` and `recipes.yaml` next to `config.yaml` override the built-in profession groups and
add hand-written recipes; see `recipes.example.yaml` and [docs/architecture.md](docs/architecture.md).

## Command line

The command is `simsar-forever` (or `python -m simsar_forever`).

```
simsar-forever serve            start the dashboard (what start.bat runs)
simsar-forever refresh          fetch TSM data and import SavedVariables once
simsar-forever top [--by sell]  print the best opportunities in the terminal
simsar-forever inspect-ato      describe your Auctionator.lua, useful when its format changes
simsar-forever install-addon    copy SimsarForeverExport into the game's AddOns folder
simsar-forever demo             build and serve the demo database
```

## How the numbers work

[docs/metrics.md](docs/metrics.md) gives every formula, its units and its failure modes. The
dashboard's glossary explains the terms in plain language, and every column has a tooltip.

## Limitations and unverified assumptions

Verified against real data in November 2026: the TSM Forever files for `eu / normal-alliance` exist
and are populated; Auctionator 345 stores its price database as CBOR (`__dbversion` 8) and the day
numbering matches its source code. Still unverified:

- **Sales volume per realm.** TSM publishes sales per day only for the whole region. `realm_share`
  and `market_share` are guesses, so every "per day" number is an order of magnitude, not a forecast.
- **Auction house cut and deposit on Forever.** 5% and 15% are Vanilla-era defaults. Simsar Forever replaces
  them with measured values once SimsarForeverExport has seen sale mails and posts.
- **SimsarForeverExport on the Forever client.** The addon is tested against a simulated API only. The
  profession, trainer, mail and auction APIs it relies on are each wrapped so a missing one cannot
  break the others; `/sfe diag` shows what works.
- **The 60-day historical price.** On a server that launched on 4 November 2026 it still holds
  launch-week prices, so cheapness is measured against the two-week market value by default.
- **Early history.** Volatility and trend need several days of data and stay blank until then.
- **Crafting** assumes you can sell at today's cheapest listing without moving the price.
- **Profession groups** for professions other than the five first built for are matched by item
  name and checked against the EU item list only; recipes reported by the addon fill the gaps.
- **Advanced statistics** describe the past. Elasticity is a correlation, not a causal estimate,
  and forecasts assume nothing changes in the game.

## Development

```powershell
.venv\Scripts\pip install -e .[dev]
.venv\Scripts\python -m pytest            # unit, API, addon (via lupa) and headless-browser tests
cd frontend; npm run dev                  # UI with hot reload, proxying /api to a running server
```

The browser test uses Edge or Chrome if one is installed and is skipped otherwise.

## Building a release

```powershell
.venv\Scripts\python scripts\build_release.py --test
```

Writes `dist/simsar-forever-<version>.zip` (app with the built UI), `dist/SimsarForeverExport-<version>.zip`
(the addon, ready for CurseForge) and `dist/SHA256SUMS.txt`. Bump the version in
`simsar_forever/__init__.py`, `pyproject.toml`, `frontend/package.json` and the addon `.toc` together;
the script refuses to build when they disagree or the working tree is not committed.

## License

MIT, see [LICENSE](LICENSE).
