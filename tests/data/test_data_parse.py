"""Parsing the two flat files, and the field layout the spec pins."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from field_return_triage.data.parse import (
    COMPLAINT_FIELDS,
    COMPLAINT_FIELD_COUNT,
    RECALL_FIELDS,
    RECALL_FIELD_COUNT,
    parse_complaint_rows,
    parse_recall_rows,
    read_archive_lines,
)
from field_return_triage.data.spec import load_spec
from data_support import complaint_line, recall_line


def test_complaint_line_parses_every_named_field() -> None:
    rows = list(parse_complaint_rows([complaint_line(ODINO="12345678", CDESCR="hello")]))
    assert len(rows) == 1
    assert COMPLAINT_FIELD_COUNT == 51
    assert set(rows[0]) == set(COMPLAINT_FIELDS)
    assert rows[0]["ODINO"] == "12345678"
    assert rows[0]["CDESCR"] == "hello"


def test_recall_line_parses_every_named_field_and_strips_cr() -> None:
    rows = list(parse_recall_rows([recall_line(CAMPNO="21V001000") + "\r\n"]))
    assert RECALL_FIELD_COUNT == 29
    assert rows[0]["CAMPNO"] == "21V001000"
    assert rows[0]["RCDATE"] == "20210120"
    assert not any(value.endswith("\r") for value in rows[0].values())


def test_wrong_field_count_names_the_line() -> None:
    with pytest.raises(ValueError, match="complaint line 1: expected 51 fields, got 2"):
        list(parse_complaint_rows(["a\tb"]))
    with pytest.raises(ValueError, match="recall line 1: expected 29 fields, got 1"):
        list(parse_recall_rows(["only-one"]))


def test_blank_lines_are_skipped() -> None:
    rows = list(parse_complaint_rows([complaint_line(), "", "\n", complaint_line(ODINO="2")]))
    assert [row["ODINO"] for row in rows] == ["10000001", "2"]


def test_field_lists_partition_exactly_as_the_spec_says(repo_root: Path) -> None:
    spec = load_spec(repo_root / "data" / "nhtsa-spec.toml")
    columns = spec["columns"]
    kept = set(columns["complaint_kept"])
    dropped = set(columns["complaint_dropped"]) | set(columns["identity_location_dropped"])
    assert kept.isdisjoint(dropped)
    assert kept | dropped == set(COMPLAINT_FIELDS)
    assert len(kept) == 13
    assert set(columns["recall_kept"]).issubset(set(RECALL_FIELDS))


def test_reading_a_zip_member_without_extracting(tmp_path: Path) -> None:
    archive = tmp_path / "sample.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("SAMPLE.txt", complaint_line() + "\n")
    rows = list(parse_complaint_rows(read_archive_lines(archive, "SAMPLE.txt")))
    assert len(rows) == 1
    assert rows[0]["ODINO"] == "10000001"


def test_missing_zip_member_is_a_clear_error(tmp_path: Path) -> None:
    archive = tmp_path / "sample.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("SAMPLE.txt", "x\n")
    with pytest.raises(ValueError, match="member 'OTHER.txt' not found"):
        list(read_archive_lines(archive, "OTHER.txt"))
