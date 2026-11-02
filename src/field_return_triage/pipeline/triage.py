"""One complaint through the whole flow (``PLAN.md`` section 4).

``triage_item`` is the single implementation: prompt ``e1`` -> one model answer ->
parse -> quote check -> hard rules -> neighbours -> suggestion -> card. It also returns
the call's usage, cost and duration, which the evaluation runner needs and the card
cannot carry.

Everything here is a pure function of its inputs plus the injected clock, so a replay
run is deterministic. The only decision the flow does not make is the technician's:
the card carries no close, scrap or return state.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

import numpy as np
from numpy.typing import NDArray

from field_return_triage.contracts import (
    UNCLEAR_GROUP,
    Complaint,
    Extraction,
    Neighbour,
    Priority,
    QuoteCheck,
    TriageCard,
)
from field_return_triage.extract.parse import parse_extraction
from field_return_triage.extract.prompt import build_messages
from field_return_triage.extract.quotecheck import check_quotes
from field_return_triage.extract.schema import ExtractionAnswer
from field_return_triage.llm.client import ChatClient
from field_return_triage.rules.hard_rules import build_card
from field_return_triage.rules.rulebook import Rulebook
from field_return_triage.similar.embedder import Embedder
from field_return_triage.similar.search import nearest

__all__ = [
    "EMPTY_CHECK",
    "CallStats",
    "render_card",
    "triage_item",
    "triage_one",
    "triage_text",
]

EMPTY_CHECK: Final[QuoteCheck] = QuoteCheck(checked=0, passed=0)

_PRIORITY_LABEL: Final[dict[Priority, str]] = {
    Priority.SAFETY: "1 (safety)",
    Priority.CLEAR_CLUES: "2 (clear clues)",
    Priority.HUMAN_READING: "3 (needs human reading)",
}


@dataclass(frozen=True, slots=True)
class CallStats:
    """What one model call cost and how long it took."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    duration_ms: float = 0.0
    failure: str | None = None


def _neighbours(
    complaint: Complaint,
    library: Sequence[Complaint],
    index: tuple[list[str], NDArray[np.float32]] | None,
    embedder: Embedder | None,
) -> tuple[Neighbour, ...]:
    """The 5 nearest past cases, or none when no index is available."""
    if index is not None and not index[0]:
        return ()
    try:
        found = nearest(complaint, library, index=index, embedder=embedder)
    except FileNotFoundError:
        # No `make index` yet: the card is still useful, it just has no neighbours.
        return ()
    return tuple(found)


def triage_item(
    complaint: Complaint,
    *,
    client: ChatClient,
    library: Sequence[Complaint],
    rulebook: Rulebook,
    groups: Mapping[str, str],
    keywords: Sequence[str],
    index: tuple[list[str], NDArray[np.float32]] | None = None,
    embedder: Embedder | None = None,
    now: datetime | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[TriageCard, CallStats]:
    """Run one complaint through the pipeline; return its card and call stats.

    An invalid model answer is a result, not an exception: the card is built from an
    empty ``unclear`` extraction, so it lands in human reading (or in safety when the
    keyword rule or the coded fields say so). The reason is kept in the call stats.
    """
    messages = build_messages(complaint, groups)
    started = clock()
    reply = client.complete(messages, schema=ExtractionAnswer)
    duration_ms = max(0.0, (clock() - started) * 1000.0)

    extraction, reason = parse_extraction(reply.content)
    if extraction is None:
        extraction = Extraction()
        quote_check = EMPTY_CHECK
    else:
        if extraction.component_group != UNCLEAR_GROUP and extraction.component_group not in groups:
            # The prompt lists the group ids and the answer must pick one of them. An
            # invented id is not a real group: map it to `unclear` so the hard rules
            # send the card to human reading (PLAN section 4, hard rule 2).
            extraction = extraction.model_copy(update={"component_group": UNCLEAR_GROUP})
        quote_check = check_quotes(extraction, complaint.narrative)

    found = _neighbours(complaint, library, index, embedder)
    card = build_card(
        complaint,
        extraction,
        quote_check,
        neighbours=found,
        rulebook=rulebook,
        model_id=client.settings.model_id,
        keywords=keywords,
        now=now,
    )
    stats = CallStats(
        input_tokens=reply.input_tokens,
        output_tokens=reply.output_tokens,
        cost_usd=reply.cost_usd,
        duration_ms=duration_ms,
        failure=reason,
    )
    return card, stats


def triage_one(
    complaint: Complaint,
    *,
    client: ChatClient,
    library: Sequence[Complaint],
    rulebook: Rulebook,
    groups: Mapping[str, str],
    keywords: Sequence[str],
    index: tuple[list[str], NDArray[np.float32]] | None = None,
    embedder: Embedder | None = None,
    now: datetime | None = None,
) -> TriageCard:
    """The card only; see :func:`triage_item` for the usage numbers."""
    card, _ = triage_item(
        complaint,
        client=client,
        library=library,
        rulebook=rulebook,
        groups=groups,
        keywords=keywords,
        index=index,
        embedder=embedder,
        now=now,
    )
    return card


def triage_text(
    text: str,
    *,
    complaint_id: str = "cli",
    client: ChatClient,
    library: Sequence[Complaint],
    rulebook: Rulebook,
    groups: Mapping[str, str],
    keywords: Sequence[str],
    index: tuple[list[str], NDArray[np.float32]] | None = None,
    embedder: Embedder | None = None,
    now: datetime | None = None,
) -> TriageCard:
    """Triage raw complaint text, as ``frt triage`` reads it."""
    narrative = text.strip()
    if not narrative:
        msg = "the complaint text is empty"
        raise ValueError(msg)
    created = now if now is not None else datetime.now(UTC)
    complaint = Complaint(id=complaint_id, narrative=narrative, received=created.date())
    return triage_one(
        complaint,
        client=client,
        library=library,
        rulebook=rulebook,
        groups=groups,
        keywords=keywords,
        index=index,
        embedder=embedder,
        now=created,
    )


def render_card(card: TriageCard) -> str:
    """A readable terminal view of one card. JSON is printed separately."""
    complaint = card.complaint
    lines = [
        f"Complaint {complaint.id} (received {complaint.received.isoformat()})",
        f"Priority {_PRIORITY_LABEL[card.priority]}"
        f" | human review: {'yes' if card.needs_human_review else 'no'}",
        "",
        "Narrative:",
        f"  {complaint.narrative.strip()}",
        "",
    ]
    if card.quotes:
        lines.append("Quotes checked against the narrative:")
        lines.extend(f"  - {quote}" for quote in card.quotes)
    else:
        lines.append("Quotes checked against the narrative: none passed")
    lines.append("")

    symptoms = list(card.extraction.symptoms)
    conditions = list(card.extraction.conditions)
    lines.append(
        "Clues: "
        + (
            ", ".join(f"{clue.kind} ({clue.quote})" for clue in (*symptoms, *conditions))
            or "none kept"
        )
    )
    lines.append("")
    lines.append("Suggested next step:")
    lines.extend(f"  test: {test}" for test in card.suggestion.tests)
    lines.extend(f"  inspect: {item}" for item in card.suggestion.inspect)
    lines.extend(f"  request: {item}" for item in card.suggestion.request)
    for reason in card.suggestion.reasons:
        lines.append(f"  why: {reason.text}")
    lines.append("")
    if card.neighbours:
        lines.append("Similar past cases:")
        lines.extend(
            f"  - {item.complaint_id} ({item.group}, score {item.score:.4f})"
            for item in card.neighbours
        )
    else:
        lines.append("Similar past cases: none available (run `make index`)")
    lines.append("")
    lines.append(
        f"Versions: model {card.model_id}, prompt {card.prompt_version}, "
        f"rulebook {card.rulebook_version}, hard rules {card.hard_rule_version}"
    )
    lines.append("A technician decides every case; the card never closes one.")
    return "\n".join(lines)
