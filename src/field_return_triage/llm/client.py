"""The OpenAI-compatible chat client (R2).

One :class:`ChatClient` calls one model through the gateway's
``/chat/completions`` endpoint. It offers two modes:

* ``RunMode.REPLAY`` - a recording lookup keyed by model, prompt version and messages.
  It never constructs an HTTP client and raises :class:`ReplayMissError` on a miss.
* ``RunMode.RECORD`` - the only paid path. It resolves the credential, paces requests,
  retries transport failures and 429s, stops the process on a policy answer, and
  writes every successful answer to the recordings.

A bad answer (empty, cut-off or schema-invalid) is a *result*, not a failure: the
client returns the content and never retries it. Validation belongs to
:mod:`field_return_triage.extract.parse`.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from field_return_triage.contracts import PROMPT_VERSION, ModelSetting, RunMode
from field_return_triage.llm import policy
from field_return_triage.llm.cost import PRICES_PATH, reply_cost_usd
from field_return_triage.llm.credentials import ApiKey, load_api_key
from field_return_triage.llm.errors import (
    LlmError,
    LlmTransportError,
    PolicyStopError,
    ProtocolError,
    ReplayMissError,
)
from field_return_triage.llm.pacing import Pacer
from field_return_triage.llm.record import Recorder, recording_key, recording_path
from field_return_triage.llm.reply import ModelReply
from field_return_triage.llm.settings import BUDGET_PATH, Budget, load_budget

__all__ = ["USER_AGENT", "ChatClient", "Message", "ModelReply", "retry_after_seconds"]

#: The client identifies itself, as the Go docs require (not a bare HTTP-library name).
USER_AGENT = "field-return-triage/1.0 (+https://github.com/sabers13/field-return-triage)"

#: Appended to ``ModelSetting.base_url``.
CHAT_PATH = "/chat/completions"

#: Tokens that suggest a 400 is about the structured-output parameter, so the JSON-mode
#: fallback is worth one request. Any other 400 is a real error.
_FORMAT_REJECTION_TOKENS = (
    "response_format",
    "json_schema",
    "json schema",
    "structured output",
    "structured outputs",
    "unsupported",
)

_MAX_BACKOFF_SECONDS = 30.0


class Message(Protocol):
    """Any object with ``role`` and ``content`` works; dicts are the base."""

    role: str
    content: str


def retry_after_seconds(value: str | None, *, now: datetime | None = None) -> float | None:
    """Parse a ``Retry-After`` header (seconds or HTTP date); ``None`` when absent."""
    if not value:
        return None
    text = value.strip()
    try:
        seconds = float(text)
    except ValueError:
        try:
            when = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        seconds = (when - (now or datetime.now(UTC))).total_seconds()
    return max(0.0, seconds)


def _token_count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


class ChatClient:
    """One model, one mode, one recorder."""

    def __init__(
        self,
        settings: ModelSetting,
        *,
        mode: RunMode = RunMode.REPLAY,
        recordings: Path = Path("recordings"),
        budget_path: Path = BUDGET_PATH,
        transport: httpx.BaseTransport | None = None,
        prices_path: Path = PRICES_PATH,
        prompt_version: str = PROMPT_VERSION,
        timeout: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self.mode = mode
        self.prompt_version = prompt_version
        self.recordings = recordings
        self.prices_path = prices_path
        self.budget: Budget = load_budget(budget_path)
        self._recorder = Recorder(recording_path(recordings, settings.model_id))
        self._pacer = Pacer(
            max_concurrency=self.budget.max_concurrency,
            requests_per_minute=self.budget.requests_per_minute,
            clock=clock,
            sleeper=sleeper,
        )
        self._transport = transport
        self._timeout = self.budget.request_timeout_seconds if timeout is None else timeout
        self._sleeper = sleeper
        self._session_id = uuid.uuid4().hex
        self._api_key: ApiKey | None = None
        self._http: httpx.Client | None = None
        self._json_schema_supported: bool | None = None

    def __repr__(self) -> str:
        return (
            f"ChatClient(model_id={self.settings.model_id!r}, "
            f"mode={self.mode.value!r}, role={self.settings.role!r})"
        )

    __str__ = __repr__

    def close(self) -> None:
        """Close the HTTP client when one was created."""
        if self._http is not None:
            self._http.close()
            self._http = None

    def complete(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        schema: type[BaseModel] | None = None,
    ) -> ModelReply:
        """One call, or one replay hit. Never touches the network in replay mode."""
        key = recording_key(self.settings.model_id, self.prompt_version, messages)
        if self.mode is RunMode.REPLAY:
            reply = self._recorder.lookup(key)
            if reply is None:
                msg = (
                    f"no recording for model {self.settings.model_id!r} and prompt "
                    f"{self.prompt_version!r} (key {key[:12]}...) in {self._recorder.path}"
                )
                raise ReplayMissError(msg)
            return reply

        policy.raise_if_stopped()
        payload = self._request_body(messages, schema)
        attempt = 0
        while True:
            attempt += 1
            try:
                with self._pacer.slot():
                    policy.raise_if_stopped()
                    response = self._post(payload)
            except httpx.TransportError as exc:
                if attempt >= self.budget.max_attempts:
                    msg = (
                        f"{exc.__class__.__name__} after {attempt} attempts "
                        f"for {self.settings.model_id!r}"
                    )
                    raise LlmTransportError(msg) from exc
                self._sleeper(self._backoff(attempt))
                continue
            except httpx.HTTPError as exc:
                msg = f"request failed: {exc.__class__.__name__}"
                raise LlmError(msg) from exc

            status = response.status_code
            body_text = self._redact(response.text)
            if 200 <= status < 300:
                reply = self._reply_from(response)
                self._recorder.record(key, reply)
                return reply

            if policy.looks_like_policy_stop(status, body_text):
                reason = f"HTTP {status}: {body_text.strip()[:500]}"
                policy.trigger(reason)
                raise PolicyStopError(f"gateway policy stop: {reason}")

            if status == 429:
                if attempt >= self.budget.max_attempts:
                    msg = f"rate limited after {attempt} attempts for {self.settings.model_id!r}"
                    raise LlmTransportError(msg)
                wait = retry_after_seconds(response.headers.get("Retry-After"))
                self._sleeper(wait if wait is not None else self._backoff(attempt))
                continue

            if (
                status == 400
                and schema is not None
                and self._json_schema_supported is not False
                and self._rejects_structured_output(body_text)
            ):
                # The endpoint does not accept JSON-schema output. Switch this client
                # to JSON mode permanently and try the same request once more.
                self._json_schema_supported = False
                payload = self._request_body(messages, schema)
                if attempt >= self.budget.max_attempts:
                    msg = "endpoint rejected both JSON-schema and JSON output modes"
                    raise LlmError(msg)
                continue

            msg = f"gateway returned HTTP {status}: {body_text.strip()[:300]}"
            raise LlmError(msg)

    # -- request building -------------------------------------------------------

    def _endpoint(self) -> str:
        return f"{self.settings.base_url.rstrip('/')}{CHAT_PATH}"

    def _request_body(
        self,
        messages: Sequence[Mapping[str, str]],
        schema: type[BaseModel] | None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.settings.model_id,
            "messages": [
                {"role": message["role"], "content": message["content"]} for message in messages
            ],
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_output_tokens,
        }
        if schema is not None:
            if self._json_schema_supported is False:
                body["response_format"] = {"type": "json_object"}
            else:
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "schema": schema.model_json_schema(),
                    },
                }
        return body

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        client = self._http_client()
        headers = {"Authorization": f"Bearer {self._key_value()}"}
        return client.post(self._endpoint(), json=payload, headers=headers)

    def _http_client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(
                transport=self._transport,
                timeout=self._timeout,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                    "x-opencode-session": self._session_id,
                },
            )
        return self._http

    def _key_value(self) -> str:
        if self._api_key is None:
            self._api_key = load_api_key()
        return self._api_key.reveal()

    def _redact(self, text: str) -> str:
        """Remove the credential from any error text before it can be logged."""
        if self._api_key is None:
            return text
        return text.replace(self._api_key.reveal(), "<redacted>")

    def _backoff(self, attempt: int) -> float:
        return min(
            _MAX_BACKOFF_SECONDS,
            self.budget.backoff_seconds * (2.0 ** (attempt - 1)),
        )

    @staticmethod
    def _rejects_structured_output(body: str) -> bool:
        lowered = body.casefold()
        return any(token in lowered for token in _FORMAT_REJECTION_TOKENS)

    # -- response parsing -------------------------------------------------------

    def _reply_from(self, response: httpx.Response) -> ModelReply:
        try:
            payload = response.json()
        except ValueError as exc:
            msg = f"gateway returned a 2xx response that is not JSON ({exc.__class__.__name__})"
            raise ProtocolError(msg) from exc
        if not isinstance(payload, dict):
            msg = "gateway returned JSON that is not an object"
            raise ProtocolError(msg)

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            msg = "gateway response has no choices"
            raise ProtocolError(msg)
        first = choices[0]
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if content is None:
            content = ""
        if not isinstance(content, str):
            msg = "gateway response message.content is not a string"
            raise ProtocolError(msg)

        usage = payload.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        input_tokens = _token_count(usage.get("prompt_tokens", usage.get("input_tokens")))
        output_tokens = _token_count(usage.get("completion_tokens", usage.get("output_tokens")))
        cost = reply_cost_usd(
            payload,
            response.headers,
            self.settings,
            prices_path=self.prices_path,
        )
        return ModelReply(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            model_id=self.settings.model_id,
            prompt_version=self.prompt_version,
        )
