"""KPI definitions for the technician feedback log (page text, PLAN.md section 4).

These are definitions, not results: the page shows acceptance rate, change reasons and
time to decision, and every value comes from the committed feedback log at build time.
An empty log gives ``None`` rather than a made-up zero.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from typing import Final

from field_return_triage.contracts import Decision, DecisionAction

__all__ = ["acceptance_rate", "change_reasons", "median_time_to_decision_s"]

_NO_REASON: Final[str] = "(no reason recorded)"


def acceptance_rate(decisions: Sequence[Decision]) -> float | None:
    """Share of decisions that accepted the card, or ``None`` for an empty log."""
    if not decisions:
        return None
    accepted = sum(1 for row in decisions if row.action is DecisionAction.ACCEPT)
    return accepted / len(decisions)


def change_reasons(decisions: Sequence[Decision]) -> Mapping[str, int]:
    """How often each change reason was given, sorted by reason text.

    A change always carries a reason (the contract enforces it); the placeholder exists
    only so a malformed historical row cannot break the page build.
    """
    counts: dict[str, int] = {}
    for row in decisions:
        if row.action is not DecisionAction.CHANGE:
            continue
        reason = (row.reason or "").strip() or _NO_REASON
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def median_time_to_decision_s(decisions: Sequence[Decision]) -> float | None:
    """Median seconds from card to decision, over the rows that recorded one."""
    values = [row.time_to_decision_s for row in decisions if row.time_to_decision_s is not None]
    if not values:
        return None
    return float(statistics.median(values))
