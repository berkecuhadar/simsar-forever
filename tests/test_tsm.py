import pytest

from simsar import db, tsm

REALM = (
    "itemId,name,marketValue,minBuyout,recent,historical,updatedAt\n"
    "2318,Light Leather,120,100,110,130,2026-11-11T15:25:24Z\n"
    '4234,"Heavy Leather, Cured",900,,850,1000,2026-11-11T15:25:24Z\n'
)
REGION = (
    "﻿itemId,name,marketValue,historical,avgSalePrice,saleRate,soldPerDay,updatedAt\n"
    "2318,Light Leather,125,128,118,0.42,150.5,2026-11-11T00:20:19Z\n"
)


class FakeResponse:
    def __init__(self, status, text="", etag=None):
        self.status_code = status
        self.content = text.encode("utf-8")
        self.headers = {"ETag": etag} if etag else {}


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, headers, timeout):
        self.calls.append((url, headers))
        return self.responses[url].pop(0)


def test_parse_realm_handles_quotes_and_blanks():
    rows, names, ts = tsm.parse("realm", REALM)
    assert names[4234] == "Heavy Leather, Cured"
    assert rows[1] == (4234, ts, 900, None, 850, 1000)
    assert ts == tsm.iso_to_ts("2026-11-11T15:25:24Z")


def test_parse_region_with_bom():
    rows, names, _ = tsm.parse("region", REGION)
    assert rows[0][2:] == (125, 128, 118, 0.42, 150.5)
    assert names == {2318: "Light Leather"}


@pytest.mark.parametrize("text, msg", [
    ("", "empty"),
    ("itemId,name\n1,x\n", "missing"),
    ("itemId,name,marketValue,minBuyout,recent,historical,updatedAt\n", "no rows"),
])
def test_parse_rejects_bad_files(text, msg):
    with pytest.raises(tsm.TsmError, match=msg):
        tsm.parse("realm", text)


def _cfg():
    return {"tsm": {"game_type": "forever", "region": "eu", "realm": "normal-alliance", "timeout_seconds": 5}}


def test_fetch_stores_once_and_skips_same_scan():
    conn = db.connect(":memory:")
    urls = tsm.urls(_cfg())
    session = FakeSession({
        urls["region"]: [FakeResponse(200, REGION), FakeResponse(200, REGION)],
        urls["realm"]: [FakeResponse(200, REALM, etag='"abc"'), FakeResponse(304)],
    })
    first = {r["source"]: r for r in tsm.fetch(_cfg(), conn, session=session)}
    assert first["tsm_realm"]["new_rows"] == 2
    assert first["tsm_region"]["new_rows"] == 1

    second = {r["source"]: r for r in tsm.fetch(_cfg(), conn, session=session)}
    assert second["tsm_region"]["unchanged"] and second["tsm_realm"]["unchanged"]
    assert session.calls[-1][1]["If-None-Match"] == '"abc"'
    assert conn.execute("SELECT COUNT(*) FROM tsm_realm").fetchone()[0] == 2
    assert conn.execute("SELECT name FROM items WHERE item_id = 4234").fetchone()[0] == "Heavy Leather, Cured"


def test_fetch_reports_missing_file():
    conn = db.connect(":memory:")
    urls = tsm.urls(_cfg())
    session = FakeSession({urls["region"]: [FakeResponse(200, REGION)], urls["realm"]: [FakeResponse(404)]})
    reports = {r["source"]: r for r in tsm.fetch(_cfg(), conn, session=session)}
    assert not reports["tsm_realm"]["ok"]
    assert "HTTP 404" in reports["tsm_realm"]["error"]
    assert reports["tsm_region"]["ok"]


def test_region_only_mode():
    cfg = _cfg()
    cfg["tsm"]["realm"] = None
    assert list(tsm.urls(cfg)) == ["region"]
