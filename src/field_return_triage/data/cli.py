"""``frt data`` / ``make data``: fetch the snapshot, derive and write the data files.

The command is deterministic and offline once the pinned snapshot is present. It writes
``data/library.jsonl.gz``, ``data/eval.jsonl``, ``data/trend/weekly.csv.gz``,
``data/trend/recalls.csv``, ``data/STATS.md`` and ``data/CHECKSUMS.txt``. A changed input
checksum is printed as a warning; it never silently replaces the committed data in git.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Final

import typer

from field_return_triage.data.complaints import (
    ResolutionStats,
    _date,
    derive_eval,
    derive_library,
    resolve_complaints_with_stats,
    screen_narratives,
)
from field_return_triage.data.fetch import ensure_inputs
from field_return_triage.data.io import (
    write_eval,
    write_library,
    write_recalls,
    write_weekly,
)
from field_return_triage.data.parse import (
    parse_complaint_rows,
    parse_recall_rows,
    read_archive_lines,
)
from field_return_triage.data.recalls import (
    RecallResolutionStats,
    derive_recalls,
    resolve_recalls_with_stats,
)
from field_return_triage.data.spec import (
    DEFAULT_GROUPS_PATH,
    DEFAULT_SPEC_PATH,
    TEST_END,
    TEST_START,
    load_groups,
    load_spec,
)
from field_return_triage.data.stats import StatsInput, build_stats
from field_return_triage.data.weekly import derive_weekly

__all__ = [
    "CHECKSUMS_PATH",
    "DATA_DIR",
    "EVAL_PATH",
    "LIBRARY_PATH",
    "RECALLS_PATH",
    "STATS_PATH",
    "WEEKLY_PATH",
    "data_main",
]

DATA_DIR: Final = Path("data")
LIBRARY_PATH: Final = DATA_DIR / "library.jsonl.gz"
EVAL_PATH: Final = DATA_DIR / "eval.jsonl"
WEEKLY_PATH: Final = DATA_DIR / "trend" / "weekly.csv.gz"
RECALLS_PATH: Final = DATA_DIR / "trend" / "recalls.csv"
CHECKSUMS_PATH: Final = DATA_DIR / "CHECKSUMS.txt"
STATS_PATH: Final = DATA_DIR / "STATS.md"

#: Files recorded in ``CHECKSUMS.txt``, relative to the repository root.
CHECKSUMMED: Final[tuple[Path, ...]] = (
    DEFAULT_SPEC_PATH,
    DEFAULT_GROUPS_PATH,
    DATA_DIR / "safety_keywords.txt",
    DATA_DIR / "condition_keywords.toml",
    LIBRARY_PATH,
    EVAL_PATH,
    WEEKLY_PATH,
    RECALLS_PATH,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_checksums(path: Path, files: tuple[Path, ...]) -> None:
    lines = [f"{_sha256(file)}  {file.as_posix()}" for file in sorted(files)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _archive_members(spec: dict[str, Any]) -> dict[str, str]:
    parse = spec.get("parse", {})
    archives = parse.get("archive", []) if isinstance(parse, dict) else []
    if not isinstance(archives, list):
        return {}
    return {
        str(entry["file"]): str(entry["member"])
        for entry in archives
        if isinstance(entry, dict) and "file" in entry and "member" in entry
    }


def _entries(spec: dict[str, Any]) -> list[dict[str, Any]]:
    files = spec.get("files", {})
    entries = files.get("entry", []) if isinstance(files, dict) else []
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def data_main() -> None:
    """Fetch, derive, write and checksum the committed data files."""
    spec = load_spec()
    fetched = ensure_inputs(spec)
    for warning in fetched.warnings:
        typer.echo(f"frt data: warning: {warning}", err=True)

    groups = load_groups()
    members = _archive_members(spec)
    entries = _entries(spec)

    resolved: list[dict[str, Any]] = []
    resolution = ResolutionStats()
    for entry in entries:
        if entry.get("role") != "complaints":
            continue
        name = str(entry["name"])
        input_file = fetched.files[name]
        member = members.get(name)
        if member is None:
            raise ValueError(f"{name}: the spec has no archive member for this file")
        chunk, chunk_stats = resolve_complaints_with_stats(
            parse_complaint_rows(read_archive_lines(input_file.path, member)),
            groups,
        )
        resolution.merge(chunk_stats)
        resolved.extend(chunk)

    screen = screen_narratives(resolved)
    library = derive_library(screen.rows, groups)
    eval_items = derive_eval(screen.rows, groups)
    weekly = derive_weekly(resolved)

    recall_rows: list[dict[str, Any]] = []
    recall_stats = RecallResolutionStats()
    for entry in entries:
        if entry.get("role") != "recalls":
            continue
        name = str(entry["name"])
        input_file = fetched.files[name]
        member = members.get(name)
        if member is None:
            raise ValueError(f"{name}: the spec has no archive member for this file")
        chunk, chunk_recall_stats = resolve_recalls_with_stats(
            parse_recall_rows(read_archive_lines(input_file.path, member)),
            groups,
        )
        recall_stats.merge(chunk_recall_stats)
        recall_rows.extend(chunk)
    recalls = derive_recalls(recall_rows)

    test_pool = [
        row
        for row in screen.rows
        if TEST_START <= _date(row.get("LDATE")) <= TEST_END
    ]

    write_library(library, LIBRARY_PATH)
    write_eval(eval_items, EVAL_PATH)
    write_weekly(weekly, WEEKLY_PATH)
    write_recalls(recalls, RECALLS_PATH)
    _write_checksums(CHECKSUMS_PATH, CHECKSUMMED)

    stats = build_stats(
        StatsInput(
            snapshot=str(spec.get("snapshot", "")),
            groups=tuple(groups),
            resolution=resolution,
            screen=screen,
            library=library,
            eval_items=eval_items,
            test_pool=test_pool,
            recalls=recall_stats,
            recalls_written=len(recalls),
        )
    )
    STATS_PATH.write_text(stats, encoding="utf-8")

    typer.echo(
        f"frt data: library {len(library)}, evaluation {len(eval_items)}, "
        f"weekly rows {len(weekly)}, recalls {len(recalls)}"
    )
    typer.echo(f"frt data: wrote {CHECKSUMS_PATH} and {STATS_PATH}")


if __name__ == "__main__":  # pragma: no cover - `make data` entry point
    data_main()
