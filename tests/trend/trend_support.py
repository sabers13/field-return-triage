"""Synthetic series helpers for the trend tests (no committed data needed)."""

from __future__ import annotations

from datetime import date, timedelta

from field_return_triage.contracts import Recall, SeriesKey, WeeklyCount

START = date(2020, 1, 6)  # a Monday


def key(
    make: str = "Acme",
    model: str = "Model A",
    model_year: int = 2020,
    group: str = "electrical",
) -> SeriesKey:
    return SeriesKey(make=make, model=model, model_year=model_year, group=group)


def mondays(count: int, start: date = START) -> list[date]:
    return [start + timedelta(days=7 * index) for index in range(count)]


def counts(values: list[int], start: date = START) -> dict[date, int]:
    return dict(zip(mondays(len(values), start), values, strict=True))


def weekly(series: SeriesKey, values: list[int], start: date = START) -> list[WeeklyCount]:
    return [
        WeeklyCount(series=series, week=week, count=count)
        for week, count in zip(mondays(len(values), start), values, strict=True)
    ]


def recall(
    week: date,
    lead_days: int,
    *,
    series: SeriesKey | None = None,
    recall_id: str = "R-1",
) -> Recall:
    series = series or key()
    return Recall(
        recall_id=recall_id,
        make=series.make,
        model=series.model,
        model_year=series.model_year,
        group=series.group,
        report_date=week + timedelta(days=lead_days),
    )
