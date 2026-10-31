"""The quote check: every clue must quote the complaint verbatim (PLAN §4).

A quote passes when it occurs in the narrative after whitespace normalisation and
case folding. Punctuation, wording and word order must still match: paraphrases fail.
A failing clue stays in :class:`QuoteCheck.dropped` so the caller can count it and
drop it from the card.
"""

from __future__ import annotations

from typing import Literal

from field_return_triage.contracts import (
    DroppedClue,
    Extraction,
    QuoteCheck,
)

__all__ = ["check_quotes", "normalise", "quote_passes"]

_SAFETY_KIND = "safety_quote"
_MILEAGE_KIND = "mileage"
_FAULT_CODE_KIND = "fault_code"

_Field = Literal["safety", "symptoms", "conditions", "fault_codes", "mileage"]


def normalise(text: str) -> str:
    """Whitespace-normalised, case-folded text used by the quote check."""
    return " ".join(text.split()).casefold()


def quote_passes(quote: str, narrative: str) -> bool:
    """True when the quote is a verbatim span of the narrative."""
    cleaned = normalise(quote)
    if not cleaned:
        return False
    return cleaned in normalise(narrative)


def check_quotes(extraction: Extraction, narrative: str) -> QuoteCheck:
    """Check every quote the extraction carries and count pass/drop."""
    checked = 0
    passed = 0
    dropped: list[DroppedClue] = []

    def check(field: _Field, kind: str, quote: str) -> None:
        nonlocal checked, passed
        checked += 1
        if quote_passes(quote, narrative):
            passed += 1
        else:
            dropped.append(DroppedClue(field=field, kind=kind, quote=quote))

    if extraction.safety_quote is not None:
        check("safety", _SAFETY_KIND, extraction.safety_quote)
    for symptom in extraction.symptoms:
        check("symptoms", symptom.kind, symptom.quote)
    for condition in extraction.conditions:
        check("conditions", condition.kind, condition.quote)
    for fault_code in extraction.fault_codes:
        check("fault_codes", _FAULT_CODE_KIND, fault_code.quote)
    if extraction.mileage is not None:
        check("mileage", _MILEAGE_KIND, extraction.mileage.quote)

    return QuoteCheck(checked=checked, passed=passed, dropped=tuple(dropped))
