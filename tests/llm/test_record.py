"""Record/replay: same key, same answer, no network on replay."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from llm_support import completion, json_response

from field_return_triage.contracts import ModelSetting, RunMode
from field_return_triage.llm.client import ChatClient
from field_return_triage.llm.errors import ConfigurationError, ReplayMissError
from field_return_triage.llm.record import Recorder, recording_key, recording_path
from field_return_triage.llm.reply import ModelReply

MESSAGES = [{"role": "user", "content": "The dashboard went dark after rain."}]


def make_reply(content: str = '{"ok": true}') -> ModelReply:
    return ModelReply(
        content=content,
        input_tokens=11,
        output_tokens=22,
        cost_usd=0.0001,
        model_id="deepseek-v4.1-flash",
        prompt_version="e1",
    )


def make_client(
    settings: ModelSetting,
    *,
    mode: RunMode,
    recordings: Path,
    budget_path: Path,
    prices_path: Path,
    handler: object | None = None,
) -> ChatClient:
    transport = httpx.MockTransport(handler) if handler is not None else None  # type: ignore[arg-type]
    return ChatClient(
        settings,
        mode=mode,
        recordings=recordings,
        budget_path=budget_path,
        prices_path=prices_path,
        transport=transport,
    )


def test_key_is_deterministic_and_sensitive() -> None:
    key = recording_key("model-a", "e1", MESSAGES)
    assert key == recording_key("model-a", "e1", MESSAGES)
    assert key != recording_key("model-b", "e1", MESSAGES)
    assert key != recording_key("model-a", "e2", MESSAGES)
    assert key != recording_key("model-a", "e1", [{"role": "user", "content": "other"}])
    # Key order inside a message does not change the canonical JSON.
    reordered = [{"content": "The dashboard went dark after rain.", "role": "user"}]
    assert key == recording_key("model-a", "e1", reordered)


def test_record_then_replay_gives_identical_output(
    settings: ModelSetting,
    api_key: str,
    budget_path: Path,
    prices_path: Path,
    tmp_path: Path,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return json_response(completion('{"answer": 42}', input_tokens=7, output_tokens=9))

    recordings = tmp_path / "recordings"
    recorder_client = make_client(
        settings,
        mode=RunMode.RECORD,
        recordings=recordings,
        budget_path=budget_path,
        prices_path=prices_path,
        handler=handler,
    )
    recorded = recorder_client.complete(MESSAGES, schema=None)
    assert calls == 1

    replay_client = make_client(
        settings,
        mode=RunMode.REPLAY,
        recordings=recordings,
        budget_path=budget_path,
        prices_path=prices_path,
        handler=lambda request: pytest.fail("replay called the network"),
    )
    replayed = replay_client.complete(MESSAGES, schema=None)

    assert replayed.model_dump() == recorded.model_dump()
    assert replay_client._api_key is None  # replay never resolves a credential
    assert calls == 1


def test_recorder_returns_none_for_an_unknown_key(tmp_path: Path) -> None:
    recorder = Recorder(tmp_path / "model.jsonl")
    assert recorder.lookup("0" * 64) is None


def test_recorder_rejects_a_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "model.jsonl"
    path.write_text("not json\n", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        Recorder(path).lookup("0" * 64)


def test_replay_of_a_missing_row_raises(
    settings: ModelSetting, budget_path: Path, prices_path: Path, tmp_path: Path
) -> None:
    client = make_client(
        settings,
        mode=RunMode.REPLAY,
        recordings=tmp_path / "recordings",
        budget_path=budget_path,
        prices_path=prices_path,
    )
    with pytest.raises(ReplayMissError):
        client.complete(MESSAGES)


def test_recording_path_is_filesystem_safe() -> None:
    assert recording_path(Path("recordings"), "vendor/model:1").name == "vendor_model_1.jsonl"
