"""Small helpers shared by the llm and extract tests."""

from __future__ import annotations

import json
from typing import Any

import httpx

#: Obvious test placeholder; starts with ``test-`` so the secrets scanner ignores it.
API_KEY = "test-placeholder-key-0000000000"


def completion(
    content: str = "{}",
    *,
    input_tokens: int | None = 30,
    output_tokens: int | None = 60,
    cost: float | None = None,
) -> dict[str, Any]:
    """A minimal OpenAI-compatible chat completion body."""
    usage: dict[str, Any] = {}
    if input_tokens is not None:
        usage["prompt_tokens"] = input_tokens
    if output_tokens is not None:
        usage["completion_tokens"] = output_tokens
    body: dict[str, Any] = {
        "id": "chatcmpl-test",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
        "usage": usage,
    }
    if cost is not None:
        body["cost_usd"] = cost
    return body


def json_response(body: dict[str, Any], status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=body)


def request_json(request: httpx.Request) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(request.content)
    return loaded
