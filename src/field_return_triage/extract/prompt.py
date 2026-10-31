"""Prompt ``e1``: turn one complaint into the PLAN §4 extraction.

The prompt carries the group list with a one-line description each, both fixed kind
vocabularies, the "quote the exact words, never paraphrase" rule, and the permission
to answer ``unclear``. It asks for one JSON object with every key, so the endpoint's
JSON-schema mode and plain JSON mode see the same request.
"""

from __future__ import annotations

from collections.abc import Mapping

from field_return_triage.contracts import (
    UNCLEAR_GROUP,
    Complaint,
    ConditionKind,
    SymptomKind,
)

__all__ = ["PROMPT_VERSION", "SYSTEM_PROMPT", "build_messages"]

PROMPT_VERSION = "e1"

SYSTEM_PROMPT = """\
You read one customer complaint about a returned electrical or electronic part and \
extract the failure clues a technician needs.

Answer with one JSON object and nothing else. It must have exactly these keys:
component_group, safety_relevant, safety_quote, symptoms, conditions, fault_codes, \
mileage.

Rules:
- component_group: one id from the group list, or "{unclear}" when the complaint does
  not clearly name a single group.
- safety_relevant: true only when the text reports a crash, fire, smoke, burn, shock
  or another risk of injury. When true, safety_quote must hold the exact words that
  show it. When false, safety_quote must be null.
- symptoms: a list of objects {{"kind": ..., "quote": ...}}. kind is one of:
  {symptom_kinds}.
- conditions: a list of objects {{"kind": ..., "quote": ...}}. kind is one of:
  {condition_kinds}.
- fault_codes: a list of objects {{"code": ..., "quote": ...}} for diagnostic trouble
  codes or other fault numbers named in the text.
- mileage: {{"value": <whole number of miles>, "quote": ...}}, or null when the text
  gives no mileage.
- Quote the exact words from the narrative, never paraphrase. Every quote must be a
  contiguous span copied character for character from the narrative. If the text does
  not support a clue, leave that clue out.
- Use [] for an empty list and null for an absent value. Do not add keys.
"""


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _group_lines(groups: Mapping[str, str]) -> str:
    lines = [f"- {UNCLEAR_GROUP}: the complaint does not clearly name one group"]
    for group_id in sorted(groups):
        if group_id == UNCLEAR_GROUP:
            continue
        description = _one_line(groups[group_id]) or "no description"
        lines.append(f"- {group_id}: {description}")
    return "\n".join(lines)


def build_messages(complaint: Complaint, groups: Mapping[str, str]) -> list[dict[str, str]]:
    """The two messages for prompt ``e1``: a system brief and the narrative."""
    system = SYSTEM_PROMPT.format(
        unclear=UNCLEAR_GROUP,
        symptom_kinds=", ".join(kind.value for kind in SymptomKind),
        condition_kinds=", ".join(kind.value for kind in ConditionKind),
    )
    system = f"{system}\nComponent groups (id: description):\n{_group_lines(groups)}"
    user = (
        "Complaint narrative:\n"
        f"{complaint.narrative.strip()}\n\n"
        "Extract the clues as one JSON object."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
