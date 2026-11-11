import logging
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from importlib import resources
from pathlib import Path

import requests
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__, addon_install, config, db, discover, forever, refresh, tsm
from .. import groups as groupmod
from ..analysis import crafts as craftmod
from ..analysis import econometrics, explain, market
from ..analysis.engine import Engine
from . import status as statusmod

log = logging.getLogger("simsar_forever")

ITEM_LIST_FIELDS = (
    "item_id", "name", "groups", "group", "price_now", "price_src", "market", "historical", "sell_price",
    "sell_ref", "net_sell", "sale_rate", "sold_per_day_region", "my_sales_per_day", "available",
    "turnover_day", "income_day", "flip_profit", "flip_margin", "flip_profit_day", "volatility", "trend",
    "reference", "disc_ref", "disc_hist", "period_min", "period_max", "n_points", "confidence", "score",
    "label", "flags", "deposit", "vendor_sell", "data_age_h",
)


def static_dir():
    return Path(str(resources.files("simsar_forever").joinpath("web/static")))


class Runtime:
    """Config, database, analysis engine and background worker. Rebuilt when the setup page saves."""

    def __init__(self, cfg, background):
        self.background = background
        self.lock = threading.Lock()
        self.worker = None
        self._open(cfg)

    def _open(self, cfg):
        self.cfg = cfg
        self.path = config.db_path(cfg)
        self.engine = Engine(cfg, db.connect(self.path))
        self.worker = refresh.Background(cfg, self.path, self.engine) if self.background else None

    def conn(self):
        return db.connect(self.path)

    def start(self):
        if self.worker:
            self.worker.start()

    def stop(self):
        if self.worker:
            self.worker.stop.set()

    def reload(self):
        with self.lock:
            self.stop()
            self._open(config.load(self.cfg["_path"]))
            self.start()


def create_app(cfg, background=True):
    rt = Runtime(cfg, background)

    @asynccontextmanager
    async def lifespan(_app):
        rt.start()
        yield
        rt.stop()

    app = FastAPI(title="Simsar Forever", version=__version__, docs_url="/api/docs", redoc_url=None,
                  lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=2000)
    allowed_hosts = {f"{h}:{cfg['server']['port']}" for h in ("127.0.0.1", "localhost", "[::1]")}
    allowed_hosts |= {"127.0.0.1", "localhost", "testserver"}

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        # Rejects requests addressed to another host name (DNS rebinding) even though we only listen on loopback.
        if request.headers.get("host") not in allowed_hosts:
            return JSONResponse({"detail": "forbidden host"}, status_code=403)
        return await call_next(request)

    @app.get("/api/status")
    def status():
        out = statusmod.build(rt.cfg, rt.conn(), rt.engine.result())
        out["configured"] = rt.cfg["_exists"] or out["demo"]
        out["realm_label"] = forever.label(rt.cfg["tsm"]["region"], rt.cfg["tsm"].get("realm"))
        return out

    @app.get("/api/overview")
    def overview():
        return {"groups": rt.engine.result()["overview"]}

    @app.get("/api/groups")
    def groups():
        mine = {p.lower() for p in rt.cfg["player"]["professions"]}
        return [{**g, "mine": g["profession"].lower() in mine} for g in groupmod.public(rt.engine.groups)]

    @app.get("/api/items")
    def items(scope: str = "tracked", group: str | None = None):
        rows = rt.engine.result()["items"]
        if group:
            rows = [i for i in rows if group in i["groups"]]
        elif scope != "all":
            rows = [i for i in rows if i["groups"]]
        return [{k: i.get(k) for k in ITEM_LIST_FIELDS} for i in rows]

    def history(item_id):
        c = rt.conn()
        since = time.time() - rt.cfg["storage"]["retain_days"] * 86400
        realm = [dict(r) for r in c.execute(
            "SELECT updated_at AS t, market, min_buyout, historical FROM tsm_realm "
            "WHERE item_id = ? AND updated_at >= ? ORDER BY updated_at", (item_id, since))]
        region = [dict(r) for r in c.execute(
            "SELECT updated_at AS t, market, avg_sale, sale_rate, sold_per_day FROM tsm_region "
            "WHERE item_id = ? AND updated_at >= ? ORDER BY updated_at", (item_id, since))]
        daily = [dict(r) for r in c.execute(
            "SELECT day_ts AS t, low, high, available FROM ato_daily WHERE item_id = ? AND day_ts >= ? "
            "ORDER BY day_ts", (item_id, since))]
        postings = [dict(r) for r in c.execute(
            "SELECT posted_at AS t, price, quantity FROM my_postings WHERE item_id = ? ORDER BY posted_at",
            (item_id,))]
        return {"realm": realm, "region": region, "auctionator": daily, "postings": postings}

    @app.get("/api/items/{item_id}")
    def item(item_id: int):
        result = rt.engine.result()
        it = result["by_id"].get(item_id)
        if not it:
            raise HTTPException(404, "unknown item")
        used_in = [x for x in result["crafts"]
                   if x["product_id"] == item_id or any(r["item_id"] == item_id for r in x["reagents"])]
        return {
            "item": it,
            "explanation": explain.item(it, result["fees"], rt.cfg),
            "history": history(item_id),
            "crafts": used_in,
        }

    @app.get("/api/items/{item_id}/stats")
    def item_stats(item_id: int):
        if item_id not in rt.engine.result()["by_id"]:
            raise HTTPException(404, "unknown item")
        return econometrics.analyse(history(item_id))

    @app.get("/api/crafts")
    def crafts(profession: str | None = None):
        rows = rt.engine.result()["crafts"]
        if profession:
            rows = [r for r in rows if r["profession"].lower() == profession.lower()]
        return rows

    @app.get("/api/meta")
    def meta():
        return {"labels": market.LABELS, "flags": market.FLAGS, "verdicts": craftmod.VERDICTS,
                "version": __version__}

    @app.get("/api/alerts")
    def alerts(limit: int = 50):
        return [dict(r) for r in rt.conn().execute(
            "SELECT id, created_at, kind, item_id, title, message, seen FROM alerts ORDER BY id DESC LIMIT ?",
            (limit,))]

    @app.post("/api/alerts/seen")
    def alerts_seen():
        c = rt.conn()
        c.execute("UPDATE alerts SET seen = 1 WHERE seen = 0")
        c.commit()
        return {"ok": True}

    @app.post("/api/refresh")
    def refresh_now():
        worker = rt.worker
        if not worker:
            raise HTTPException(409, "refresh is disabled in demo mode")
        if not worker.lock.acquire(blocking=False):
            return {"ok": True, "busy": True}
        worker.lock.release()
        threading.Thread(target=worker.refresh_now, daemon=True).start()
        return {"ok": True, "started": True}

    @app.get("/api/setup")
    def setup_info():
        c = rt.cfg
        game_dir = c["wow"].get("game_dir")
        return {
            "config_exists": c["_exists"],
            "current": {
                "region": c["tsm"]["region"], "realm": c["tsm"].get("realm"),
                "game_dir": game_dir, "account": c["wow"].get("account"),
                "auctionator_realm": c["wow"].get("auctionator_realm"),
                "professions": c["player"]["professions"],
            },
            "catalog": forever.catalog(),
            "professions": sorted({g["profession"] for g in rt.engine.groups if g["role"] != "recipe"}),
            "installs": discover.find_installs(),
            "addon_version": addon_install.shipped_version(),
            "selected": discover.describe(game_dir) if game_dir else None,
        }

    @app.get("/api/setup/inspect")
    def setup_inspect(path: str, account: str | None = None):
        info = discover.describe(path)
        if account:
            info["auctionator_realms"] = discover.auctionator_realms(info["path"], account)
        return info

    @app.get("/api/setup/check")
    def setup_check(region: str, realm: str | None = None):
        if not forever.valid(region, realm):
            raise HTTPException(400, "unknown region or realm")
        probe = {**rt.cfg, "tsm": {**rt.cfg["tsm"], "region": region, "realm": realm}}
        out = {}
        for kind, url in tsm.urls(probe).items():
            try:
                r = requests.head(url, headers=tsm.HEADERS, timeout=15)
                out[kind] = {"url": url, "status": r.status_code,
                             "ok": r.status_code == 200, "rate_limited": r.status_code == 429}
            except requests.RequestException as e:
                out[kind] = {"url": url, "status": None, "ok": False, "error": str(e)}
        return out

    @app.post("/api/setup/install-addon")
    def setup_install_addon(body: dict = Body(...)):
        if not rt.background:
            raise HTTPException(409, "not available in demo mode")
        try:
            target = addon_install.install(body.get("game_dir"))
        except addon_install.InstallError as e:
            raise HTTPException(400, str(e))
        return {"ok": True, "path": str(target), "version": addon_install.shipped_version()}

    @app.post("/api/setup")
    def setup_save(body: dict = Body(...)):
        if not rt.background:
            raise HTTPException(409, "setup is disabled in demo mode")
        region, realm = body.get("region"), body.get("realm")
        if not forever.valid(region, realm):
            raise HTTPException(400, "unknown region or realm")
        updates = {
            "tsm": {"game_type": forever.GAME_TYPE, "region": region, "realm": realm},
            "wow": {"game_dir": body.get("game_dir") or None, "account": body.get("account") or None,
                    "auctionator_realm": body.get("auctionator_realm") or None},
            "player": {"professions": list(body.get("professions") or [])},
        }
        try:
            config.save(rt.cfg["_path"], updates)
        except config.ConfigError as e:
            raise HTTPException(400, str(e))
        rt.reload()
        return {"ok": True, "db_path": str(rt.path)}

    static = static_dir()
    if (static / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            target = static / path
            if path and target.is_file() and static in target.resolve().parents:
                return FileResponse(target)
            return FileResponse(static / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def missing_ui():
            return JSONResponse({"detail": "The web UI is not built. Run: npm --prefix frontend ci && "
                                           "npm --prefix frontend run build"}, status_code=503)

    app.state.runtime = rt
    return app


def run(cfg, open_browser=True, background=True):
    import uvicorn
    host, port = cfg["server"]["host"], cfg["server"]["port"]
    app = create_app(cfg, background=background)
    url = f"http://{host}:{port}/"
    if not cfg["_exists"] and background:
        url += "setup"
    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    log.info("Simsar Forever is running at %s (Ctrl+C to stop)", url)
    uvicorn.run(app, host=host, port=port, log_level="warning")
