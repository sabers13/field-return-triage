"""The wire schema the model answers with (prompt ``e1``).

This is the JSON-schema shape handed to the endpoint's structured-output parameter.
It is deliberately separate from the frozen :class:`~field_return_triage.contracts.
Extraction` contract: the wire schema is what the model is asked to produce, and
:func:`field_return_triage.extract.parse.parse_extraction` re-validates the answer
through the contract, so a shape change can never leak into the frozen types.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from field_return_triage.contracts import ConditionKind, SymptomKind

__all__ = [
    "ConditionAnswer",
    "ExtractionAnswer",
    "FaultCodeAnswer",
    "MileageAnswer",
    "SymptomAnswer",
]


class _Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SymptomAnswer(_Answer):
    kind: SymptomKind
    quote: str = Field(min_length=1)


class ConditionAnswer(_Answer):
    kind: ConditionKind
    quote: str = Field(min_length=1)


class FaultCodeAnswer(_Answer):
    code: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class MileageAnswer(_Answer):
    value: int = Field(ge=0)
    quote: str = Field(min_length=1)


class ExtractionAnswer(_Answer):
    """One complaint's structured reading; every key is part of the prompt."""

    component_group: str = Field(default="unclear", min_length=1)
    safety_relevant: bool = False
    safety_quote: str | None = None
    symptoms: list[SymptomAnswer] = Field(default_factory=list)
    conditions: list[ConditionAnswer] = Field(default_factory=list)
    fault_codes: list[FaultCodeAnswer] = Field(default_factory=list)
    mileage: MileageAnswer | None = None
