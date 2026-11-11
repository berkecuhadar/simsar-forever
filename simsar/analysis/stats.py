"""Robust statistics. A single absurd listing should not move any of these much."""

import math
import statistics
from itertools import combinations

MAD_TO_SIGMA = 1.4826


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def mad(values):
    m = median(values)
    if m is None:
        return None
    return statistics.median(abs(v - m) for v in values)


def robust_cv(values):
    """Spread relative to the typical price: 1.4826 * MAD / median.
    Matches the ordinary coefficient of variation for normally distributed prices."""
    m = median(values)
    if not m:
        return None
    return MAD_TO_SIGMA * mad(values) / m


def theil_sen_slope(xs, ys):
    """Median of pairwise slopes. Ignores up to ~29% of wild points."""
    slopes = [(y2 - y1) / (x2 - x1) for (x1, y1), (x2, y2) in combinations(zip(xs, ys), 2) if x2 != x1]
    return statistics.median(slopes) if slopes else None


def daily_trend(days, prices):
    """Percent change per day, fitted on log prices so up and down moves weigh the same."""
    pairs = [(d, math.log(p)) for d, p in zip(days, prices) if p and p > 0]
    if len(pairs) < 2:
        return None
    slope = theil_sen_slope([d for d, _ in pairs], [y for _, y in pairs])
    return None if slope is None else math.expm1(slope)


def percentile_rank(values, x):
    """Share of values at or below x (0..1)."""
    if not values or x is None:
        return None
    return sum(v <= x for v in values) / len(values)
