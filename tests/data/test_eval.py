"""The evaluation sample: halving, floors, the safety top-up and disjointness."""

from __future__ import annotations

import hashlib
import random

import pytest

from field_return_triage.data.complaints import derive_eval, derive_library, split_half
from field_return_triage.data.spec import load_groups
from data_support import complaint_row

GROUPS = load_groups()
COMPONENTS = {
    "airbags": "AIR BAGS:FRONTAL",
    "driver_assist_sensors": "FORWARD COLLISION AVOIDANCE:SOFTWARE",
    "exterior_lighting": "EXTERIOR LIGHTING:BRAKE LIGHTS",
    "wipers_washers": "VISIBILITY/WIPER",
}


def _half(odino: str) -> str:
    digest = hashlib.sha256(f"20261031:{odino}".encode()).hexdigest()
    return "wam" if int(digest, 16) % 2 == 0 else "frt"


def _test_pool(per_group: int, *, safe_every_other: bool = False) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for gid, component in COMPONENTS.items():
        for index in range(per_group):
            odino = f"92{list(COMPONENTS).index(gid):02d}{index:05d}"
            crash = "Y" if safe_every_other and index % 2 == 0 else "N"
            rows.append(
                complaint_row(
                    ODINO=odino,
                    CMPLID="1",
                    COMPDESC=component,
                    LDATE="20250601",
                    CRASH=crash,
                )
            )
    return rows


def test_halving_rule_is_the_spec_formula() -> None:
    for index in range(40):
        odino = f"93{index:06d}"
        assert split_half(odino) == _half(odino)


def test_eval_keeps_only_frt_half_and_the_test_window() -> None:
    rows = _test_pool(60)
    items = derive_eval(rows, GROUPS, size=100)
    assert items
    assert all(split_half(item.id) == "frt" for item in items)
    assert all(item.received.year >= 2025 for item in items)


def test_eval_is_disjoint_from_the_wam_half() -> None:
    rows = _test_pool(100)
    eval_ids = {item.id for item in derive_eval(rows, GROUPS, size=100)}
    wam_ids = {row["ODINO"] for row in rows if _half(row["ODINO"]) == "wam"}
    assert eval_ids
    assert eval_ids.isdisjoint(wam_ids)


def test_library_and_eval_do_not_overlap() -> None:
    train = [
        complaint_row(ODINO=f"94{index:06d}", COMPDESC=COMPONENTS["airbags"], LDATE="20220601")
        for index in range(20)
    ]
    test = _test_pool(60)
    library_ids = {item.id for item in derive_library(train + test, GROUPS, limit=20_000)}
    eval_ids = {item.id for item in derive_eval(train + test, GROUPS, size=100)}
    assert library_ids.isdisjoint(eval_ids)


def test_eval_meets_the_group_floor_and_the_size() -> None:
    items = derive_eval(_test_pool(200), GROUPS, size=100)
    assert len(items) == 100
    counts = {group: sum(1 for item in items if item.group == group) for group in COMPONENTS}
    assert set(counts) == set(COMPONENTS)
    assert all(count >= 20 for count in counts.values()), counts


def test_eval_is_safety_topped_up_to_the_floor() -> None:
    items = derive_eval(_test_pool(200, safe_every_other=True), GROUPS, size=100)
    safety = sum(1 for item in items if item.coded_safety)
    assert safety >= 80
    assert len(items) == 100


def test_eval_seed_is_deterministic_under_shuffled_input() -> None:
    rows = _test_pool(100)
    first = derive_eval(rows, GROUPS, size=100)
    shuffled = list(rows)
    random.Random(11).shuffle(shuffled)
    second = derive_eval(shuffled, GROUPS, size=100)
    assert [item.id for item in first] == [item.id for item in second]


def test_eval_refuses_to_overdraw_the_pool() -> None:
    with pytest.raises(ValueError, match="cannot draw"):
        derive_eval(_test_pool(5), GROUPS, size=100)


def test_eval_rejects_a_size_below_the_group_minimum() -> None:
    with pytest.raises(ValueError, match="cannot cover"):
        derive_eval(_test_pool(100), GROUPS, size=10)
