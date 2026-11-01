"""``data/STATS.md`` renders the funnel, rates and recall mapping deterministically."""

from __future__ import annotations

from field_return_triage.data.complaints import (
    ResolutionStats,
    ScreenResult,
    complaint_from_row,
    split_half,
)
from field_return_triage.data.recalls import RecallResolutionStats
from field_return_triage.data.stats import StatsInput, build_stats
from data_support import resolved_row


def _source() -> StatsInput:
    rows = [
        resolved_row(ODINO="1", LDATE="20240101", CRASH="Y"),
        resolved_row(ODINO="2", LDATE="20240102"),
        resolved_row(ODINO="3", LDATE="20250601", CRASH="Y"),
        resolved_row(ODINO="4", LDATE="20250602"),
    ]
    items = [complaint_from_row(row) for row in rows]
    test_pool = [row for row in rows if str(row["LDATE"]).startswith("2025")]
    return StatsInput(
        snapshot="2026-10-31",
        groups=("airbags", "driver_assist_sensors"),
        resolution=ResolutionStats(
            parsed_rows=10,
            vehicle_rows=9,
            vehicle_complaints=5,
            single_group_complaints=4,
        ),
        screen=ScreenResult(rows=rows, length_dropped=1, pii_dropped=1),
        library=[item for item in items if item.received.year == 2024],
        eval_items=[item for item in items if item.received.year == 2025],
        test_pool=test_pool,
        recalls=RecallResolutionStats(
            parsed_rows=100,
            vehicle_rows=90,
            mapped_rows=45,
            vehicle_campaigns=10,
            mapped_campaigns=5,
        ),
        recalls_written=44,
    )


def test_stats_has_every_required_section_and_stable_numbers() -> None:
    text = build_stats(_source())
    assert text == build_stats(_source())
    for heading in (
        "# Data statistics",
        "## Derivation funnel",
        "## Counts per group",
        "## Safety (coded crash / fire / injury or death)",
        "## PII screen",
        "## Recall mapping",
    ):
        assert heading in text
    assert "50.0%" in text  # 45 mapped rows of 90 vehicle rows
    assert "Evaluation sample (oversampled)" in text


def test_every_test_pool_row_belongs_to_a_half() -> None:
    for index in range(100):
        odino = f"95{index:04d}"
        assert split_half(odino) in {"wam", "frt"}
