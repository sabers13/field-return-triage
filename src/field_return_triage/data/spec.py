"""The binding NHTSA snapshot spec and the component-group mapping (PLAN.md section 5).

``data/nhtsa-spec.toml`` and ``data/groups.toml`` are copied byte for byte from scout X0
and never edited here. This module only reads them, normalises component labels exactly
as the spec says, and exposes the snapshot constants the derivation uses.

The PII patterns are also copied from the spec, as module constants, so the screen does
not depend on the process working directory. ``tests/data/test_spec.py`` checks the
constants against the committed TOML, so the two cannot drift.
"""

from __future__ import annotations

import re
import tomllib
from datetime import date
from pathlib import Path
from typing import Any, Final

__all__ = [
    "DEFAULT_GROUPS_PATH",
    "DEFAULT_SPEC_PATH",
    "PII_PATTERNS",
    "SNAPSHOT_DATE",
    "SPLIT_KEY_PREFIX",
    "TEST_END",
    "TEST_START",
    "TRAIN_END",
    "TRAIN_START",
    "load_groups",
    "load_spec",
    "map_component",
    "normalise_component",
]

DEFAULT_SPEC_PATH: Final[Path] = Path("data/nhtsa-spec.toml")
DEFAULT_GROUPS_PATH: Final[Path] = Path("data/groups.toml")

#: The snapshot the committed derived data was built from.
SNAPSHOT_DATE: Final = date(2026, 10, 31)

#: Split window fixed by the spec's ``[split]`` table.
TRAIN_START: Final = date(2020, 1, 1)
TRAIN_END: Final = date(2024, 12, 31)
TEST_START: Final = date(2025, 1, 1)
TEST_END: Final = SNAPSHOT_DATE

#: The half-split key prefix from ``[split].halving_key_prefix``.
SPLIT_KEY_PREFIX: Final = "20261031:"

#: ``[pii.patterns]`` copied verbatim. Names are the spec keys, in spec order.
PII_PATTERNS: Final[tuple[tuple[str, str], ...]] = (
    ("vin17", r"\b[A-HJ-NPR-Z0-9]{17}\b"),
    ("email", r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
    (
        "phone_us",
        r"(?<!\d)(?:\+?1[\s.\-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.\-])\d{3}[\s.\-]\d{4}(?!\d)",
    ),
    (
        "street",
        r"\b\d{1,6}\s+(?:[A-Z][A-Za-z.\-]*\s+){1,4}"
        r"(?:STREET|ST|AVENUE|AVE|ROAD|RD|BOULEVARD|BLVD|DRIVE|DR|LANE|LN|COURT|CT|"
        r"PLACE|PL|WAY|HIGHWAY|HWY|PARKWAY|PKWY|CIRCLE|CIR|TERRACE|TER|TRAIL|TRL|"
        r"ALLEY|PLAZA|SQUARE|SQ)\b",
    ),
)


def load_spec(path: Path = DEFAULT_SPEC_PATH) -> dict[str, Any]:
    """Read a copied ``nhtsa-spec.toml`` and reject a file of the wrong schema."""
    with path.open("rb") as handle:
        spec = tomllib.load(handle)
    if spec.get("schema") != "nhtsa-odi-snapshot-spec":
        raise ValueError(f"{path}: not a nhtsa-odi-snapshot-spec file")
    return spec


def load_groups(path: Path = DEFAULT_GROUPS_PATH) -> dict[str, tuple[str, ...]]:
    """Group id -> raw component prefixes, in the order the file lists them."""
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    groups: dict[str, tuple[str, ...]] = {}
    for entry in data.get("group", []):
        group_id = str(entry.get("id", "")).strip()
        prefixes = tuple(str(prefix) for prefix in entry.get("prefixes", []))
        if not group_id or not prefixes:
            raise ValueError(f"{path}: every group needs an id and at least one prefix")
        if group_id in groups:
            raise ValueError(f"{path}: duplicate group id {group_id!r}")
        groups[group_id] = prefixes
    if not groups:
        raise ValueError(f"{path}: the group list is empty")
    return groups


def normalise_component(value: str) -> str:
    """Trim, uppercase, collapse whitespace and remove spaces around ``:``."""
    collapsed = " ".join(value.split()).upper()
    return re.sub(r"\s*:\s*", ":", collapsed)


def map_component(component: str, groups: dict[str, tuple[str, ...]]) -> str | None:
    """The single group for a raw label, or ``None`` for unmapped/multi-group.

    A prefix matches when the normalised value equals it or starts with ``prefix:``.
    The longest matching prefix wins; an identical-prefix tie breaks on the group id so
    the answer never depends on dict order.
    """
    value = normalise_component(component)
    if not value:
        return None
    best: tuple[int, str] | None = None
    for group_id in sorted(groups):
        for prefix in groups[group_id]:
            candidate = normalise_component(prefix)
            if not candidate:
                continue
            if value == candidate or value.startswith(f"{candidate}:"):
                key = (len(candidate), group_id)
                if best is None or key > best:
                    best = key
    return None if best is None else best[1]
