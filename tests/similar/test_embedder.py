"""The embedding pin and the lazy model seam (no download in tests)."""

from __future__ import annotations

import sys

import pytest

from field_return_triage.similar.embedder import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    EMBEDDING_REVISION,
    SentenceTransformerEmbedder,
    default_embedder,
)


def test_model_and_revision_are_pinned() -> None:
    assert EMBEDDING_MODEL == "BAAI/bge-small-en-v1.5"
    assert EMBEDDING_REVISION == "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
    assert EMBEDDING_DIMENSIONS == 384


def test_importing_the_lane_does_not_import_the_model() -> None:
    assert "sentence_transformers" not in sys.modules


def test_empty_input_needs_no_model() -> None:
    embedder = SentenceTransformerEmbedder()
    vectors = embedder.encode([])

    assert vectors.shape == (0, EMBEDDING_DIMENSIONS)
    assert vectors.dtype.name == "float32"
    assert embedder._model is None


def test_non_positive_batch_size_is_rejected_before_loading() -> None:
    with pytest.raises(ValueError, match="batch_size must be positive"):
        SentenceTransformerEmbedder().encode([], batch_size=0)


def test_default_embedder_is_one_process_wide_instance() -> None:
    assert default_embedder() is default_embedder()


def test_replay_is_offline_and_only_make_index_may_download() -> None:
    assert SentenceTransformerEmbedder()._local_files_only is True
    assert SentenceTransformerEmbedder(local_files_only=False)._local_files_only is False
    assert default_embedder() is not default_embedder(allow_download=True)
