"""The pipeline lane (R6): triage one complaint, evaluate the set, report results.

Public surface (``docs/INTERFACES.md`` section 8):

* :mod:`pipeline.triage` - ``triage_one``, ``triage_text`` and the readable card view;
* :mod:`pipeline.run` - ``run_eval``, the resumable runner with the PLAN section 8
  budget guard;
* :mod:`pipeline.metrics` - every PLAN section 6 metric with its interval;
* :mod:`pipeline.baseline` - the cost-free baselines under ``results/baseline/``;
* :mod:`pipeline.summary` - ``results/SUMMARY.md`` and ``results/MANIFEST.sha256``;
* :mod:`pipeline.cli` - ``frt triage``, ``frt eval`` and the make-only commands.
"""

from __future__ import annotations

from field_return_triage.pipeline.config import (
    HashingEmbedder,
    Paths,
    load_group_descriptions,
    resolve_paths,
)
from field_return_triage.pipeline.metrics import Metric
from field_return_triage.pipeline.run import BudgetExceededError, run_eval
from field_return_triage.pipeline.summary import build_summary, write_manifest
from field_return_triage.pipeline.triage import (
    CallStats,
    render_card,
    triage_item,
    triage_one,
    triage_text,
)

__all__ = [
    "BudgetExceededError",
    "CallStats",
    "HashingEmbedder",
    "Metric",
    "Paths",
    "build_summary",
    "load_group_descriptions",
    "render_card",
    "resolve_paths",
    "run_eval",
    "triage_item",
    "triage_one",
    "triage_text",
    "write_manifest",
]
