"""The rulebook: condition or symptom kind -> test, inspection, and information to request.

The rulebook is data, not code (``config/rulebook.toml``). This module loads and
validates it once; everything downstream treats it as immutable. The shipped file is an
example to adapt to a lab's own test catalogue (PLAN.md section 4), so the loader checks
the shape and the vocabulary, never the individual test names.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from field_return_triage.contracts import (
    RULEBOOK_VERSION,
    ConditionKind,
    SymptomKind,
)

__all__ = [
    "RULEBOOK_PATH",
    "RULEBOOK_VERSION",
    "Rule",
    "Rulebook",
    "load_rulebook",
]

RULEBOOK_PATH: Final[Path] = Path("config/rulebook.toml")

#: Every kind the rulebook may name; symptom and condition kinds share one table.
_KINDS: Final[frozenset[str]] = frozenset(
    {kind.value for kind in SymptomKind} | {kind.value for kind in ConditionKind}
)


@dataclass(frozen=True, slots=True)
class Rule:
    """What one kind suggests: the test(s), what to inspect, what to ask for."""

    tests: tuple[str, ...]
    inspect: tuple[str, ...] = ()
    request: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.tests:
            msg = "a rule needs at least one suggested test"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Rulebook:
    """The loaded rulebook: one rule per kind plus the standard-test fallback."""

    version: str
    by_kind: Mapping[str, Rule]
    fallback_test: str
    fallback_inspect: tuple[str, ...] = ()
    fallback_request: tuple[str, ...] = ()


def _strings(value: Any, where: str) -> tuple[str, ...]:
    """Read a TOML list of non-empty strings, or raise with the exact location."""
    if value is None:
        return ()
    if not isinstance(value, list):
        msg = f"{where} must be a list of strings"
        raise ValueError(msg)
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            msg = f"{where} must hold non-empty strings"
            raise ValueError(msg)
        items.append(item.strip())
    return tuple(items)


def _table(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        msg = f"{where} must be a TOML table"
        raise ValueError(msg)
    return value


def load_rulebook(path: Path = RULEBOOK_PATH) -> Rulebook:
    """Load and validate ``path`` as a rulebook.

    Raises ``ValueError`` for a wrong version, an unknown kind, or a malformed rule, so a
    broken rulebook fails loudly instead of silently falling back to the standard test.
    """
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    version = data.get("version")
    if version != RULEBOOK_VERSION:
        msg = f"{path}: version must be {RULEBOOK_VERSION!r}, got {version!r}"
        raise ValueError(msg)

    fallback = _table(data.get("fallback"), f"{path}: fallback")
    fallback_test = fallback.get("test")
    if not isinstance(fallback_test, str) or not fallback_test.strip():
        msg = f"{path}: fallback.test must be a non-empty string"
        raise ValueError(msg)

    kinds = _table(data.get("kinds"), f"{path}: kinds")
    unknown = sorted(set(kinds) - _KINDS)
    if unknown:
        msg = f"{path}: unknown kinds {unknown}; allowed are {sorted(_KINDS)}"
        raise ValueError(msg)

    by_kind: dict[str, Rule] = {}
    for kind, raw in kinds.items():
        where = f"{path}: kinds.{kind}"
        table = _table(raw, where)
        by_kind[kind] = Rule(
            tests=_strings(table.get("tests"), f"{where}.tests"),
            inspect=_strings(table.get("inspect"), f"{where}.inspect"),
            request=_strings(table.get("request"), f"{where}.request"),
        )

    return Rulebook(
        version=version,
        by_kind=MappingProxyType(by_kind),
        fallback_test=fallback_test.strip(),
        fallback_inspect=_strings(fallback.get("inspect"), f"{path}: fallback.inspect"),
        fallback_request=_strings(fallback.get("request"), f"{path}: fallback.request"),
    )
