"""The one spike rule (``PLAN.md`` §6): a Poisson 99.9 % upper limit.

A week alerts when its count is at least 3 **and** above the 99.9 % upper limit of a
Poisson distribution whose mean is the previous 26 weeks' average, with that mean
floored at 0.5. The limit is the smallest integer ``k`` with ``P(X <= k) >= 0.999``,
so "above the limit" means ``count > k``.

The CDF is computed directly from the Poisson pmf (no SciPy dependency, no random
numbers), with a mode-centred upper tail so large means do not underflow. Every input
is a plain number or count, so the rule is exactly reproducible.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Final

from field_return_triage.contracts import TrendAlert
from field_return_triage.trend.series import SeriesMap, series_sort_key, week_grid

__all__ = [
    "MEAN_FLOOR",
    "MIN_COUNT",
    "QUANTILE",
    "TRAILING_WEEKS",
    "detect_alerts",
    "is_spike",
    "poisson_upper_limit",
    "trailing_mean",
]

#: The trailing window, in weeks (``PLAN.md`` §6).
TRAILING_WEEKS: Final = 26
#: A week below this count never alerts, whatever the limit says.
MIN_COUNT: Final = 3
#: The trailing mean is floored here so a quiet series still needs a real spike.
MEAN_FLOOR: Final = 0.5
#: The upper-limit quantile (99.9 %).
QUANTILE: Final = 0.999


def _poisson_cdf(mean: float, k: int) -> float:
    """``P(X <= k)`` for ``X ~ Poisson(mean)``, accurate in both tails."""
    if k < 0:
        return 0.0
    if mean <= 0.0:
        return 1.0
    if k < mean:
        term = math.exp(-mean)
        total = term
        for i in range(1, k + 1):
            term *= mean / i
            total += term
        return min(1.0, total)
    # Start at the requested point and sum the upper tail; the pmf is computed in
    # log space so ``exp(-mean)`` cannot underflow for a large mean.
    term = math.exp(-mean + k * math.log(mean) - math.lgamma(k + 1))
    tail = 0.0
    j = k
    while True:
        j += 1
        term *= mean / j
        tail += term
        if term < 1e-18 or j - k > 20_000:
            break
    return max(0.0, min(1.0, 1.0 - tail))


def poisson_upper_limit(mean: float, quantile: float = QUANTILE) -> int:
    """The smallest ``k`` with ``P(X <= k) >= quantile`` for ``X ~ Poisson(mean)``."""
    if mean < 0.0:
        raise ValueError("mean must be >= 0")
    if not 0.0 < quantile < 1.0:
        raise ValueError("quantile must be in (0, 1)")
    if mean == 0.0:
        return 0
    low = 0
    high = int(mean + 12.0 * math.sqrt(mean + 1.0) + 30)
    while _poisson_cdf(mean, high) < quantile:
        high *= 2
    while low < high:
        middle = (low + high) // 2
        if _poisson_cdf(mean, middle) >= quantile:
            high = middle
        else:
            low = middle + 1
    return low


def trailing_mean(window: Sequence[int]) -> float:
    """The 26-week mean, floored at 0.5. The window must hold exactly 26 weeks."""
    if len(window) != TRAILING_WEEKS:
        raise ValueError(f"the trailing window must hold {TRAILING_WEEKS} weeks")
    return max(MEAN_FLOOR, math.fsum(window) / TRAILING_WEEKS)


def is_spike(count: int, mean: float) -> bool:
    """Whether a count clears both the minimum and the Poisson upper limit."""
    return count >= MIN_COUNT and count > poisson_upper_limit(mean)


def detect_alerts(series: SeriesMap) -> list[TrendAlert]:
    """Apply the rule to every series, in series-then-week order.

    A series needs a full 26-week history before its first week can alert; missing
    weeks inside the grid count as zero. The first 26 weeks of a series are therefore
    never alerts, which keeps the rule honest on a young series.
    """
    alerts: list[TrendAlert] = []
    for key in sorted(series, key=series_sort_key):
        grid = week_grid(series[key])
        for index in range(TRAILING_WEEKS, len(grid)):
            week, count = grid[index]
            if count < MIN_COUNT:
                continue
            mean = round(
                trailing_mean([value for _, value in grid[index - TRAILING_WEEKS : index]]), 6
            )
            threshold = poisson_upper_limit(mean)
            if count > threshold:
                alerts.append(
                    TrendAlert(
                        series=key,
                        week=week,
                        count=count,
                        trailing_mean=mean,
                        threshold=float(threshold),
                    )
                )
    return alerts
