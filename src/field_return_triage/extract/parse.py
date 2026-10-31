"""Parse a model answer into the frozen contract, or say why it is invalid.

The reason is a deterministic, human-readable string that ends up on the run record.
An invalid answer is never retried: the client only retries transport failures and
429s, and this module is pure.
"""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from field_return_triage.contracts import Extraction
from field_return_triage.extract.schema import ExtractionAnswer

__all__ = ["parse_extraction"]

_FENCE = re.compile(r"^```(?:json)?\s*(?P<body>.*?)\s*```$", re.DOTALL)


def _strip_fence(text: str) -> str:
    match = _FENCE.match(text)
    return match.group("body").strip() if match else text


def _summarise(error: ValidationError) -> str:
    parts: list[str] = []
    for item in error.errors()[:3]:
        location = ".".join(str(part) for part in item.get("loc", ())) or "answer"
        parts.append(f"{location}: {item.get('msg', 'invalid')}")
    return "; ".join(parts)


def parse_extraction(raw: str) -> tuple[Extraction | None, str | None]:
    """``(extraction, None)`` or ``(None, reason)``. Never retries an invalid answer.

    Every failure is reported as ``schema-invalid: <why>`` so a run record can count
    invalid answers with one rule and still show whether the cause was empty, cut-off,
    unparseable or a schema breach.
    """
    text = (raw or "").strip()
    if not text:
        return None, "schema-invalid: empty answer"
    text = _strip_fence(text)
    if not text:
        return None, "schema-invalid: empty answer"

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        cut_off = text.startswith(("{", "[")) and (
            text.count("{") > text.count("}") or text.count("[") > text.count("]")
        )
        if cut_off:
            return None, f"schema-invalid: cut-off answer: {exc.msg} at position {exc.pos}"
        return None, f"schema-invalid: unparseable answer: {exc.msg} at position {exc.pos}"

    if not isinstance(payload, dict):
        return None, "schema-invalid: answer is not a JSON object"

    try:
        answer = ExtractionAnswer.model_validate(payload)
    except ValidationError as exc:
        return None, f"schema-invalid: {_summarise(exc)}"

    try:
        extraction = Extraction.model_validate(answer.model_dump(mode="json"))
    except ValidationError as exc:
        return None, f"schema-invalid: {_summarise(exc)}"
    return extraction, None
