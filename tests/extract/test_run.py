"""One extraction call over a fake client, and record/replay equivalence."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from extract_support import answer, completion, json_response

from field_return_triage.contracts import Complaint, ModelSetting, RunMode
from field_return_triage.extract.run import extract
from field_return_triage.extract.schema import ExtractionAnswer
from field_return_triage.llm.client import ChatClient
from field_return_triage.llm.reply import ModelReply

COMPLAINT = Complaint(
    id="c-1",
    narrative="The dashboard went dark intermittently after rain.",
    received=date(2026, 1, 15),
)
GROUPS = {"body_control": "Body and dashboard electronics"}


class FakeClient:
    """A ChatClient stand-in: returns one fixed content string."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[tuple[Sequence[Mapping[str, str]], type[Any] | None]] = []

    def complete(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        schema: type[Any] | None = None,
    ) -> ModelReply:
        self.calls.append((messages, schema))
        return ModelReply(
            content=self.content,
            model_id="fake-model",
            prompt_version="e1",
        )


def test_extract_returns_the_extraction_and_a_passing_check() -> None:
    client = FakeClient(answer())
    extraction, check, reason = extract(COMPLAINT, client, GROUPS)  # type: ignore[arg-type]

    assert reason is None
    assert extraction is not None
    assert extraction.component_group == "body_control"
    assert check.checked == 2
    assert check.passed == 2
    assert client.calls[0][1] is ExtractionAnswer


def test_a_failing_quote_is_dropped_but_the_extraction_stays() -> None:
    client = FakeClient(
        answer(symptoms=[{"kind": "display_fault", "quote": "the screen turned off"}])
    )
    extraction, check, reason = extract(COMPLAINT, client, GROUPS)  # type: ignore[arg-type]

    assert reason is None
    assert extraction is not None
    assert check.checked == 2
    assert check.passed == 1
    assert check.dropped[0].field == "symptoms"


def test_an_empty_answer_is_a_reason_not_a_retry() -> None:
    client = FakeClient("")
    extraction, check, reason = extract(COMPLAINT, client, GROUPS)  # type: ignore[arg-type]

    assert extraction is None
    assert reason == "schema-invalid: empty answer"
    assert check.checked == 0
    assert len(client.calls) == 1


def test_record_then_replay_gives_identical_extraction_output(
    tmp_path: Path,
    budget_path: Path,
    prices_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FRT_API_KEY", "test-placeholder-key-0000000000")
    monkeypatch.delenv("FRT_ENV_FILE", raising=False)
    settings = ModelSetting(role="primary", model_id="deepseek-v4.1-flash")
    recordings = tmp_path / "recordings"

    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(completion(answer()))

    record_client = ChatClient(
        settings,
        mode=RunMode.RECORD,
        recordings=recordings,
        budget_path=budget_path,
        prices_path=prices_path,
        transport=httpx.MockTransport(handler),
    )
    recorded = extract(COMPLAINT, record_client, GROUPS)

    replay_client = ChatClient(
        settings,
        mode=RunMode.REPLAY,
        recordings=recordings,
        budget_path=budget_path,
        prices_path=prices_path,
        transport=httpx.MockTransport(lambda request: pytest.fail("replay used the network")),
    )
    replayed = extract(COMPLAINT, replay_client, GROUPS)

    assert json.dumps(recorded[0].model_dump(mode="json"), sort_keys=True) == json.dumps(
        replayed[0].model_dump(mode="json"), sort_keys=True
    )
    assert recorded[1] == replayed[1]
    assert recorded[2] == replayed[2] is None
