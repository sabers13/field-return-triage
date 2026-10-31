"""Trend watch and recall backtest (``PLAN.md`` §6, no AI).

The lane reads the committed weekly table and recall table, applies one deterministic
spike rule to every series and backtests the alerts against recalls for the same
make + model + model year + group. It imports ``contracts`` only; the data lane's
loaders are not used, because lanes never import each other.

Public surface:

``load_weekly`` / ``load_recalls``
    Read the two committed CSV files into contract rows.
``group_weeks`` / ``week_grid``
    Turn rows into continuous Monday grids, with missing weeks counted as zero.
``detect_alerts``
    Apply the count ≥ 3 and Poisson 99.9 % rule over a 26-week trailing mean.
``run_backtest``
    Join alerts to recalls, draw the seeded base rate and collect the report.
``pick_example_series``
    Choose the one series the page chart shows.
"""

from __future__ import annotations

from field_return_triage.trend.backtest import (
    BASE_RATE_SEED,
    MAX_LEAD_DAYS,
    Backtest,
    pick_example_series,
    run_backtest,
    wilson_interval,
)
from field_return_triage.trend.series import (
    SeriesMap,
    group_weeks,
    load_recalls,
    load_weekly,
    series_total,
    week_grid,
)
from field_return_triage.trend.spike import (
    MEAN_FLOOR,
    MIN_COUNT,
    QUANTILE,
    TRAILING_WEEKS,
    detect_alerts,
    poisson_upper_limit,
    trailing_mean,
)

__all__ = [
    "BASE_RATE_SEED",
    "MAX_LEAD_DAYS",
    "MEAN_FLOOR",
    "MIN_COUNT",
    "QUANTILE",
    "TRAILING_WEEKS",
    "Backtest",
    "SeriesMap",
    "detect_alerts",
    "group_weeks",
    "load_recalls",
    "load_weekly",
    "pick_example_series",
    "poisson_upper_limit",
    "run_backtest",
    "series_total",
    "trailing_mean",
    "week_grid",
    "wilson_interval",
]
