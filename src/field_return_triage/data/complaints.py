"""Turn parsed complaint rows into the committed library and evaluation sets.

The rules are the binding ones from ``nhtsa-spec.toml`` and ``PLAN.md`` section 5:

* only ``PROD_TYPE == 'V'`` rows count;
* a complaint counts only when **every** component row maps to one and the same group;
* the narrative is at least 80 characters after trimming and passes the PII screen;
* the library is the 2020-2024 window, at most 20,000 items, stratified by group;
* the evaluation set is the 2025-2026 window, ``frt`` half only, 400 items, stratified
  by group, at least 20 per group and at least 80 safety-relevant;
* the halves are ``int(sha256("20261031:" + ODINO), 16) % 2``: 0 is ``wam``, 1 is ``frt``.

Sampling is deterministic: within a group, items are ordered by the full lowercase hex
sha256 of ``"<seed>:<ODINO>"`` and the quota is taken from the front. The quota starts at
``min(min_per_group, pool)``; the remainder is shared in proportion to pool size by the
largest-remainder method, capped at pool size. A safety top-up then swaps the largest-hash
selected non-safety item for the smallest-hash unselected safety item of a group until
the floor is met, exactly as ``[sampling.algorithm]`` says.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Final

from field_return_triage.contracts import Complaint
from field_return_triage.data.pii import PII_PATTERN_NAMES, pii_matches
from field_return_triage.data.spec import (
    SPLIT_KEY_PREFIX,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    map_component,
)

__all__ = [
    "EVAL_MIN_PER_GROUP",
    "EVAL_MIN_SAFETY",
    "MIN_NARRATIVE_CHARS",
    "ResolutionStats",
    "ScreenResult",
    "coded_safety_row",
    "complaint_from_row",
    "derive_eval",
    "derive_library",
    "group_counts",
    "resolve_complaints",
    "resolve_complaints_with_stats",
    "screen_narratives",
    "split_half",
]

#: ``[filters].minimum_narrative_chars`` and ``[sampling.frt]`` from the spec.
MIN_NARRATIVE_CHARS: Final = 80
EVAL_MIN_PER_GROUP: Final = 20
EVAL_MIN_SAFETY: Final = 80


@dataclass
class ResolutionStats:
    """How many rows and complaints the single-group rule saw."""

    parsed_rows: int = 0
    vehicle_rows: int = 0
    vehicle_complaints: int = 0
    single_group_complaints: int = 0

    def merge(self, other: ResolutionStats) -> None:
        self.parsed_rows += other.parsed_rows
        self.vehicle_rows += other.vehicle_rows
        self.vehicle_complaints += other.vehicle_complaints
        self.single_group_complaints += other.single_group_complaints


@dataclass
class ScreenResult:
    """The narrative filter's kept rows and its drop counts."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    length_dropped: int = 0
    pii_dropped: int = 0
    pii_by_pattern: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys(PII_PATTERN_NAMES, 0)
    )


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    if len(text) == 8 and text.isdigit():
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    raise ValueError(f"not a YYYYMMDD date: {value!r}")


def _count(value: Any) -> int:
    text = _text(value)
    if not text:
        return 0
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"not an integer count: {value!r}") from exc


def _year(value: Any) -> int | None:
    text = _text(value)
    if not text:
        return None
    try:
        year = int(text)
    except ValueError as exc:
        raise ValueError(f"not an integer model year: {value!r}") from exc
    return year if 1900 <= year <= 2100 else None


def split_half(odino: str) -> str:
    """``wam`` for an even hash, ``frt`` for an odd one (``[split].halving_rule``)."""
    digest = hashlib.sha256(f"{SPLIT_KEY_PREFIX}{odino}".encode()).hexdigest()
    return "wam" if int(digest, 16) % 2 == 0 else "frt"


def _row_order(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _text(row.get("CMPLID")),
        _text(row.get("COMPDESC")),
        _text(row.get("CDESCR")),
    )


def _is_vehicle(row: dict[str, Any]) -> bool:
    """Only ``PROD_TYPE == 'V'`` rows count; a resolved row without the field is one."""
    if "PROD_TYPE" not in row:
        return True
    return _text(row.get("PROD_TYPE")).upper() == "V"


def _is_resolved(row: dict[str, Any]) -> bool:
    return "component_group" in row


def _resolve_one(rows: Iterable[dict[str, Any]], groups: dict[str, tuple[str, ...]]) -> list[dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for row in rows:
        if _is_resolved(row):
            continue
        if not _is_vehicle(row):
            continue
        odino = _text(row.get("ODINO"))
        if not odino:
            continue
        entry = state.get(odino)
        if entry is None:
            entry = {"row": row, "groups": set(), "bad": False}
            state[odino] = entry
        mapping = map_component(_text(row.get("COMPDESC")), groups)
        if mapping is None:
            entry["bad"] = True
        else:
            entry["groups"].add(mapping)
        if _row_order(row) < _row_order(entry["row"]):
            entry["row"] = row
    resolved: list[dict[str, Any]] = []
    for odino in sorted(state):
        entry = state[odino]
        mapped: set[str] = entry["groups"]
        if entry["bad"] or len(mapped) != 1:
            continue
        merged = dict(entry["row"])
        merged["component_group"] = next(iter(mapped))
        resolved.append(merged)
    return resolved


def resolve_complaints(
    rows: Iterable[dict[str, Any]],
    groups: dict[str, tuple[str, ...]],
) -> list[dict[str, Any]]:
    """One row per vehicle complaint that passes the single-group rule.

    Rows that already carry ``component_group`` (the CLI resolves each file chunk once)
    pass through unchanged. An empty or unmapped component label, or two different
    groups on one complaint, excludes the whole complaint.
    """
    return resolve_complaints_with_stats(rows, groups)[0]


def resolve_complaints_with_stats(
    rows: Iterable[dict[str, Any]],
    groups: dict[str, tuple[str, ...]],
) -> tuple[list[dict[str, Any]], ResolutionStats]:
    """``resolve_complaints`` plus the funnel counts used by ``data/STATS.md``."""
    stats = ResolutionStats()
    passthrough: list[dict[str, Any]] = []
    raw: list[dict[str, Any]] = []
    for row in rows:
        if _is_resolved(row):
            if _is_vehicle(row):
                passthrough.append(dict(row))
                stats.single_group_complaints += 1
                stats.vehicle_complaints += 1
                stats.parsed_rows += 1
                stats.vehicle_rows += 1
            continue
        stats.parsed_rows += 1
        if _is_vehicle(row):
            stats.vehicle_rows += 1
            raw.append(row)
    odino_count = len({_text(row.get("ODINO")) for row in raw if _text(row.get("ODINO"))})
    stats.vehicle_complaints += odino_count
    resolved = passthrough + _resolve_one(raw, groups)
    if passthrough:
        stats.single_group_complaints += len(resolved) - len(passthrough)
    else:
        stats.single_group_complaints += len(resolved)
    return resolved, stats


def screen_narratives(rows: Iterable[dict[str, Any]]) -> ScreenResult:
    """Apply the 80-character minimum and the PII screen, counting every drop."""
    result = ScreenResult()
    for row in rows:
        narrative = _text(row.get("CDESCR"))
        if len(narrative) < MIN_NARRATIVE_CHARS:
            result.length_dropped += 1
            continue
        matches = pii_matches(narrative)
        if matches:
            result.pii_dropped += 1
            for name in matches:
                result.pii_by_pattern[name] += 1
            continue
        result.rows.append(row)
    return result


def coded_safety_row(row: dict[str, Any]) -> bool:
    """The spec's coded safety rule over one raw row."""
    return (
        _text(row.get("CRASH")).upper() == "Y"
        or _text(row.get("FIRE")).upper() == "Y"
        or _count(row.get("INJURED")) > 0
        or _count(row.get("DEATHS")) > 0
    )


def complaint_from_row(row: dict[str, Any]) -> Complaint:
    """Build the frozen ``Complaint`` contract from one resolved row."""
    group = row.get("component_group")
    narrative = _text(row.get("CDESCR"))
    return Complaint(
        id=_text(row.get("ODINO")),
        narrative=narrative,
        received=_date(row.get("LDATE")),
        make=_text(row.get("MAKETXT")) or None,
        model=_text(row.get("MODELTXT")) or None,
        model_year=_year(row.get("YEARTXT")),
        component=_text(row.get("COMPDESC")) or None,
        group=str(group) if group else None,
        crash=_text(row.get("CRASH")).upper() == "Y",
        fire=_text(row.get("FIRE")).upper() == "Y",
        injury=_count(row.get("INJURED")) > 0 or _count(row.get("DEATHS")) > 0,
    )


def _order_key(seed: int) -> Callable[[Complaint], str]:
    def key(item: Complaint) -> str:
        return hashlib.sha256(f"{seed}:{item.id}".encode()).hexdigest()

    return key


def _quotas(pool_sizes: dict[str, int], size: int, min_per_group: int) -> dict[str, int]:
    """Stratified quotas: the minimum first, then largest remainder, capped at the pool."""
    total_pool = sum(pool_sizes.values())
    if size > total_pool:
        raise ValueError(f"cannot draw {size} items from a pool of {total_pool}")
    quotas = {group: min(min_per_group, pool) for group, pool in pool_sizes.items()}
    if sum(quotas.values()) > size:
        raise ValueError(
            f"{size} items cannot cover {len(pool_sizes)} groups at {min_per_group} each"
        )
    remaining = size - sum(quotas.values())
    while remaining > 0:
        open_groups = [group for group in sorted(pool_sizes) if quotas[group] < pool_sizes[group]]
        if not open_groups:
            break
        open_pool = sum(pool_sizes[group] for group in open_groups)
        shares = {
            group: remaining * pool_sizes[group] / open_pool for group in open_groups
        }
        added = 0
        for group in open_groups:
            room = pool_sizes[group] - quotas[group]
            take = min(int(shares[group]), room)
            quotas[group] += take
            added += take
        remaining -= added
        if added:
            continue
        # Every share rounded to zero: give this item to the largest remainder.
        group = max(
            open_groups,
            key=lambda name: (shares[name] - int(shares[name]), name),
        )
        quotas[group] += 1
        remaining -= 1
    return quotas


def _safety_count(items: Iterable[Complaint]) -> int:
    return sum(1 for item in items if item.coded_safety)


def _top_up_safety(
    selected: dict[str, list[Complaint]],
    unselected: dict[str, list[Complaint]],
    target: int,
    key: Callable[[Complaint], str],
) -> None:
    while _safety_count(item for items in selected.values() for item in items) < target:
        donors = [
            group
            for group in sorted(unselected)
            if any(item.coded_safety for item in unselected[group])
            and any(not item.coded_safety for item in selected[group])
        ]
        if not donors:
            return
        group = max(
            donors,
            key=lambda name: (
                sum(1 for item in unselected[name] if item.coded_safety),
                name,
            ),
        )
        replacement = next(item for item in unselected[group] if item.coded_safety)
        victim = max(
            (item for item in selected[group] if not item.coded_safety),
            key=key,
        )
        unselected[group].remove(replacement)
        selected[group].remove(victim)
        selected[group].append(replacement)
        unselected[group].append(victim)
        unselected[group].sort(key=key)


def _select(
    items: list[Complaint],
    *,
    size: int,
    seed: int,
    min_per_group: int,
    min_safety: int,
) -> list[Complaint]:
    if size <= 0:
        raise ValueError(f"size must be positive, got {size}")
    key = _order_key(seed)
    pools: dict[str, list[Complaint]] = {}
    for item in items:
        if item.group is None:
            continue
        pools.setdefault(item.group, []).append(item)
    if not pools:
        return []
    for pool in pools.values():
        pool.sort(key=key)
    quotas = _quotas({group: len(pool) for group, pool in pools.items()}, size, min_per_group)
    selected = {group: pool[: quotas[group]] for group, pool in pools.items()}
    unselected = {group: pool[quotas[group] :] for group, pool in pools.items()}
    if min_safety:
        _top_up_safety(selected, unselected, min_safety, key)
    return [item for group in sorted(selected) for item in selected[group]]


def derive_library(
    rows: Iterable[dict[str, Any]],
    groups: dict[str, tuple[str, ...]],
    *,
    seed: int = 20261031,
    limit: int = 20_000,
) -> list[Complaint]:
    """The 2020-2024 past-case library, at most ``limit`` items, stratified by group."""
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit}")
    resolved = resolve_complaints(rows, groups)
    screened = screen_narratives(
        row for row in resolved if TRAIN_START <= _date(row.get("LDATE")) <= TRAIN_END
    )
    items = [complaint_from_row(row) for row in screened.rows]
    if limit >= len(items):
        return sorted(items, key=lambda item: item.id)
    selected = _select(
        items,
        size=limit,
        seed=seed,
        min_per_group=0,
        min_safety=0,
    )
    return sorted(selected, key=lambda item: item.id)


def derive_eval(
    rows: Iterable[dict[str, Any]],
    groups: dict[str, tuple[str, ...]],
    *,
    seed: int = 20261031,
    size: int = 400,
) -> list[Complaint]:
    """The 2025-2026 ``frt``-half evaluation set, disjoint from the ``wam`` half."""
    resolved = resolve_complaints(rows, groups)
    candidates: list[dict[str, Any]] = []
    for row in resolved:
        received = _date(row.get("LDATE"))
        if not (TEST_START <= received <= TEST_END):
            continue
        if split_half(_text(row.get("ODINO"))) != "frt":
            continue
        candidates.append(row)
    screened = screen_narratives(candidates)
    items = [complaint_from_row(row) for row in screened.rows]
    selected = _select(
        items,
        size=size,
        seed=seed,
        min_per_group=EVAL_MIN_PER_GROUP,
        min_safety=EVAL_MIN_SAFETY,
    )
    return sorted(selected, key=lambda item: item.id)


def group_counts(
    items: Iterable[Complaint],
    groups: Iterable[str],
) -> dict[str, int]:
    """Count items per group id, including zero rows for every known group."""
    counts: Counter[str] = Counter(item.group for item in items if item.group is not None)
    return {group: counts.get(group, 0) for group in groups}
