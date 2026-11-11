import math
import random

import pytest

from simsar_forever.analysis import econometrics as em

H3 = 3 * 3600


def ou_series(n, phi, mean=1000, sigma=0.03, seed=1, start=1_800_000_000):
    rnd = random.Random(seed)
    y, out = math.log(mean) + 0.3, []
    for i in range(n):
        y = math.log(mean) + phi * (y - math.log(mean)) + rnd.gauss(0, sigma)
        out.append((start + i * H3, math.exp(y)))
    return out


def test_mean_reversion_recovers_half_life():
    pts = ou_series(400, phi=0.8)
    r = em.mean_reversion(pts)
    expected = math.log(0.5) / math.log(0.8) * 3 / 24     # about 0.39 days
    assert r["ok"] and r["half_life_days"] == pytest.approx(expected, rel=0.35)
    assert r["equilibrium"] == pytest.approx(1000, rel=0.05)
    assert r["verdict"] == "strong"


def test_random_walk_is_not_called_mean_reverting():
    rnd = random.Random(3)
    y, pts = 0.0, []
    for i in range(300):
        y += rnd.gauss(0.002, 0.03)
        pts.append((i * H3, 1000 * math.exp(y)))
    assert em.mean_reversion(pts)["verdict"] in ("none", "weak")


def test_mean_reversion_needs_data():
    assert em.mean_reversion(ou_series(5, 0.8)) == {"ok": False, "needs": "11 more price scans"}


def test_forecast_follows_trend_with_interval():
    pts = [(d * 86400 + 3600, 1000 * 1.03 ** d * (1 + 0.01 * (-1) ** d)) for d in range(20)]
    f = em.forecast(pts, horizon=3)
    assert f["ok"] and len(f["points"]) == 3
    first = f["points"][0]
    assert first["low"] < first["mean"] < first["high"]
    assert f["change"] > 0


def test_forecast_needs_a_week():
    assert not em.forecast([(d * 86400, 100) for d in range(3)])["ok"]


def test_elasticity_recovers_slope():
    rnd = random.Random(5)
    rows = []
    for _ in range(40):
        p = math.exp(rnd.uniform(math.log(500), math.log(2000)))
        rows.append({"avg_sale": p, "sold_per_day": 5e5 * p ** -1.5 * math.exp(rnd.gauss(0, 0.05))})
    e = em.elasticity(rows)
    assert e["ok"] and e["elasticity"] == pytest.approx(-1.5, abs=0.1) and e["clear"]


def test_timing_finds_cheap_hours():
    import time
    pts = []
    for d in range(10):
        for h in range(0, 24, 3):
            t = 1_800_000_000 + d * 86400 + h * 3600
            pts.append((t, 900 if time.localtime(t).tm_hour < 6 else 1000))
    r = em.timing(pts)
    assert r["ok"] and r["hours"]["cheapest"].startswith(("00", "03")) and r["hours"]["significant"]
    assert r["weekdays"] is None      # needs two weeks
