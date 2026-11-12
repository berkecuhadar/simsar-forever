"""Price forecasts for the sell advice, and how good they have been.

Model (one for all items, refitted every day on the data available that day):

    y[i, t]   = log of item i's median cheapest listing on day t
    gap[i, t] = y[i, t] - median(y[i, t-13 .. t])            how far today is from the item's 2-week level
    y[i, t+H] - y[i, t] = a_H + b_H * gap[i, t] + e           pooled least squares over every item and day

b_H < 0 means gaps close (mean reversion); a_H is the market-wide drift (prices on a young server
tend to sink). Both are shrunk towards zero by their t statistic, so a coefficient the data cannot
tell from zero has little effect. The errors are divided by each item's own daily volatility, and
their observed distribution (not a normal curve) gives the 80% range and the chance of a rise.

Accuracy is measured by rolling-origin backtesting: for every past day the model is fitted only on
what was known that day, and its forecasts are compared with what then happened. The yardstick is
"no change" (tomorrow's price = today's), which is hard to beat on markets. The sell advice only
says "hold" when the backtest shows the model beating that yardstick, with statistical evidence.
"""

import math
import time
from collections import defaultdict

import numpy as np
from scipy import stats as sps

HORIZONS = (1, 3, 7)
WINDOW = 14                 # days in the reference level
MIN_WINDOW_OBS = 3          # prices needed in the window
FIT_DAYS = 30               # pairs from this many most recent days fit the model
HISTORY_DAYS = 120
MIN_PAIRS = 60              # pairs needed to fit
MIN_EVAL = 30               # forecasts needed before accuracy is shown
MIN_ORIGINS = 3             # forecast days needed for the significance test
SIGNIFICANCE = 0.05

_cache = {}


def _key(conn):
    r = conn.execute("SELECT MAX(updated_at), COUNT(*) FROM tsm_realm").fetchone()
    a = conn.execute("SELECT MAX(day_ts), COUNT(*) FROM ato_daily").fetchone()
    return tuple(r) + tuple(a)


def daily_matrix(conn, now=None, days=HISTORY_DAYS):
    """Items x days matrix of log daily median prices (NaN where unknown)."""
    now = now or time.time()
    since = now - days * 86400
    obs = defaultdict(list)
    for item_id, ts, price in conn.execute(
            "SELECT item_id, updated_at, min_buyout FROM tsm_realm WHERE updated_at >= ? AND min_buyout > 0",
            (since,)):
        obs[(item_id, int(ts // 86400))].append(price)
    for item_id, ts, price in conn.execute(
            "SELECT item_id, day_ts, low FROM ato_daily WHERE day_ts >= ? AND low > 0", (since,)):
        obs[(item_id, int(ts // 86400))].append(price)
    if not obs:
        return {"days": [], "items": [], "index": {}, "Y": np.empty((0, 0))}
    day_list = sorted({d for _, d in obs})
    first, last = day_list[0], day_list[-1]
    days_all = list(range(first, last + 1))
    items = sorted({i for i, _ in obs})
    index = {item: n for n, item in enumerate(items)}
    Y = np.full((len(items), len(days_all)), np.nan)
    for (item, d), prices in obs.items():
        Y[index[item], d - first] = math.log(float(np.median(prices)))
    return {"days": days_all, "items": items, "index": index, "Y": Y}


def gaps(Y):
    """gap[i, t] = y[i, t] - median of the item's last WINDOW days (needs MIN_WINDOW_OBS of them)."""
    G = np.full_like(Y, np.nan)
    for t in range(Y.shape[1]):
        win = Y[:, max(0, t - WINDOW + 1):t + 1]
        enough = np.sum(np.isfinite(win), axis=1) >= MIN_WINDOW_OBS
        with np.errstate(all="ignore"), _quiet():
            level = np.nanmedian(win, axis=1)
        G[:, t] = np.where(enough & np.isfinite(Y[:, t]), Y[:, t] - level, np.nan)
    return G


class _quiet:
    def __enter__(self):
        import warnings
        self._w = warnings.catch_warnings()
        self._w.__enter__()
        warnings.simplefilter("ignore", RuntimeWarning)

    def __exit__(self, *exc):
        return self._w.__exit__(*exc)


def changes(Y, H):
    D = np.full_like(Y, np.nan)
    if Y.shape[1] > H:
        D[:, :-H] = Y[:, H:] - Y[:, :-H]
    return D


def volatility(Y, until):
    """Each item's robust daily volatility of log price, from data up to day `until` (inclusive)."""
    d1 = Y[:, 1:until + 1] - Y[:, :until]
    with _quiet():
        med = np.nanmedian(d1, axis=1, keepdims=True)
        sigma = 1.4826 * np.nanmedian(np.abs(d1 - med), axis=1)
    counts = np.sum(np.isfinite(d1), axis=1)
    pooled = np.nanmedian(sigma[(counts >= 3) & (sigma > 0)]) if np.any((counts >= 3) & (sigma > 0)) else 0.1
    sigma = np.where((counts >= 3) & (sigma > 0), sigma, pooled)
    return np.maximum(sigma, 0.01)


def _shrink(coef, se):
    if not se or not math.isfinite(se) or se <= 0:
        return 0.0
    t = coef / se
    return coef * max(0.0, 1 - 1 / (t * t)) if abs(t) > 1 else 0.0


def fit(G, D, sigma, until, H):
    """Fit a_H, b_H on pairs whose outcome is known by day `until`."""
    hi = until - H + 1                        # last usable start day is until - H
    lo = max(0, hi - FIT_DAYS)
    if hi <= lo:
        return None
    x, y = G[:, lo:hi], D[:, lo:hi]
    s = np.broadcast_to(sigma[:, None], x.shape)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < MIN_PAIRS:
        return None
    x, y, s = x[ok], y[ok], s[ok]
    # Clip the 1% tails so a handful of absurd listings cannot steer the fit.
    x = np.clip(x, *np.percentile(x, [1, 99]))
    y = np.clip(y, *np.percentile(y, [1, 99]))
    X = np.column_stack([np.ones_like(x), x])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    n = len(y)
    dof = max(n - 2, 1)
    try:
        cov = np.linalg.inv(X.T @ X) * float(resid @ resid) / dof
        se = np.sqrt(np.diag(cov))
    except np.linalg.LinAlgError:
        se = np.array([np.inf, np.inf])
    a, b = _shrink(float(coef[0]), float(se[0])), _shrink(float(coef[1]), float(se[1]))
    z = np.sort((y - a - b * x) / (s * math.sqrt(H)))
    return {"H": H, "a": a, "b": b, "a_raw": float(coef[0]), "b_raw": float(coef[1]),
            "b_t": float(coef[1] / se[1]) if se[1] > 0 else None, "n": int(n), "z": z}


def predict(model, g, sigma):
    """Expected log change, 80% range and chance of a rise, for arrays of gaps and volatilities."""
    m = model["a"] + model["b"] * g
    scale = sigma * math.sqrt(model["H"])
    z = model["z"]
    q10, q90 = np.percentile(z, [10, 90])
    # P(change > 0) = P(z > -m / scale), read off the observed errors
    p_up = 1 - np.searchsorted(z, -m / scale, side="right") / len(z)
    return m, m + q10 * scale, m + q90 * scale, p_up


MIN_CALIBRATION = 100       # past forecasts needed before the chance of a rise is corrected


def calibrator(p_raw, rose):
    """Map the model's chance of a rise to how often prices really rose, from past forecasts.

    Forecasts are sorted by their raw chance and grouped in tens; pool-adjacent-violators makes the
    observed rates non-decreasing (isotonic regression), and new values are interpolated between
    the groups. Returns None while there are too few past forecasts."""
    if len(p_raw) < MIN_CALIBRATION:
        return None
    order = np.argsort(p_raw)
    p, y = np.asarray(p_raw)[order], np.asarray(rose, dtype=float)[order]
    groups = max(5, min(20, len(p) // 50))
    xs = [float(c.mean()) for c in np.array_split(p, groups)]
    blocks = [[float(c.mean()), len(c)] for c in np.array_split(y, groups)]
    # pool adjacent violators
    merged = []
    for x, (v, n) in zip(xs, blocks):
        merged.append([x * n, v * n, n])
        while len(merged) > 1 and merged[-2][1] / merged[-2][2] > merged[-1][1] / merged[-1][2]:
            x2, v2, n2 = merged.pop()
            merged[-1][0] += x2
            merged[-1][1] += v2
            merged[-1][2] += n2
    gx = np.array([m[0] / m[2] for m in merged])
    gy = np.array([m[1] / m[2] for m in merged])
    return lambda q: np.interp(q, gx, gy)


def backtest(G, D_by_h, Y, advice_cfg):
    out, calibrators = {}, {}
    T = Y.shape[1]
    for H in HORIZONS:
        D = D_by_h[H]
        rows = defaultdict(list)
        origins = []
        for o in range(H, T - H):
            sigma = volatility(Y, o)
            model = fit(G, D, sigma, o, H)
            if model is None:
                continue
            g, actual = G[:, o], D[:, o]
            ok = np.isfinite(g) & np.isfinite(actual)
            if not ok.any():
                continue
            m, lo, hi, p_up = predict(model, g[ok], sigma[ok])
            # Correct the chance of a rise with forecasts whose outcome was known by day o.
            cal = None
            if origins:
                mask = np.concatenate(rows["o"]) + H <= o
                cal = calibrator(np.concatenate(rows["p_raw"])[mask], np.concatenate(rows["a"])[mask] > 0)
            origins.append(o)
            rows["o"].append(np.full(ok.sum(), o))
            for k, v in (("a", actual[ok]), ("m", m), ("lo", lo), ("hi", hi), ("p_raw", p_up),
                         ("p", cal(p_up) if cal else p_up)):
                rows[k].append(v)
        r = {k: np.concatenate(v) for k, v in rows.items()} if origins else None
        out[H] = summarise(r, origins, advice_cfg, H)
        calibrators[H] = calibrator(r["p_raw"], r["a"] > 0) if r is not None else None
    return out, calibrators


def summarise(r, origins, advice_cfg, H):
    n = 0 if r is None else len(r["a"])
    base = {"horizon": H, "n": n, "days": len(origins)}
    if n < MIN_EVAL:
        return {**base, "ok": False, "needs": f"{MIN_EVAL - n} more forecasts with a known outcome"
                if n else f"more price history (about {WINDOW // 2 + H + 2} days)"}
    a, m = r["a"], r["m"]
    err_model, err_naive = np.abs(a - m), np.abs(a)
    mae_m, mae_n = float(err_model.mean()), float(err_naive.mean())
    # Significance: average improvement per forecast day, t-tested across days (forecasts made on the
    # same day share market moves, so they are not independent).
    per_day = [float((err_naive[r["o"] == o] - err_model[r["o"] == o]).mean()) for o in origins]
    p_value = None
    if len(per_day) >= MIN_ORIGINS and np.std(per_day, ddof=1) > 0:
        t = np.mean(per_day) / (np.std(per_day, ddof=1) / math.sqrt(len(per_day)))
        p_value = float(1 - sps.t.cdf(t, df=len(per_day) - 1))
    elif len(per_day) >= MIN_ORIGINS:
        p_value = 0.0 if np.mean(per_day) > 0 else 1.0
    moved = np.abs(m) > 0.01
    gain = np.expm1(m)
    hold = (gain >= advice_cfg["hold_min_gain"]) & (r["p"] >= advice_cfg["hold_min_probability"])
    calib = []
    for lo_p, hi_p in ((0, 0.3), (0.3, 0.45), (0.45, 0.55), (0.55, 0.7), (0.7, 1.01)):
        sel = (r["p"] >= lo_p) & (r["p"] < hi_p)
        if sel.sum() >= 5:
            calib.append({"from": lo_p, "to": min(hi_p, 1), "n": int(sel.sum()), "predicted": float(r["p"][sel].mean()),
                          "observed": float((a[sel] > 0).mean())})
    skill = 1 - mae_m / mae_n if mae_n > 0 else 0.0
    return {
        **base, "ok": True,
        "mae_model": mae_m, "mae_naive": mae_n, "skill": skill,
        "median_error_model": float(np.median(err_model)), "median_error_naive": float(np.median(err_naive)),
        "p_value": p_value,
        "beats_naive": bool(skill > 0 and p_value is not None and p_value < SIGNIFICANCE),
        "coverage": float(((a >= r["lo"]) & (a <= r["hi"])).mean()),
        "direction": float((np.sign(a[moved]) == np.sign(m[moved])).mean()) if moved.sum() >= 10 else None,
        "direction_n": int(moved.sum()),
        "calibration": calib,
        "hold": {"n": int(hold.sum()),
                 "hit": float((a[hold] > 0).mean()) if hold.sum() else None,
                 "avg_change": float(np.expm1(a[hold]).mean()) if hold.sum() else None},
        "sell": {"n": int((~hold).sum()),
                 "avg_change": float(np.expm1(a[~hold]).mean()) if (~hold).sum() else None,
                 "rose_much": float((np.expm1(a[~hold]) > advice_cfg["hold_min_gain"]).mean()) if (~hold).sum() else None},
    }


def build(conn, cfg, now=None):
    """Today's forecast for every item with enough history, plus the backtest. Cached until prices change."""
    key = (_key(conn), tuple(sorted(cfg["advice"].items())))
    if _cache.get("key") == key and now is None:
        return _cache["value"]
    M = daily_matrix(conn, now)
    Y = M["Y"]
    value = {"items": {}, "models": {}, "backtest": {}, "last_day": None, "days": len(M["days"])}
    if Y.size:
        G = gaps(Y)
        D_by_h = {H: changes(Y, H) for H in HORIZONS}
        T = Y.shape[1] - 1
        sigma = volatility(Y, T)
        value["last_day"] = M["days"][T]
        value["backtest"], calibrators = backtest(G, D_by_h, Y, cfg["advice"])
        # Today's gap may be from an older day when today's scan has not arrived for this item.
        g = _latest_gap(G)
        ok = np.isfinite(g)
        for H in HORIZONS:
            model = fit(G, D_by_h[H], sigma, T, H)
            if model is None:
                continue
            value["models"][H] = {k: v for k, v in model.items() if k != "z"}
            value["models"][H]["calibrated"] = calibrators.get(H) is not None
            m, lo, hi, p_up = predict(model, g[ok], sigma[ok])
            if calibrators.get(H):
                p_up = calibrators[H](p_up)
            for n, idx in enumerate(np.flatnonzero(ok)):
                e = value["items"].setdefault(M["items"][idx], {"gap": float(g[idx]), "sigma": float(sigma[idx])})
                e[H] = {"change": float(np.expm1(m[n])), "low": float(np.expm1(lo[n])),
                        "high": float(np.expm1(hi[n])), "p_up": float(p_up[n])}
    _cache.update(key=key, value=value)
    return value


def _latest_gap(G, max_age=2):
    """Each item's most recent gap within the last `max_age` days."""
    g = np.full(G.shape[0], np.nan)
    for back in range(max_age + 1):
        col = G[:, G.shape[1] - 1 - back] if G.shape[1] > back else np.full(G.shape[0], np.nan)
        g = np.where(np.isfinite(g), g, col)
    return g


# Live tracking ---------------------------------------------------------------------------------

def record(conn, fc, advice, item_ids, today=None):
    """Store today's forecasts for these items once per day, then score any whose outcome is known."""
    day = fc.get("last_day")
    if day is None:
        return 0
    rows = []
    for item_id in item_ids:
        e = fc["items"].get(item_id)
        if not e:
            continue
        for H in HORIZONS:
            f = e.get(H)
            if f:
                rows.append((item_id, day, H, f["change"], f["low"], f["high"],
                             (advice.get(item_id) or {}).get("advice")))
    conn.executemany(
        "INSERT OR IGNORE INTO forecasts(item_id, made_day, horizon, predicted, low, high, advice) "
        "VALUES(?,?,?,?,?,?,?)", rows)
    conn.commit()
    return len(rows)


def score(conn, M=None):
    """Fill in the real change for stored forecasts whose target day has a price now."""
    M = M or daily_matrix(conn, days=HISTORY_DAYS)
    if not M["days"]:
        return 0
    first = M["days"][0]
    Y = M["Y"]
    todo = conn.execute("SELECT item_id, made_day, horizon FROM forecasts WHERE actual IS NULL").fetchall()
    done = []
    for item_id, made, H in todo:
        i = M["index"].get(item_id)
        t0, t1 = made - first, made + H - first
        if i is None or t0 < 0 or t1 >= Y.shape[1]:
            continue
        # The base is the last price known on the day the forecast was made.
        base = next((Y[i, t] for t in range(t0, max(t0 - 3, -1), -1) if np.isfinite(Y[i, t])), np.nan)
        if np.isfinite(base) and np.isfinite(Y[i, t1]):
            done.append((float(np.expm1(Y[i, t1] - base)), item_id, made, H))
    conn.executemany("UPDATE forecasts SET actual = ? WHERE item_id = ? AND made_day = ? AND horizon = ?", done)
    conn.commit()
    return len(done)


def live_summary(conn, advice_cfg):
    out = {}
    for H in HORIZONS:
        rows = conn.execute("SELECT made_day, predicted, low, high, actual, advice FROM forecasts "
                            "WHERE horizon = ? AND actual IS NOT NULL", (H,)).fetchall()
        pending = conn.execute("SELECT COUNT(*) FROM forecasts WHERE horizon = ? AND actual IS NULL", (H,)).fetchone()[0]
        n = len(rows)
        base = {"horizon": H, "n": n, "pending": pending}
        if n < MIN_EVAL:
            out[H] = {**base, "ok": False}
            continue
        a = np.log1p(np.array([r["actual"] for r in rows]))
        m = np.log1p(np.array([r["predicted"] for r in rows]))
        lo = np.log1p(np.array([r["low"] for r in rows]))
        hi = np.log1p(np.array([r["high"] for r in rows]))
        mae_m, mae_n = float(np.abs(a - m).mean()), float(np.abs(a).mean())
        holds = [r for r in rows if r["advice"] == "hold"]
        out[H] = {**base, "ok": True, "mae_model": mae_m, "mae_naive": mae_n,
                  "skill": 1 - mae_m / mae_n if mae_n else 0.0,
                  "coverage": float(((a >= lo) & (a <= hi)).mean()),
                  "days": len({r["made_day"] for r in rows}),
                  "hold": {"n": len(holds), "hit": (sum(r["actual"] > 0 for r in holds) / len(holds)) if holds else None,
                           "avg_change": (sum(r["actual"] for r in holds) / len(holds)) if holds else None}}
    return out
