"""``index_main`` reads the committed library and writes the cache."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest
import typer
from support import FakeEmbedder, make_complaint

from field_return_triage.similar.cli import index_main
from field_return_triage.similar.index import load_index


def _write_library(path: Path, complaints: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for complaint in complaints:
            handle.write(json.dumps(complaint.model_dump(mode="json"), sort_keys=True) + "\n")


def _checksums(tmp_path: Path) -> Path:
    path = tmp_path / "CHECKSUMS.txt"
    path.write_text("library.jsonl.gz  e5e5\n", encoding="utf-8")
    return path


def test_index_main_embeds_the_library_and_reports_timing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    library = [
        make_complaint("c1", "charging", "battery drains overnight"),
        make_complaint("c2", "heat", "smoke from connector"),
    ]
    library_path = tmp_path / "data" / "library.jsonl.gz"
    _write_library(library_path, library)

    index_main(
        library_path=library_path,
        checksums=_checksums(tmp_path),
        embedder=FakeEmbedder(
            {
                "battery drains overnight": [1.0, 0.0],
                "smoke from connector": [0.0, 1.0],
            },
            dimensions=2,
        ),
    )

    output = capsys.readouterr().out
    assert "embedded 2 complaints" in output
    assert "in " in output
    assert "s -> " in output
    cache_file = Path(output.rsplit("-> ", 1)[1].strip())
    ids, vectors = load_index(cache_file)
    assert ids == ["c1", "c2"]
    assert vectors.shape == (2, 2)


def test_missing_library_exits_with_a_pointer_to_make_data(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(typer.Exit) as raised:
        index_main(
            library_path=tmp_path / "absent.jsonl.gz",
            checksums=_checksums(tmp_path),
            embedder=FakeEmbedder(),
        )
    assert raised.value.exit_code == 1
    assert "make data" in capsys.readouterr().err


def test_invalid_jsonl_line_exits_with_the_location(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    library_path = tmp_path / "library.jsonl.gz"
    with gzip.open(library_path, "wt", encoding="utf-8") as handle:
        handle.write('{"not": "a complaint"}\n')

    with pytest.raises(typer.Exit) as raised:
        index_main(
            library_path=library_path,
            checksums=_checksums(tmp_path),
            embedder=FakeEmbedder(),
        )
    assert raised.value.exit_code == 1
    assert "not a complaint" in capsys.readouterr().err


def test_empty_library_exits(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    library_path = tmp_path / "library.jsonl.gz"
    with gzip.open(library_path, "wt", encoding="utf-8"):
        pass

    with pytest.raises(typer.Exit) as raised:
        index_main(
            library_path=library_path,
            checksums=_checksums(tmp_path),
            embedder=FakeEmbedder(),
        )
    assert raised.value.exit_code == 1
    assert "holds no complaints" in capsys.readouterr().err


def test_missing_checksums_exits_with_a_pointer_to_make_data(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    library_path = tmp_path / "library.jsonl.gz"
    _write_library(library_path, [make_complaint("c1", "charging", "battery drains overnight")])

    with pytest.raises(typer.Exit) as raised:
        index_main(
            library_path=library_path,
            checksums=tmp_path / "absent.txt",
            embedder=FakeEmbedder(),
        )
    assert raised.value.exit_code == 1
    assert "make data" in capsys.readouterr().err
