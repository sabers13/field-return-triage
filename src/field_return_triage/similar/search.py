"""Cosine search over the cached library vectors.

The search is deliberately plain numpy: one matrix-vector product, scores rounded to
4 decimals, then a deterministic sort. Rounding before ranking is what makes ties real,
and the complaint id is the tie-break (PLAN.md §9). No approximate index, no random
state, no model call beyond encoding the query.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

import numpy as np
from numpy.typing import NDArray

from field_return_triage.contracts import UNCLEAR_GROUP, Complaint, Neighbour
from field_return_triage.similar.embedder import Embedder, default_embedder
from field_return_triage.similar.index import load_index

__all__ = ["EXCERPT_CHARS", "excerpt", "nearest", "search"]

#: ``Neighbour.excerpt`` and PLAN.md §4 fix the excerpt length at 200 characters.
EXCERPT_CHARS: Final[int] = 200

_WHITESPACE = re.compile(r"\s+")


def excerpt(narrative: str) -> str:
    """The first 200 characters after whitespace normalisation."""
    normalised = _WHITESPACE.sub(" ", narrative).strip()
    return (normalised or " ")[:EXCERPT_CHARS]


def _normalised(vectors: NDArray[np.float32]) -> NDArray[np.float32]:
    """Row-normalise vectors; zero rows stay zero instead of turning into NaN."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    normalised: NDArray[np.float32] = np.asarray(vectors / norms, dtype=np.float32)
    return normalised


def _query_vector(embedder: Embedder, query_text: str) -> NDArray[np.float32]:
    vector = np.asarray(embedder.encode([query_text]), dtype=np.float32)
    if vector.ndim != 2 or vector.shape[0] != 1:
        msg = f"embedder must return one row for one query, got shape {vector.shape}"
        raise ValueError(msg)
    row: NDArray[np.float32] = np.asarray(vector[0], dtype=np.float32)
    return row


def search(
    query_text: str,
    index: tuple[list[str], NDArray[np.float32]],
    library: Sequence[Complaint],
    *,
    k: int = 5,
    embedder: Embedder | None = None,
) -> list[Neighbour]:
    """The ``k`` nearest library complaints to ``query_text``, best first."""
    if k <= 0:
        msg = f"k must be positive, got {k}"
        raise ValueError(msg)
    ids, vectors = index
    if not ids:
        return []
    if len(ids) != vectors.shape[0]:
        msg = f"index has {len(ids)} ids but {vectors.shape[0]} vectors"
        raise ValueError(msg)

    by_id = {complaint.id: complaint for complaint in library}
    missing = [complaint_id for complaint_id in ids if complaint_id not in by_id]
    if missing:
        msg = f"index ids are not in the library: {', '.join(missing[:3])}"
        raise ValueError(msg)

    model = embedder if embedder is not None else default_embedder()
    query = _query_vector(model, query_text)
    matrix = _normalised(np.asarray(vectors, dtype=np.float32))
    if matrix.shape[1] != query.shape[0]:
        msg = f"query vector has {query.shape[0]} dimensions but the index has {matrix.shape[1]}"
        raise ValueError(msg)
    scores = np.round(matrix @ query, 4)
    order = sorted(range(len(ids)), key=lambda position: (-float(scores[position]), ids[position]))

    neighbours: list[Neighbour] = []
    for position in order[:k]:
        complaint = by_id[ids[position]]
        neighbours.append(
            Neighbour(
                complaint_id=complaint.id,
                group=complaint.group or UNCLEAR_GROUP,
                received=complaint.received,
                safety_relevant=complaint.coded_safety,
                excerpt=excerpt(complaint.narrative),
                score=float(scores[position]),
            )
        )
    return neighbours


def nearest(
    complaint: Complaint,
    library: Sequence[Complaint],
    *,
    k: int = 5,
    index: tuple[list[str], NDArray[np.float32]] | None = None,
    embedder: Embedder | None = None,
) -> list[Neighbour]:
    """The ``k`` nearest past complaints to ``complaint``, using its narrative."""
    resolved = index if index is not None else load_index()
    return search(
        complaint.narrative,
        resolved,
        library,
        k=k,
        embedder=embedder,
    )
