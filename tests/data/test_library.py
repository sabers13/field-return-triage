"""The library sample: stratification, the cap, the seed and determinism."""

from __future__ import annotations

import random

from field_return_triage.data.complaints import derive_library
from field_return_triage.data.spec import load_groups
from data_support import complaint_row

GROUPS = load_groups()
AIRBAG = "AIR BAGS:FRONTAL"
ASSIST = "FORWARD COLLISION AVOIDANCE:SOFTWARE"


def _pool(group_components: dict[str, int]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for offset, (component, count) in enumerate(group_components.items()):
        for index in range(count):
            rows.append(
                complaint_row(
                    ODINO=f"91{offset:02d}{index:05d}",
                    CMPLID="1",
                    COMPDESC=component,
                )
            )
    return rows


def test_limit_is_shared_in_proportion_to_the_pool() -> None:
    items = derive_library(_pool({AIRBAG: 10, ASSIST: 10}), GROUPS, limit=10)
    assert len(items) == 10
    assert sum(1 for item in items if item.group == "airbags") == 5
    assert sum(1 for item in items if item.group == "driver_assist_sensors") == 5


def test_a_small_group_contributes_everything_it_has() -> None:
    # 10 + 2 items, cap 12: the proportional shares are exactly the two pool sizes.
    items = derive_library(_pool({AIRBAG: 10, ASSIST: 2}), GROUPS, limit=12)
    assert sum(1 for item in items if item.group == "driver_assist_sensors") == 2
    assert len(items) == 12


def test_limit_above_the_pool_returns_everything_sorted_by_id() -> None:
    rows = _pool({AIRBAG: 3})
    items = derive_library(rows, GROUPS, limit=20_000)
    assert [item.id for item in items] == sorted(item.id for item in items)
    assert len(items) == 3


def test_the_seed_is_deterministic_under_shuffled_input() -> None:
    rows = _pool({AIRBAG: 30, ASSIST: 30})
    first = derive_library(rows, GROUPS, limit=10, seed=20261031)
    shuffled = list(rows)
    random.Random(7).shuffle(shuffled)
    second = derive_library(shuffled, GROUPS, limit=10, seed=20261031)
    assert [item.id for item in first] == [item.id for item in second]


def test_a_different_seed_draws_a_different_sample() -> None:
    rows = _pool({AIRBAG: 30, ASSIST: 30})
    first = {item.id for item in derive_library(rows, GROUPS, limit=10, seed=20261031)}
    second = {item.id for item in derive_library(rows, GROUPS, limit=10, seed=1)}
    assert first != second


def test_a_non_positive_limit_is_rejected() -> None:
    import pytest

    with pytest.raises(ValueError, match="limit must be positive"):
        derive_library([], GROUPS, limit=0)
