"""Shared helpers for the extraction tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]

#: A complete e1 answer with one clue in every field.
VALID_ANSWER: dict[str, Any] = {
    "component_group": "body_control",
    "safety_relevant": False,
    "safety_quote": None,
    "symptoms": [{"kind": "display_fault", "quote": "dashboard went dark"}],
    "conditions": [{"kind": "moisture", "quote": "after rain"}],
    "fault_codes": [],
    "mileage": None,
}


def answer(**overrides: Any) -> str:
    payload = {**VALID_ANSWER, **overrides}
    return json.dumps(payload)


def completion(content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 30, "completion_tokens": 60},
    }


def json_response(body: dict[str, Any], status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=body)
