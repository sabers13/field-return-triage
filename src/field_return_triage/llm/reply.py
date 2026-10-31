"""The reply one model call returns.

Kept in its own module so both the HTTP client and the recorder can use it without a
circular import. ``field_return_triage.llm.client`` re-exports it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ModelReply"]


class ModelReply(BaseModel):
    """One answer plus the usage the gateway reported (``docs/INTERFACES.md`` §4)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    model_id: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
