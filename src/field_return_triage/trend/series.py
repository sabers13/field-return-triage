"""Read the committed trend tables and shape them into continuous weekly grids.

The trend lane reads the two committed CSV files directly (``PLAN.md`` §5): lanes do not
import each other, so the loader lives here rather than in ``data``. The canonical
column names are the contract field names:

``data/trend/weekly.csv.gz``
    ``make,model,model_year,group,week,count``
``data/trend/recalls.csv``
    ``recall_id,make,model,model_year,group,report_date``

A few obvious aliases are accepted so a harmless spelling difference in the data lane
cannot break the join; anything else is an error with the file, line and column named.
Blank lines are skipped, and a duplicate ``(series, week)`` row is rejected rather than
silently summed.
"""

from __future__ import annotations

import csv
import gzip
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import IO, Final

from field_return_triage.contracts import Recall, SeriesKey, WeeklyCount

__all__ = [
    "SeriesMap",
    "group_weeks",
    "load_recalls",
    "load_weekly",
    "series_key_dict",
    "series_sort_key",
    "series_total",
    "week_grid",
]

#: ``SeriesKey`` -> ``{week: count}``. Every series maps only the weeks it has rows for.
SeriesMap = dict[SeriesKey, dict[date, int]]

_WEEKLY_ALIASES: Final[dict[str, str]] = {
    "make": "make",
    "model": "model",
    "model_year": "model_year",
    "year": "model_year",
    "my": "model_year",
    "group": "group",
    "component_group": "group",
    "week": "week",
    "week_start": "week",
    "week_begin": "week",
    "count": "count",
    "complaints": "count",
    "complaint_count": "count",
}

_RECALL_ALIASES: Final[dict[str, str]] = {
    "recall_id": "recall_id",
    "id": "recall_id",
    "campaign": "recall_id",
    "campaign_number": "recall_id",
    "make": "make",
    "model": "model",
    "model_year": "model_year",
    "year": "model_year",
    "my": "model_year",
    "group": "group",
    "component_group": "group",
    "report_date": "report_date",
    "date": "report_date",
    "rcl_date": "report_date",
    "rcdate": "report_date",
}

_WEEKLY_REQUIRED: Final[tuple[str, ...]] = (
    "make",
    "model",
    "model_year",
    "group",
    "week",
    "count",
)
_RECALL_REQUIRED: Final[tuple[str, ...]] = (
    "recall_id",
    "make",
    "model",
    "model_year",
    "group",
    "report_date",
)


@contextmanager
def _open_text(path: Path) -> Iterator[IO[str]]:
    """Open a plain or gzipped CSV in text mode, by file suffix."""
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            yield handle
    else:
        with path.open("r", encoding="utf-8", newline="") as handle:
            yield handle


def _normalise_header(name: str) -> str:
    return name.strip().lstrip("\ufeff").lower().replace(" ", "_").replace("-", "_")


def _read_rows(
    path: Path,
    aliases: Mapping[str, str],
    required: tuple[str, ...],
    label: str,
) -> Iterator[tuple[int, dict[str, str]]]:
    """Yield ``(line number, canonical row)`` for every non-blank CSV row."""
    with _open_text(path) as handle:
        reader = csv.reader(handle)
        try:
            raw_header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"{path}: empty {label} CSV") from exc
        header = [_normalise_header(name) for name in raw_header]
        columns: list[str] = []
        for name in header:
            canonical = aliases.get(name)
            if canonical is None:
                raise ValueError(f"{path}: unknown {label} column {name!r}")
            columns.append(canonical)
        missing = [name for name in required if name not in columns]
        if missing:
            raise ValueError(f"{path}: missing {label} column(s): {', '.join(missing)}")
        if len(set(columns)) != len(columns):
            raise ValueError(f"{path}: duplicate {label} column in header")
        for values in reader:
            if not values or all(not value.strip() for value in values):
                continue
            if len(values) != len(columns):
                raise ValueError(
                    f"{path}:{reader.line_num}: expected {len(columns)} values, got {len(values)}"
                )
            yield (
                reader.line_num,
                {name: value.strip() for name, value in zip(columns, values, strict=True)},
            )


def _parse_int(path: Path, lineno: int, name: str, value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{path}:{lineno}: {name} is not an integer: {value!r}") from exc


def _parse_date(path: Path, lineno: int, name: str, value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{path}:{lineno}: {name} is not an ISO date: {value!r}") from exc


def load_weekly(path: Path = Path("data/trend/weekly.csv.gz")) -> list[WeeklyCount]:
    """Read the weekly counts table, one ``WeeklyCount`` per row."""
    rows: list[WeeklyCount] = []
    for lineno, row in _read_rows(path, _WEEKLY_ALIASES, _WEEKLY_REQUIRED, "weekly"):
        try:
            rows.append(
                WeeklyCount(
                    series=SeriesKey(
                        make=row["make"],
                        model=row["model"],
                        model_year=_parse_int(path, lineno, "model_year", row["model_year"]),
                        group=row["group"],
                    ),
                    week=_parse_date(path, lineno, "week", row["week"]),
                    count=_parse_int(path, lineno, "count", row["count"]),
                )
            )
        except ValueError as exc:
            raise ValueError(f"{path}:{lineno}: invalid weekly row: {exc}") from exc
    return rows


def load_recalls(path: Path = Path("data/trend/recalls.csv")) -> list[Recall]:
    """Read the recall table, one ``Recall`` per row."""
    rows: list[Recall] = []
    for lineno, row in _read_rows(path, _RECALL_ALIASES, _RECALL_REQUIRED, "recall"):
        try:
            rows.append(
                Recall(
                    recall_id=row["recall_id"],
                    make=row["make"],
                    model=row["model"],
                    model_year=_parse_int(path, lineno, "model_year", row["model_year"]),
                    group=row["group"],
                    report_date=_parse_date(path, lineno, "report_date", row["report_date"]),
                )
            )
        except ValueError as exc:
            raise ValueError(f"{path}:{lineno}: invalid recall row: {exc}") from exc
    return rows


def series_sort_key(series: SeriesKey) -> tuple[str, str, int, str]:
    """A stable, human-readable ordering for series keys."""
    return (series.make, series.model, series.model_year, series.group)


def series_key_dict(series: SeriesKey) -> dict[str, str | int]:
    """The JSON shape of a ``SeriesKey``."""
    return {
        "make": series.make,
        "model": series.model,
        "model_year": series.model_year,
        "group": series.group,
    }


def group_weeks(rows: Iterable[WeeklyCount]) -> SeriesMap:
    """Group weekly rows by series, rejecting a duplicate week for the same series."""
    series: SeriesMap = {}
    seen: set[tuple[SeriesKey, date]] = set()
    for row in rows:
        if (row.series, row.week) in seen:
            raise ValueError(
                f"duplicate weekly row for {series_sort_key(row.series)} on {row.week}"
            )
        seen.add((row.series, row.week))
        series.setdefault(row.series, {})[row.week] = row.count
    return {
        key: dict(sorted(counts.items()))
        for key, counts in sorted(series.items(), key=lambda item: series_sort_key(item[0]))
    }


def week_grid(counts: Mapping[date, int]) -> list[tuple[date, int]]:
    """Every Monday from the first to the last counted week, missing weeks as zero."""
    if not counts:
        return []
    start = min(counts)
    end = max(counts)
    grid: list[tuple[date, int]] = []
    week = start
    while week <= end:
        grid.append((week, counts.get(week, 0)))
        week += timedelta(days=7)
    return grid


def series_total(counts: Mapping[date, int]) -> int:
    """All complaints in a series over the whole table."""
    return sum(counts.values())
