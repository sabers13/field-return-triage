"""Index persistence: cache location, data key and round trip."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from support import FakeEmbedder, make_complaint

from field_return_triage.similar import index as index_module
from field_return_triage.similar.embedder import EMBEDDING_MODEL, EMBEDDING_REVISION
from field_return_triage.similar.index import (
    build_index,
    cache_dir,
    checksum_key,
    index_path,
    load_index,
)


def _library() -> list:
    return [
        make_complaint("c1", "charging", "battery drains overnight"),
        make_complaint("c2", "heat", "smoke from the connector"),
        make_complaint("c3", "noise", "rattle over bumps"),
    ]


def test_cache_lives_outside_the_repository() -> None:
    assert cache_dir() == Path.home() / ".cache" / "field-return-triage"
    assert "field-return-triage" in str(cache_dir())


def test_build_index_round_trips_ids_and_normalised_vectors(checksums: Path) -> None:
    library = _library()
    embedder = FakeEmbedder(
        {
            "battery drains overnight": [2.0, 0.0, 0.0, 0.0],
            "smoke from the connector": [0.0, 4.0, 0.0, 0.0],
            "rattle over bumps": [0.0, 0.0, 0.5, 0.0],
        },
        dimensions=4,
    )

    path = build_index(library, embedder=embedder, checksums=checksums)

    assert path.is_file()
    assert path.parent == cache_dir()
    assert checksum_key(checksums) in path.name
    ids, vectors = load_index(path)
    assert ids == ["c1", "c2", "c3"]
    assert vectors.shape == (3, 4)
    np.testing.assert_allclose(
        vectors,
        np.array(
            [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
            ],
            dtype=np.float32,
        ),
    )
    assert embedder.calls == [
        ["battery drains overnight", "smoke from the connector", "rattle over bumps"]
    ]


def test_data_key_changes_with_the_checksums_file(tmp_path: Path) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("library.jsonl.gz  aaaa\n", encoding="utf-8")
    second.write_text("library.jsonl.gz  bbbb\n", encoding="utf-8")
    same = tmp_path / "same.txt"
    same.write_text("library.jsonl.gz  aaaa\n", encoding="utf-8")

    assert index_path(first) == index_path(same)
    assert index_path(first) != index_path(second)


def test_missing_checksums_fails_before_any_embedding(tmp_path: Path) -> None:
    embedder = FakeEmbedder()
    with pytest.raises(FileNotFoundError, match="make data"):
        build_index(_library(), embedder=embedder, checksums=tmp_path / "absent.txt")
    assert embedder.calls == []


def test_duplicate_ids_are_rejected(checksums: Path) -> None:
    library = _library()
    library.append(make_complaint("c1", "heat", "duplicate id"))
    with pytest.raises(ValueError, match="duplicate complaint ids"):
        build_index(library, embedder=FakeEmbedder(), checksums=checksums)


def test_empty_library_is_rejected(checksums: Path) -> None:
    with pytest.raises(ValueError, match="empty library"):
        build_index([], embedder=FakeEmbedder(), checksums=checksums)


def test_wrong_vector_count_is_rejected(checksums: Path) -> None:
    class ShortEmbedder:
        def encode(self, texts: object, *, batch_size: int = 64) -> np.ndarray:
            return np.zeros((1, 2), dtype=np.float32)

    with pytest.raises(ValueError, match="vectors for"):
        build_index(_library(), embedder=ShortEmbedder(), checksums=checksums)


def test_missing_index_names_the_command_to_run(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="make index"):
        load_index(tmp_path / "absent.npz")


def test_index_pins_and_checks_the_embedding_revision(checksums: Path) -> None:
    path = build_index(_library(), embedder=FakeEmbedder(), checksums=checksums)
    with np.load(path, allow_pickle=False) as archive:
        assert str(archive["revision"].item()) == EMBEDDING_REVISION

    np.savez_compressed(
        path,
        ids=np.asarray(["c1"], dtype=np.str_),
        vectors=np.ones((1, 4), dtype=np.float32),
        model=np.asarray(EMBEDDING_MODEL),
        checksums=np.asarray(checksum_key(checksums)),
    )
    with pytest.raises(ValueError, match="no pinned revision"):
        load_index(path)


def test_a_different_revision_is_refused(checksums: Path) -> None:
    path = build_index(_library(), embedder=FakeEmbedder(), checksums=checksums)
    np.savez_compressed(
        path,
        ids=np.asarray(["c1"], dtype=np.str_),
        vectors=np.ones((1, 4), dtype=np.float32),
        model=np.asarray(EMBEDDING_MODEL),
        revision=np.asarray("0" * 40),
        checksums=np.asarray(checksum_key(checksums)),
    )
    with pytest.raises(ValueError, match="expected revision"):
        load_index(path)


def test_corrupt_index_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "index.npz"
    path.write_bytes(b"not an npz")
    with pytest.raises(ValueError, match="pickled"):
        load_index(path)


def test_index_built_with_another_model_is_rejected(checksums: Path, tmp_path: Path) -> None:
    path = build_index(_library(), embedder=FakeEmbedder(), checksums=checksums)
    with np.load(path, allow_pickle=False) as archive:
        ids = archive["ids"]
        vectors = archive["vectors"]
    other = tmp_path / "other.npz"
    np.savez_compressed(other, ids=ids, vectors=vectors, model=np.asarray("other/model"))
    with pytest.raises(ValueError, match="run `make index`"):
        load_index(other)


def test_module_default_path_is_keyed_by_the_committed_checksums(tmp_path: Path) -> None:
    committed = tmp_path / "CHECKSUMS.txt"
    committed.write_text("library.jsonl.gz  cccc\n", encoding="utf-8")
    assert index_module.index_path(committed) == index_path(committed)
