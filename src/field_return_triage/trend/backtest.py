"""Recall backtest, base rate and the page's example series (``PLAN.md`` §6).

An alert "precedes a recall" when a recall with the same make + model + model year +
group has a report date from the alert week through 365 days after it. The base rate
is the same measure on randomly drawn weeks of the same series, with one draw per
alert and a fixed seed. The base rate is the headline comparison; the raw share is
never reported alone.

If fewer than 20 alerts precede any recall, the join is too weak to support the
share. The backtest file says so plainly and the alerts are kept.
"""

from __future__ import annotations

import math
import random
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Final

from field_return_triage.contracts import Recall, SeriesKey, TrendAlert
from field_return_triage.trend.series import (
    SeriesMap,
    series_key_dict,
    series_sort_key,
    series_total,
    week_grid,
)
from field_return_triage.trend.spike import TRAILING_WEEKS

__all__ = [
    "BASE_RATE_SEED",
    "MAX_LEAD_DAYS",
    "WEAK_JOIN_MIN",
    "AlertMatch",
    "Backtest",
    "BaseRateDraw",
    "pick_example_series",
    "preceding_recall",
    "recall_index",
    "run_backtest",
    "wilson_interval",
]

#: Fixed seed for the base-rate draws (the same seed as the project's other draws).
BASE_RATE_SEED: Final = 20261031
#: The recall window after an alert week, in days.
MAX_LEAD_DAYS: Final = 365
#: Fewer matches than this means the recall join is too weak to report a share.
WEAK_JOIN_MIN: Final = 20
#: 95 % two-sided normal quantile.
_Z95: Final = 1.959963984540054

RecallIndex = dict[SeriesKey, tuple[Recall, ...]]


@dataclass(frozen=True)
class AlertMatch:
    """An alert and the first recall inside its 365-day window."""

    alert: TrendAlert
    recall: Recall
    lead_days: int


@dataclass(frozen=True)
class BaseRateDraw:
    """One random week of one series, compared with the recall window."""

    alert: TrendAlert
    week: date
    recall: Recall | None

    @property
    def lead_days(self) -> int | None:
        if self.recall is None:
            return None
        return (self.recall.report_date - self.week).days


@dataclass(frozen=True)
class Backtest:
    """Everything the report needs, in a deterministic order."""

    alerts: tuple[TrendAlert, ...]
    matches: tuple[AlertMatch, ...]
    draws: tuple[BaseRateDraw, ...]
    seed: int = BASE_RATE_SEED

    @property
    def preceding(self) -> int:
        return len(self.matches)

    @property
    def share(self) -> float | None:
        if not self.alerts:
            return None
        return self.preceding / len(self.alerts)

    @property
    def median_lead_days(self) -> float | None:
        if not self.matches:
            return None
        return float(statistics.median(match.lead_days for match in self.matches))

    @property
    def base_rate_hits(self) -> int:
        return sum(1 for draw in self.draws if draw.recall is not None)

    @property
    def base_rate_share(self) -> float | None:
        if not self.draws:
            return None
        return self.base_rate_hits / len(self.draws)

    @property
    def base_rate_interval(self) -> tuple[float, float] | None:
        if not self.draws:
            return None
        return wilson_interval(self.base_rate_hits, len(self.draws))

    @property
    def weak_join(self) -> bool:
        return self.preceding < WEAK_JOIN_MIN

    def as_dict(self) -> dict[str, Any]:
        """The JSON body of ``results/trend/backtest.json``."""
        interval = self.base_rate_interval
        note: str | None = None
        if not self.alerts:
            note = "No alerts were produced, so there is nothing to backtest."
        elif self.weak_join:
            note = (
                f"Only {self.preceding} of {len(self.alerts)} alerts precede a recall within "
                f"{MAX_LEAD_DAYS} days, fewer than the {WEAK_JOIN_MIN} needed to support a "
                "share. The recall join is too weak to read as evidence; the alerts are kept."
            )
        matches = {(match.alert.series, match.alert.week): match for match in self.matches}
        per_alert = []
        for alert in self.alerts:
            match = matches.get((alert.series, alert.week))
            per_alert.append(
                {
                    "series": series_key_dict(alert.series),
                    "week": alert.week.isoformat(),
                    "count": alert.count,
                    "trailing_mean": alert.trailing_mean,
                    "threshold": alert.threshold,
                    "recall_id": match.recall.recall_id if match is not None else None,
                    "report_date": (
                        match.recall.report_date.isoformat() if match is not None else None
                    ),
                    "lead_days": match.lead_days if match is not None else None,
                }
            )
        return {
            "method": {
                "rule": "count >= 3 and count > Poisson 99.9% upper limit of the trailing 26-week mean (floored at 0.5)",
                "recall_window_days": MAX_LEAD_DAYS,
                "base_rate": "one random evaluated week of the same series per alert, fixed seed",
            },
            "alerts": {
                "total": len(self.alerts),
                "preceding_recall": self.preceding,
                "share": _round(self.share),
                "median_lead_days": _round(self.median_lead_days),
                "weak_join": self.weak_join,
                "note": note,
            },
            "base_rate": {
                "draws": len(self.draws),
                "preceding_recall": self.base_rate_hits,
                "share": _round(self.base_rate_share),
                "ci95": (
                    {"low": _round(interval[0]), "high": _round(interval[1])}
                    if interval is not None
                    else None
                ),
                "seed": self.seed,
            },
            "per_alert": per_alert,
        }


def _round(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(value, digits)


def wilson_interval(successes: int, draws: int, z: float = _Z95) -> tuple[float, float]:
    """The Wilson 95 % interval for a binomial share."""
    if draws <= 0:
        raise ValueError("draws must be positive")
    if not 0 <= successes <= draws:
        raise ValueError("successes must be between 0 and draws")
    share = successes / draws
    denominator = 1.0 + z * z / draws
    centre = (share + z * z / (2.0 * draws)) / denominator
    margin = z * math.sqrt(share * (1.0 - share) / draws + z * z / (4.0 * draws * draws))
    margin /= denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def recall_index(recalls: Sequence[Recall]) -> RecallIndex:
    """Recalls grouped by series, each list sorted by report date."""
    grouped: dict[SeriesKey, list[Recall]] = {}
    for recall in recalls:
        grouped.setdefault(
            SeriesKey(
                make=recall.make,
                model=recall.model,
                model_year=recall.model_year,
                group=recall.group,
            ),
            [],
        ).append(recall)
    return {
        key: tuple(sorted(items, key=lambda item: (item.report_date, item.recall_id)))
        for key, items in grouped.items()
    }


def preceding_recall(
    series: SeriesKey,
    week: date,
    index: Mapping[SeriesKey, Sequence[Recall]],
    *,
    max_days: int = MAX_LEAD_DAYS,
) -> Recall | None:
    """The first recall from ``week`` through ``week + max_days``, or ``None``."""
    for recall in index.get(series, ()):
        lead = (recall.report_date - week).days
        if 0 <= lead <= max_days:
            return recall
        if lead > max_days:
            break
    return None


def run_backtest(
    alerts: Sequence[TrendAlert],
    series: SeriesMap,
    recalls: Sequence[Recall],
    *,
    seed: int = BASE_RATE_SEED,
) -> Backtest:
    """Join alerts to recalls and draw the base rate deterministically."""
    ordered = sorted(alerts, key=lambda item: (*series_sort_key(item.series), item.week))
    index = recall_index(recalls)
    matches: list[AlertMatch] = []
    for alert in ordered:
        recall = preceding_recall(alert.series, alert.week, index)
        if recall is not None:
            matches.append(
                AlertMatch(
                    alert=alert,
                    recall=recall,
                    lead_days=(recall.report_date - alert.week).days,
                )
            )
    rng = random.Random(seed)
    draws: list[BaseRateDraw] = []
    for alert in ordered:
        grid = week_grid(series[alert.series])
        eligible = [week for position, (week, _) in enumerate(grid) if position >= TRAILING_WEEKS]
        week = eligible[rng.randrange(len(eligible))]
        draws.append(
            BaseRateDraw(
                alert=alert,
                week=week,
                recall=preceding_recall(alert.series, week, index),
            )
        )
    return Backtest(
        alerts=tuple(ordered),
        matches=tuple(matches),
        draws=tuple(draws),
        seed=seed,
    )


def pick_example_series(
    backtest: Backtest,
    series: SeriesMap,
    *,
    min_total: int = 20,
) -> dict[str, Any] | None:
    """The alert with the longest lead time among series with at least 20 complaints."""
    candidates = [
        match
        for match in backtest.matches
        if series_total(series.get(match.alert.series, {})) >= min_total
    ]
    if not candidates:
        return None
    best = min(
        candidates,
        key=lambda match: (
            -match.lead_days,
            match.alert.week,
            series_sort_key(match.alert.series),
        ),
    )
    alert = best.alert
    grid = week_grid(series[alert.series])
    return {
        "series": series_key_dict(alert.series),
        "total_complaints": series_total(series[alert.series]),
        "alert": {
            "week": alert.week.isoformat(),
            "count": alert.count,
            "trailing_mean": alert.trailing_mean,
            "threshold": alert.threshold,
        },
        "recall": {
            "recall_id": best.recall.recall_id,
            "report_date": best.recall.report_date.isoformat(),
            "lead_days": best.lead_days,
        },
        "weeks": [{"week": week.isoformat(), "count": count} for week, count in grid],
    }
