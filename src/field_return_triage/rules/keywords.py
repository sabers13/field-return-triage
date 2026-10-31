"""The deterministic safety keyword rule (PLAN.md section 6, baselines).

The list itself is data committed by the data lane (``data/safety_keywords.txt``) before
any model result exists, so the rule cannot be tuned to a model's answers. Matching is
case-insensitive over the raw narrative and returns the exact span that matched, so the
card can quote it like any other clue.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Final

__all__ = ["DEFAULT_KEYWORDS_PATH", "keyword_safety", "load_safety_keywords"]

DEFAULT_KEYWORDS_PATH: Final[Path] = Path("data/safety_keywords.txt")


def load_safety_keywords(path: Path = DEFAULT_KEYWORDS_PATH) -> tuple[str, ...]:
    """Read one keyword per line; blank lines and ``#`` comments are ignored.

    Duplicates are removed in first-seen order. An empty file is an error: it would
    silently disable the keyword rule, which is a safety decision, not a style choice.
    """
    keywords: list[str] = []
    seen: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        folded = line.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        keywords.append(line)
    if not keywords:
        msg = f"{path}: the safety keyword list is empty"
        raise ValueError(msg)
    return tuple(keywords)


def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    """A keyword matches its words in order, with any whitespace between them."""
    words = keyword.split()
    body = r"\s+".join(re.escape(word) for word in words)
    return re.compile(body, re.IGNORECASE)


def keyword_safety(narrative: str, keywords: Sequence[str]) -> str | None:
    """The earliest narrative span that matched a keyword, or ``None``.

    Ties at the same start position go to the longer span, then to the keyword that came
    first in the committed list, so the result is deterministic.
    """
    best_start = -1
    best_span: str | None = None
    for keyword in keywords:
        if not keyword.strip():
            continue
        match = _keyword_pattern(keyword).search(narrative)
        if match is None:
            continue
        span = match.group(0)
        if best_span is None or (match.start(), -len(span)) < (best_start, -len(best_span)):
            best_start, best_span = match.start(), span
    return best_span
