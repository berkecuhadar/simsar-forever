"""Forecasts, their backtest and the sell advice built on them."""

import math

import numpy as np
import pytest

from simsar_forever import config, db
from simsar_forever.analysis import forecast, sellplan

DAY = 86400
START = 1793000000 // DAY * DAY


def cfg():
    return config.load("does-not-exist.yaml")


def panel(kind, items=120, days=40, seed=1):
    """Log prices: 'revert' pulls back to each item's level, 'walk' is a random walk."""
    rng = np.random.default_rng(seed)
    level = rng.uniform(4, 9, size=items)
    Y = np.empty((items, days))
    Y[:, 0] = level + rng.normal(0, 0.2, items)
    for t in range(1, days):
        shock = rng.normal(0, 0.08, items)
        Y[:, t] = Y[:, t - 1] + shock if kind == "walk" else level + 0.5 * (Y[:, t - 1] - level) + shock
    return Y


def run_backtest(Y):
    G = forecast.gaps(Y)
    D = {H: forecast.changes(Y, H) for H in forecast.HORIZONS}
    return forecast.backtest(G, D, Y, cfg()["advice"])[0]


def test_mean_reverting_market_is_forecast_better_than_no_change():
    bt = run_backtest(panel("revert"))
    for H in (1, 3):
        b = bt[H]
        assert b["ok"] and b["skill"] > 0.05 and b["beats_naive"], (H, b)
        assert 0.65 <= b["coverage"] <= 0.92                        # the 80% range is roughly right
        assert b["direction"] > 0.6


def test_random_walk_is_not_claimed_to_be_predictable():
    bt = run_backtest(panel("walk"))
    for H in (1, 3):
        assert not bt[H]["beats_naive"], bt[H]
        assert bt[H]["skill"] < 0.03


def test_too_little_history_says_what_it_needs():
    bt = run_backtest(panel("revert", days=6))
    assert not bt[3]["ok"] and "more" in bt[3]["needs"]


def test_fit_recovers_the_pull_back():
    Y = panel("revert", items=300, days=40)
    G = forecast.gaps(Y)
    model = forecast.fit(G, forecast.changes(Y, 1), forecast.volatility(Y, 39), 39, 1)
    # gaps against a 2-week median close at about half a day's distance per day here
    assert -0.75 < model["b"] < -0.3 and abs(model["a"]) < 0.02


def store(conn, Y, item0=1000):
    rows = []
    for i in range(Y.shape[0]):
        for t in range(Y.shape[1]):
            rows.append((item0 + i, START + t * DAY, round(math.exp(Y[i, t])), round(math.exp(Y[i, t])), 5))
    conn.executemany("INSERT INTO ato_daily VALUES(?,?,?,?,?)", rows)


def test_build_from_the_database_and_live_scoring():
    conn = db.connect(":memory:")
    Y = panel("revert", items=60, days=30)
    store(conn, Y[:, :25])
    now = START + 25 * DAY
    fc = forecast.build(conn, cfg(), now=now)
    assert fc["days"] == 25 and fc["items"][1000][3]["p_up"] is not None
    assert forecast.record(conn, fc, {}, [1000, 1001, 99999]) == 6          # 2 items x 3 horizons
    assert forecast.record(conn, fc, {}, [1000]) == 3                      # once per item and day: ignored
    assert conn.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0] == 6
    # Five more days arrive: the 1 and 3 day forecasts get their outcome, the 7 day one does not yet.
    conn.execute("DELETE FROM ato_daily")
    store(conn, Y)
    assert forecast.score(conn, forecast.daily_matrix(conn, now=START + 30 * DAY)) == 4
    actual = conn.execute("SELECT actual FROM forecasts WHERE item_id = 1000 AND horizon = 1").fetchone()[0]
    assert actual == pytest.approx(math.expm1(Y[0, 25] - Y[0, 24]), abs=0.01)


# Sell advice --------------------------------------------------------------------------------------

ITEM = {"item_id": 1, "net_sell": 1000, "vendor_sell": 100, "my_sales_per_day": 5}


def fc_item(change, p_up):
    return {3: {"change": change, "p_up": p_up, "low": change - 0.1, "high": change + 0.1}}


def test_advice_rules():
    c = cfg()
    assert sellplan.advise(ITEM, None, c, True)["advice"] == "sell"
    assert sellplan.advise({**ITEM, "vendor_sell": 1200}, None, c, True)["advice"] == "vendor"
    assert sellplan.advise({**ITEM, "net_sell": None}, None, c, True)["advice"] == "vendor"
    assert sellplan.advise(ITEM, fc_item(0.10, 0.8), c, True)["advice"] == "hold"
    assert sellplan.advise(ITEM, fc_item(0.10, 0.5), c, True)["advice"] == "sell"         # not likely enough
    assert sellplan.advise(ITEM, fc_item(0.02, 0.9), c, True)["advice"] == "sell"         # too small a gain
    # Without backtest evidence the forecast never turns into "hold".
    assert sellplan.advise(ITEM, fc_item(0.30, 0.95), c, False)["advice"] == "sell"
    assert sellplan.advise(ITEM, None, c, True, quantity=100)["advice"] == "gradual"      # 20 days of sales
    assert sellplan.advise(ITEM, None, c, True, quantity=10)["advice"] == "sell"
    assert sellplan.advise(ITEM, None, c, True, quantity=3, bound=3)["advice"] == "bound"
    assert sellplan.advise({**ITEM, "my_sales_per_day": None}, None, c, True)["advice"] is None


def test_hold_needs_a_backtest_that_beats_no_change():
    c = cfg()
    assert not sellplan.hold_allowed({"backtest": {}}, c)
    assert not sellplan.hold_allowed({"backtest": {3: {"ok": True, "beats_naive": False}}}, c)
    assert sellplan.hold_allowed({"backtest": {3: {"ok": True, "beats_naive": True}}}, c)


def test_chance_of_a_rise_is_corrected_by_past_outcomes():
    rng = np.random.default_rng(3)
    raw = rng.uniform(0, 1, 4000)
    rose = rng.uniform(0, 1, 4000) < 0.25 + 0.5 * raw       # the raw number overstates both ends
    cal = forecast.calibrator(raw, rose)
    assert cal(np.array([0.9]))[0] == pytest.approx(0.7, abs=0.06)
    assert cal(np.array([0.1]))[0] == pytest.approx(0.3, abs=0.06)
    assert np.all(np.diff(cal(np.linspace(0, 1, 50))) >= 0)                # never decreasing
    assert forecast.calibrator(raw[:50], rose[:50]) is None


def test_backtest_probabilities_are_calibrated_out_of_sample():
    bt = run_backtest(panel("revert", items=150, days=45))
    for c in bt[3]["calibration"]:
        assert abs(c["predicted"] - c["observed"]) < 0.15, c
