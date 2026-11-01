"""The cost-free baselines of ``PLAN.md`` section 6.

Three deterministic baselines run on the evaluation set with no model call:

* **group**: TF-IDF plus a multinomial logistic-regression classifier trained on the
  library (implemented here with numpy, so the project needs no extra dependency);
* **safety**: the committed keyword rule against the coded crash/fire/injury fields;
* **conditions**: the committed keyword rule's output, reported as coverage of the
  evaluation set and explicitly labelled agreement data, not accuracy.

The classifier is deterministic: fixed vocabulary order, zero initial weights, fixed
mini-batch order and no random state. The files are written by ``make results``.
"""

from __future__ import annotations

import json
import math
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray

from field_return_triage.contracts import Complaint
from field_return_triage.pipeline.metrics import (
    Metric,
    accuracy,
    answered_accuracy,
    coverage,
    macro_f1,
    wilson_interval,
)
from field_return_triage.rules.keywords import keyword_safety

__all__ = [
    "CONDITION_KEYWORDS_PATH",
    "TFIDF_MAX_FEATURES",
    "load_condition_keywords",
    "run_baselines",
    "write_baselines",
]

CONDITION_KEYWORDS_PATH: Final[Path] = Path("data/condition_keywords.toml")

#: Vocabulary cap: enough for the complaint vocabulary, small enough to train in seconds.
TFIDF_MAX_FEATURES: Final = 20_000
_EPOCHS: Final = 12
_BATCH: Final = 256
_LEARNING_RATE: Final = 0.6
_L2: Final = 1e-4

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return [word for word in _TOKEN.findall(text.casefold()) if len(word) > 1]


@dataclass(frozen=True, slots=True)
class _Sparse:
    """A document-term matrix in flat coordinate form."""

    rows: int
    features: int
    doc_index: NDArray[np.int32]
    column: NDArray[np.int32]
    weight: NDArray[np.float64]

    def batch(
        self, start: int, stop: int
    ) -> tuple[NDArray[np.int64], NDArray[np.int32], NDArray[np.float64]]:
        """The entries whose document index is in ``[start, stop)``."""
        mask = (self.doc_index >= start) & (self.doc_index < stop)
        return (
            (self.doc_index[mask] - start).astype(np.int64),
            self.column[mask],
            self.weight[mask],
        )


def _fit_vectoriser(
    texts: Sequence[str],
    *,
    max_features: int = TFIDF_MAX_FEATURES,
) -> tuple[dict[str, int], NDArray[np.float64], list[dict[str, int]]]:
    """Build the vocabulary, the idf vector and one term-frequency map per document."""
    document_frequency: dict[str, int] = {}
    term_counts: list[dict[str, int]] = []
    for text in texts:
        counts: dict[str, int] = {}
        for token in _tokens(text):
            counts[token] = counts.get(token, 0) + 1
        term_counts.append(counts)
        for token in counts:
            document_frequency[token] = document_frequency.get(token, 0) + 1

    ranked = sorted(document_frequency, key=lambda term: (-document_frequency[term], term))
    vocabulary = {term: index for index, term in enumerate(ranked[:max_features])}
    total = len(texts)
    idf = np.asarray(
        [math.log((1.0 + total) / (1.0 + document_frequency[term])) + 1.0 for term in vocabulary],
        dtype=np.float64,
    )
    return vocabulary, idf, term_counts


def _transform(
    term_counts: Sequence[dict[str, int]],
    vocabulary: Mapping[str, int],
    idf: NDArray[np.float64],
) -> _Sparse:
    doc_indices: list[int] = []
    columns: list[int] = []
    weights: list[float] = []
    for row, counts in enumerate(term_counts):
        pairs = [
            (vocabulary[token], 1.0 + math.log(count))
            for token, count in counts.items()
            if token in vocabulary
        ]
        if not pairs:
            continue
        norm = math.sqrt(sum((value * float(idf[column])) ** 2 for column, value in pairs))
        norm = norm or 1.0
        for column, value in sorted(pairs):
            doc_indices.append(row)
            columns.append(column)
            weights.append(value * float(idf[column]) / norm)
    return _Sparse(
        rows=len(term_counts),
        features=len(vocabulary),
        doc_index=np.asarray(doc_indices, dtype=np.int32),
        column=np.asarray(columns, dtype=np.int32),
        weight=np.asarray(weights, dtype=np.float64),
    )


def _softmax(scores: NDArray[np.float64]) -> NDArray[np.float64]:
    shifted = scores - scores.max(axis=1, keepdims=True)
    exponent = np.exp(shifted)
    return exponent / exponent.sum(axis=1, keepdims=True)


def _train(
    matrix: _Sparse,
    labels: NDArray[np.int64],
    classes: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Full deterministic mini-batch softmax regression."""
    weights = np.zeros((matrix.features, classes), dtype=np.float64)
    bias = np.zeros(classes, dtype=np.float64)
    for _epoch in range(_EPOCHS):
        for start in range(0, matrix.rows, _BATCH):
            stop = min(start + _BATCH, matrix.rows)
            rows, columns, values = matrix.batch(start, stop)
            size = stop - start
            if size == 0:
                continue
            scores = np.zeros((size, classes), dtype=np.float64) + bias
            if rows.size:
                contributions = values[:, None] * weights[columns]
                for index in range(size):
                    selected = rows == index
                    if selected.any():
                        scores[index] += contributions[selected].sum(axis=0)
            probabilities = _softmax(scores)
            error = probabilities
            error[np.arange(size), labels[start:stop]] -= 1.0
            error /= size

            gradient = np.zeros_like(weights)
            for class_index in range(classes):
                if rows.size:
                    gradient[:, class_index] = np.bincount(
                        columns,
                        weights=values * error[rows, class_index],
                        minlength=matrix.features,
                    )
            gradient += _L2 * weights
            weights -= _LEARNING_RATE * gradient
            bias -= _LEARNING_RATE * error.sum(axis=0)
    return weights, bias


def _predict(
    matrix: _Sparse,
    weights: NDArray[np.float64],
    bias: NDArray[np.float64],
) -> NDArray[np.int64]:
    predictions = np.zeros(matrix.rows, dtype=np.int64)
    for start in range(0, matrix.rows, _BATCH):
        stop = min(start + _BATCH, matrix.rows)
        rows, columns, values = matrix.batch(start, stop)
        size = stop - start
        scores = np.zeros((size, weights.shape[1]), dtype=np.float64) + bias
        if rows.size:
            contributions = values[:, None] * weights[columns]
            for index in range(size):
                selected = rows == index
                if selected.any():
                    scores[index] += contributions[selected].sum(axis=0)
        predictions[start:stop] = np.argmax(scores, axis=1)
    return predictions


def _group_baseline(items: Sequence[Complaint], library: Sequence[Complaint]) -> dict[str, object]:
    training = [row for row in library if row.group]
    queries = [row for row in items if row.group]
    if not training or not queries:
        return {
            "method": "TF-IDF + multinomial logistic regression",
            "available": False,
            "reason": "the library or the evaluation set has no grouped complaint",
            "metrics": {},
        }

    vocabulary, idf, counts = _fit_vectoriser([row.narrative for row in training])
    matrix = _transform(counts, vocabulary, idf)
    classes = sorted({str(row.group) for row in training})
    index_of = {label: position for position, label in enumerate(classes)}
    labels = np.asarray([index_of[str(row.group)] for row in training], dtype=np.int64)
    weights, bias = _train(matrix, labels, len(classes))

    query_counts: list[dict[str, int]] = []
    for text in [row.narrative for row in queries]:
        counts_for_row: dict[str, int] = {}
        for token in _tokens(text):
            counts_for_row[token] = counts_for_row.get(token, 0) + 1
        query_counts.append(counts_for_row)
    query_matrix = _transform(query_counts, vocabulary, idf)
    predicted = [classes[int(position)] for position in _predict(query_matrix, weights, bias)]
    gold = [str(row.group) for row in queries]

    return {
        "method": "TF-IDF + multinomial logistic regression",
        "available": True,
        "training_items": len(training),
        "evaluation_items": len(queries),
        "vocabulary_size": len(vocabulary),
        "parameters": {
            "max_features": TFIDF_MAX_FEATURES,
            "epochs": _EPOCHS,
            "batch_size": _BATCH,
            "learning_rate": _LEARNING_RATE,
            "l2": _L2,
        },
        "metrics": {
            "macro_f1": macro_f1(gold, predicted).model_dump(),
            "accuracy": accuracy(gold, predicted).model_dump(),
            "coverage": coverage(predicted).model_dump(),
            "answered_accuracy": answered_accuracy(gold, predicted).model_dump(),
        },
    }


def _safety_baseline(items: Sequence[Complaint], keywords: Sequence[str]) -> dict[str, object]:
    pairs = [
        (keyword_safety(row.narrative, keywords) is not None, row.coded_safety) for row in items
    ]
    true_positive = sum(1 for guess, truth in pairs if guess and truth)
    positives = sum(1 for _, truth in pairs if truth)
    predicted_positive = sum(1 for guess, _ in pairs if guess)

    def share(successes: int, trials: int) -> dict[str, object]:
        low, high = wilson_interval(successes, trials)
        return Metric(
            value=(successes / trials) if trials else None,
            ci_low=low,
            ci_high=high,
        ).model_dump()

    return {
        "method": "committed safety keyword rule",
        "available": bool(items),
        "evaluation_items": len(items),
        "coded_safety_items": positives,
        "predicted_safety_items": predicted_positive,
        "metrics": {
            "recall": share(true_positive, positives),
            "precision": share(true_positive, predicted_positive),
        },
    }


def load_condition_keywords(path: Path = CONDITION_KEYWORDS_PATH) -> dict[str, tuple[str, ...]]:
    """Read ``[conditions]`` from the committed keyword TOML."""
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except FileNotFoundError:
        msg = f"condition keyword file not found: {path}"
        raise ValueError(msg) from None
    table = raw.get("conditions")
    if not isinstance(table, dict) or not table:
        msg = f"{path}: [conditions] must be a non-empty table"
        raise ValueError(msg)
    keywords: dict[str, tuple[str, ...]] = {}
    for kind, phrases in table.items():
        if not isinstance(phrases, list) or not all(isinstance(phrase, str) for phrase in phrases):
            msg = f"{path}: conditions.{kind} must be a list of strings"
            raise ValueError(msg)
        keywords[str(kind)] = tuple(phrases)
    return keywords


def _conditions_baseline(
    items: Sequence[Complaint],
    keywords: Mapping[str, Sequence[str]],
) -> dict[str, object]:
    from field_return_triage.pipeline.metrics import condition_kinds

    counts = dict.fromkeys(sorted(keywords), 0)
    any_hit = 0
    for row in items:
        found = condition_kinds(row.narrative, keywords)
        if found:
            any_hit += 1
        for kind in found:
            counts[kind] = counts.get(kind, 0) + 1
    low, high = wilson_interval(any_hit, len(items))
    return {
        "method": "committed condition keyword rule",
        "available": bool(items),
        "note": "coverage of the rule only; agreement with a model is not accuracy",
        "evaluation_items": len(items),
        "items_with_any_condition": any_hit,
        "any_condition_share": Metric(
            value=(any_hit / len(items)) if items else None,
            ci_low=low,
            ci_high=high,
        ).model_dump(),
        "per_kind": counts,
    }


def run_baselines(
    items: Sequence[Complaint],
    library: Sequence[Complaint],
    *,
    safety_keywords: Sequence[str],
    condition_keywords: Mapping[str, Sequence[str]],
) -> dict[str, object]:
    """Compute all three baselines; the result is JSON-ready."""
    return {
        "group": _group_baseline(items, library),
        "safety": _safety_baseline(items, safety_keywords),
        "conditions": _conditions_baseline(items, condition_keywords),
    }


def write_baselines(payload: Mapping[str, object], out_dir: Path) -> list[Path]:
    """Write one JSON file per baseline and return the paths, sorted by name."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in sorted(payload):
        path = out_dir / f"{name}.json"
        path.write_text(
            json.dumps(payload[name], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return written
