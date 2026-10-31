"""Small helpers shared by the similar-lane tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

import numpy as np
from numpy.typing import NDArray

from field_return_triage.contracts import Complaint


class FakeEmbedder:
    """A deterministic embedder: known texts use a fixed vector, others a char bag.

    It records every batch so a test can prove the model was called (or not called)
    at the right time. No network, no model weights, no randomness.
    """

    def __init__(
        self,
        vectors: Mapping[str, Sequence[float]] | None = None,
        *,
        dimensions: int = 4,
    ) -> None:
        self._vectors = {
            text: np.asarray(vector, dtype=np.float32) for text, vector in (vectors or {}).items()
        }
        self._dimensions = dimensions
        self.calls: list[list[str]] = []

    def encode(
        self,
        texts: Sequence[str],
        *,
        batch_size: int = 64,
    ) -> NDArray[np.float32]:
        if batch_size <= 0:
            msg = f"batch_size must be positive, got {batch_size}"
            raise ValueError(msg)
        items = list(texts)
        self.calls.append(items)
        if not items:
            return np.zeros((0, self._dimensions), dtype=np.float32)
        rows = [self._vectors.get(text, self._fallback(text)) for text in items]
        return np.vstack(rows).astype(np.float32)

    def _fallback(self, text: str) -> NDArray[np.float32]:
        vector = np.zeros(self._dimensions, dtype=np.float32)
        for char in text:
            vector[ord(char) % self._dimensions] += 1.0
        return vector


def make_complaint(
    complaint_id: str,
    group: str | None,
    narrative: str,
    *,
    received: date = date(2023, 5, 1),
    crash: bool = False,
    fire: bool = False,
    injury: bool = False,
) -> Complaint:
    """One valid contract, with only the fields a similar-case test cares about."""
    return Complaint(
        id=complaint_id,
        narrative=narrative,
        received=received,
        group=group,
        crash=crash,
        fire=fire,
        injury=injury,
    )
