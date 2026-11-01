"""The single-group rule and the column drop (PLAN.md section 5)."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from field_return_triage.contracts import Complaint
from field_return_triage.data.complaints import (
    complaint_from_row,
    derive_library,
    resolve_complaints,
)
from field_return_triage.data.io import write_eval
from field_return_triage.data.spec import load_groups
from data_support import complaint_row

GROUPS = load_groups()


def _rows(*components: str, odino: str = "90000001", **overrides: object) -> list[dict[str, str]]:
    return [
        complaint_row(
            ODINO=odino,
            CMPLID=str(index + 1),
            COMPDESC=component,
            **overrides,
        )
        for index, component in enumerate(components)
    ]


def test_all_rows_in_one_group_is_kept() -> None:
    rows = _rows("AIR BAGS:FRONTAL", "AIR BAGS:SIDE")
    resolved = resolve_complaints(rows, GROUPS)
    assert len(resolved) == 1
    assert resolved[0]["component_group"] == "airbags"


def test_one_unmapped_row_excludes_the_whole_complaint() -> None:
    rows = _rows("AIR BAGS:FRONTAL", "ENGINE")
    assert resolve_complaints(rows, GROUPS) == []


def test_two_groups_exclude_the_whole_complaint() -> None:
    rows = _rows("AIR BAGS:FRONTAL", "FORWARD COLLISION AVOIDANCE:SOFTWARE")
    assert resolve_complaints(rows, GROUPS) == []


def test_non_vehicle_rows_are_out_of_scope() -> None:
    rows = _rows("AIR BAGS:FRONTAL", PROD_TYPE="T")
    assert resolve_complaints(rows, GROUPS) == []


def test_resolution_is_independent_of_input_order() -> None:
    rows = _rows("AIR BAGS:FRONTAL", "AIR BAGS:SIDE")
    forward = resolve_complaints(rows, GROUPS)
    backward = resolve_complaints(list(reversed(rows)), GROUPS)
    assert forward[0]["component_group"] == backward[0]["component_group"] == "airbags"


def test_derived_complaint_has_no_identity_or_location_field() -> None:
    row = complaint_row(
        ODINO="90000002",
        CITY="Cityville",
        STATE="ZZ",
        VIN="1HGCM82633A004352",
        STATE_OF_INCIDENT="ZZ",
        VEHICLE_OPERATOR="A Person",
        DEALER_NAME="Dealer Name",
        DEALER_TEL="555-000-0000",
        DEALER_CITY="Dealertown",
        DEALER_STATE="ZZ",
        DEALER_ZIP="00000",
    )
    row["component_group"] = "airbags"
    item = complaint_from_row(row)
    dumped = item.model_dump(mode="json")
    assert set(dumped) == set(Complaint.model_fields)
    serialised = json.dumps(dumped)
    for secret in (
        "Cityville",
        "1HGCM82633A004352",
        "A Person",
        "Dealer Name",
        "555-000-0000",
        "Dealertown",
    ):
        assert secret not in serialised


def test_written_eval_never_carries_a_dropped_column(tmp_path: Path) -> None:
    row = complaint_row(
        ODINO="90000003",
        CITY="Cityville",
        VIN="1HGCM82633A004352",
        DEALER_NAME="Dealer Name",
    )
    row["component_group"] = "airbags"
    path = tmp_path / "eval.jsonl"
    write_eval([complaint_from_row(row)], path)
    text = path.read_text(encoding="utf-8")
    assert "Cityville" not in text
    assert "1HGCM82633A004352" not in text
    assert "Dealer Name" not in text


def test_derive_library_only_keeps_the_train_window() -> None:
    rows = [
        *_rows("AIR BAGS:FRONTAL", odino="90000010", LDATE="20201231"),
        *_rows("AIR BAGS:FRONTAL", odino="90000011", LDATE="20241231"),
        *_rows("AIR BAGS:FRONTAL", odino="90000012", LDATE="20250101"),
    ]
    ids = {item.id for item in derive_library(rows, GROUPS)}
    assert ids == {"90000010", "90000011"}


def test_short_and_pii_narratives_are_dropped() -> None:
    rows = [
        *_rows("AIR BAGS:FRONTAL", odino="90000020", CDESCR="too short"),
        *_rows("AIR BAGS:FRONTAL", odino="90000021", CDESCR="Call me on 555-123-4567 to hear the rest of this long story about the dashboard failure."),
        *_rows("AIR BAGS:FRONTAL", odino="90000022"),
    ]
    ids = {item.id for item in derive_library(rows, GROUPS)}
    assert ids == {"90000022"}


def test_compressed_library_round_trip_is_clean(tmp_path: Path) -> None:
    rows = _rows("AIR BAGS:FRONTAL", odino="90000030")
    from field_return_triage.data.io import load_library, write_library

    path = tmp_path / "library.jsonl.gz"
    digest = write_library(derive_library(rows, GROUPS), path)
    assert load_library(path)[0].id == "90000030"
    assert gzip.decompress(path.read_bytes())  # a real gzip member
    assert len(digest) == 64
