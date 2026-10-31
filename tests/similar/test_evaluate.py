"""precision@5 against the component group, on known vectors."""

from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray
from support import FakeEmbedder, make_complaint

from field_return_triage.similar.evaluate import precision_at_k

Index = tuple[list[str], NDArray[np.float32]]


def _library() -> list:
    return [
        make_complaint("a1", "charging", "charging one"),
        make_complaint("a2", "charging", "charging two"),
        make_complaint("b1", "heat", "heat one"),
        make_complaint("b2", "heat", "heat two"),
        make_complaint("c1", "noise", "noise one"),
    ]


def _index() -> Index:
    vectors = {
        "a1": [1.0, 0.0],
        "a2": [0.9, 0.1],
        "b1": [0.0, 1.0],
        "b2": [0.1, 0.9],
        "c1": [-1.0, 0.0],
    }
    return list(vectors), np.asarray(list(vectors.values()), dtype=np.float32)


def _embedder() -> FakeEmbedder:
    return FakeEmbedder(
        {
            "query charging": [1.0, 0.0],
            "query heat": [0.0, 1.0],
            "query noise": [-1.0, 0.0],
        },
        dimensions=2,
    )


def test_precision_at_1_counts_matching_groups() -> None:
    queries = [
        make_complaint("q1", "charging", "query charging"),
        make_complaint("q2", "heat", "query heat"),
        make_complaint("q3", "charging", "query noise"),
    ]
    assert precision_at_k(
        queries, _library(), k=1, index=_index(), embedder=_embedder()
    ) == pytest.approx(2 / 3)


def test_precision_at_5_uses_the_full_neighbour_list() -> None:
    queries = [
        make_complaint("q1", "charging", "query charging"),
        make_complaint("q2", "heat", "query heat"),
        make_complaint("q3", "noise", "query noise"),
    ]
    assert precision_at_k(
        queries, _library(), k=5, index=_index(), embedder=_embedder()
    ) == pytest.approx(5 / 15)


def test_fewer_than_k_neighbours_are_not_padded() -> None:
    library = [make_complaint("a1", "charging", "charging one")]
    index: Index = (["a1"], np.array([[1.0, 0.0]], dtype=np.float32))
    query = make_complaint("q", "charging", "query charging")
    assert precision_at_k([query], library, k=5, index=index, embedder=_embedder()) == 1.0


def test_no_queries_gives_zero() -> None:
    assert precision_at_k([], _library(), embedder=_embedder()) == 0.0


def test_query_without_a_group_scores_zero() -> None:
    query = make_complaint("q", None, "query charging")
    assert precision_at_k([query], _library(), k=1, index=_index(), embedder=_embedder()) == 0.0


def test_non_positive_k_is_rejected() -> None:
    with pytest.raises(ValueError, match="k must be positive"):
        precision_at_k([], _library(), k=0, embedder=_embedder())
