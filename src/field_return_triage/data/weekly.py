"""The weekly complaint-count table (``data/trend/weekly.csv.gz``).

The trend table is counts only: all single-group complaints, no narrative length filter
and no PII screen (``PLAN.md`` section 5; applying those would distort the series). Rows
arrive already resolved by the single-group rule, with a ``component_group`` key.

A row's week is the Monday that starts its ISO week. Series are ``make + model + model
year + group``; a row with an unknown model year (``9999``) or a missing make/model
cannot form a series and is skipped rather than guessed.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any

from field_return_triage.contracts import SeriesKey, WeeklyCount
from field_return_triage.data.complaints import _date, _text, _year

__all__ = ["derive_weekly", "week_start"]


def week_start(day: date | datetime | str) -> date:
    """The Monday that starts the ISO week of ``day``."""
    value = _date(day)
    return value - timedelta(days=value.weekday())


def derive_weekly(rows: Iterable[dict[str, Any]]) -> list[WeeklyCount]:
    """Aggregate resolved complaint rows into one row per series and Monday week."""
    counts: Counter[tuple[str, str, int, str, date]] = Counter()
    for row in rows:
        group = _text(row.get("component_group"))
        if not group:
            continue
        make = _text(row.get("MAKETXT")).upper()
        model = _text(row.get("MODELTXT")).upper()
        year = _year(row.get("YEARTXT"))
        if not make or not model or year is None:
            continue
        week = week_start(_date(row.get("LDATE")))
        counts[(make, model, year, group, week)] += 1
    weekly: list[WeeklyCount] = []
    for (make, model, year, group, week), count in sorted(counts.items()):
        weekly.append(
            WeeklyCount(
                series=SeriesKey(make=make, model=model, model_year=year, group=group),
                week=week,
                count=count,
            )
        )
    return weekly
