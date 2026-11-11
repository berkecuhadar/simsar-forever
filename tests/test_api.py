import pytest
from fastapi.testclient import TestClient

from simsar import config, db, demo
from simsar.web.app import create_app


@pytest.fixture
def client(tmp_path):
    cfg = config.load(tmp_path / "config.yaml")
    conn = db.connect(config.db_path(cfg))
    demo.build(conn)
    conn.close()
    with TestClient(create_app(cfg, background=False)) as c:
        yield c


def test_status_reports_demo(client):
    s = client.get("/api/status").json()
    assert s["demo"] is True
    assert s["warnings"][0]["level"] == "demo"
    assert s["fees"]["ah_cut"] == 0.05
    assert s["tracked_items"] > 0


def test_items_and_detail(client):
    items = client.get("/api/items").json()
    assert items and all(i["groups"] for i in items)
    leather = next(i for i in items if i["name"] == "Light Leather (demo)")
    detail = client.get(f"/api/items/{leather['item_id']}").json()
    assert detail["history"]["realm"] and detail["history"]["auctionator"]
    assert detail["explanation"]
    assert client.get("/api/items/1").status_code == 404


def test_group_filter_and_crafts(client):
    tailoring = client.get("/api/items", params={"group": "tailoring"}).json()
    assert tailoring and all("tailoring" in i["groups"] for i in tailoring)
    crafts = client.get("/api/crafts", params={"profession": "Tailoring"}).json()
    assert crafts and all(c["profession"] == "Tailoring" for c in crafts)


def test_overview_meta_alerts(client):
    groups = client.get("/api/overview").json()["groups"]
    assert {g["key"] for g in groups} >= {"skinning", "tailoring", "enchanting"}
    meta = client.get("/api/meta").json()
    assert "fast_profitable" in meta["labels"]
    assert client.get("/api/alerts").json() == []
    assert client.post("/api/alerts/seen").json()["ok"]


def test_refresh_disabled_without_worker(client):
    assert client.post("/api/refresh").status_code == 409


def test_foreign_host_rejected(client):
    assert client.get("/api/status", headers={"host": "evil.example:8765"}).status_code == 403


def test_config_rejects_public_host(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("server:\n  host: 0.0.0.0\n")
    with pytest.raises(config.ConfigError):
        config.load(f)
