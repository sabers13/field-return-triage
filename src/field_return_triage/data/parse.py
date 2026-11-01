"""Parsing for the NHTSA ODI flat files (``CMPL.txt`` / ``RCL.txt`` layouts).

The files are TAB delimited, UTF-8, with no header row and a fixed field count per row
(51 complaints, 29 recalls). We parse every field into a dict first, then the derivation
keeps only the columns the spec lists as kept and never writes an identity or location
column to a derived file.

Rows are read from the zipped downloads without extracting them. Line endings are
stripped per row: complaints are LF, recalls CRLF.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Final

__all__ = [
    "COMPLAINT_FIELDS",
    "COMPLAINT_FIELD_COUNT",
    "RECALL_FIELDS",
    "RECALL_FIELD_COUNT",
    "parse_complaint_rows",
    "parse_recall_rows",
    "read_archive_lines",
]

#: ``CMPL.txt`` field order (1-based list positions).
COMPLAINT_FIELDS: Final[tuple[str, ...]] = (
    "CMPLID",
    "ODINO",
    "MFR_NAME",
    "MAKETXT",
    "MODELTXT",
    "YEARTXT",
    "CRASH",
    "FAILDATE",
    "FIRE",
    "INJURED",
    "DEATHS",
    "COMPDESC",
    "CITY",
    "STATE",
    "VIN",
    "DATEA",
    "LDATE",
    "MILES",
    "OCCURENCES",
    "CDESCR",
    "CMPL_TYPE",
    "POLICE_RPT_YN",
    "PURCH_DT",
    "ORIG_OWNER_YN",
    "ANTI_BRAKES_YN",
    "CRUISE_CONT_YN",
    "NUM_CYLS",
    "DRIVE_TRAIN",
    "FUEL_SYS",
    "FUEL_TYPE",
    "TRANS_TYPE",
    "VEH_SPEED",
    "DOT",
    "TIRE_SIZE",
    "LOC_OF_TIRE",
    "TIRE_FAIL_TYPE",
    "ORIG_EQUIP_YN",
    "MANUF_DT",
    "SEAT_TYPE",
    "RESTRAINT_TYPE",
    "DEALER_NAME",
    "DEALER_TEL",
    "DEALER_CITY",
    "DEALER_STATE",
    "DEALER_ZIP",
    "PROD_TYPE",
    "REPAIRED_YN",
    "MEDICAL_ATTN",
    "VEHICLES_TOWED_YN",
    "STATE_OF_INCIDENT",
    "VEHICLE_OPERATOR",
)

#: ``RCL.txt`` field order (1-based list positions).
RECALL_FIELDS: Final[tuple[str, ...]] = (
    "RECORD_ID",
    "CAMPNO",
    "MAKETXT",
    "MODELTXT",
    "YEARTXT",
    "MFGCAMPNO",
    "COMPNAME",
    "MFGNAME",
    "BGMAN",
    "ENDMAN",
    "RCLTYPECD",
    "POTAFF",
    "ODATE",
    "INFLUENCED_BY",
    "MFGTXT",
    "RCDATE",
    "DATEA",
    "RPNO",
    "FMVSS",
    "DESC_DEFECT",
    "CONEQUENCE_DEFECT",
    "CORRECTIVE_ACTION",
    "NOTES",
    "RCL_CMPT_ID",
    "MFR_COMP_NAME",
    "MFR_COMP_DESC",
    "MFR_COMP_PTNO",
    "DO_NOT_DRIVE",
    "PARK_OUTSIDE",
)

COMPLAINT_FIELD_COUNT: Final = len(COMPLAINT_FIELDS)
RECALL_FIELD_COUNT: Final = len(RECALL_FIELDS)


def _parse_rows(
    lines: Iterable[str],
    fields: tuple[str, ...],
    label: str,
    *,
    skip_blank: bool,
) -> Iterator[dict[str, str]]:
    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip("\r\n")
        if not line.strip():
            if skip_blank:
                continue
            raise ValueError(f"{label} line {lineno}: blank row")
        values = line.split("\t")
        if len(values) != len(fields):
            raise ValueError(
                f"{label} line {lineno}: expected {len(fields)} fields, got {len(values)}"
            )
        yield dict(zip(fields, values, strict=True))


def parse_complaint_rows(lines: Iterable[str]) -> Iterator[dict[str, str]]:
    """Yield one dict per complaint component row, keyed by ``CMPL.txt`` names."""
    yield from _parse_rows(lines, COMPLAINT_FIELDS, "complaint", skip_blank=True)


def parse_recall_rows(lines: Iterable[str]) -> Iterator[dict[str, str]]:
    """Yield one dict per recall row, keyed by ``RCL.txt`` names and CR-stripped."""
    yield from _parse_rows(lines, RECALL_FIELDS, "recall", skip_blank=True)


def read_archive_lines(path: Path, member: str) -> Iterator[str]:
    """Read a text member from a zip download without extracting it to disk."""
    with zipfile.ZipFile(path) as archive:
        try:
            handle = archive.open(member)
        except KeyError as exc:
            names = ", ".join(archive.namelist())
            raise ValueError(f"{path}: member {member!r} not found (has {names})") from exc
        with handle, io.TextIOWrapper(handle, encoding="utf-8", newline="") as text:
            yield from text
