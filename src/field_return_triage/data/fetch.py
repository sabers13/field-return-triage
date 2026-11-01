"""Get the five NHTSA input files, preferring the pinned local snapshot.

The binding spec records a sha256 for every file. A file that matches is used from the
snapshot directory; anything else is downloaded into ``data/raw/`` (gitignored) and
checked. A changed checksum is a **warning, not a stop**: NHTSA rebuilds the complaint
files every day, and the committed derived files are the source of truth. The warning is
printed by ``data_main`` and ``scripts/fetch_nhtsa.py``; it never replaces committed
derived data silently.
"""

from __future__ import annotations

import hashlib
import shutil
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from field_return_triage.data.spec import load_spec

__all__ = ["FetchResult", "InputFile", "ensure_inputs", "sha256_file"]

#: Identifies the downloader without ever sending a credential.
USER_AGENT: Final = "field-return-triage/1.0 (+https://github.com/sabers13/field-return-triage)"
CHUNK: Final = 1024 * 1024


@dataclass(frozen=True)
class InputFile:
    """One input file and where it came from."""

    name: str
    path: Path
    sha256: str
    matched: bool
    source: str  # "snapshot", "cache" or "download"


@dataclass
class FetchResult:
    """Every input path plus the checksum warnings to show the operator."""

    files: dict[str, InputFile] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def all_matched(self) -> bool:
        return all(item.matched for item in self.files.values())


def sha256_file(path: Path) -> str:
    """The lowercase hex sha256 of a file's bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _entries(spec: dict[str, Any]) -> list[dict[str, Any]]:
    entries = spec.get("files", {}).get("entry", [])
    if not entries:
        raise ValueError("the spec lists no files")
    return list(entries)


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    temporary = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as out:
        shutil.copyfileobj(response, out, length=CHUNK)
    temporary.replace(destination)


def _from(path: Path, expected: str) -> tuple[Path, bool, str] | None:
    if not path.is_file():
        return None
    actual = sha256_file(path)
    return path, actual == expected, actual


def ensure_inputs(
    spec: dict[str, Any] | None = None,
    *,
    raw_dir: Path = Path("data/raw"),
) -> FetchResult:
    """Resolve every spec file, using the snapshot first and downloading only as needed."""
    resolved = load_spec() if spec is None else spec
    snapshot = Path(str(resolved.get("snapshot_dir", "")))
    result = FetchResult()
    for entry in _entries(resolved):
        name = str(entry["name"])
        expected = str(entry["sha256"])
        url = str(entry["url"])

        candidate = _from(snapshot / name, expected)
        if candidate is not None and candidate[1]:
            result.files[name] = InputFile(name, candidate[0], candidate[2], True, "snapshot")
            continue

        cached = _from(raw_dir / name, expected)
        if cached is not None and cached[1]:
            result.files[name] = InputFile(name, cached[0], cached[2], True, "cache")
            continue

        destination = raw_dir / name
        _download(url, destination)
        actual = sha256_file(destination)
        matched = actual == expected
        if not matched:
            result.warnings.append(
                f"{name}: downloaded sha256 {actual} differs from the pinned {expected}; "
                "derived files were built from this copy, and the committed data stays "
                "the source of truth"
            )
        result.files[name] = InputFile(name, destination, actual, matched, "download")
    return result
