"""The policy stop latch (PLAN §10.5).

A 403, or an abuse/policy/suspension message, stops **every** later call in the
process - for every model and every client - and writes ``reports/STOP.md``. Retrying
around the gateway's answer is forbidden, so the latch is checked before each request
and is never cleared by normal code.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path

from field_return_triage.llm.errors import PolicyStopError

__all__ = [
    "STOP_PATH",
    "looks_like_policy_stop",
    "reset",
    "stop_reason",
    "trigger",
]

#: Where the stop notice is written; a test may patch this module attribute.
STOP_PATH: Path = Path("reports/STOP.md")

#: Phrases that mean "the account or client is not welcome" in an error body. They are
#: matched only against non-2xx response text, never against model output.
POLICY_PATTERNS: tuple[str, ...] = (
    "abuse",
    "usage policy",
    "content policy",
    "policy violation",
    "violates",
    "suspended",
    "suspension",
    "banned",
    "terms of service",
    "account warning",
)

_MAX_REASON_CHARS = 500

_lock = threading.Lock()
_stopped_reason: str | None = None
_write_failed = False


def looks_like_policy_stop(status: int | None, body: str) -> bool:
    """True for a 403, or for an error body naming abuse, policy or suspension."""
    if status == 403:
        return True
    lowered = body.casefold()
    return any(pattern in lowered for pattern in POLICY_PATTERNS)


def stop_reason() -> str | None:
    """The reason the process is stopped, or ``None`` while calls are allowed."""
    with _lock:
        return _stopped_reason


def trigger(reason: str) -> None:
    """Latch the process-wide stop and write ``reports/STOP.md`` once.

    ``reason`` must already be redacted by the caller; no credential may reach this
    module. If the report cannot be written, the latch still holds: stopping all
    calls is more important than the file.
    """
    global _stopped_reason, _write_failed
    with _lock:
        if _stopped_reason is not None:
            return
        _stopped_reason = reason
    notice = (
        "# STOP: model gateway policy stop\n\n"
        "The gateway returned a 403, or an abuse/policy/suspension message, at "
        f"{datetime.now(UTC).isoformat()}.\n\n"
        "Every live model call is stopped (PLAN.md §10.5). Do not retry around it.\n\n"
        "Reason (from the gateway, truncated):\n\n"
        f"{reason[:_MAX_REASON_CHARS]}\n"
    )
    try:
        STOP_PATH.parent.mkdir(parents=True, exist_ok=True)
        STOP_PATH.write_text(notice, encoding="utf-8")
    except OSError:
        with _lock:
            _write_failed = True


def reset() -> None:
    """Clear the latch. For tests only; a live run never clears a policy stop."""
    global _stopped_reason, _write_failed
    with _lock:
        _stopped_reason = None
        _write_failed = False


def raise_if_stopped() -> None:
    """Raise :class:`PolicyStopError` when the latch is set."""
    reason = stop_reason()
    if reason is not None:
        raise PolicyStopError(f"live model calls are stopped: {reason}")
