"""R1 data lane: the NHTSA fetch, derivation, PII screen and splits.

Public surface (``docs/INTERFACES.md`` section 3):

* :func:`load_groups`, :func:`map_component` - the binding ``groups.toml`` mapping;
* :func:`pii_reason` - the spec's PII screen;
* :func:`derive_library`, :func:`derive_eval` - the committed sample sets;
* :func:`derive_weekly`, :func:`derive_recalls` - the trend tables;
* :func:`write_*` / :func:`load_*` - the committed file formats.

``data_main`` (in :mod:`data.cli`) runs the whole derivation and writes ``STATS.md`` and
``CHECKSUMS.txt``.
"""

from __future__ import annotations

from field_return_triage.data.complaints import (
    EVAL_MIN_PER_GROUP,
    EVAL_MIN_SAFETY,
    MIN_NARRATIVE_CHARS,
    derive_eval,
    derive_library,
    resolve_complaints,
    screen_narratives,
    split_half,
)
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
from field_return_triage.data.pii import pii_reason
from field_return_triage.data.recalls import derive_recalls, resolve_recalls
from field_return_triage.data.spec import (
    SNAPSHOT_DATE,
    load_groups,
    load_spec,
    map_component,
)
from field_return_triage.data.weekly import derive_weekly

__all__ = [
    "EVAL_MIN_PER_GROUP",
    "EVAL_MIN_SAFETY",
    "MIN_NARRATIVE_CHARS",
    "SNAPSHOT_DATE",
    "derive_eval",
    "derive_library",
    "derive_recalls",
    "derive_weekly",
    "load_eval",
    "load_groups",
    "load_library",
    "load_recalls",
    "load_spec",
    "load_weekly",
    "map_component",
    "pii_reason",
    "resolve_complaints",
    "resolve_recalls",
    "screen_narratives",
    "split_half",
    "write_eval",
    "write_library",
    "write_recalls",
    "write_weekly",
]
