"""Prompt ``e1`` extraction: schema, prompt, parse, quote check, one-call runner."""

from __future__ import annotations

from field_return_triage.extract.parse import parse_extraction
from field_return_triage.extract.prompt import PROMPT_VERSION, build_messages
from field_return_triage.extract.quotecheck import check_quotes, normalise, quote_passes
from field_return_triage.extract.run import extract
from field_return_triage.extract.schema import ExtractionAnswer

__all__ = [
    "PROMPT_VERSION",
    "ExtractionAnswer",
    "build_messages",
    "check_quotes",
    "extract",
    "normalise",
    "parse_extraction",
    "quote_passes",
]
