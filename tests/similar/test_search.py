"""Cosine search: ordering, rounding, ties, neighbour fields and excerpts."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from numpy.typing import NDArray
from support import FakeEmbedder, make_complaint

from field_return_triage.similar.search import EXCERPT_CHARS, nearest, search

Index = tuple[list[str], NDArray[np.float32]]


def _library() -> list:
    return [
        make_complaint("c1", "charging", "battery drains overnight", received=date(2023, 1, 2)),
        make_complaint("c2", "heat", "smoke from connector", received=date(2023, 2, 3)),
        make_complaint(
            "c3",
            "display",
            "intermittent dashboard",
            received=date(2023, 3, 4),
            crash=True,
        ),
        make_complaint("c4", "noise", "unrelated", received=date(2023, 4, 5)),
    ]


def _index(vector_by_id: dict[str, list[float]] | None = None) -> Index:
    vectors = vector_by_id or {
        "c1": [2.0, 0.0],
        "c2": [0.0, 1.0],
        "c3": [1.0, 1.0],
        "c4": [-1.0, 0.0],
    }
    ids = list(vectors)
    matrix = np.asarray(list(vectors.values()), dtype=np.float32)
    return ids, matrix


def _embedder() -> FakeEmbedder:
    return FakeEmbedder({"query": [1.0, 0.0]}, dimensions=2)


def test_search_orders_by_rounded_cosine_with_stable_ties() -> None:
    neighbours = search("query", _index(), _library(), k=4, embedder=_embedder())

    assert [item.complaint_id for item in neighbours] == ["c1", "c3", "c2", "c4"]
    assert [item.score for item in neighbours] == pytest.approx([1.0, 0.7071, 0.0, -1.0])


def test_equal_scores_break_by_complaint_id() -> None:
    library = [
        make_complaint("b", "heat", "b narrative"),
        make_complaint("a", "heat", "a narrative"),
    ]
    index: Index = (["b", "a"], np.array([[1.0, 0.0], [1.0, 0.0]], dtype=np.float32))

    neighbours = search("query", index, library, k=2, embedder=_embedder())

    assert [item.complaint_id for item in neighbours] == ["a", "b"]
    assert [item.score for item in neighbours] == [1.0, 1.0]


def test_neighbour_carries_id_group_date_safety_and_excerpt() -> None:
    neighbours = search("query", _index(), _library(), k=1, embedder=_embedder())

    neighbour = neighbours[0]
    assert neighbour.complaint_id == "c1"
    assert neighbour.group == "charging"
    assert neighbour.received == date(2023, 1, 2)
    assert neighbour.safety_relevant is False
    assert neighbour.excerpt == "battery drains overnight"


def test_coded_crash_makes_the_neighbour_safety_relevant() -> None:
    neighbours = search("query", _index(), _library(), k=3, embedder=_embedder())

    by_id = {item.complaint_id: item for item in neighbours}
    assert by_id["c3"].safety_relevant is True
    assert by_id["c2"].safety_relevant is False


def test_excerpt_is_normalised_and_truncated_to_200_characters() -> None:
    narrative = "  alpha\n\nbeta   gamma\t" + ("word " * 100)
    library = [make_complaint("long", "heat", narrative)]
    index: Index = (["long"], np.array([[1.0, 0.0]], dtype=np.float32))

    neighbour = search("query", index, library, k=1, embedder=_embedder())[0]

    assert len(neighbour.excerpt) == EXCERPT_CHARS
    assert "\n" not in neighbour.excerpt
    assert "  " not in neighbour.excerpt
    assert neighbour.excerpt.startswith("alpha beta gamma word")


def test_k_above_library_size_returns_everything() -> None:
    neighbours = search("query", _index(), _library(), k=99, embedder=_embedder())
    assert len(neighbours) == 4


def test_non_positive_k_is_rejected() -> None:
    for k in (0, -1):
        with pytest.raises(ValueError, match="k must be positive"):
            search("query", _index(), _library(), k=k, embedder=_embedder())


def test_empty_index_returns_no_neighbours() -> None:
    empty: Index = ([], np.zeros((0, 2), dtype=np.float32))
    assert search("query", empty, _library(), embedder=_embedder()) == []


def test_index_id_missing_from_the_library_is_rejected() -> None:
    index: Index = (["absent"], np.array([[1.0, 0.0]], dtype=np.float32))
    with pytest.raises(ValueError, match="not in the library"):
        search("query", index, _library(), embedder=_embedder())


def test_query_dimension_mismatch_is_rejected() -> None:
    index: Index = (["c1"], np.array([[1.0, 0.0]], dtype=np.float32))
    embedder = FakeEmbedder({"query": [1.0, 0.0, 0.0]}, dimensions=3)
    with pytest.raises(ValueError, match="dimensions"):
        search("query", index, _library(), embedder=embedder)


def test_nearest_uses_the_complaint_narrative() -> None:
    query = make_complaint("q", "charging", "query")
    neighbours = nearest(query, _library(), k=2, index=_index(), embedder=_embedder())

    assert [item.complaint_id for item in neighbours] == ["c1", "c3"]
