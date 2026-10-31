"""``frt review`` shows one card, records accept/change/reason, and never closes a case."""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers import NOW, make_complaint, make_extraction, make_quote_check
from typer.testing import CliRunner, Result

from field_return_triage.cli import app
from field_return_triage.contracts import DecisionAction, TriageCard
from field_return_triage.rules.feedback import load_decisions
from field_return_triage.rules.hard_rules import build_card
from field_return_triage.rules.rulebook import Rulebook

runner = CliRunner()


def combined(result: Result) -> str:
    return (result.output or "") + getattr(result, "stderr", "")


def make_card(rulebook: Rulebook, complaint_id: str = "c-1") -> TriageCard:
    return build_card(
        make_complaint(id=complaint_id),
        make_extraction(),
        make_quote_check(),
        neighbours=(),
        rulebook=rulebook,
        model_id="model-x",
        keywords=(),
        now=NOW,
    )


def write_cards(path: Path, cards: list[TriageCard]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(f"{card.model_dump_json()}\n" for card in cards),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def review_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, rulebook: Rulebook
) -> dict[str, Path]:
    cards = write_cards(tmp_path / "run" / "cards.jsonl", [make_card(rulebook)])
    log = tmp_path / "feedback" / "decisions.jsonl"
    monkeypatch.setenv("FRT_CARDS_FILE", str(cards))
    monkeypatch.setenv("FRT_DECISIONS_PATH", str(log))
    return {"cards": cards, "log": log}


def test_review_shows_the_card_then_records_accept(review_env: dict[str, Path]) -> None:
    result = runner.invoke(app, ["review"], input="accept\n")
    assert result.exit_code == 0, combined(result)
    assert "card c-1:model-x" in result.output
    assert "priority 2 (clear clues)" in result.output
    assert "humidity / condensation test" in result.output
    assert "versions: prompt e1, rulebook rb1, hard rules hr1" in result.output
    rows = load_decisions(review_env["log"])
    assert len(rows) == 1
    assert rows[0].card_id == "c-1:model-x"
    assert rows[0].action is DecisionAction.ACCEPT
    assert rows[0].reason is None


def test_review_records_change_with_an_inline_reason(review_env: dict[str, Path]) -> None:
    result = runner.invoke(app, ["review"], input="change no humidity chamber here\n")
    assert result.exit_code == 0, combined(result)
    row = load_decisions(review_env["log"])[0]
    assert row.action is DecisionAction.CHANGE
    assert row.reason == "no humidity chamber here"


def test_review_asks_for_the_reason_when_change_is_bare(review_env: dict[str, Path]) -> None:
    result = runner.invoke(app, ["review"], input="change\npart was never wet\n")
    assert result.exit_code == 0, combined(result)
    row = load_decisions(review_env["log"])[0]
    assert row.action is DecisionAction.CHANGE
    assert row.reason == "part was never wet"


def test_review_records_a_reason_line_as_an_accept_with_a_note(
    review_env: dict[str, Path],
) -> None:
    result = runner.invoke(app, ["review"], input="reason customer already replaced it\n")
    assert result.exit_code == 0, combined(result)
    row = load_decisions(review_env["log"])[0]
    assert row.action is DecisionAction.ACCEPT
    assert row.reason == "customer already replaced it"


def test_review_rejects_a_close_command_and_asks_again(review_env: dict[str, Path]) -> None:
    result = runner.invoke(app, ["review"], input="close\naccept\n")
    assert result.exit_code == 0, combined(result)
    assert "write 'accept', 'change <text>' or 'reason <text>'" in combined(result)
    row = load_decisions(review_env["log"])[0]
    assert row.action is DecisionAction.ACCEPT


def test_review_skips_a_card_that_already_has_a_decision(
    review_env: dict[str, Path], rulebook: Rulebook
) -> None:
    write_cards(review_env["cards"], [make_card(rulebook, "c-1"), make_card(rulebook, "c-2")])
    first = runner.invoke(app, ["review"], input="accept\n")
    second = runner.invoke(app, ["review"], input="accept\n")
    assert first.exit_code == 0, combined(first)
    assert second.exit_code == 0, combined(second)
    assert "card c-2:model-x" in second.output
    assert [row.card_id for row in load_decisions(review_env["log"])] == [
        "c-1:model-x",
        "c-2:model-x",
    ]


def test_review_says_when_every_card_is_decided(
    review_env: dict[str, Path],
) -> None:
    assert runner.invoke(app, ["review"], input="accept\n").exit_code == 0
    result = runner.invoke(app, ["review"], input="")
    assert result.exit_code == 0
    assert "no undecided cards" in result.output


def test_review_without_a_cards_file_fails_clearly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FRT_CARDS_FILE", str(tmp_path / "missing.jsonl"))
    monkeypatch.setenv("FRT_DECISIONS_PATH", str(tmp_path / "decisions.jsonl"))
    result = runner.invoke(app, ["review"], input="")
    assert result.exit_code == 1
    assert "does not exist" in combined(result)


def test_review_reports_a_malformed_card_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cards = tmp_path / "cards.jsonl"
    cards.write_text("{not a card}\n", encoding="utf-8")
    monkeypatch.setenv("FRT_CARDS_FILE", str(cards))
    monkeypatch.setenv("FRT_DECISIONS_PATH", str(tmp_path / "decisions.jsonl"))
    result = runner.invoke(app, ["review"], input="")
    assert result.exit_code == 1
    assert ":1: not a card" in combined(result)


def test_review_shows_a_safety_card_as_priority_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, rulebook: Rulebook
) -> None:
    extraction = make_extraction(safety_relevant=True, safety_quote="went dark")
    card = build_card(
        make_complaint(narrative="The dashboard went dark and smoke came out."),
        extraction,
        make_quote_check(),
        neighbours=(),
        rulebook=rulebook,
        model_id="model-x",
        keywords=("smoke",),
        now=NOW,
    )
    cards = write_cards(tmp_path / "cards.jsonl", [card])
    monkeypatch.setenv("FRT_CARDS_FILE", str(cards))
    monkeypatch.setenv("FRT_DECISIONS_PATH", str(tmp_path / "decisions.jsonl"))
    result = runner.invoke(app, ["review"], input="accept\n")
    assert result.exit_code == 0, combined(result)
    assert "priority 1 (safety) - human review" in result.output
