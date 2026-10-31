"""The technician feedback log: one JSON line per card, append-only.

``PLAN.md`` section 4: the card goes to a technician, who accepts it or changes it, and
the decision is recorded. The log lives under ``data/feedback/``, which git ignores except
for the committed example row, so a real lab's decisions never enter the repository.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from field_return_triage.contracts import Decision

__all__ = ["DECISIONS_PATH", "append_decision", "load_decisions"]

DECISIONS_PATH: Final[Path] = Path("data/feedback/decisions.jsonl")


def append_decision(decision: Decision, path: Path = DECISIONS_PATH) -> None:
    """Append one decision as a sorted-key JSON line, creating the directory if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    row = decision.model_dump(mode="json")
    line = json.dumps(row, sort_keys=True, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{line}\n")


def load_decisions(path: Path = DECISIONS_PATH) -> list[Decision]:
    """Read the log; a missing file is an empty log. Blank lines are skipped."""
    if not path.exists():
        return []
    decisions: list[Decision] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            msg = f"{path}:{lineno}: not valid JSON: {exc.msg}"
            raise ValueError(msg) from exc
        try:
            decisions.append(Decision.model_validate(payload))
        except ValueError as exc:
            msg = f"{path}:{lineno}: not a valid decision: {exc}"
            raise ValueError(msg) from exc
    return decisions
