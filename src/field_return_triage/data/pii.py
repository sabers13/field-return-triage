"""The PII screen from the binding spec (PLAN.md section 5).

A narrative that matches any pattern is dropped whole; nothing is redacted in place.
The patterns are the spec's four normative regexes, copied in :mod:`data.spec`:

* a 17-character VIN,
* an e-mail address,
* a US phone number,
* a street address (number, capitalised words, street suffix).

The screen is deliberately conservative. A dropped narrative is counted in
``data/STATS.md``; the drop itself never appears in a committed derived file.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Final

from field_return_triage.data.spec import PII_PATTERNS

__all__ = ["PII_PATTERN_NAMES", "pii_matches", "pii_reason"]

PII_PATTERN_NAMES: Final[tuple[str, ...]] = tuple(name for name, _ in PII_PATTERNS)


@lru_cache(maxsize=1)
def _compiled() -> tuple[tuple[str, re.Pattern[str]], ...]:
    return tuple((name, re.compile(pattern)) for name, pattern in PII_PATTERNS)


def pii_matches(narrative: str) -> tuple[str, ...]:
    """Every pattern name that matches, in spec order (may be empty)."""
    return tuple(name for name, pattern in _compiled() if pattern.search(narrative))


def pii_reason(narrative: str) -> str | None:
    """The first pattern that matches, or ``None`` when the narrative is clean."""
    matches = pii_matches(narrative)
    return matches[0] if matches else None
