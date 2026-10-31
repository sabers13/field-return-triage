"""One extraction call: prompt, model answer, parse, quote check."""

from __future__ import annotations

from collections.abc import Mapping

from field_return_triage.contracts import Complaint, Extraction, QuoteCheck
from field_return_triage.extract.parse import parse_extraction
from field_return_triage.extract.prompt import build_messages
from field_return_triage.extract.quotecheck import check_quotes
from field_return_triage.extract.schema import ExtractionAnswer
from field_return_triage.llm.client import ChatClient

__all__ = ["extract"]

_EMPTY_CHECK = QuoteCheck(checked=0, passed=0)


def extract(
    complaint: Complaint,
    client: ChatClient,
    groups: Mapping[str, str],
) -> tuple[Extraction | None, QuoteCheck, str | None]:
    """``(extraction, quote check, failure reason)``.

    An empty, cut-off or unparseable answer returns ``None`` and the reason; the
    client is never asked again for the same complaint.
    """
    messages = build_messages(complaint, groups)
    reply = client.complete(messages, schema=ExtractionAnswer)
    extraction, reason = parse_extraction(reply.content)
    if extraction is None:
        return None, _EMPTY_CHECK, reason
    return extraction, check_quotes(extraction, complaint.narrative), None
