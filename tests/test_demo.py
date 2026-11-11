from simsar_forever import config, db, demo
from simsar_forever.analysis.engine import Engine


def test_demo_is_labelled_and_analysable():
    conn = db.connect(":memory:")
    demo.build(conn, now=1_800_000_000)
    assert db.get_meta(conn, "demo") is True
    names = [r[0] for r in conn.execute("SELECT name FROM items")]
    assert names and all(n.endswith("(demo)") for n in names)
    assert all(i >= demo.ID_BASE for (i,) in conn.execute("SELECT item_id FROM items"))

    cfg = config.load("does-not-exist.yaml")
    cfg["analysis"]["stale_hours"] = 10 ** 9
    result = Engine(cfg, conn).result()
    assert len(result["items"]) == len(demo.ITEMS)
    verdicts = {c["verdict"] for c in result["crafts"]}
    assert "no_product" in verdicts
    assert any(c["profit"] is not None for c in result["crafts"])
