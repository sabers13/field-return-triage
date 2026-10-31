"""Evaluation: precision@k of the similar-case search against the component group.

PLAN.md §6 fixes the metric: the share of the 5 nearest library cases that carry the
query's group. There is no model judgement and no randomness here; the same index and
the same queries give the same number. The search is the product feature; this metric
exists so a run can report whether the neighbours are useful.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from field_return_triage.contracts import Complaint
from field_return_triage.similar.embedder import Embedder, default_embedder
from field_return_triage.similar.index import load_index
from field_return_triage.similar.search import search

__all__ = ["precision_at_k"]


def precision_at_k(
    queries: Sequence[Complaint],
    library: Sequence[Complaint],
    *,
    k: int = 5,
    index: tuple[list[str], NDArray[np.float32]] | None = None,
    embedder: Embedder | None = None,
) -> float:
    """Mean share of each query's ``k`` neighbours that share its group.

    Queries without a group cannot match anything, so they contribute zero rather than
    being silently dropped. A query with fewer than ``k`` available neighbours is
    scored over the neighbours it has, never padded.
    """
    if k <= 0:
        msg = f"k must be positive, got {k}"
        raise ValueError(msg)
    if not queries:
        return 0.0
    resolved = index if index is not None else load_index()
    model = embedder if embedder is not None else default_embedder()

    hits = 0
    total = 0
    for query in queries:
        neighbours = search(
            query.narrative,
            resolved,
            library,
            k=k,
            embedder=model,
        )
        total += len(neighbours)
        hits += sum(1 for neighbour in neighbours if neighbour.group == query.group)
    return hits / total if total else 0.0
