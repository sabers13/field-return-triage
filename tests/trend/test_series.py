"""Reading the committed trend CSV files and building continuous weekly grids."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest
from trend_support import START, counts, key, recall, weekly

from field_return_triage.trend.series import (
    group_weeks,
    load_recalls,
    load_weekly,
    series_sort_key,
    series_total,
    week_grid,
)

HEADER = "make,model,model_year,group,week,count\n"


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_load_weekly_reads_a_plain_csv(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "weekly.csv",
        HEADER
        + "Acme,Model A,2020,electrical,2020-01-06,3\nAcme,Model A,2020,electrical,2020-01-13,0\n",
    )
    rows = load_weekly(path)
    assert len(rows) == 2
    assert rows[0].series == key()
    assert rows[0].week == START
    assert rows[0].count == 3


def test_load_weekly_reads_a_gzipped_csv(tmp_path: Path) -> None:
    path = tmp_path / "weekly.csv.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(HEADER + "Acme,Model A,2020,electrical,2020-01-06,7\n")
    assert load_weekly(path)[0].count == 7


def test_load_weekly_accepts_column_aliases_and_blank_lines(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "weekly.csv",
        "make,model,year,group,week_start,complaints\n\n"
        "Acme,Model A,2020,electrical,2020-01-06,3\n\n",
    )
    row = load_weekly(path)[0]
    assert row.week == START
    assert row.count == 3


def test_load_weekly_rejects_an_unknown_column(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "weekly.csv",
        "make,model,model_year,group,week,count,mystery\n"
        "Acme,Model A,2020,electrical,2020-01-06,3,x\n",
    )
    with pytest.raises(ValueError, match="unknown weekly column 'mystery'"):
        load_weekly(path)


def test_load_weekly_rejects_a_missing_column(tmp_path: Path) -> None:
    path = _write(tmp_path / "weekly.csv", "make,model,week,count\nAcme,Model A,2020-01-06,3\n")
    with pytest.raises(ValueError, match="missing weekly column"):
        load_weekly(path)


def test_load_weekly_rejects_a_bad_value_with_the_line(tmp_path: Path) -> None:
    for bad in ("notanint", "-1"):
        path = _write(
            tmp_path / "weekly.csv",
            HEADER + f"Acme,Model A,2020,electrical,2020-01-06,{bad}\n",
        )
        with pytest.raises(ValueError, match=r"weekly.csv:2"):
            load_weekly(path)


def test_load_weekly_rejects_a_bad_date(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "weekly.csv",
        HEADER + "Acme,Model A,2020,electrical,06/01/2020,3\n",
    )
    with pytest.raises(ValueError, match="not an ISO date"):
        load_weekly(path)


def test_load_weekly_requires_a_monday(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "weekly.csv",
        HEADER + "Acme,Model A,2020,electrical,2020-01-07,3\n",
    )
    with pytest.raises(ValueError, match="Monday"):
        load_weekly(path)


def test_load_weekly_rejects_a_short_row(tmp_path: Path) -> None:
    path = _write(tmp_path / "weekly.csv", HEADER + "Acme,Model A,2020,electrical\n")
    with pytest.raises(ValueError, match="expected 6 values"):
        load_weekly(path)


def test_load_weekly_rejects_an_empty_file(tmp_path: Path) -> None:
    path = _write(tmp_path / "weekly.csv", "")
    with pytest.raises(ValueError, match="empty weekly CSV"):
        load_weekly(path)


def test_load_recalls_reads_aliases(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "recalls.csv",
        "id,make,model,my,group,date\nR-9,Acme,Model A,2020,electrical,2021-03-01\n",
    )
    rows = load_recalls(path)
    assert len(rows) == 1
    assert rows[0].recall_id == "R-9"
    assert rows[0].report_date.isoformat() == "2021-03-01"


def test_load_recalls_rejects_a_bad_row(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "recalls.csv",
        "recall_id,make,model,model_year,group,report_date\n\nR-1,Acme,Model A,2020,electrical,nope\n",
    )
    with pytest.raises(ValueError, match=r"recalls\.csv:3"):
        load_recalls(path)


def test_group_weeks_rejects_a_duplicate_week() -> None:
    rows = weekly(key(), [1]) + weekly(key(), [2], start=START)
    with pytest.raises(ValueError, match="duplicate weekly row"):
        group_weeks(rows)


def test_group_weeks_orders_series_and_weeks() -> None:
    rows = weekly(key(make="Beta"), [1]) + weekly(key(make="Acme"), [2])
    series = group_weeks(rows)
    assert [series_sort_key(item) for item in series] == [
        ("Acme", "Model A", 2020, "electrical"),
        ("Beta", "Model A", 2020, "electrical"),
    ]


def test_week_grid_fills_gaps_with_zero() -> None:
    rows = counts([2, 0, 5])
    weeks = sorted(rows)
    sparse = {weeks[0]: 2, weeks[2]: 5}
    assert week_grid(sparse) == [(weeks[0], 2), (weeks[1], 0), (weeks[2], 5)]


def test_week_grid_and_total_on_an_empty_series() -> None:
    assert week_grid({}) == []
    assert series_total({}) == 0


def test_series_total_sums_all_weeks() -> None:
    assert series_total(counts([1, 2, 3])) == 6


def test_recall_helper_is_in_the_test_package() -> None:
    item = recall(START, 10)
    assert item.report_date > START
