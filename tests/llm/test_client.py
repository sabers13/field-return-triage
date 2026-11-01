"""The client's request shape, retries, policy stop and cost accounting."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from llm_support import completion, json_response, request_json

from field_return_triage.contracts import ModelSetting, RunMode
from field_return_triage.extract.schema import ExtractionAnswer
from field_return_triage.llm.client import USER_AGENT, ChatClient, retry_after_seconds
from field_return_triage.llm.errors import (
    LlmError,
    LlmTransportError,
    PolicyStopError,
    ReplayMissError,
)

MESSAGES = [{"role": "user", "content": "The dashboard went dark after rain."}]
Handler = Callable[[httpx.Request], httpx.Response]


def make_client(
    settings: ModelSetting,
    handler: Handler,
    *,
    tmp_path: Path,
    budget_path: Path,
    prices_path: Path,
    mode: RunMode = RunMode.RECORD,
    **kwargs: Any,
) -> ChatClient:
    return ChatClient(
        settings,
        mode=mode,
        recordings=tmp_path / "recordings",
        budget_path=budget_path,
        transport=httpx.MockTransport(handler),
        prices_path=prices_path,
        **kwargs,
    )


def test_success_sends_the_documented_request(
    settings: ModelSetting,
    api_key: str,
    budget_path: Path,
    prices_path: Path,
    tmp_path: Path,
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return json_response(completion("{}"))

    client = make_client(
        settings,
        handler,
        tmp_path=tmp_path,
        budget_path=budget_path,
        prices_path=prices_path,
    )
    reply = client.complete(MESSAGES, schema=ExtractionAnswer)

    assert reply.content == "{}"
    assert reply.input_tokens == 30
    assert reply.output_tokens == 60
    assert reply.model_id == settings.model_id
    assert reply.prompt_version == "e1"
    assert reply.cost_usd == pytest.approx((30 * 0.30 + 60 * 1.20) / 1_000_000)

    sent = seen[0]
    assert str(sent.url) == f"{settings.base_url}/chat/completions"
    assert sent.headers["user-agent"] == USER_AGENT
    assert sent.headers["authorization"] == f"Bearer {api_key}"
    assert sent.headers["x-opencode-session"]
    body = request_json(sent)
    assert body["model"] == settings.model_id
    assert body["temperature"] == 0.0
    assert body["max_tokens"] == 1024
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["name"] == "ExtractionAnswer"


def test_a_reasoning_model_gets_a_capped_effort(
    api_key: str,
    budget_path: Path,
    prices_path: Path,
    tmp_path: Path,
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return json_response(completion("{}"))

    reasoning = ModelSetting(role="primary", model_id="muse-spark-1.3-contributor")
    client = make_client(
        reasoning,
        handler,
        tmp_path=tmp_path,
        budget_path=budget_path,
        prices_path=prices_path,
    )
    client.complete(MESSAGES, schema=ExtractionAnswer)
    assert request_json(seen[0])["reasoning_effort"] == "low"

    plain = ModelSetting(role="comparison", model_id="gemini-4-argon")
    client = make_client(
        plain,
        handler,
        tmp_path=tmp_path,
        budget_path=budget_path,
        prices_path=prices_path,
    )
    client.complete(MESSAGES, schema=ExtractionAnswer)
    assert "reasoning_effort" not in request_json(seen[1])


def test_gateway_list_cost_wins_over_tokens(
    settings: ModelSetting,
    api_key: str,
    budget_path: Path,
    prices_path: Path,
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(completion("{}", cost=0.00123))

    client = make_client(
        settings,
        handler,
        tmp_path=tmp_path,
        budget_path=budget_path,
        prices_path=prices_path,
    )
    assert client.complete(MESSAGES).cost_usd == pytest.approx(0.00123)


def test_429_honours_retry_after_then_succeeds(
    settings: ModelSetting,
    api_key: str,
    budget_path: Path,
    prices_path: Path,
    tmp_path: Path,
) -> None:
    calls = 0
    waits: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, text="slow down")
        return json_response(completion("{}"))

    client = make_client(
        settings,
        handler,
        tmp_path=tmp_path,
        budget_path=budget_path,
        prices_path=prices_path,
        sleeper=waits.append,
    )
    reply = client.complete(MESSAGES)

    assert reply.content == "{}"
    assert calls == 2
    assert waits == [0.0]


def test_transport_error_is_retried(
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
        if calls == 1:
            raise httpx.ConnectError("connection refused", request=request)
        return json_response(completion("{}"))

    client = make_client(
        settings,
        handler,
        tmp_path=tmp_path,
        budget_path=budget_path,
        prices_path=prices_path,
        sleeper=lambda _seconds: None,
    )
    assert client.complete(MESSAGES).content == "{}"
    assert calls == 2


def test_transport_error_exhausts_the_budget(
    settings: ModelSetting,
    api_key: str,
    budget_path: Path,
    prices_path: Path,
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = make_client(
        settings,
        handler,
        tmp_path=tmp_path,
        budget_path=budget_path,
        prices_path=prices_path,
        sleeper=lambda _seconds: None,
    )
    with pytest.raises(LlmTransportError):
        client.complete(MESSAGES)


def test_403_stops_every_call_and_writes_stop_md(
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
        return httpx.Response(
            403,
            json={"error": {"message": "account suspended for abuse"}},
        )

    client = make_client(
        settings,
        handler,
        tmp_path=tmp_path,
        budget_path=budget_path,
        prices_path=prices_path,
    )
    with pytest.raises(PolicyStopError):
        client.complete(MESSAGES)
    assert calls == 1

    stop = tmp_path / "reports" / "STOP.md"
    assert stop.is_file()
    assert "abuse" in stop.read_text(encoding="utf-8")

    # A different client must not reach the transport once the latch is set.
    other = make_client(
        settings,
        handler,
        tmp_path=tmp_path,
        budget_path=budget_path,
        prices_path=prices_path,
    )
    with pytest.raises(PolicyStopError):
        other.complete(MESSAGES)
    assert calls == 1


def test_abuse_text_without_403_also_stops(
    settings: ModelSetting,
    api_key: str,
    budget_path: Path,
    prices_path: Path,
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "violates usage policy"}})

    client = make_client(
        settings,
        handler,
        tmp_path=tmp_path,
        budget_path=budget_path,
        prices_path=prices_path,
    )
    with pytest.raises(PolicyStopError):
        client.complete(MESSAGES)
    assert (tmp_path / "reports" / "STOP.md").is_file()


def test_a_rate_limit_policy_message_is_retried_not_a_stop(
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
        if calls == 1:
            return httpx.Response(429, text="rate limit policy exceeded; retry later")
        return json_response(completion("{}"))

    client = make_client(
        settings,
        handler,
        tmp_path=tmp_path,
        budget_path=budget_path,
        prices_path=prices_path,
        sleeper=lambda _seconds: None,
    )
    assert client.complete(MESSAGES).content == "{}"
    assert calls == 2
    assert not (tmp_path / "reports" / "STOP.md").exists()


def test_stop_md_never_contains_the_key(
    settings: ModelSetting,
    api_key: str,
    budget_path: Path,
    prices_path: Path,
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403, json={"error": {"message": f"account warning for key {api_key}"}}
        )

    client = make_client(
        settings,
        handler,
        tmp_path=tmp_path,
        budget_path=budget_path,
        prices_path=prices_path,
    )
    with pytest.raises(PolicyStopError):
        client.complete(MESSAGES)
    notice = (tmp_path / "reports" / "STOP.md").read_text(encoding="utf-8")
    assert api_key not in notice
    assert "<redacted>" in notice


def test_a_bad_answer_is_not_retried(
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
        return json_response(completion("this is not json"))

    client = make_client(
        settings,
        handler,
        tmp_path=tmp_path,
        budget_path=budget_path,
        prices_path=prices_path,
    )
    reply = client.complete(MESSAGES, schema=ExtractionAnswer)
    assert reply.content == "this is not json"
    assert calls == 1


def test_json_schema_rejection_falls_back_to_json_mode(
    settings: ModelSetting,
    api_key: str,
    budget_path: Path,
    prices_path: Path,
    tmp_path: Path,
) -> None:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request_json(request)
        bodies.append(body)
        if len(bodies) == 1:
            return httpx.Response(
                400,
                json={"error": {"message": "response_format json_schema is unsupported"}},
            )
        return json_response(completion("{}"))

    client = make_client(
        settings,
        handler,
        tmp_path=tmp_path,
        budget_path=budget_path,
        prices_path=prices_path,
    )
    assert client.complete(MESSAGES, schema=ExtractionAnswer).content == "{}"
    assert bodies[0]["response_format"]["type"] == "json_schema"
    assert bodies[1]["response_format"] == {"type": "json_object"}
    # The client remembers the choice for the next call.
    assert client.complete(MESSAGES, schema=ExtractionAnswer).content == "{}"
    assert bodies[2]["response_format"] == {"type": "json_object"}


def test_other_400_is_not_retried(
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
        return httpx.Response(400, json={"error": {"message": "model not found"}})

    client = make_client(
        settings,
        handler,
        tmp_path=tmp_path,
        budget_path=budget_path,
        prices_path=prices_path,
    )
    with pytest.raises(LlmError):
        client.complete(MESSAGES, schema=ExtractionAnswer)
    assert calls == 1


def test_replay_miss_never_touches_the_network(
    settings: ModelSetting, budget_path: Path, prices_path: Path, tmp_path: Path
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("replay must not call the transport")

    client = make_client(
        settings,
        handler,
        tmp_path=tmp_path,
        budget_path=budget_path,
        prices_path=prices_path,
        mode=RunMode.REPLAY,
    )
    with pytest.raises(ReplayMissError):
        client.complete(MESSAGES)


def test_no_key_in_repr_logs_or_error(
    settings: ModelSetting,
    api_key: str,
    budget_path: Path,
    prices_path: Path,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def ok(request: httpx.Request) -> httpx.Response:
        return json_response(completion("{}"))

    client = make_client(
        settings,
        ok,
        tmp_path=tmp_path,
        budget_path=budget_path,
        prices_path=prices_path,
    )
    with caplog.at_level(logging.DEBUG):
        client.complete(MESSAGES)
    assert api_key not in repr(client)
    assert api_key not in str(client)
    assert api_key not in caplog.text

    def echo_key(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": f"invalid key {api_key}"}})

    failing = make_client(
        settings,
        echo_key,
        tmp_path=tmp_path,
        budget_path=budget_path,
        prices_path=prices_path,
    )
    with pytest.raises(LlmError) as caught:
        failing.complete(MESSAGES)
    assert api_key not in str(caught.value)


def test_recordings_hold_only_key_content_and_usage(
    settings: ModelSetting,
    api_key: str,
    budget_path: Path,
    prices_path: Path,
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(completion("{}"))

    client = make_client(
        settings,
        handler,
        tmp_path=tmp_path,
        budget_path=budget_path,
        prices_path=prices_path,
    )
    client.complete(MESSAGES)
    files = list((tmp_path / "recordings").glob("*.jsonl"))
    assert len(files) == 1
    row = json.loads(files[0].read_text(encoding="utf-8").splitlines()[0])
    assert set(row) == {"key", "model_id", "prompt_version", "content", "usage", "cost_usd"}
    assert set(row["usage"]) == {"input_tokens", "output_tokens"}
    assert api_key not in files[0].read_text(encoding="utf-8")


def test_retry_after_parses_seconds_and_http_dates() -> None:
    assert retry_after_seconds("3") == pytest.approx(3.0)
    assert retry_after_seconds(None) is None
    assert retry_after_seconds("not a value") is None
    assert retry_after_seconds("0") == 0.0

    now = datetime(2026, 10, 31, 12, 0, 0, tzinfo=UTC)
    assert retry_after_seconds("Sat, 31 Oct 2026 12:00:05 GMT", now=now) == pytest.approx(5.0)
