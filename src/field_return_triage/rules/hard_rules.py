"""Hard rules ``hr1``: safety first, then clear clues, then human reading.

Exactly the rules fixed by ``PLAN.md`` section 4, as pure functions over the extraction,
the quote check, the keyword rule and the coded crash/fire/injury fields:

1. Safety (model flag, keyword rule, or coded fields) -> priority 1 and human review.
   Nothing can demote it.
2. An unclear component group, or no clue that passed the quote check -> priority 3 and
   "needs human reading".
3. Every card lists its reasons, its quotes and the model, prompt, rulebook and hard-rule
   versions.
4. There is no automatic close, scrap or return state. The card type has no such field,
   and nothing here invents one.

The suggestion comes from the rulebook; the card is assembled from all of the above and
nothing else. A technician decides every case downstream.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Final

from field_return_triage.contracts import (
    PROMPT_VERSION,
    UNCLEAR_GROUP,
    Clue,
    Complaint,
    Extraction,
    FaultCode,
    Neighbour,
    Priority,
    QuoteCheck,
    Reason,
    Suggestion,
    TriageCard,
)
from field_return_triage.rules.keywords import keyword_safety
from field_return_triage.rules.rulebook import Rulebook

__all__ = [
    "HARD_RULE_VERSION",
    "build_card",
    "decides_safety",
    "route",
    "suggest",
]

HARD_RULE_VERSION: Final[str] = "hr1"

#: Kinds that carry no specific failure indication and so suggest nothing on their own.
_GENERIC_KINDS: Final[frozenset[str]] = frozenset({"other"})

_FALLBACK_REASON: Final[str] = (
    "no condition and no specific symptom passed the quote check: "
    "run the standard test and ask for the missing information"
)


def _kept_clues(clues: Sequence[Clue], field: str, quote_check: QuoteCheck) -> tuple[Clue, ...]:
    """The clues that passed the quote check, in extraction order."""
    dropped = {(row.kind, row.quote) for row in quote_check.dropped if row.field == field}
    return tuple(clue for clue in clues if (clue.kind, clue.quote) not in dropped)


def _kept_fault_codes(extraction: Extraction, quote_check: QuoteCheck) -> tuple[FaultCode, ...]:
    dropped = {row.quote for row in quote_check.dropped if row.field == "fault_codes"}
    return tuple(item for item in extraction.fault_codes if item.quote not in dropped)


def _kept_mileage_quote(extraction: Extraction, quote_check: QuoteCheck) -> str | None:
    if extraction.mileage is None:
        return None
    if any(row.field == "mileage" for row in quote_check.dropped):
        return None
    return extraction.mileage.quote


def _safety_quote_kept(extraction: Extraction, quote_check: QuoteCheck) -> bool:
    return not any(row.field == "safety" for row in quote_check.dropped)


def _safety_findings(
    complaint: Complaint,
    extraction: Extraction,
    keyword_quote: str | None,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Why the case is safety-relevant, as ``(text, quotes)`` in a fixed order."""
    findings: list[tuple[str, tuple[str, ...]]] = []
    if extraction.safety_relevant:
        quote = extraction.safety_quote or ""
        text = "the model marked the complaint safety-relevant"
        findings.append((f"{text}: {quote}" if quote else text, (quote,) if quote else ()))
    if keyword_quote:
        findings.append(
            (f"a safety keyword appears in the complaint: {keyword_quote}", (keyword_quote,))
        )
    coded = [
        name
        for name, flagged in (
            ("crash", complaint.crash),
            ("fire", complaint.fire),
            ("injury", complaint.injury),
        )
        if flagged
    ]
    if coded:
        findings.append((f"the coded fields flag {', '.join(coded)}", ()))
    return tuple(findings)


def decides_safety(
    complaint: Complaint,
    extraction: Extraction,
    keyword_quote: str | None,
) -> tuple[bool, tuple[str, ...]]:
    """``(safety, reasons)`` for one complaint, in a fixed order.

    Safety is the model's flag OR the keyword rule OR the coded crash/fire/injury fields
    (``PLAN.md`` section 4, hard rule 1). The reasons are plain text; the matching quotes
    are attached when the card is assembled.
    """
    findings = _safety_findings(complaint, extraction, keyword_quote)
    return bool(findings), tuple(text for text, _ in findings)


def route(
    complaint: Complaint,
    extraction: Extraction,
    quote_check: QuoteCheck,
    *,
    safety: bool,
) -> tuple[Priority, bool]:
    """``(priority, needs_human_review)`` per the hard rules.

    Safety wins over every other branch and can never be demoted: priority 1 and human
    review. The coded fields are re-checked here so a caller cannot lose safety by
    passing ``safety=False``. Below that, an unclear group or no passing clue sends the
    card to human reading (priority 3); otherwise it is a clear-clue card (priority 2).
    """
    if safety or complaint.coded_safety:
        return Priority.SAFETY, True
    if extraction.component_group == UNCLEAR_GROUP or quote_check.passed == 0:
        return Priority.HUMAN_READING, True
    return Priority.CLEAR_CLUES, False


def _dedupe(items: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


def suggest(
    extraction: Extraction,
    quote_check: QuoteCheck,
    rulebook: Rulebook,
) -> Suggestion:
    """The rulebook's next test(s), with one reason per kind that points at its quotes.

    Only clues that passed the quote check are used. When nothing specific is left, the
    suggestion is the standard test plus the information that would change the next test
    (``PLAN.md`` section 4), and the reason says so instead of inventing a quote.
    """
    conditions = _kept_clues(extraction.conditions, "conditions", quote_check)
    symptoms = _kept_clues(extraction.symptoms, "symptoms", quote_check)

    matched: dict[str, list[str]] = {}
    for clue in (*conditions, *symptoms):
        if clue.kind in _GENERIC_KINDS or clue.kind not in rulebook.by_kind:
            continue
        matched.setdefault(clue.kind, []).append(clue.quote)

    if not matched:
        quotes = _dedupe([clue.quote for clue in (*conditions, *symptoms)])
        return Suggestion(
            tests=(rulebook.fallback_test,),
            inspect=rulebook.fallback_inspect,
            request=rulebook.fallback_request,
            reasons=(Reason(text=_FALLBACK_REASON, quotes=quotes),),
        )

    tests: list[str] = []
    inspect: list[str] = []
    request: list[str] = []
    reasons: list[Reason] = []
    for kind, kind_quotes in matched.items():
        rule = rulebook.by_kind[kind]
        tests.extend(rule.tests)
        inspect.extend(rule.inspect)
        request.extend(rule.request)
        reasons.append(
            Reason(
                text=f"{kind} indicated: {rule.tests[0]}",
                quotes=_dedupe(kind_quotes),
            )
        )

    # A fault code is the cheapest thing that turns a symptom into a targeted test, so
    # ask for it whenever the extractor found none.
    if not _kept_fault_codes(extraction, quote_check):
        request.append("fault codes")

    return Suggestion(
        tests=_dedupe(tests),
        inspect=_dedupe(inspect),
        request=_dedupe(request),
        reasons=tuple(reasons),
    )


def _card_quotes(
    extraction: Extraction,
    quote_check: QuoteCheck,
    keyword_quote: str | None,
) -> tuple[str, ...]:
    """Every quote the card can honestly show, in reading order."""
    quotes: list[str] = []
    if extraction.safety_quote and _safety_quote_kept(extraction, quote_check):
        quotes.append(extraction.safety_quote)
    if keyword_quote:
        quotes.append(keyword_quote)
    quotes.extend(clue.quote for clue in _kept_clues(extraction.symptoms, "symptoms", quote_check))
    quotes.extend(
        clue.quote for clue in _kept_clues(extraction.conditions, "conditions", quote_check)
    )
    quotes.extend(item.quote for item in _kept_fault_codes(extraction, quote_check))
    mileage_quote = _kept_mileage_quote(extraction, quote_check)
    if mileage_quote:
        quotes.append(mileage_quote)
    return _dedupe(quotes)


def _routing_reason(
    extraction: Extraction,
    quote_check: QuoteCheck,
    *,
    priority: Priority,
) -> Reason:
    if priority is Priority.SAFETY:
        return Reason(
            text="safety wins over every other rule: priority 1 and human review",
            quotes=(),
        )
    if priority is Priority.HUMAN_READING:
        if extraction.component_group == UNCLEAR_GROUP and quote_check.passed == 0:
            why = "the component group is unclear and no clue passed the quote check"
        elif extraction.component_group == UNCLEAR_GROUP:
            why = "the component group is unclear"
        else:
            why = "no clue passed the quote check"
        return Reason(text=f"{why}: needs human reading", quotes=())
    kept = _card_quotes(extraction, quote_check, None)
    count = len(kept)
    noun = "clue" if count == 1 else "clues"
    return Reason(text=f"clear clues: {count} {noun} passed the quote check", quotes=kept)


def build_card(
    complaint: Complaint,
    extraction: Extraction,
    quote_check: QuoteCheck,
    *,
    neighbours: Sequence[Neighbour],
    rulebook: Rulebook,
    model_id: str,
    keywords: Sequence[str],
    now: datetime | None = None,
) -> TriageCard:
    """Assemble the technician-facing card. Pure: the same inputs give the same card.

    ``now`` is injected so tests and replay runs are deterministic; it defaults to the
    current UTC time. The card carries no closure state: see :class:`TriageCard`.
    """
    keyword_quote = keyword_safety(complaint.narrative, keywords)
    safety, _ = decides_safety(complaint, extraction, keyword_quote)
    priority, needs_human_review = route(complaint, extraction, quote_check, safety=safety)
    suggestion = suggest(extraction, quote_check, rulebook)

    reasons = [
        Reason(text=text, quotes=quotes)
        for text, quotes in _safety_findings(complaint, extraction, keyword_quote)
    ]
    reasons.append(_routing_reason(extraction, quote_check, priority=priority))

    return TriageCard(
        card_id=f"{complaint.id}:{model_id}",
        complaint=complaint,
        extraction=extraction,
        quote_check=quote_check,
        priority=priority,
        needs_human_review=needs_human_review,
        reasons=tuple(reasons),
        quotes=_card_quotes(extraction, quote_check, keyword_quote),
        neighbours=tuple(neighbours),
        suggestion=suggestion,
        model_id=model_id,
        prompt_version=PROMPT_VERSION,
        rulebook_version=rulebook.version,
        hard_rule_version=HARD_RULE_VERSION,
        created_at=now if now is not None else datetime.now(UTC),
    )
