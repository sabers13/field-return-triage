"""Tiny row builders for the data-lane tests.

No test reads the real snapshot: fixtures are built in memory from the committed field
layouts, so the suite stays fast and offline.
"""

from __future__ import annotations

from field_return_triage.data.parse import COMPLAINT_FIELDS, RECALL_FIELDS

#: A clean narrative of at least 80 characters, mixed case as the 2022+ data is.
CLEAN_NARRATIVE = (
    "The dashboard went dark while driving and the warning light came on again. "
    "The dealer could not reproduce the fault."
)

COMPLAINT_DEFAULTS: dict[str, str] = {
    name: "" for name in COMPLAINT_FIELDS
} | {
    "CMPLID": "1",
    "ODINO": "10000001",
    "MAKETXT": "ACME",
    "MODELTXT": "MODEL A",
    "YEARTXT": "2021",
    "CRASH": "N",
    "FAILDATE": "20210501",
    "FIRE": "N",
    "INJURED": "0",
    "DEATHS": "0",
    "COMPDESC": "AIR BAGS:FRONTAL",
    "LDATE": "20210601",
    "CDESCR": CLEAN_NARRATIVE,
    "PROD_TYPE": "V",
}

RECALL_DEFAULTS: dict[str, str] = {
    name: "" for name in RECALL_FIELDS
} | {
    "RECORD_ID": "1",
    "CAMPNO": "21V020000",
    "MAKETXT": "ACME",
    "MODELTXT": "MODEL A",
    "YEARTXT": "2021",
    "COMPNAME": "AIR BAGS:FRONTAL",
    "RCLTYPECD": "V",
    "RCDATE": "20210120",
}


def complaint_row(**overrides: object) -> dict[str, str]:
    """One complaint row with every field present and a valid default."""
    row = dict(COMPLAINT_DEFAULTS)
    row.update({name: str(value) for name, value in overrides.items()})
    return row


def complaint_line(**overrides: object) -> str:
    """The TSV line for :func:`complaint_row`, in ``CMPL.txt`` field order."""
    row = complaint_row(**overrides)
    return "\t".join(row[name] for name in COMPLAINT_FIELDS)


def recall_row(**overrides: object) -> dict[str, str]:
    """One recall row with every field present and a valid default."""
    row = dict(RECALL_DEFAULTS)
    row.update({name: str(value) for name, value in overrides.items()})
    return row


def recall_line(**overrides: object) -> str:
    """The TSV line for :func:`recall_row`, in ``RCL.txt`` field order."""
    row = recall_row(**overrides)
    return "\t".join(row[name] for name in RECALL_FIELDS)


def resolved_row(**overrides: object) -> dict[str, object]:
    """A row already resolved by the single-group rule (has ``component_group``)."""
    row: dict[str, object] = complaint_row(**overrides)
    row["component_group"] = str(overrides.get("component_group", "airbags"))
    return row
