"""The trend tables: weekly aggregation and the recall map."""

from __future__ import annotations

from field_return_triage.data.recalls import derive_recalls, resolve_recalls
from field_return_triage.data.spec import load_groups
from field_return_triage.data.weekly import derive_weekly, week_start
from data_support import recall_row, resolved_row

GROUPS = load_groups()


def test_week_start_is_the_monday() -> None:
    assert week_start("20210106").isoformat() == "2021-01-04"  # Wednesday
    assert week_start("20210104").isoformat() == "2021-01-04"  # Monday
    assert week_start("20210110").isoformat() == "2021-01-04"  # Sunday


def test_weekly_counts_one_row_per_series_and_week() -> None:
    rows = [
        resolved_row(ODINO="1", MAKETXT="acme", MODELTXT="model a", YEARTXT="2021", LDATE="20210104"),
        resolved_row(ODINO="2", MAKETXT="ACME", MODELTXT="MODEL A", YEARTXT="2021", LDATE="20210106"),
        resolved_row(ODINO="3", MAKETXT="ACME", MODELTXT="MODEL A", YEARTXT="2021", LDATE="20210111"),
        resolved_row(ODINO="4", MAKETXT="ACME", MODELTXT="MODEL A", YEARTXT="2021", LDATE="20210113"),
    ]
    weekly = derive_weekly(rows)
    assert len(weekly) == 2
    assert weekly[0].week.isoformat() == "2021-01-04"
    assert weekly[0].count == 2
    assert weekly[1].week.isoformat() == "2021-01-11"
    assert weekly[1].count == 2
    assert weekly[0].series.make == "ACME"
    assert weekly[0].series.model == "MODEL A"


def test_weekly_keeps_groups_apart_and_skips_unknown_years() -> None:
    rows = [
        resolved_row(ODINO="1", component_group="airbags", YEARTXT="2021"),
        resolved_row(ODINO="2", component_group="wipers_washers", YEARTXT="2021"),
        resolved_row(ODINO="3", component_group="airbags", YEARTXT="9999"),
        resolved_row(ODINO="4", component_group="airbags", MAKETXT=""),
    ]
    weekly = derive_weekly(rows)
    assert {(row.series.group, row.count) for row in weekly} == {
        ("airbags", 1),
        ("wipers_washers", 1),
    }


def test_weekly_is_sorted_by_series_then_week() -> None:
    rows = [
        resolved_row(ODINO="1", MAKETXT="ZETA", LDATE="20210111"),
        resolved_row(ODINO="2", MAKETXT="ALPHA", LDATE="20210111"),
        resolved_row(ODINO="3", MAKETXT="ALPHA", LDATE="20210104"),
    ]
    weekly = derive_weekly(rows)
    keys = [(row.series.make, row.week) for row in weekly]
    assert keys == sorted(keys)


def test_recall_rows_map_components_and_skip_non_vehicles() -> None:
    rows = [
        recall_row(CAMPNO="21V001000", COMPNAME="AIR BAGS:FRONTAL"),
        recall_row(CAMPNO="21V002000", COMPNAME="ENGINE"),
        recall_row(CAMPNO="21V003000", COMPNAME="AIR BAGS:SIDE", RCLTYPECD="E"),
        recall_row(CAMPNO="21V004000", COMPNAME="VISIBILITY/WIPER", YEARTXT="9999"),
    ]
    resolved = resolve_recalls(rows, GROUPS)
    assert [row["CAMPNO"] for row in resolved] == ["21V001000", "21V004000"]
    recalls = derive_recalls(resolved)
    assert [recall.recall_id for recall in recalls] == ["21V001000"]


def test_recall_rows_are_normalised_and_sorted_by_report_date() -> None:
    rows = resolve_recalls(
        [
            recall_row(CAMPNO="B", RCDATE="20220101", MAKETXT="beta", MODELTXT="two"),
            recall_row(CAMPNO="A", RCDATE="20210101", MAKETXT="alpha", MODELTXT="one"),
        ],
        GROUPS,
    )
    recalls = derive_recalls(rows)
    assert [recall.recall_id for recall in recalls] == ["A", "B"]
    assert recalls[0].make == "ALPHA"
    assert recalls[0].model == "ONE"
