"""Similar past cases: embed the library once, then search it by cosine similarity.

PLAN.md §4 step 4 asks for the nearest past complaints for a new complaint. The
embedding model and its exact revision are pinned here, the vectors live in a cache
outside git (keyed by ``data/CHECKSUMS.txt``), and the search is a plain numpy brute
force. Scores are rounded to 4 decimals *before* ranking and ties break on complaint id,
so the same library and query always produce the same neighbours (PLAN.md §9).

Tests inject an :class:`~field_return_triage.similar.embedder.Embedder` fake; importing
this package never loads a model and never touches the network. Only ``make index``
downloads the model, once.
"""

from __future__ import annotations

from field_return_triage.similar.embedder import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    EMBEDDING_REVISION,
    Embedder,
    default_embedder,
)
from field_return_triage.similar.evaluate import precision_at_k
from field_return_triage.similar.index import (
    DEFAULT_CHECKSUMS,
    build_index,
    cache_dir,
    index_path,
    load_index,
)
from field_return_triage.similar.search import EXCERPT_CHARS, nearest, search

__all__ = [
    "DEFAULT_CHECKSUMS",
    "EMBEDDING_DIMENSIONS",
    "EMBEDDING_MODEL",
    "EMBEDDING_REVISION",
    "EXCERPT_CHARS",
    "Embedder",
    "build_index",
    "cache_dir",
    "default_embedder",
    "index_path",
    "load_index",
    "nearest",
    "precision_at_k",
    "search",
]
