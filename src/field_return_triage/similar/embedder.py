"""The pinned embedding model and the ``Embedder`` seam.

The model, its exact commit and the CPU device are the same pin as which-ai-model's
``rag/embed.py``: ``BAAI/bge-small-en-v1.5`` at revision
``5c38ec7c405ec4b44b94cc5a9bb96e735b38267a``. Re-embedding with a different revision
would silently change every neighbour, so the revision is part of the cache key metadata.

The real model is imported lazily: importing this module is offline and cheap, which is
what lets the test suite replace it with a fake. The index dependency lives in the
``index`` extra, so the test environment does not carry torch.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from typing import Any, Final, Protocol

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "EMBEDDING_DIMENSIONS",
    "EMBEDDING_MODEL",
    "EMBEDDING_REVISION",
    "Embedder",
    "SentenceTransformerEmbedder",
    "default_embedder",
]

#: Embedding model (MIT licence) used for the library.
EMBEDDING_MODEL: Final[str] = "BAAI/bge-small-en-v1.5"
#: Exact commit of the model repository every index build must use.
EMBEDDING_REVISION: Final[str] = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
#: Output dimensions of bge-small-en-v1.5.
EMBEDDING_DIMENSIONS: Final[int] = 384


class Embedder(Protocol):
    """Anything that turns texts into an ``(n, dimensions)`` float32 matrix."""

    def encode(
        self,
        texts: Sequence[str],
        *,
        batch_size: int = 64,
    ) -> NDArray[np.float32]: ...


class SentenceTransformerEmbedder:
    """The real CPU model, loaded on first use and reused for the process lifetime.

    ``local_files_only`` is true by default: replay must never touch the network, so a
    missing local model is an error telling the caller to run ``make index`` once, not a
    silent download. ``make index`` is the one command that passes ``False``.
    """

    def __init__(self, *, local_files_only: bool = True) -> None:
        self._model: Any = None
        self._local_files_only = local_files_only

    def _load_model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ModuleNotFoundError as exc:  # pragma: no cover - real index only
                msg = (
                    "the index extra is not installed; run `uv sync --extra index` "
                    "before `make index`"
                )
                raise RuntimeError(msg) from exc
            self._model = SentenceTransformer(
                EMBEDDING_MODEL,
                revision=EMBEDDING_REVISION,
                device="cpu",
                trust_remote_code=False,
                local_files_only=self._local_files_only,
            )
        return self._model

    def encode(
        self,
        texts: Sequence[str],
        *,
        batch_size: int = 64,
    ) -> NDArray[np.float32]:
        """Embed ``texts``; vectors are L2-normalised by the model."""
        if batch_size <= 0:
            msg = f"batch_size must be positive, got {batch_size}"
            raise ValueError(msg)
        items = list(texts)
        if not items:
            return np.zeros((0, EMBEDDING_DIMENSIONS), dtype=np.float32)
        model = self._load_model()
        vectors = model.encode(
            items,
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)


@lru_cache(maxsize=2)
def default_embedder(*, allow_download: bool = False) -> Embedder:
    """The pinned CPU model, cached in-process.

    It is offline by default. ``make index`` passes ``allow_download=True`` for the one
    permitted cold-cache download; every replay path stays offline.
    """
    return SentenceTransformerEmbedder(local_files_only=not allow_download)
