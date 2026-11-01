"""Read and write the committed derived files.

Formats are fixed by ``docs/INTERFACES.md`` section 3:

* JSONL is one contract per line, keys sorted, UTF-8, ``\\n`` endings;
* gzip members are written with ``mtime=0`` so a rerun is byte-identical;
* the trend CSVs use the contract field names as their header row.

``write_*`` returns the sha256 of the bytes written (the compressed bytes for a ``.gz``
file), which is what ``data/CHECKSUMS.txt`` records. ``load_*`` takes a path so tests and
other lanes can read a fixture.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Final

from field_return_triage.contracts import Complaint, Recall, SeriesKey, WeeklyCount

__all__ = [
    "RECALL_HEADER",
    "WEEKLY_HEADER",
    "load_eval",
    "load_library",
    "load_recalls",
    "load_weekly",
    "write_eval",
    "write_library",
    "write_recalls",
    "write_weekly",
]

WEEKLY_HEADER: Final[tuple[str, ...]] = ("make", "model", "model_year", "group", "week", "count")
RECALL_HEADER: Final[tuple[str, ...]] = (
    "recall_id",
    "make",
    "model",
    "model_year",
    "group",
    "report_date",
)


def _write_bytes(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _jsonl_bytes(items: Iterable[Complaint]) -> bytes:
    lines = [
        json.dumps(item.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        for item in items
    ]
    return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")


def _csv_bytes(header: Sequence[str], rows: Iterable[Sequence[str | int]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _gzip(payload: bytes) -> bytes:
    return gzip.compress(payload, compresslevel=9, mtime=0)


def write_library(items: Sequence[Complaint], path: Path) -> str:
    """Write gzipped JSONL; return the sha256 of the written bytes."""
    return _write_bytes(path, _gzip(_jsonl_bytes(items)))


def write_eval(items: Sequence[Complaint], path: Path) -> str:
    """Write plain JSONL; return the sha256 of the written bytes."""
    return _write_bytes(path, _jsonl_bytes(items))


def write_weekly(items: Sequence[WeeklyCount], path: Path) -> str:
    """Write the gzipped weekly CSV; return the sha256 of the written bytes."""
    rows = (
        (item.series.make, item.series.model, item.series.model_year, item.series.group,
         item.week.isoformat(), item.count)
        for item in items
    )
    return _write_bytes(path, _gzip(_csv_bytes(WEEKLY_HEADER, rows)))


def write_recalls(items: Sequence[Recall], path: Path) -> None:
    """Write the plain recall CSV."""
    rows = (
        (item.recall_id, item.make, item.model, item.model_year, item.group,
         item.report_date.isoformat())
        for item in items
    )
    _write_bytes(path, _csv_bytes(RECALL_HEADER, rows))


def _load_complaints(path: Path, gzipped: bool) -> list[Complaint]:
    opener = gzip.open if gzipped else open
    items: list[Complaint] = []
    with opener(path, "rt", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                items.append(Complaint.model_validate_json(text))
            except ValueError as exc:
                raise ValueError(f"{path}:{lineno}: invalid Complaint row: {exc}") from exc
    return items


def load_library(path: Path = Path("data/library.jsonl.gz")) -> list[Complaint]:
    """Read the committed gzipped library."""
    return _load_complaints(path, gzipped=True)


def load_eval(path: Path = Path("data/eval.jsonl")) -> list[Complaint]:
    """Read the committed plain JSONL evaluation set."""
    return _load_complaints(path, gzipped=False)


def _read_csv(path: Path, header: tuple[str, ...], *, gzipped: bool) -> Iterable[tuple[int, list[str]]]:
    opener = gzip.open if gzipped else open
    with opener(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            found = tuple(next(reader))
        except StopIteration as exc:
            raise ValueError(f"{path}: empty CSV") from exc
        if found != header:
            raise ValueError(f"{path}: header must be {','.join(header)}, got {','.join(found)}")
        for values in reader:
            if not values:
                continue
            if len(values) != len(header):
                raise ValueError(
                    f"{path}:{reader.line_num}: expected {len(header)} values, got {len(values)}"
                )
            yield reader.line_num, values


def _int(path: Path, lineno: int, name: str, value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{path}:{lineno}: {name} is not an integer: {value!r}") from exc


def _date(path: Path, lineno: int, name: str, value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{path}:{lineno}: {name} is not an ISO date: {value!r}") from exc


def load_weekly(path: Path = Path("data/trend/weekly.csv.gz")) -> list[WeeklyCount]:
    """Read the committed gzipped weekly counts."""
    items: list[WeeklyCount] = []
    for lineno, row in _read_csv(path, WEEKLY_HEADER, gzipped=True):
        make, model, model_year, group, week, count = row
        items.append(
            WeeklyCount(
                series=SeriesKey(
                    make=make,
                    model=model,
                    model_year=_int(path, lineno, "model_year", model_year),
                    group=group,
                ),
                week=_date(path, lineno, "week", week),
                count=_int(path, lineno, "count", count),
            )
        )
    return items


def load_recalls(path: Path = Path("data/trend/recalls.csv")) -> list[Recall]:
    """Read the committed recall table."""
    items: list[Recall] = []
    for lineno, row in _read_csv(path, RECALL_HEADER, gzipped=False):
        recall_id, make, model, model_year, group, report_date = row
        items.append(
            Recall(
                recall_id=recall_id,
                make=make,
                model=model,
                model_year=_int(path, lineno, "model_year", model_year),
                group=group,
                report_date=_date(path, lineno, "report_date", report_date),
            )
        )
    return items
