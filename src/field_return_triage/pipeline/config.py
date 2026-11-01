"""Where the pipeline reads its inputs from (PLAN.md section 3 and 9).

One place decides the paths, so ``frt triage``, ``frt eval``, ``make results`` and the
baseline builder cannot disagree. Every path can be overridden by an explicit argument
or by an ``FRT_*`` environment variable; the defaults are the committed files.

Before lane R7 writes ``config/models.lock.toml`` and ``recordings/`` the pipeline runs
in **fixture mode**: two fake models and 20 fake recordings under
``tests/fixtures/recordings/``. Fixture mode is announced on every command line and in
``results/SUMMARY.md``; it never pretends to be a model result.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray

from field_return_triage.contracts import Complaint
from field_return_triage.data.io import load_library
from field_return_triage.llm.errors import ConfigurationError
from field_return_triage.similar.embedder import EMBEDDING_DIMENSIONS, Embedder
from field_return_triage.similar.index import index_path, load_index

__all__ = [
    "DEFAULT_CHECKSUMS",
    "DEFAULT_GROUPS",
    "DEFAULT_ITEMS",
    "DEFAULT_LIBRARY",
    "DEFAULT_MODELS",
    "DEFAULT_PRICES",
    "DEFAULT_RECORDINGS",
    "FIXTURE_DIR",
    "HashingEmbedder",
    "Paths",
    "fixture_index",
    "load_group_descriptions",
    "resolve_paths",
]

DEFAULT_MODELS: Final[Path] = Path("config/models.lock.toml")
DEFAULT_ITEMS: Final[Path] = Path("data/eval.jsonl")
DEFAULT_LIBRARY: Final[Path] = Path("data/library.jsonl.gz")
DEFAULT_GROUPS: Final[Path] = Path("data/groups.toml")
DEFAULT_RECORDINGS: Final[Path] = Path("recordings")
DEFAULT_PRICES: Final[Path] = Path("config/prices.toml")
DEFAULT_CHECKSUMS: Final[Path] = Path("data/CHECKSUMS.txt")

FIXTURE_DIR: Final[Path] = Path("tests/fixtures/recordings")
FIXTURE_MODELS: Final[Path] = FIXTURE_DIR / "models.lock.toml"
FIXTURE_ITEMS: Final[Path] = FIXTURE_DIR / "items.jsonl"
FIXTURE_LIBRARY: Final[Path] = FIXTURE_DIR / "library.jsonl.gz"


def _env(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else None


def _pick(explicit: Path | None, env_name: str, default: Path) -> Path:
    if explicit is not None:
        return explicit
    from_env = _env(env_name)
    return from_env if from_env is not None else default


@dataclass(frozen=True, slots=True)
class Paths:
    """Every input path for one pipeline invocation."""

    models: Path
    items: Path
    library: Path
    groups: Path
    recordings: Path
    prices: Path
    checksums: Path
    fixture: bool

    def describe(self) -> str:
        """A one-line, credential-free description for the CLI."""
        if self.fixture:
            return (
                "fixture mode: no config/models.lock.toml yet, so two fake models and "
                f"the 20 fake recordings in {FIXTURE_DIR} are used"
            )
        return f"models: {self.models}, recordings: {self.recordings}"


def resolve_paths(
    *,
    models: Path | None = None,
    items: Path | None = None,
    library: Path | None = None,
    groups: Path | None = None,
    recordings: Path | None = None,
    prices: Path | None = None,
    checksums: Path | None = None,
) -> Paths:
    """Resolve every input path, falling back to fixtures until R7 locks models.

    Fixture mode is on when the chosen models file is the missing default lock or the
    committed fixture lock itself. The other paths then default to the fixture copies,
    so one switch keeps a run self-consistent.
    """
    chosen_models = _pick(models, "FRT_MODELS", DEFAULT_MODELS)
    fixture = chosen_models.resolve() == FIXTURE_MODELS.resolve() or (
        chosen_models == DEFAULT_MODELS and not chosen_models.is_file()
    )
    resolved_models = (
        FIXTURE_MODELS if fixture and chosen_models == DEFAULT_MODELS else chosen_models
    )

    items_default = FIXTURE_ITEMS if fixture else DEFAULT_ITEMS
    library_default = FIXTURE_LIBRARY if fixture else DEFAULT_LIBRARY
    recordings_default = FIXTURE_DIR if fixture else DEFAULT_RECORDINGS

    resolved = Paths(
        models=resolved_models,
        items=_pick(items, "FRT_ITEMS", items_default),
        library=_pick(library, "FRT_LIBRARY", library_default),
        groups=_pick(groups, "FRT_GROUPS", DEFAULT_GROUPS),
        recordings=_pick(recordings, "FRT_RECORDINGS", recordings_default),
        prices=_pick(prices, "FRT_PRICES", DEFAULT_PRICES),
        checksums=_pick(checksums, "FRT_CHECKSUMS", DEFAULT_CHECKSUMS),
        fixture=fixture,
    )
    if not resolved.models.is_file():
        msg = f"model lock not found: {resolved.models}"
        raise ConfigurationError(msg)
    return resolved


def load_group_descriptions(path: Path = DEFAULT_GROUPS) -> dict[str, str]:
    """Group id -> its one-line description, for prompt ``e1``.

    ``data/groups.toml`` carries a description per group (``docs/INTERFACES.md`` section
    3 keeps the prefixes for the data lane). A file without descriptions falls back to
    the first prefixes, so a hand-written group file still produces a usable prompt.
    """
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except FileNotFoundError:
        msg = f"group file not found: {path}"
        raise ConfigurationError(msg) from None
    except (OSError, tomllib.TOMLDecodeError) as exc:
        msg = f"cannot read {path}: {exc.__class__.__name__}"
        raise ConfigurationError(msg) from None

    descriptions: dict[str, str] = {}
    for entry in raw.get("group", []):
        if not isinstance(entry, dict):
            continue
        group_id = str(entry.get("id", "")).strip()
        if not group_id:
            continue
        description = str(entry.get("description", "")).strip()
        if not description:
            prefixes = entry.get("prefixes", [])
            description = ", ".join(str(prefix) for prefix in prefixes[:3])
        descriptions[group_id] = description or group_id
    if not descriptions:
        msg = f"{path}: no group descriptions found"
        raise ConfigurationError(msg)
    return descriptions


class HashingEmbedder:
    """A deterministic offline embedder for fixture mode only.

    It hashes word tokens into ``EMBEDDING_DIMENSIONS`` signed buckets and L2-normalises
    the result, so fixture runs need neither torch nor a model download. It is never used
    with real data: the real path goes through :func:`similar.default_embedder`.
    """

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        if dimensions <= 0:
            msg = "dimensions must be positive"
            raise ValueError(msg)
        self.dimensions = dimensions

    def _bucket(self, token: str) -> tuple[int, float]:
        import hashlib

        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        return value % self.dimensions, 1.0 if (value >> 63) & 1 else -1.0

    def encode(
        self,
        texts: Sequence[str],
        *,
        batch_size: int = 64,
    ) -> NDArray[np.float32]:
        """Embed ``texts`` into a row-normalised float32 matrix."""
        if batch_size <= 0:
            msg = "batch_size must be positive"
            raise ValueError(msg)
        items = [str(item) for item in texts]
        matrix = np.zeros((len(items), self.dimensions), dtype=np.float32)
        for row, text in enumerate(items):
            for token in _tokens(text):
                index, sign = self._bucket(token)
                matrix[row, index] += sign
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        return np.asarray(matrix / norms, dtype=np.float32)


def _tokens(text: str) -> list[str]:
    stripped = "".join(char.lower() if char.isalnum() else " " for char in text)
    return [word for word in stripped.split() if len(word) > 1]


def fixture_index(library: list[Complaint]) -> tuple[list[str], NDArray[np.float32]]:
    """The in-process index for fixture mode, built with :class:`HashingEmbedder`."""
    embedder: Embedder = HashingEmbedder()
    vectors = np.asarray(embedder.encode([item.narrative for item in library]), dtype=np.float32)
    return [item.id for item in library], vectors


def resolve_index(
    paths: Paths,
    *,
    embedder: Embedder | None = None,
) -> tuple[tuple[list[str], NDArray[np.float32]] | None, Embedder | None]:
    """The neighbour index and embedder for a run, or ``(None, None)``.

    Fixture mode builds a cheap in-process index. Real mode loads the cached embedding
    index; when ``make index`` has not run yet the pipeline still evaluates, with an
    empty neighbour list (the card says so by carrying no neighbours).
    """
    if paths.fixture:
        model: Embedder = embedder if embedder is not None else HashingEmbedder()
        library = load_library(paths.library)
        vectors = np.asarray(
            model.encode([item.narrative for item in library]),
            dtype=np.float32,
        )
        return ([item.id for item in library], vectors), model

    if embedder is not None:
        library = load_library(paths.library)
        vectors = np.asarray(
            embedder.encode([item.narrative for item in library]),
            dtype=np.float32,
        )
        return ([item.id for item in library], vectors), embedder

    try:
        return load_index(index_path(paths.checksums)), None
    except (FileNotFoundError, ValueError):
        return None, None


def empty_index() -> tuple[list[str], NDArray[np.float32]]:
    """An index with no ids: ``search`` returns no neighbours for it."""
    return [], np.zeros((0, EMBEDDING_DIMENSIONS), dtype=np.float32)
