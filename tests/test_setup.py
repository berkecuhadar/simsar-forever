import pytest
import yaml
from fastapi.testclient import TestClient

from simsar import config, discover, forever, refresh, tsm
from simsar.web.app import create_app


def test_forever_slugs():
    assert forever.slug("roleplay-pvp", "horde") == "roleplay-pvp-horde"
    assert forever.parse_slug("roleplay-pvp-horde") == ("roleplay-pvp", "horde")
    assert forever.parse_slug("normal") is None
    assert forever.valid("eu", "pvp-alliance")
    assert not forever.valid("kr", "roleplay-alliance")      # Korea has no roleplay realms
    assert forever.valid("tw", None)
    assert not forever.valid("cn", "normal-horde")
    assert forever.label("us", "pvp-horde") == "Americas (US) - PvP - Horde"


def test_config_rejects_unknown_realm(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("tsm:\n  region: kr\n  realm: roleplay-horde\n")
    with pytest.raises(config.ConfigError, match="region/realm"):
        config.load(f)


def test_db_path_per_realm_and_legacy_rename(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "simsar.db").write_bytes(b"old")
    cfg = config.load(tmp_path / "config.yaml")
    p = config.db_path(cfg)
    assert p.name == "forever-eu-normal-alliance.db"
    assert p.read_bytes() == b"old" and not (tmp_path / "data" / "simsar.db").exists()


def test_save_merges_and_keeps_other_keys(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("economy:\n  market_share: 0.3\n")
    config.save(f, {"tsm": {"region": "us", "realm": "pvp-horde"}})
    data = yaml.safe_load(f.read_text())
    assert data["economy"]["market_share"] == 0.3 and data["tsm"]["realm"] == "pvp-horde"
    with pytest.raises(config.ConfigError):
        config.save(f, {"tsm": {"region": "us", "realm": "nope"}})


def test_discover_describes_a_forever_folder(tmp_path):
    sv = tmp_path / "World of Warcraft" / "_forever_" / "WTF" / "Account" / "ACC#1" / "SavedVariables"
    sv.mkdir(parents=True)
    (sv / "Auctionator.lua").write_text("AUCTIONATOR_CONFIG = {}\n")
    (tmp_path / "World of Warcraft" / "_forever_" / ".flavor.info").write_text("#Flavor\nwowf\n")
    info = discover.describe(tmp_path / "World of Warcraft")
    assert info["is_forever"] and info["flavor"] == "wowf"
    assert info["accounts"] == [{"name": "ACC#1", "has_auctionator": True,
                                 "auctionator_mtime": info["accounts"][0]["auctionator_mtime"],
                                 "has_simsar_export": False}]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(refresh.Background, "start", lambda self: None)
    monkeypatch.setattr(discover, "find_installs", lambda: [])
    cfg = config.load(tmp_path / "config.yaml")
    return TestClient(create_app(cfg, background=True)), tmp_path


def test_setup_flow_switches_realm_database(client):
    c, tmp = client
    assert c.get("/api/status").json()["configured"] is False
    info = c.get("/api/setup").json()
    assert {r["key"] for r in info["catalog"]["regions"]} == {"us", "eu", "tw", "kr"}
    assert "Leatherworking" in info["professions"]

    r = c.post("/api/setup", json={"region": "us", "realm": "pvp-horde", "professions": ["Mining"]})
    assert r.status_code == 200 and r.json()["db_path"].endswith("forever-us-pvp-horde.db")
    status = c.get("/api/status").json()
    assert status["configured"] is True and status["realm_label"] == "Americas (US) - PvP - Horde"
    mine = [g["key"] for g in c.get("/api/groups").json() if g["mine"]]
    assert mine == ["mining"]

    assert c.post("/api/setup", json={"region": "kr", "realm": "roleplay-horde"}).status_code == 400


def test_install_addon_endpoint(client):
    c, tmp = client
    game = tmp / "_forever_"
    (game / "Interface" / "AddOns").mkdir(parents=True)
    r = c.post("/api/setup/install-addon", json={"game_dir": str(game)})
    assert r.status_code == 200
    assert (game / "Interface" / "AddOns" / "SimsarExport" / "SimsarExport.lua").exists()
    assert c.post("/api/setup/install-addon", json={"game_dir": str(tmp / "nope")}).status_code == 400


def test_rate_limit_respects_retry_after(monkeypatch):
    calls, sleeps = [], []

    class R:
        def __init__(self, status, headers=None):
            self.status_code, self.headers, self.content = status, headers or {}, b"itemId\n"

    responses = [R(429, {"Retry-After": "3"}), R(200)]

    class S:
        def get(self, url, headers, timeout):
            calls.append(url)
            return responses.pop(0)

    monkeypatch.setattr(tsm.time, "sleep", sleeps.append)
    status, _, _ = tsm.download("http://x", 5, session=S())
    assert status == 200 and sleeps == [3.0]
