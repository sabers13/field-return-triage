"""The model client and extraction support for field-return-triage."""

from __future__ import annotations

from field_return_triage.llm.client import USER_AGENT, ChatClient, Message
from field_return_triage.llm.cost import estimate_cost_usd, load_prices
from field_return_triage.llm.credentials import ApiKey, load_api_key
from field_return_triage.llm.errors import (
    ConfigurationError,
    LlmError,
    LlmTransportError,
    PolicyStopError,
    ProtocolError,
    ReplayMissError,
)
from field_return_triage.llm.record import Recorder, recording_key
from field_return_triage.llm.reply import ModelReply
from field_return_triage.llm.settings import Budget, load_budget, load_model_settings

__all__ = [
    "USER_AGENT",
    "ApiKey",
    "Budget",
    "ChatClient",
    "ConfigurationError",
    "LlmError",
    "LlmTransportError",
    "Message",
    "ModelReply",
    "PolicyStopError",
    "ProtocolError",
    "Recorder",
    "ReplayMissError",
    "estimate_cost_usd",
    "load_api_key",
    "load_budget",
    "load_model_settings",
    "load_prices",
    "recording_key",
]
