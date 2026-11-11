"""Data freshness, source health and warnings for the status panel."""

import json
import time

from pathlib import Path

from .. import __version__, auctionator, db, refresh

ADDON_TOC = Path(__file__).resolve().parents[2] / "addon" / "SimsarForeverExport" / "SimsarForeverExport.toc"


def _last_log(conn, source):
    row = conn.execute("SELECT at, ok, details FROM fetch_log WHERE source = ? ORDER BY id DESC LIMIT 1",
                       (source,)).fetchone()
    return {"at": row["at"], "ok": bool(row["ok"]), **json.loads(row["details"])} if row else None


def build(cfg, conn, result, now=None):
    now = now or time.time()
    demo = bool(db.get_meta(conn, "demo"))
    stale_h = cfg["analysis"]["stale_hours"]
    warnings = []

    def warn(level, message):
        warnings.append({"level": level, "message": message})

    if demo:
        warn("demo", "Demo mode: every number on this page is synthetic and says nothing about the real market.")

    sources = []
    for kind in ("realm", "region"):
        if kind == "realm" and not cfg["tsm"].get("realm"):
            continue
        updated = db.get_meta(conn, f"tsm_{kind}_updated_at")
        log = _last_log(conn, f"tsm_{kind}")
        age = (now - updated) / 3600 if updated else None
        src = {"key": f"tsm_{kind}", "label": f"TSM {kind} prices", "updated_at": updated, "age_h": age,
               "checked_at": db.get_meta(conn, f"tsm_{kind}_checked_at"),
               "ok": bool(updated) and (log is None or log["ok"]),
               "error": log.get("error") if log and not log["ok"] else None,
               "url": log.get("url") if log else None}
        sources.append(src)
        if src["error"]:
            warn("error", f"TSM {kind} download failed: {src['error']}")
        elif not updated and not demo:
            warn("error", f"No TSM {kind} data yet. Check your internet connection and the tsm settings.")
        # Region files refresh about daily, realm files every few hours.
        limit = stale_h if kind == "realm" else max(stale_h, 36)
        if age is not None and age > limit and not demo:
            warn("warn", f"TSM {kind} data is {age:.0f} hours old.")

    ato = db.get_meta(conn, "ato_last_import")
    ato_log = _last_log(conn, "auctionator")
    ato_path = refresh.auctionator_path(cfg)
    src = {"key": "auctionator", "label": "Auctionator scan", "path": str(ato_path) if ato_path else None,
           "ok": bool(ato) and (ato_log is None or ato_log["ok"]),
           "imported_at": ato_log["at"] if ato_log else None,
           "file_mtime": ato.get("file_mtime") if ato else None,
           "last_full_scan": ato.get("last_full_scan") if ato else None,
           "addon_version": db.get_meta(conn, "ato_addon_version"),
           "items": ato.get("items") if ato else None,
           "error": ato_log.get("error") if ato_log and not ato_log["ok"] else None}
    sources.append(src)
    if not demo:
        if not cfg["wow"].get("game_dir"):
            warn("info", "Set wow.game_dir in config.yaml so Simsar Forever can read your Auctionator scans.")
        for w in db.get_meta(conn, "ato_warnings") or []:
            warn("warn", w)
        if src["last_full_scan"] and now - src["last_full_scan"] > 3 * 86400:
            days = (now - src["last_full_scan"]) / 86400
            warn("info", f"Your last full Auctionator scan was {days:.0f} days ago. A fresh scan gives better "
                         "'price now' values.")

    addon = db.get_meta(conn, "addon_last_import")
    addon_path = refresh.addon_path(cfg)
    has_addon_file = bool(addon_path and addon_path.exists())
    sources.append({"key": "addon", "label": "SimsarForeverExport addon", "ok": bool(addon and addon.get("ok")),
                    "path": str(addon_path) if addon_path else None, "present": has_addon_file,
                    "recipes": (addon or {}).get("recipes"), "invoices": (addon or {}).get("invoices"),
                    "error": (addon or {}).get("error") or (addon or {}).get("last_error")})
    installed_dir = auctionator.addon_dir(cfg, "SimsarForeverExport")
    if installed_dir and (installed_dir / "SimsarForeverExport.toc").exists() and ADDON_TOC.exists():
        have = auctionator.read_toc(installed_dir / "SimsarForeverExport.toc").get("Version")
        want = auctionator.read_toc(ADDON_TOC).get("Version")
        if have != want:
            warn("warn", f"The installed SimsarForeverExport addon is version {have}, this Simsar Forever ships {want}. "
                         "Run: simsar-forever install-addon")
    installed = bool(installed_dir and (installed_dir / "SimsarForeverExport.toc").exists())
    if not demo and cfg["wow"].get("game_dir") and not has_addon_file:
        if installed:
            warn("info", "SimsarForeverExport is installed but has not written any data yet. Log in, open your "
                         "profession windows, then /reload.")
        else:
            warn("info", "Install the SimsarForeverExport addon (run: simsar-forever install-addon) to import your recipes, "
                         "vendor prices and the real AH cut and deposits.")

    fees = result["fees"]
    if fees.cut_source == "config" and not demo:
        warn("info", f"The auction house cut is assumed to be {fees.ah_cut:.0%}. It will be measured from your "
                     "sale mails once the SimsarForeverExport addon has seen some.")
    if not result["crafts"] and not demo:
        warn("info", "No recipes yet. Open your profession windows in game with SimsarForeverExport installed, "
                     "then /reload.")

    eco = cfg["economy"]
    return {
        "version": __version__,
        "demo": demo,
        "now": now,
        "sources": sources,
        "warnings": warnings,
        "fees": {"ah_cut": fees.ah_cut, "cut_source": fees.cut_source, "deposit_rate": fees.deposit_rate,
                 "deposit_source": fees.deposit_source, "auction_hours": fees.auction_hours,
                 "max_relists": fees.max_relists, "min_deposit": fees.min_deposit,
                 "listing_size": fees.listing_size},
        "assumptions": {
            "realm_share": eco["realm_share"], "market_share": eco["market_share"],
            "sell_price": eco["sell_price"], "history_days": cfg["analysis"]["history_days"],
            "good_margin": cfg["analysis"]["good_margin"],
            "fast_sales_per_day": cfg["analysis"]["fast_sales_per_day"],
            "stale_hours": stale_h, "reference_price": cfg["analysis"]["reference_price"], "tsm": f"{cfg['tsm']['game_type']}/{cfg['tsm']['region']}/{cfg['tsm']['realm']}",
        },
        "alerts_unseen": conn.execute("SELECT COUNT(*) FROM alerts WHERE seen = 0").fetchone()[0],
        "items": len(result["items"]),
        "tracked_items": sum(1 for i in result["items"] if i["groups"]),
        "recipes": len(result["crafts"]),
        "built_at": result["built_at"],
        "build_seconds": result["build_seconds"],
    }
