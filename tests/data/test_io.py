"""The committed file formats: round trips, determinism and clear errors."""

from __future__ import annotations

import gzip
import hashlib

import pytest

from field_return_triage.data.complaints import complaint_from_row
from field_return_triage.data.io import (
    load_eval,
    load_library,
    load_recalls,
    load_weekly,
    write_eval,
    write_library,
    write_recalls,
    write_weekly,
)
from field_return_triage.data.recalls import derive_recalls, resolve_recalls
from field_return_triage.data.spec import load_groups
from field_return_triage.data.weekly import derive_weekly
from data_support import recall_row, resolved_row

GROUPS = load_groups()


def _items() -> list:
    rows = [
        resolved_row(ODINO="1", LDATE="20220601"),
        resolved_row(ODINO="2", LDATE="20220606", CRASH="Y"),
    ]
    return [complaint_from_row(row) for row in rows]


def test_library_round_trip_and_gzip_determinism(tmp_path) -> None:
    items = _items()
    first = tmp_path / "a.jsonl.gz"
    second = tmp_path / "b.jsonl.gz"
    digest = write_library(items, first)
    write_library(items, second)
    assert first.read_bytes() == second.read_bytes()
    assert digest == hashlib.sha256(first.read_bytes()).hexdigest()
    assert load_library(first) == items
    assert gzip.decompress(first.read_bytes()).count(b"\n") == 2


def test_eval_round_trip(tmp_path) -> None:
    path = tmp_path / "eval.jsonl"
    items = _items()
    digest = write_eval(items, path)
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert load_eval(path) == items
    assert not path.read_bytes().startswith(b"\x1f\x8b")


def test_weekly_round_trip(tmp_path) -> None:
    rows = derive_weekly(
        [
            resolved_row(ODINO="1", LDATE="20210104"),
            resolved_row(ODINO="2", LDATE="20210106"),
        ]
    )
    path = tmp_path / "weekly.csv.gz"
    digest = write_weekly(rows, path)
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert load_weekly(path) == rows
    assert gzip.decompress(path.read_bytes()).splitlines()[0] == (
        b"make,model,model_year,group,week,count"
    )


def test_recalls_round_trip(tmp_path) -> None:
    rows = derive_recalls(resolve_recalls([recall_row(CAMPNO="21V001000")], GROUPS))
    path = tmp_path / "recalls.csv"
    write_recalls(rows, path)
    assert load_recalls(path) == rows
    assert path.read_text(encoding="utf-8").splitlines()[0] == (
        "recall_id,make,model,model_year,group,report_date"
    )


def test_a_bad_weekly_header_names_the_file(tmp_path) -> None:
    path = tmp_path / "weekly.csv.gz"
    path.write_bytes(gzip.compress(b"wrong,header\n"))
    with pytest.raises(ValueError, match="header must be"):
        load_weekly(path)


def test_a_bad_jsonl_row_names_the_line(tmp_path) -> None:
    path = tmp_path / "eval.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid Complaint row"):
        load_eval(path)


def test_empty_files_are_empty_lists(tmp_path) -> None:
    library = tmp_path / "library.jsonl.gz"
    library.write_bytes(gzip.compress(b""))
    assert load_library(library) == []
