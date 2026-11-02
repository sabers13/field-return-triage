"""``frt index`` / ``make index``: embed the committed library into the local cache.

This is the one command in the project that may download the embedding model, once. It
reads ``data/library.jsonl.gz`` directly (the similar lane does not import the data lane;
the contracts are the shared surface) and writes vectors to
``~/.cache/field-return-triage/``, keyed by ``data/CHECKSUMS.txt``. Re-running is cheap:
the same data snapshot reuses the same cache file name.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from time import perf_counter
from typing import Final

import typer

from field_return_triage.contracts import Complaint
from field_return_triage.similar.embedder import Embedder, default_embedder
from field_return_triage.similar.index import DEFAULT_CHECKSUMS, build_index

__all__ = ["DEFAULT_LIBRARY", "index_main"]

DEFAULT_LIBRARY: Final[Path] = Path("data/library.jsonl.gz")


def _read_library(path: Path) -> list[Complaint]:
    """Read one ``Complaint`` per gzipped JSONL line."""
    if not path.is_file():
        typer.echo(f"frt index: {path} is missing; run `make data` first", err=True)
        raise typer.Exit(code=1)
    library: list[Complaint] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                library.append(Complaint.model_validate(json.loads(line)))
            except ValueError as exc:
                typer.echo(f"frt index: {path}:{lineno}: not a complaint: {exc}", err=True)
                raise typer.Exit(code=1) from exc
    if not library:
        typer.echo(f"frt index: {path} holds no complaints", err=True)
        raise typer.Exit(code=1)
    return library


def index_main(
    *,
    library_path: Path = DEFAULT_LIBRARY,
    checksums: Path = DEFAULT_CHECKSUMS,
    embedder: Embedder | None = None,
) -> None:
    """Embed the library and report the cache path, item count and elapsed time."""
    library = _read_library(library_path)
    started = perf_counter()
    try:
        chosen = embedder if embedder is not None else default_embedder(allow_download=True)
        path = build_index(library, embedder=chosen, checksums=checksums)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        typer.echo(f"frt index: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    elapsed = perf_counter() - started
    typer.echo(f"frt index: embedded {len(library)} complaints in {elapsed:.1f}s -> {path}")


if __name__ == "__main__":  # pragma: no cover - `make index` entry point
    index_main()
