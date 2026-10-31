"""Errors raised by the model client.

Every message is safe to log: no credential, header or environment value is ever
put into an exception (see :mod:`field_return_triage.llm.credentials`).
"""

from __future__ import annotations

__all__ = [
    "ConfigurationError",
    "LlmError",
    "LlmTransportError",
    "PolicyStopError",
    "ProtocolError",
    "ReplayMissError",
]


class LlmError(RuntimeError):
    """Base class for every client failure."""


class ConfigurationError(LlmError):
    """A setting, price entry or credential is missing or unusable."""


class LlmTransportError(LlmError):
    """The transport failed (connection, timeout or 429) after every retry."""


class ProtocolError(LlmError):
    """A 2xx response did not have the OpenAI-compatible shape."""


class ReplayMissError(LlmError):
    """Replay mode was asked for a key that is not in the recordings."""


class PolicyStopError(LlmError):
    """The gateway returned 403 or an abuse/policy message (PLAN §10.5).

    Raised for this call and for every later call in the process. The caller must
    stop the run; retrying around it is forbidden.
    """
