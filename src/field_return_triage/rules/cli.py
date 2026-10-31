"""``frt review``: show one card and record the technician's decision.

The technician is the only party that decides. This command never closes, scraps or
returns anything: it offers ``accept`` or ``change``, records the row under
``data/feedback/``, and moves on to the next undecided card on the next run.

Each invocation shows one card. Undecided cards come from the run's ``cards.jsonl``;
the run directory defaults to the newest under ``results/runs/`` and can be chosen with
``FRT_CARDS_FILE``. The log path can be redirected with ``FRT_DECISIONS_PATH`` so a demo
never writes into a real lab's log.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import typer

from field_return_triage.contracts import (
    Decision,
    DecisionAction,
    Neighbour,
    Priority,
    TriageCard,
)
from field_return_triage.rules.feedback import (
    DECISIONS_PATH,
    append_decision,
    load_decisions,
)

__all__ = ["review_main"]

CARDS_FILE_ENV: Final[str] = "FRT_CARDS_FILE"
DECISIONS_FILE_ENV: Final[str] = "FRT_DECISIONS_PATH"
DEFAULT_RUNS_DIR: Final[Path] = Path("results/runs")

_PRIORITY_LABEL: Final[dict[Priority, str]] = {
    Priority.SAFETY: "1 (safety)",
    Priority.CLEAR_CLUES: "2 (clear clues)",
    Priority.HUMAN_READING: "3 (needs human reading)",
}


def _cards_path() -> Path:
    override = os.environ.get(CARDS_FILE_ENV)
    if override:
        return Path(override)
    candidates = sorted(
        DEFAULT_RUNS_DIR.glob("*/cards.jsonl"),
        key=lambda path: (path.stat().st_mtime, str(path)),
    )
    if not candidates:
        msg = (
            f"no cards found: run `frt eval` or `frt triage` first, "
            f"or set {CARDS_FILE_ENV} to a cards.jsonl file"
        )
        typer.echo(f"frt review: {msg}", err=True)
        raise typer.Exit(code=1)
    return candidates[-1]


def _decisions_path() -> Path:
    override = os.environ.get(DECISIONS_FILE_ENV)
    return Path(override) if override else DECISIONS_PATH


def _load_cards(path: Path) -> list[TriageCard]:
    if not path.exists():
        typer.echo(f"frt review: {path} does not exist", err=True)
        raise typer.Exit(code=1)
    cards: list[TriageCard] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cards.append(TriageCard.model_validate(json.loads(line)))
        except ValueError as exc:
            typer.echo(f"frt review: {path}:{lineno}: not a card: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    return cards


def _neighbour_line(neighbour: Neighbour) -> str:
    flag = ", safety" if neighbour.safety_relevant else ""
    return (
        f"  - {neighbour.complaint_id} [{neighbour.group}{flag}] "
        f"score {neighbour.score:.4f} {neighbour.received.isoformat()}: {neighbour.excerpt}"
    )


def _render(card: TriageCard) -> str:
    complaint = card.complaint
    identity = " ".join(
        part
        for part in (
            complaint.make,
            complaint.model,
            str(complaint.model_year) if complaint.model_year is not None else None,
        )
        if part
    )
    lines = [
        f"card {card.card_id}",
        f"priority {_PRIORITY_LABEL[card.priority]}"
        f"{' - human review' if card.needs_human_review else ''}",
        f"complaint {complaint.id}"
        + (f" - {identity}" if identity else "")
        + (f" - group {complaint.group}" if complaint.group else ""),
        "",
        complaint.narrative,
        "",
        "clues:",
    ]
    kept = [
        f'  - {clue.kind}: "{clue.quote}"'
        for clue in (*card.extraction.symptoms, *card.extraction.conditions)
        if clue.quote in card.quotes
    ]
    lines.extend(kept or ["  (none passed the quote check)"])
    lines.append("")
    lines.append("why:")
    lines.extend(f"  - {reason.text}" for reason in card.reasons)
    lines.append("")
    lines.append("suggested next step:")
    lines.extend(f"  test: {test}" for test in card.suggestion.tests)
    lines.extend(f"  inspect: {item}" for item in card.suggestion.inspect)
    lines.extend(f"  request: {item}" for item in card.suggestion.request)
    for reason in card.suggestion.reasons:
        quotes = "; ".join(f'"{quote}"' for quote in reason.quotes)
        lines.append(f"  because: {reason.text}" + (f" [{quotes}]" if quotes else ""))
    if card.neighbours:
        lines.append("")
        lines.append("nearest past cases:")
        lines.extend(_neighbour_line(neighbour) for neighbour in card.neighbours)
    lines.append("")
    lines.append(
        f"versions: prompt {card.prompt_version}, rulebook {card.rulebook_version}, "
        f"hard rules {card.hard_rule_version}, model {card.model_id}"
    )
    return "\n".join(lines)


def _read_decision() -> tuple[DecisionAction, str | None]:
    """Read one decision: ``accept``, ``change <text>`` or ``reason <text>``.

    ``reason <text>`` records an acceptance with a note; ``change`` without text asks for
    the reason, because a change always carries one.
    """
    while True:
        raw = typer.prompt("decision (accept | change <text> | reason <text>)").strip()
        verb, _, rest = raw.partition(" ")
        verb = verb.lower()
        rest = rest.strip()
        if verb == "accept":
            return DecisionAction.ACCEPT, rest or None
        if verb == "reason":
            if not rest:
                typer.echo("frt review: 'reason' needs the text to record", err=True)
                continue
            return DecisionAction.ACCEPT, rest
        if verb == "change":
            reason = rest
            while not reason:
                reason = typer.prompt("reason for the change").strip()
                if not reason:
                    typer.echo("frt review: a change needs a reason", err=True)
            return DecisionAction.CHANGE, reason
        typer.echo(
            "frt review: write 'accept', 'change <text>' or 'reason <text>'",
            err=True,
        )


def review_main() -> None:
    """Show the first undecided card and append the technician's decision."""
    cards_path = _cards_path()
    decisions_path = _decisions_path()
    cards = _load_cards(cards_path)
    decided = {row.card_id for row in load_decisions(decisions_path)}
    card = next((item for item in cards if item.card_id not in decided), None)
    if card is None:
        typer.echo(f"frt review: no undecided cards in {cards_path}")
        return

    typer.echo(_render(card))
    typer.echo("")
    action, reason = _read_decision()
    decided_at = datetime.now(UTC)
    elapsed = (decided_at - card.created_at).total_seconds()
    decision = Decision(
        card_id=card.card_id,
        complaint_id=card.complaint.id,
        action=action,
        reason=reason,
        decided_at=decided_at,
        time_to_decision_s=elapsed if elapsed >= 0 else None,
    )
    append_decision(decision, decisions_path)
    typer.echo(f"recorded {decision.action.value} for {decision.card_id} in {decisions_path}")
