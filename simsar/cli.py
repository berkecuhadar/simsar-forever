import argparse
import json
import logging
import sys

from . import auctionator, config, db, refresh
from .money import fmt


def _conn(cfg):
    return db.connect(config.db_path(cfg))


def cmd_serve(cfg, args):
    from .web.app import run
    run(cfg, open_browser=not args.no_browser)


def cmd_refresh(cfg, args):
    conn = _conn(cfg)
    print(json.dumps(refresh.refresh_all(cfg, conn, force=True), indent=2, default=str))


def cmd_fetch(cfg, args):
    conn = _conn(cfg)
    for rep in refresh.fetch_tsm(cfg, conn):
        if rep["ok"]:
            state = "unchanged" if rep.get("unchanged") else f"{rep.get('new_rows', 0)} new rows"
            print(f"{rep['source']}: {rep.get('rows', '-')} rows, {state}")
        else:
            print(f"{rep['source']}: FAILED - {rep['error']}")


def cmd_import(cfg, args):
    conn = _conn(cfg)
    print(json.dumps({"auctionator": refresh.import_auctionator(cfg, conn, force=True),
                      "addon": refresh.import_addon(cfg, conn, force=True)}, indent=2, default=str))


def cmd_inspect_ato(cfg, args):
    path = args.path or refresh.auctionator_path(cfg)
    if not path:
        sys.exit("Set wow.game_dir in config.yaml or pass the path to Auctionator.lua.")
    print(auctionator.inspect(path))


def cmd_find_ato(cfg, args):
    hits = auctionator.find_files(args.root)
    print("\n".join(hits) if hits else "No Auctionator.lua found under that folder.")


def cmd_install_addon(cfg, args):
    from . import addon_install
    try:
        target = addon_install.install(cfg["wow"].get("game_dir"))
    except addon_install.InstallError as e:
        sys.exit(f"Could not install the addon: {e}")
    print(f"Installed SimsarExport to {target}. Restart the game or /reload, then type /simsar diag.")


def cmd_demo(cfg, args):
    from . import demo
    path = config.db_path(cfg).with_name("demo.db")
    if path.exists():
        path.unlink()
    conn = db.connect(path)
    rep = demo.build(conn)
    print(f"Demo database written to {path} ({rep['items']} synthetic items).")
    if not args.no_serve:
        cfg["storage"]["db_path"] = str(path)
        from .web.app import run
        run(cfg, open_browser=not args.no_browser, background=False)


def cmd_top(cfg, args):
    from .analysis.engine import Engine
    result = Engine(cfg, _conn(cfg)).result()
    rows = [i for i in result["items"] if i["groups"]] if not args.all else result["items"]
    key = {"flip": "score", "sell": "income_day"}[args.by]
    rows = sorted((i for i in rows if i[key]), key=lambda i: -i[key])[: args.n]
    for i in rows:
        print(f"{i['name'][:34]:34} {i['group'] or '-':15} now {fmt(i['price_now']):>14}  "
              f"{key} {fmt(i[key]):>14}/day  {i['label']}")
    print(f"\nFees: cut {result['fees'].ah_cut:.1%} ({result['fees'].cut_source}), "
          f"deposit rate {result['fees'].deposit_rate:.0%} ({result['fees'].deposit_source}). "
          f"Built in {result['build_seconds']}s.")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="simsar-forever", description="Simsar Forever: local auction house dashboard for WoW Forever.")
    parser.add_argument("--config", help="path to config.yaml (default: ./config.yaml)")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="start the dashboard and keep data up to date")
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(func=cmd_serve)
    sub.add_parser("refresh", help="download TSM data and import SavedVariables once").set_defaults(func=cmd_refresh)
    sub.add_parser("fetch", help="download TSM data only").set_defaults(func=cmd_fetch)
    sub.add_parser("import", help="import Auctionator and SimsarExport files now").set_defaults(func=cmd_import)
    p = sub.add_parser("inspect-ato", help="describe an Auctionator.lua file")
    p.add_argument("path", nargs="?")
    p.set_defaults(func=cmd_inspect_ato)
    p = sub.add_parser("find-ato", help="search a folder for Auctionator.lua")
    p.add_argument("root")
    p.set_defaults(func=cmd_find_ato)
    sub.add_parser("install-addon", help="copy the SimsarExport addon into the game's AddOns folder")         .set_defaults(func=cmd_install_addon)
    p = sub.add_parser("demo", help="build a synthetic demo database and serve it")
    p.add_argument("--no-serve", action="store_true")
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(func=cmd_demo)
    p = sub.add_parser("top", help="print the best opportunities in the terminal")
    p.add_argument("--by", choices=["flip", "sell"], default="flip")
    p.add_argument("-n", type=int, default=25)
    p.add_argument("--all", action="store_true", help="include items outside the profession groups")
    p.set_defaults(func=cmd_top)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        cfg = config.load(args.config)
    except config.ConfigError as e:
        sys.exit(f"Config error: {e}")
    args.func(cfg, args)
