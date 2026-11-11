import logging
import threading
from contextlib import asynccontextmanager
import time
import webbrowser
from importlib import resources
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__, config, db, refresh
from .. import groups as groupmod
from ..analysis import crafts as craftmod
from ..analysis import explain, market
from ..analysis.engine import Engine
from . import status as statusmod

log = logging.getLogger("simsar")

ITEM_LIST_FIELDS = (
    "item_id", "name", "groups", "group", "price_now", "price_src", "market", "historical", "sell_price",
    "sell_ref", "net_sell", "sale_rate", "sold_per_day_region", "my_sales_per_day", "available",
    "turnover_day", "income_day", "flip_profit", "flip_margin", "flip_profit_day", "volatility", "trend",
    "reference", "disc_ref", "disc_hist", "period_min", "period_max", "n_points", "confidence", "score", "label", "flags",
    "deposit", "vendor_sell", "data_age_h",
)


def static_dir():
    return Path(str(resources.files("simsar").joinpath("web/static")))


def create_app(cfg, background=True):
    path = config.db_path(cfg)
    engine = Engine(cfg, db.connect(path))
    worker = refresh.Background(cfg, db.connect(path), engine) if background else None

    @asynccontextmanager
    async def lifespan(_app):
        if worker:
            worker.start()
        yield
        if worker:
            worker.stop.set()

    app = FastAPI(title="Simsar", version=__version__, docs_url="/api/docs", redoc_url=None, lifespan=lifespan)
    allowed_hosts = {f"{h}:{cfg['server']['port']}" for h in ("127.0.0.1", "localhost", "[::1]")}
    allowed_hosts |= {"127.0.0.1", "localhost", "testserver"}

    def conn():
        return db.connect(path)

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        # Rejects requests addressed to another host name (DNS rebinding) even though we only listen on loopback.
        if request.headers.get("host") not in allowed_hosts:
            return JSONResponse({"detail": "forbidden host"}, status_code=403)
        return await call_next(request)

    @app.get("/api/status")
    def status():
        return statusmod.build(cfg, conn(), engine.result())

    @app.get("/api/overview")
    def overview():
        return {"groups": engine.result()["overview"]}

    @app.get("/api/groups")
    def groups():
        return groupmod.public(engine.groups)

    @app.get("/api/items")
    def items(scope: str = "tracked", group: str | None = None):
        rows = engine.result()["items"]
        if group:
            rows = [i for i in rows if group in i["groups"]]
        elif scope != "all":
            rows = [i for i in rows if i["groups"]]
        return [{k: i.get(k) for k in ITEM_LIST_FIELDS} for i in rows]

    @app.get("/api/items/{item_id}")
    def item(item_id: int):
        result = engine.result()
        it = result["by_id"].get(item_id)
        if not it:
            raise HTTPException(404, "unknown item")
        c = conn()
        since = time.time() - cfg["storage"]["retain_days"] * 86400
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
        used_in = [x for x in result["crafts"]
                   if x["product_id"] == item_id or any(r["item_id"] == item_id for r in x["reagents"])]
        return {
            "item": it,
            "explanation": explain.item(it, result["fees"], cfg),
            "history": {"realm": realm, "region": region, "auctionator": daily, "postings": postings},
            "crafts": used_in,
        }

    @app.get("/api/crafts")
    def crafts(profession: str | None = None):
        rows = engine.result()["crafts"]
        if profession:
            rows = [r for r in rows if r["profession"].lower() == profession.lower()]
        return rows

    @app.get("/api/meta")
    def meta():
        return {"labels": market.LABELS, "flags": market.FLAGS, "verdicts": craftmod.VERDICTS,
                "version": __version__}

    @app.get("/api/alerts")
    def alerts(limit: int = 50):
        return [dict(r) for r in conn().execute(
            "SELECT id, created_at, kind, item_id, title, message, seen FROM alerts ORDER BY id DESC LIMIT ?",
            (limit,))]

    @app.post("/api/alerts/seen")
    def alerts_seen():
        c = conn()
        c.execute("UPDATE alerts SET seen = 1 WHERE seen = 0")
        c.commit()
        return {"ok": True}

    @app.post("/api/refresh")
    def refresh_now():
        if not worker:
            raise HTTPException(409, "refresh is disabled in demo mode")
        if not worker.lock.acquire(blocking=False):
            return {"ok": True, "busy": True}
        worker.lock.release()
        threading.Thread(target=worker.refresh_now, daemon=True).start()
        return {"ok": True, "started": True}

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

    app.state.engine = engine
    app.state.worker = worker
    return app


def run(cfg, open_browser=True, background=True):
    import uvicorn
    host, port = cfg["server"]["host"], cfg["server"]["port"]
    app = create_app(cfg, background=background)
    url = f"http://{host}:{port}/"
    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    log.info("Simsar is running at %s (Ctrl+C to stop)", url)
    uvicorn.run(app, host=host, port=port, log_level="warning")
