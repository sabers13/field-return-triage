"""The recall table (``data/trend/recalls.csv``).

Only vehicle recall rows whose ``COMPNAME`` maps to a group are kept, with the joined
key fields (``CAMPNO``, make, model, model year, group, ``RCDATE``). Unmapped components
are not forced into a group: the honest result is the mapping rate in ``STATS.md``.

Model year ``9999`` means unknown; the binding spec says it never joins, so those rows
are skipped.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from field_return_triage.contracts import Recall
from field_return_triage.data.complaints import _date, _text, _year
from field_return_triage.data.spec import map_component

__all__ = [
    "RecallResolutionStats",
    "derive_recalls",
    "resolve_recalls",
    "resolve_recalls_with_stats",
]


@dataclass
class RecallResolutionStats:
    """How many recall rows the vehicle filter and the group map kept."""

    parsed_rows: int = 0
    vehicle_rows: int = 0
    mapped_rows: int = 0
    vehicle_campaigns: int = 0
    mapped_campaigns: int = 0

    def merge(self, other: RecallResolutionStats) -> None:
        self.parsed_rows += other.parsed_rows
        self.vehicle_rows += other.vehicle_rows
        self.mapped_rows += other.mapped_rows
        self.vehicle_campaigns += other.vehicle_campaigns
        self.mapped_campaigns += other.mapped_campaigns



def _is_vehicle(row: dict[str, Any]) -> bool:
    if "RCLTYPECD" not in row:
        return True
    return _text(row.get("RCLTYPECD")).upper() == "V"


def resolve_recalls(
    rows: Iterable[dict[str, Any]],
    groups: dict[str, tuple[str, ...]],
) -> list[dict[str, Any]]:
    """Keep vehicle recall rows that map to one group, adding ``component_group``."""
    return resolve_recalls_with_stats(rows, groups)[0]


def resolve_recalls_with_stats(
    rows: Iterable[dict[str, Any]],
    groups: dict[str, tuple[str, ...]],
) -> tuple[list[dict[str, Any]], RecallResolutionStats]:
    """``resolve_recalls`` plus the row/campaign counts used by ``STATS.md``."""
    stats = RecallResolutionStats()
    resolved: list[dict[str, Any]] = []
    vehicle_campaigns: set[str] = set()
    mapped_campaigns: set[str] = set()
    for row in rows:
        stats.parsed_rows += 1
        if not _is_vehicle(row):
            continue
        stats.vehicle_rows += 1
        campaign = _text(row.get("CAMPNO"))
        if campaign:
            vehicle_campaigns.add(campaign)
        if "component_group" in row:
            merged = dict(row)
        else:
            group = map_component(_text(row.get("COMPNAME")), groups)
            if group is None:
                continue
            merged = dict(row)
            merged["component_group"] = group
        stats.mapped_rows += 1
        if campaign:
            mapped_campaigns.add(campaign)
        resolved.append(merged)
    stats.vehicle_campaigns = len(vehicle_campaigns)
    stats.mapped_campaigns = len(mapped_campaigns)
    return resolved, stats



def derive_recalls(rows: Iterable[dict[str, Any]]) -> list[Recall]:
    """Build one ``Recall`` per resolved recall row, skipping unknown years/dates."""
    recalls: list[Recall] = []
    for row in rows:
        group = _text(row.get("component_group"))
        recall_id = _text(row.get("CAMPNO"))
        make = _text(row.get("MAKETXT")).upper()
        model = _text(row.get("MODELTXT")).upper()
        year = _year(row.get("YEARTXT"))
        if not group or not recall_id or not make or not model or year is None:
            continue
        try:
            report_date = _date(row.get("RCDATE"))
        except ValueError:
            continue
        recalls.append(
            Recall(
                recall_id=recall_id,
                make=make,
                model=model,
                model_year=year,
                group=group,
                report_date=report_date,
            )
        )
    return sorted(
        recalls,
        key=lambda recall: (
            recall.report_date,
            recall.recall_id,
            recall.make,
            recall.model,
            recall.model_year,
            recall.group,
        ),
    )
