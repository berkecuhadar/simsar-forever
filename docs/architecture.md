# Architecture

```
TSM public CSVs ──► tsm.py ─────────┐
                                    │
Auctionator.lua ──► auctionator.py ─┤                         ┌─► web/app.py (FastAPI, /api/*)
                    (lua.py, CBOR)  ├─► SQLite (db.py) ─► analysis/engine.py
SimsarForeverExport.lua ─► addon_import.py ┘                         └─► cli.py (simsar-forever top)
                                                                        │
                                                    frontend/ (React) ◄─┘ built into web/static
```

## Modules

| Path | Role |
|---|---|
| `simsar_forever/config.py` | Defaults, `config.yaml` loading, validation. |
| `simsar_forever/db.py` | SQLite schema, small helpers, migrations. |
| `simsar_forever/lua.py` | Data-only SavedVariables parser. Keeps binary strings intact. |
| `simsar_forever/tsm.py` | Downloads and parses TSM CSVs with retries, ETags and duplicate-scan skip. |
| `simsar_forever/auctionator.py` | Reads Auctionator's price database (CBOR), posting history, vendor cache. |
| `simsar_forever/addon_import.py` | Reads SimsarForeverExport data and derives measured AH fees. |
| `simsar_forever/refresh.py` | One-shot refresh and the background thread (TSM polling, file watching, alerts). |
| `simsar_forever/groups.py`, `simsar_forever/data/groups.yaml` | Profession groups by item name pattern. |
| `simsar_forever/analysis/` | Fees, robust statistics, the item table, crafts, commentary, alerts, cached engine. |
| `simsar_forever/web/` | FastAPI app and the status panel builder. Serves the built UI from `web/static`. |
| `simsar_forever/demo.py` | Synthetic demo data. |
| `addon/SimsarForeverExport/` | In-game addon. |
| `frontend/` | React + TypeScript UI (Vite, ECharts, TanStack Table). |

## Data flow

1. The background thread checks TSM every `tsm.check_minutes`. A new scan (new `updatedAt`) is
   stored as one row per item in `tsm_realm` or `tsm_region`, so price history accumulates.
   Unchanged files are skipped by ETag and by `updatedAt`.
2. Every `wow.watch_seconds` it compares the size and modification time of `Auctionator.lua` and
   `SimsarForeverExport.lua` with the last import and re-imports changed files. The game only writes these
   files on `/reload`, logout or exit.
3. Each import bumps `data_version` in the `meta` table. The analysis engine caches its result and
   rebuilds only when `data_version` changes (about 0.3 s for 6,000 items).
4. After a rebuild the thread generates alerts and stores them with a per-day dedupe key. The UI
   polls `/api/status` every 30 seconds and shows browser notifications for new alerts.

## Auctionator format changes

Auctionator updates itself through CurseForge. On each import Simsar Forever records the addon version
(from `Auctionator.toc`), the database version (`__dbversion`) and a fingerprint of the entry
fields. An unknown database version stops the import with an error instead of guessing. A new
addon version, a changed fingerprint or unknown fields produce warnings on the data status page.
The verified layout is pinned by `tests/fixtures/Auctionator.lua`, cut from a real file.

## Security

The server only binds to loopback addresses (enforced in `config.validate`) and rejects requests
whose `Host` header is not local, which blocks DNS-rebinding pages from reaching the API. There are
no secrets: TSM's public files need no key.

## Adding a profession group

Groups match items by name. To change one, copy `simsar_forever/data/groups.yaml` to `groups.yaml` next to
`config.yaml` and edit it; a group there replaces the built-in group with the same key.

```yaml
groups:
  mining:
    title: Mining
    profession: Mining          # matched against the profession name in recipes
    role: gather                # gather, craft or recipe
    color: "#8a8f98"
    patterns:                   # case-insensitive regular expressions on the item name
      - "Ore$"
      - "Bar$"
    exclude:
      - "^Enchanted Thorium Bar$"
    ids: [2770]                 # optional, pins items by id
```

Products and reagents of recipes from that profession join the group automatically.
