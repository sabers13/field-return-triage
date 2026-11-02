"""Build and load the vector cache outside git.

``make index`` embeds ``data/library.jsonl.gz`` once and writes an ``.npz`` file under
``~/.cache/field-return-triage/``. The file name carries a hash of ``data/CHECKSUMS.txt``,
so new data can never be searched with old vectors: a changed library produces a new
cache entry, and the old one is simply never read again.

Nothing here needs the network except :func:`default_embedder` loading the model on a
cold cache, which only ``make index`` does in a normal run.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray

from field_return_triage.contracts import Complaint
from field_return_triage.similar.embedder import (
    EMBEDDING_MODEL,
    EMBEDDING_REVISION,
    Embedder,
    default_embedder,
)

__all__ = [
    "DEFAULT_CHECKSUMS",
    "build_index",
    "cache_dir",
    "checksum_key",
    "index_path",
    "load_index",
]

DEFAULT_CHECKSUMS: Final[Path] = Path("data/CHECKSUMS.txt")


def cache_dir() -> Path:
    """``~/.cache/field-return-triage/``; never inside the repository."""
    return Path.home() / ".cache" / "field-return-triage"


def checksum_key(checksums: Path = DEFAULT_CHECKSUMS) -> str:
    """A short, stable key for the data snapshot described by ``checksums``."""
    if not checksums.is_file():
        msg = f"{checksums} is missing; run `make data` before `make index`"
        raise FileNotFoundError(msg)
    return hashlib.sha256(checksums.read_bytes()).hexdigest()[:16]


def index_path(checksums: Path = DEFAULT_CHECKSUMS) -> Path:
    """The cache file for one ``data/CHECKSUMS.txt`` snapshot."""
    return cache_dir() / f"index-{checksum_key(checksums)}.npz"


def _as_matrix(vectors: NDArray[np.float32], *, rows: int) -> NDArray[np.float32]:
    """Validate the embedder output before it is persisted."""
    matrix = np.asarray(vectors, dtype=np.float32)
    if matrix.ndim != 2:
        msg = f"embedder must return a 2-D matrix, got shape {matrix.shape}"
        raise ValueError(msg)
    if matrix.shape[0] != rows:
        msg = f"embedder returned {matrix.shape[0]} vectors for {rows} complaints"
        raise ValueError(msg)
    if matrix.shape[1] == 0:
        msg = "embedder returned zero-dimensional vectors"
        raise ValueError(msg)
    return matrix


def build_index(
    library: Sequence[Complaint],
    *,
    embedder: Embedder | None = None,
    checksums: Path = DEFAULT_CHECKSUMS,
) -> Path:
    """Embed ``library`` and persist ids + vectors; return the cache path.

    Ids are stored in library order and vectors are stored L2-normalised, so cosine
    similarity later is a dot product. The data key is read before any embedding work,
    so a missing library checksum fails fast instead of after a long model run.
    """
    if not library:
        msg = "cannot build an index for an empty library"
        raise ValueError(msg)
    path = index_path(checksums)
    ids = [complaint.id for complaint in library]
    if len(set(ids)) != len(ids):
        msg = "library contains duplicate complaint ids"
        raise ValueError(msg)

    model = embedder if embedder is not None else default_embedder()
    vectors = _as_matrix(
        model.encode([complaint.narrative for complaint in library]),
        rows=len(library),
    )
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    vectors = (vectors / norms).astype(np.float32)

    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        ids=np.asarray(ids, dtype=np.str_),
        vectors=vectors,
        model=np.asarray(EMBEDDING_MODEL),
        revision=np.asarray(EMBEDDING_REVISION),
        checksums=np.asarray(checksum_key(checksums)),
    )
    return path


def load_index(path: Path | None = None) -> tuple[list[str], NDArray[np.float32]]:
    """Load ``(ids, vectors)`` from the cache, or fail with what to run first."""
    resolved = Path(path) if path is not None else index_path()
    if not resolved.is_file():
        msg = f"no embedding index at {resolved}; run `make index` first"
        raise FileNotFoundError(msg)

    archive = np.load(resolved, allow_pickle=False)
    try:
        if not isinstance(archive, np.lib.npyio.NpzFile):
            msg = f"{resolved} is not an embedding index"
            raise ValueError(msg)
        ids = [str(value) for value in archive["ids"].tolist()]
        vectors = np.asarray(archive["vectors"], dtype=np.float32)
        model = str(archive["model"].item()) if "model" in archive else EMBEDDING_MODEL
        revision = str(archive["revision"].item()) if "revision" in archive else None
    finally:
        archive.close()

    if model != EMBEDDING_MODEL:
        msg = f"index was built with {model}, expected {EMBEDDING_MODEL}; run `make index`"
        raise ValueError(msg)
    if revision != EMBEDDING_REVISION:
        found = revision or "no pinned revision"
        msg = (
            f"index was built with {found}, expected revision {EMBEDDING_REVISION}; "
            "run `make index`"
        )
        raise ValueError(msg)
    if len(ids) == 0:
        msg = f"{resolved}: the index holds no ids"
        raise ValueError(msg)
    vectors = _as_matrix(vectors, rows=len(ids))
    return ids, vectors
