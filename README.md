# Simsar Forever

Simsar Forever ("simsar" is Turkish for "broker") is a local auction house analysis dashboard for **WoW Forever**. It
combines TradeSkillMaster's public price files with your own Auctionator scans, keeps a growing
price history in SQLite, and answers practical questions in a web page on your own machine:

- What sells, how fast, and for how much after the auction house cut?
- Which of my gathered materials earn the most per day, for every profession?
- Which recipes are worth crafting, and is crafting better than selling the materials?
- What is everything in my characters' bags and banks worth at today's prices?
- Where did my gold come from and go, per character, day and category, and how has it grown?
- Should I sell what I hold now, a few at a time, to a vendor, or wait, and how often has that
  advice been right?
- How long does a recipe take to pay for itself?
- What do I need to buy for the crafts I plan, after what my characters already hold?
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
2. **Install the Simsar Forever addon** (once, and again after updating Simsar Forever): press
   *Install addon* on the dashboard's Settings page, or run

   ```powershell
   .venv\Scripts\python -m simsar_forever install-addon
   ```

   It records, into its own SavedVariables file:
   - all recipes of the profession window you open (on clients with the modern profession API this
     includes recipes you have not learned yet), trainer recipes with their cost and required skill,
     recipes shown in tooltips, and recipes vendors sell;
   - each character's profession skill levels and which recipes that character knows;
   - the bags of every character you log in with, and the bank whenever you open it;
   - a gold ledger: every change of gold, booked under what you were doing (auction sale, auction
     purchase, deposit, vendor, repair, mail, gold sent between your own characters, quest, loot,
     trainer, taxi, ...), and the gold on hand at the end of each day;
   - auction mail: sales (used to double-check the auction house cut), purchases with the price
     paid, and expired or cancelled auctions;
   - the icon id of every item, so the dashboard can show item icons;
   - vendor prices of unlimited items (thread, salt, dyes) when you open a vendor.

   It also adds the dashboard's advice to item tooltips: what one sale on the auction house leaves
   you, how many sell per day, whether to sell now, vendor or hold, and what crafting it makes. The
   dashboard writes that data into the addon folder while it runs; the game loads it on login or
   `/reload`. `/sfe tooltip off` hides it.

   Type `/sfe` for a summary and `/sfe diag` to see which game APIs are available. Before 0.2.0 the
   addon was called SimsarForeverExport; installing the new one removes the old folder, and the old
   addon's saved data is still read, so nothing is lost.
3. **Save.** The game writes addon data to disk only on `/reload`, logout or a character switch; no
   addon can make it write sooner. Logging out is enough. To send data right away, type `/reload`
   yourself; the addon never reloads the interface for you. After a bank visit or new recipes it
   reminds you in chat and on screen (at most every ten minutes; `/sfe prompt off` turns it off).
   Characters you are not logged in with keep their last saved bags, bank and gold. Simsar Forever
   picks up the new files within seconds; there is nothing to do on the dashboard side.

If you use [Accountant Classic](https://www.curseforge.com/wow/addons/accountant-classic), its gold
history is imported too, so the ledger reaches back to before the Simsar Forever addon was installed.

## Data sources

| Source | What | How often |
|---|---|---|
| TSM auction house file `forever/<region>/realm/<realm>-<faction>` | cheapest listing, market value, historical | about every 3 hours |
| TSM region file `forever/<region>/region` | average sale price, sale rate, sales per day | about daily |
| `Auctionator.lua` | your scans: cheapest price, daily low/high, units on sale, your posts, vendor prices | when you scan and `/reload` |
| `SimsarForever.lua` | recipes, professions, vendor prices, bags, bank, gold ledger, item icons, auction mail | when you `/reload` |
| `Accountant_Classic.lua` | gold history from the Accountant Classic addon, if you use it | when you `/reload` |
| render.worldofwarcraft.com | item and coin icons, cached in `data/icons` | first time an icon is shown |

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
| `economy.auction_house` | `faction` | `faction` (Alliance/Horde, 5% cut) or `neutral` (15% cut). Set in Settings. |
| `icons.enabled` | true | Item and coin icons from Blizzard's CDN. |
| `analysis.reference_price` | `market` | What "cheap" is measured against; see below. |
| `advice.*` | | When the sell plan says hold or sell gradually; see docs/metrics.md. |
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
simsar-forever install-addon    copy the Simsar Forever addon into the game's AddOns folder
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
- **Deposits are not counted.** Profits are after the auction house cut only; listing deposits
  are refunded on sale and Simsar Forever does not model expired listings.
- **Icons** need a one-off download of the community listfile (about 150 MB, only the icon rows
  are kept) to turn the game's icon ids into names. Icons Forever added after the listfile was
  last updated show as blank squares.
- **The bank** is only as current as the last time you opened it in game.
- **The addon on the Forever client.** The addon is tested against a simulated API only. The
  profession, trainer, mail and auction APIs it relies on are each wrapped so a missing one cannot
  break the others; `/sfe diag` shows what works.
- **Ledger categories** come from the window that is open when gold changes. Gold that changes with
  no window open is booked as "Other", and gold that changed while the addon was not running is
  booked once at the next login as "Untracked".
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

Writes `dist/simsar-forever-<version>.zip` (app with the built UI), `dist/SimsarForever-<version>.zip`
(the addon, ready for CurseForge) and `dist/SHA256SUMS.txt`. Bump the version in
`simsar_forever/__init__.py`, `pyproject.toml`, `frontend/package.json` and the addon `.toc` together;
the script refuses to build when they disagree or the working tree is not committed.

## License

MIT, see [LICENSE](LICENSE).
