"""Time-series statistics for one item: mean reversion, forecast, price elasticity and timing.

Each section reports `ok: False` with a `needs` message until there is enough data. All of them
describe the past; none of them is a promise about the future.
"""

import math
import time
import warnings
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy import stats as sps

MIN_POINTS_REVERSION = 16       # two days of 3-hourly TSM scans
MIN_DAYS_FORECAST = 7
MIN_POINTS_ELASTICITY = 10
MIN_DAYS_TIMING = 5
MIN_DAYS_WEEKDAY = 14
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _needs(msg):
    return {"ok": False, "needs": msg}


def mean_reversion(points):
    """AR(1) on log prices: dy = a + b * y[t-1]. With phi = 1 + b between 0 and 1 the price pulls back
    toward a level, and a gap halves every ln(0.5) / ln(phi) steps. ADF tests that pull for significance."""
    from statsmodels.tsa.stattools import adfuller

    points = sorted((t, p) for t, p in points if p and p > 0)
    if len(points) < MIN_POINTS_REVERSION:
        return _needs(f"{MIN_POINTS_REVERSION - len(points)} more price scans")
    t = np.array([x[0] for x in points], dtype=float)
    y = np.log([x[1] for x in points])
    if np.ptp(y) < 1e-9:
        return _needs("the price has not moved yet")
    step_h = float(np.median(np.diff(t))) / 3600
    dy, lag = np.diff(y), y[:-1]
    slope, intercept, *_ = sps.linregress(lag, dy)
    phi = 1 + slope
    out = {"ok": True, "n": len(y), "step_hours": step_h, "phi": phi, "half_life_days": None,
           "equilibrium": None}
    if 0 < phi < 1:
        out["half_life_days"] = math.log(0.5) / math.log(phi) * step_h / 24
        out["equilibrium"] = float(math.exp(-intercept / slope))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            out["adf_p"] = float(adfuller(y, maxlag=min(4, len(y) // 5), autolag="AIC")[1])
        except (ValueError, np.linalg.LinAlgError):
            out["adf_p"] = None
    p = out["adf_p"]
    out["verdict"] = ("strong" if p is not None and p < 0.05 and out["half_life_days"]
                      else "weak" if p is not None and p < 0.15 and out["half_life_days"]
                      else "none")
    return out


def _daily_medians(points):
    by_day = defaultdict(list)
    for t, p in points:
        if p and p > 0:
            by_day[int(t // 86400)].append(p)
    days = sorted(by_day)
    return days, [float(np.median(by_day[d])) for d in days]


def forecast(points, horizon=3):
    """Damped-trend exponential smoothing (ETS A,Ad,N) on log daily medians, with an 80% interval."""
    from statsmodels.tsa.exponential_smoothing.ets import ETSModel

    days, prices = _daily_medians(points)
    if len(days) < MIN_DAYS_FORECAST:
        return _needs(f"{MIN_DAYS_FORECAST - len(days)} more days of prices")
    # Fill missing days by carrying the last price forward so the series is evenly spaced.
    full = list(range(days[0], days[-1] + 1))
    lookup = dict(zip(days, prices))
    series, last = [], prices[0]
    for d in full:
        last = lookup.get(d, last)
        series.append(math.log(last))
    y = np.array(series)
    if np.ptp(y) < 1e-9:
        return {"ok": True, "flat": True, "points": [
            {"t": (full[-1] + i) * 86400, "mean": prices[-1], "low": prices[-1], "high": prices[-1]}
            for i in range(1, horizon + 1)]}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            # statsmodels needs a pandas Series here; plain arrays break get_prediction in 0.15.
            fit = ETSModel(pd.Series(y), error="add", trend="add", damped_trend=True).fit(disp=False)
            frame = fit.get_prediction(start=len(y), end=len(y) + horizon - 1).summary_frame(alpha=0.2)
        except Exception as e:  # statsmodels raises a variety of numerical errors on short series
            return {"ok": False, "needs": f"the model did not converge ({type(e).__name__})"}
    rows = []
    for i, (_, r) in enumerate(frame.iterrows(), 1):
        rows.append({"t": (full[-1] + i) * 86400 + 43200, "mean": math.exp(r["mean"]),
                     "low": math.exp(r["pi_lower"]), "high": math.exp(r["pi_upper"])})
    change = rows[-1]["mean"] / prices[-1] - 1
    return {"ok": True, "points": rows, "last": prices[-1], "change": change, "days_used": len(full)}


def elasticity(region_rows):
    """Log-log regression of daily units sold on the average sale price across region snapshots."""
    import statsmodels.api as sm

    pts = [(r["avg_sale"], r["sold_per_day"]) for r in region_rows
           if (r.get("avg_sale") or 0) > 0 and (r.get("sold_per_day") or 0) > 0]
    if len(pts) < MIN_POINTS_ELASTICITY:
        return _needs(f"{MIN_POINTS_ELASTICITY - len(pts)} more days of region sales data")
    x = np.log([p for p, _ in pts])
    y = np.log([q for _, q in pts])
    if np.std(x) < 0.02:
        return _needs("more price variation (the price has barely moved)")
    model = sm.OLS(y, sm.add_constant(x)).fit()
    lo, hi = model.conf_int(alpha=0.1)[1]
    beta = float(model.params[1])
    return {"ok": True, "elasticity": beta, "ci_low": float(lo), "ci_high": float(hi),
            "p": float(model.pvalues[1]), "r2": float(model.rsquared), "n": len(pts),
            "clear": not (lo <= 0 <= hi)}


def timing(points, now=None):
    """Which local hour block and weekday tend to be cheapest, relative to that day's median.
    Kruskal-Wallis checks whether the differences are larger than chance."""
    pts = [(t, p) for t, p in points if p and p > 0]
    days, med = _daily_medians(pts)
    if len(days) < MIN_DAYS_TIMING:
        return _needs(f"{MIN_DAYS_TIMING - len(days)} more days of scans")
    day_med = dict(zip(days, med))
    hours, weekdays = defaultdict(list), defaultdict(list)
    for t, p in pts:
        rel = p / day_med[int(t // 86400)] - 1
        lt = time.localtime(t)
        hours[lt.tm_hour // 3 * 3].append(rel)
        weekdays[lt.tm_wday].append(rel)

    def summarise(groups, label, min_groups):
        groups = {k: v for k, v in groups.items() if len(v) >= 3}
        if len(groups) < min_groups:
            return None
        try:
            p = float(sps.kruskal(*groups.values()).pvalue)
        except ValueError:
            p = None
        medians = {k: float(np.median(v)) for k, v in groups.items()}
        cheap = min(medians, key=medians.get)
        dear = max(medians, key=medians.get)
        return {"cheapest": label(cheap), "cheapest_gap": medians[cheap], "dearest": label(dear),
                "dearest_gap": medians[dear], "p": p, "significant": p is not None and p < 0.05,
                "profile": [{"key": label(k), "median": medians[k], "n": len(groups[k])} for k in sorted(groups)]}

    out = {"ok": True, "hours": summarise(hours, lambda h: f"{h:02d}:00-{h + 3:02d}:00", 3)}
    out["weekdays"] = summarise(weekdays, lambda d: WEEKDAYS[d], 4) if len(days) >= MIN_DAYS_WEEKDAY else None
    return out


def _finite(value):
    if isinstance(value, dict):
        return {k: _finite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_finite(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def analyse(history):
    realm = [(r["t"], r["min_buyout"]) for r in history["realm"]]
    combined = realm + [(r["t"] + 43200, r["low"]) for r in history["auctionator"]]
    return _finite({
        "mean_reversion": mean_reversion(realm),
        "forecast": forecast(combined),
        "elasticity": elasticity(history["region"]),
        "timing": timing(realm),
    })
