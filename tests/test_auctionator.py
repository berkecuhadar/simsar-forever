from pathlib import Path

import pytest

from simsar_forever import auctionator, db
from tests.wowfiles import auctionator_file

FIXTURE = Path(__file__).parent / "fixtures" / "Auctionator.lua"
CFG = {"wow": {"auctionator_realm": None}}


def test_scan_day_zero_matches_known_day():
    # Day 2503 holds data from the full scan on 2026-11-08 (local time).
    import time
    assert time.strftime("%Y-%m-%d", time.localtime(auctionator.day_to_ts(2503))) == "2026-11-08"
    assert auctionator.ts_to_day(auctionator.day_to_ts(2503) + 3600) == 2503


def test_real_fixture_imports():
    conn = db.connect(":memory:")
    rep = auctionator.import_file(conn, FIXTURE, CFG)
    assert rep["realm"] == "PvE"
    assert rep["db_version"] == 8
    assert rep["items"] == 6
    assert rep["unknown_fields"] == []
    assert rep["postings"] == 2
    assert rep["vendor_prices"] == 3
    row = conn.execute("SELECT low, high, available FROM ato_daily WHERE item_id = 1445 ORDER BY day_ts").fetchall()
    assert [tuple(r) for r in row] == [(900, 900, 34), (700, 700, 58)]


def test_low_defaults_to_high_and_gear_keys_fold(tmp_path):
    f = tmp_path / "Auctionator.lua"
    f.write_bytes(auctionator_file({"PvE": {
        "2318": {"m": 95, "h": {2505: 120, 2506: 100}, "l": {2506: 90}, "a": {2506: 40}},
        "g:15211:20": {"m": 2000, "h": {2506: 2100}, "l": {}, "a": {}},
        "p:39": {"m": 5, "h": {2506: 5}, "l": {}, "a": {}},
        "version": 2,
    }}))
    conn = db.connect(":memory:")
    rep = auctionator.import_file(conn, f, CFG)
    assert rep["items"] == 2 and rep["skipped_keys"] == 1
    lows = dict(conn.execute("SELECT day_ts, low FROM ato_daily WHERE item_id = 2318").fetchall())
    assert lows[auctionator.day_to_ts(2505)] == 120
    assert lows[auctionator.day_to_ts(2506)] == 90
    assert conn.execute("SELECT price FROM ato_current WHERE item_id = 15211").fetchone()[0] == 2000


def test_unknown_db_version_is_rejected(tmp_path):
    f = tmp_path / "Auctionator.lua"
    f.write_bytes(auctionator_file({"PvE": {"1": {"m": 1, "h": {1: 1}}}}, db_version=9))
    with pytest.raises(auctionator.AuctionatorFormatError, match="version 9"):
        auctionator.import_file(db.connect(":memory:"), f, CFG)


def test_unknown_fields_are_reported(tmp_path):
    f = tmp_path / "Auctionator.lua"
    f.write_bytes(auctionator_file({"PvE": {"1": {"m": 1, "h": {1: 1}, "q": {1: 3}}}}))
    rep = auctionator.import_file(db.connect(":memory:"), f, CFG)
    assert rep["unknown_fields"] == ["q"]


def test_deserialized_realm_table_is_accepted(tmp_path):
    f = tmp_path / "Auctionator.lua"
    f.write_text('AUCTIONATOR_PRICE_DATABASE = {\n["__dbversion"] = 8,\n["PvE"] = {\n["version"] = 2,\n'
                 '["2318"] = {["m"] = 50, ["h"] = {["2506"] = 50}, ["l"] = {}, ["a"] = {["2506"] = 7}},\n},\n}\n')
    rep = auctionator.import_file(db.connect(":memory:"), f, CFG)
    assert rep["items"] == 1 and rep["current_prices"] == 1


def test_inspect_describes_fixture():
    text = auctionator.inspect(FIXTURE)
    assert "realm 'PvE': CBOR string, 6 items" in text
    assert "__dbversion: 8" in text


def test_toc_reader(tmp_path):
    toc = tmp_path / "Auctionator.toc"
    toc.write_text("## Interface: 120100, 16001\n## Version: 345\n## Title: Auctionator\nSource\\Main.xml\n")
    assert auctionator.read_toc(toc)["Version"] == "345"
