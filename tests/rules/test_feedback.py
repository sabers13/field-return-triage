"""The feedback log appends one JSON line per decision and the KPIs read it back."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from field_return_triage.contracts import Decision, DecisionAction
from field_return_triage.rules.feedback import append_decision, load_decisions
from field_return_triage.rules.kpi import (
    acceptance_rate,
    change_reasons,
    median_time_to_decision_s,
)

DECIDED_AT = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def make_decision(**overrides: object) -> Decision:
    values: dict[str, object] = {
        "card_id": "c-1:model-x",
        "complaint_id": "c-1",
        "action": DecisionAction.ACCEPT,
        "decided_at": DECIDED_AT,
    }
    values.update(overrides)
    return Decision.model_validate(values)


def test_append_then_load_round_trips(tmp_path: Path) -> None:
    log = tmp_path / "nested" / "decisions.jsonl"
    first = make_decision()
    second = make_decision(
        card_id="c-2:model-x",
        complaint_id="c-2",
        action=DecisionAction.CHANGE,
        reason="wrong test",
        time_to_decision_s=12.5,
    )
    append_decision(first, log)
    append_decision(second, log)
    assert load_decisions(log) == [first, second]


def test_append_writes_one_sorted_key_json_line(tmp_path: Path) -> None:
    log = tmp_path / "decisions.jsonl"
    append_decision(make_decision(), log)
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert list(payload) == sorted(payload)
    assert payload["action"] == "accept"
    assert lines[0].endswith("}")


def test_missing_log_is_empty(tmp_path: Path) -> None:
    assert load_decisions(tmp_path / "absent.jsonl") == []


def test_blank_lines_are_skipped(tmp_path: Path) -> None:
    log = tmp_path / "decisions.jsonl"
    log.write_text("\n\n", encoding="utf-8")
    assert load_decisions(log) == []


def test_a_corrupt_line_names_its_line(tmp_path: Path) -> None:
    log = tmp_path / "decisions.jsonl"
    log.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(ValueError, match=":1: not valid JSON"):
        load_decisions(log)


def test_a_valid_json_wrong_row_names_its_line(tmp_path: Path) -> None:
    log = tmp_path / "decisions.jsonl"
    log.write_text('{"card_id": "c-1"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match=":1: not a valid decision"):
        load_decisions(log)


def test_a_change_without_a_reason_is_refused() -> None:
    with pytest.raises(ValidationError, match="requires the technician's reason"):
        make_decision(action=DecisionAction.CHANGE)


def test_acceptance_rate_is_none_for_an_empty_log() -> None:
    assert acceptance_rate([]) is None


def test_acceptance_rate_counts_only_accepts() -> None:
    rows = [
        make_decision(),
        make_decision(action=DecisionAction.CHANGE, reason="a"),
        make_decision(),
        make_decision(),
    ]
    assert acceptance_rate(rows) == 0.75


def test_change_reasons_counts_and_sorts() -> None:
    rows = [
        make_decision(action=DecisionAction.CHANGE, reason="wrong test"),
        make_decision(action=DecisionAction.CHANGE, reason="a better test exists"),
        make_decision(action=DecisionAction.CHANGE, reason="wrong test"),
        make_decision(),
    ]
    assert change_reasons(rows) == {"a better test exists": 1, "wrong test": 2}


def test_change_reasons_is_empty_without_changes() -> None:
    assert change_reasons([make_decision()]) == {}


def test_median_time_to_decision_uses_recorded_rows() -> None:
    rows = [
        make_decision(time_to_decision_s=10.0),
        make_decision(time_to_decision_s=30.0),
        make_decision(),
    ]
    assert median_time_to_decision_s(rows) == 20.0


def test_median_time_to_decision_is_none_without_rows() -> None:
    assert median_time_to_decision_s([make_decision()]) is None
