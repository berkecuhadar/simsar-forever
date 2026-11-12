"""Smoke test: serve the built UI with demo data and render pages in a headless browser."""

import os
import shutil
import socket
import subprocess
import threading
import time

import pytest

from simsar_forever import config, db, demo
from simsar_forever.web.app import create_app, static_dir

BROWSERS = [
    os.environ.get("SIMSAR_FOREVER_BROWSER", ""),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    shutil.which("chromium") or "", shutil.which("google-chrome") or "", shutil.which("chrome") or "",
]
BROWSER = next((b for b in BROWSERS if b and os.path.exists(b)), None)

pytestmark = [
    pytest.mark.skipif(BROWSER is None, reason="no Edge or Chrome found"),
    pytest.mark.skipif(not (static_dir() / "index.html").exists(), reason="web UI not built"),
]


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import uvicorn
    tmp = tmp_path_factory.mktemp("browser")
    port = _free_port()
    cfg = config.load(tmp / "config.yaml", overrides={"server": {"port": port}, "icons": {"enabled": False}})
    conn = db.connect(config.db_path(cfg))
    demo.build(conn)
    conn.close()
    srv = uvicorn.Server(uvicorn.Config(create_app(cfg, background=False), host="127.0.0.1", port=port,
                                        log_level="error"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", tmp
    srv.should_exit = True
    thread.join(5)


def render(url, profile):
    out = subprocess.run(
        [BROWSER, "--headless=new", "--disable-gpu", f"--user-data-dir={profile}", "--virtual-time-budget=6000",
         "--dump-dom", url],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    return out.stdout


@pytest.mark.parametrize("path, expected", [
    ("/", ["Demo mode", "Skinning", "Market size/day"]),
    ("/opportunities", ["Demo mode", "Opportunities", "(demo)"]),
    ("/gathering", ["What to sell", "Light Leather (demo)"]),
    ("/crafts", ["Crafts", "Bolt of Linen Cloth (demo)"]),
    ("/glossary", ["Opportunity cost", "Sale rate"]),
    ("/status", ["Data status", "Auction house cut"]),
    ("/inventory", ["Bags and bank", "Leatherhand (demo)", "Heavy Leather (demo)"]),
    ("/ledger", ["Gold ledger", "Auction sales", "Heavy Armor Kit (demo)", "Gold over time"]),
    ("/sell", ["Sell plan", "Heavy Leather (demo)", "Do this"]),
    ("/accuracy", ["Forecast accuracy", "Backtest", "Live record"]),
    ("/professions", ["Professions", "Leatherworking", "Thick Armor Kit (demo)", "How to get it"]),
    ("/shopping?add=demo:Leatherworking|Heavy Armor Kit", ["Shopping list", "Heavy Leather (demo)", "Expected profit"]),
])
def test_page_renders(server, path, expected):
    base, tmp = server
    dom = render(base + path, tmp / "profile")
    for text in expected:
        assert text in dom, f"{text!r} missing on {path}"
