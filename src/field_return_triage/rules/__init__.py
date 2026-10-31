"""Hard rules, the rulebook, triage cards and the technician feedback log (lane R4).

Public entry points mirror ``docs/INTERFACES.md`` section 6:

* :mod:`field_return_triage.rules.rulebook` loads ``config/rulebook.toml``;
* :mod:`field_return_triage.rules.keywords` is the deterministic safety keyword rule;
* :mod:`field_return_triage.rules.hard_rules` holds ``hr1``: safety, routing, the
  suggestion builder and card assembly;
* :mod:`field_return_triage.rules.feedback` is the append-only decision log;
* :mod:`field_return_triage.rules.kpi` holds the KPI definitions for the page;
* :mod:`field_return_triage.rules.cli` is ``frt review``.
"""

from __future__ import annotations

from field_return_triage.rules.feedback import (
    DECISIONS_PATH,
    append_decision,
    load_decisions,
)
from field_return_triage.rules.hard_rules import (
    HARD_RULE_VERSION,
    build_card,
    decides_safety,
    route,
    suggest,
)
from field_return_triage.rules.keywords import (
    DEFAULT_KEYWORDS_PATH,
    keyword_safety,
    load_safety_keywords,
)
from field_return_triage.rules.kpi import (
    acceptance_rate,
    change_reasons,
    median_time_to_decision_s,
)
from field_return_triage.rules.rulebook import (
    RULEBOOK_PATH,
    RULEBOOK_VERSION,
    Rule,
    Rulebook,
    load_rulebook,
)

__all__ = [
    "DECISIONS_PATH",
    "DEFAULT_KEYWORDS_PATH",
    "HARD_RULE_VERSION",
    "RULEBOOK_PATH",
    "RULEBOOK_VERSION",
    "Rule",
    "Rulebook",
    "acceptance_rate",
    "append_decision",
    "build_card",
    "change_reasons",
    "decides_safety",
    "keyword_safety",
    "load_decisions",
    "load_rulebook",
    "load_safety_keywords",
    "median_time_to_decision_s",
    "route",
    "suggest",
]
