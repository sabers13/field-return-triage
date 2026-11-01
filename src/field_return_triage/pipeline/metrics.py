"""The deterministic metrics of ``PLAN.md`` section 6, each with its interval.

No metric is judged by a model: every score is a comparison with a committed label, a
fixed keyword rule, or a count. Confidence intervals are:

* a 2,000-resample bootstrap (seed ``20261031``) for means, macro-F1 and percentiles;
* a Wilson 95 % interval for a share of a fixed number of trials.

``Metric.value`` is ``None`` when the denominator is zero (for example precision when a
model flags nothing). That is a missing measurement, not a zero.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Final

import numpy as np
from pydantic import BaseModel, ConfigDict

from field_return_triage.contracts import UNCLEAR_GROUP, Complaint, Priority, TriageCard

__all__ = [
    "BOOTSTRAP_RESAMPLES",
    "SEED",
    "Metric",
    "accuracy",
    "answered_accuracy",
    "bootstrap_ci",
    "condition_agreement",
    "cost_metrics",
    "coverage",
    "latency_ms",
    "macro_f1",
    "quote_grounding",
    "routing",
    "safety_scores",
    "similar_precision",
    "wilson_interval",
]

#: PLAN.md section 6 fixes 2,000 bootstrap resamples and the project seed.
BOOTSTRAP_RESAMPLES: Final = 2_000
SEED: Final = 20261031
_Z95: Final = 1.959963984540054


class Metric(BaseModel):
    """A score and its 95 % interval. ``value`` is ``None`` when undefined."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None


def wilson_interval(successes: int, trials: int) -> tuple[float | None, float | None]:
    """The Wilson 95 % interval for ``successes / trials``, or ``(None, None)``."""
    if trials <= 0:
        return None, None
    if successes < 0 or successes > trials:
        msg = "successes must be between 0 and trials"
        raise ValueError(msg)
    proportion = successes / trials
    denominator = 1.0 + _Z95**2 / trials
    centre = (proportion + _Z95**2 / (2.0 * trials)) / denominator
    margin = (
        _Z95
        * math.sqrt(proportion * (1.0 - proportion) / trials + _Z95**2 / (4.0 * trials**2))
        / denominator
    )
    return max(0.0, centre - margin), min(1.0, centre + margin)


def _share_metric(successes: int, trials: int) -> Metric:
    if trials <= 0:
        return Metric()
    low, high = wilson_interval(successes, trials)
    return Metric(value=successes / trials, ci_low=low, ci_high=high)


def bootstrap_ci(
    values: Sequence[float],
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = SEED,
) -> tuple[float, float]:
    """The 2.5 / 97.5 percentile interval of the mean of ``values``."""
    if not values:
        msg = "bootstrap_ci needs at least one value"
        raise ValueError(msg)
    if resamples <= 0:
        msg = "resamples must be positive"
        raise ValueError(msg)
    array = np.asarray(values, dtype=np.float64)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(array), size=(resamples, len(array)))
    means = array[indices].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return float(low), float(high)


def _bootstrap_stat(
    values: Sequence[float],
    statistic: Callable[[np.ndarray], float],
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = SEED,
) -> tuple[float, float]:
    array = np.asarray(values, dtype=np.float64)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(array), size=(resamples, len(array)))
    sample = array[indices]
    scores = np.asarray([statistic(row) for row in sample], dtype=np.float64)
    low, high = np.percentile(scores, [2.5, 97.5])
    return float(low), float(high)


def _mean_metric(values: Sequence[float]) -> Metric:
    if not values:
        return Metric()
    low, high = bootstrap_ci(values)
    return Metric(value=float(np.mean(values)), ci_low=low, ci_high=high)


def _f1(gold: np.ndarray, predicted: np.ndarray, label: str) -> float:
    true_positive = int(np.sum((gold == label) & (predicted == label)))
    false_positive = int(np.sum((gold != label) & (predicted == label)))
    false_negative = int(np.sum((gold == label) & (predicted != label)))
    denominator = 2 * true_positive + false_positive + false_negative
    if denominator == 0:
        return 0.0
    return 2 * true_positive / denominator


def _macro_f1(gold: np.ndarray, predicted: np.ndarray, labels: Sequence[str]) -> float:
    scores = [
        _f1(gold, predicted, label)
        for label in labels
        if bool(np.any(gold == label)) or bool(np.any(predicted == label))
    ]
    return float(np.mean(scores)) if scores else 0.0


def macro_f1(gold: Sequence[str], predicted: Sequence[str]) -> Metric:
    """Macro-F1 over the true groups, with a bootstrap 95 % interval.

    A predicted ``unclear`` never matches a group, so it counts as wrong, as PLAN.md
    section 6 requires. The true labels are fixed before resampling, so a class that a
    bootstrap sample happens to miss still contributes to the macro average.
    """
    if len(gold) != len(predicted):
        msg = "gold and predicted must have the same length"
        raise ValueError(msg)
    if not gold:
        return Metric()
    labels = sorted(set(gold))
    gold_array = np.asarray(gold)
    predicted_array = np.asarray(predicted)
    value = _macro_f1(gold_array, predicted_array, labels)

    rng = np.random.default_rng(SEED)
    indices = rng.integers(0, len(gold), size=(BOOTSTRAP_RESAMPLES, len(gold)))
    scores = np.asarray(
        [_macro_f1(gold_array[row], predicted_array[row], labels) for row in indices],
        dtype=np.float64,
    )
    low, high = np.percentile(scores, [2.5, 97.5])
    return Metric(value=value, ci_low=float(low), ci_high=float(high))


def accuracy(gold: Sequence[str], predicted: Sequence[str]) -> Metric:
    """Share of exact label matches, with a Wilson interval."""
    if len(gold) != len(predicted):
        msg = "gold and predicted must have the same length"
        raise ValueError(msg)
    hits = sum(1 for truth, guess in zip(gold, predicted, strict=True) if truth == guess)
    return _share_metric(hits, len(gold))


def coverage(predicted: Sequence[str]) -> Metric:
    """Share of answers that are not ``unclear``."""
    answered = sum(1 for label in predicted if label != UNCLEAR_GROUP)
    return _share_metric(answered, len(predicted))


def answered_accuracy(gold: Sequence[str], predicted: Sequence[str]) -> Metric:
    """Accuracy over the items the model did not answer ``unclear``."""
    if len(gold) != len(predicted):
        msg = "gold and predicted must have the same length"
        raise ValueError(msg)
    pairs = [
        (truth, guess)
        for truth, guess in zip(gold, predicted, strict=True)
        if guess != UNCLEAR_GROUP
    ]
    hits = sum(1 for truth, guess in pairs if truth == guess)
    return _share_metric(hits, len(pairs))


def _safety_metric(pairs: Sequence[tuple[bool, bool]]) -> tuple[Metric, Metric]:
    """Recall and precision for ``(predicted, gold)`` pairs."""
    true_positive = sum(1 for guess, truth in pairs if guess and truth)
    positives = sum(1 for _, truth in pairs if truth)
    predicted_positive = sum(1 for guess, _ in pairs if guess)
    return _share_metric(true_positive, positives), _share_metric(true_positive, predicted_positive)


def safety_scores(
    cards: Sequence[TriageCard],
    items: Sequence[Complaint] | None = None,
) -> dict[str, Metric]:
    """Final and model-only safety recall/precision against the coded fields.

    ``final`` is the hard-rule decision (model flag OR keyword rule OR the coded
    crash/fire/injury fields), i.e. the priority-1 routing. ``model`` is the model's own
    flag alone. ``items`` may supply the coded labels by complaint id; a card's own
    embedded complaint is used when it does not.
    """
    coded: dict[str, bool] = {}
    if items is not None:
        for item in items:
            identifier = getattr(item, "id", None)
            flag = getattr(item, "coded_safety", None)
            if isinstance(identifier, str) and isinstance(flag, bool):
                coded[identifier] = flag

    final_pairs: list[tuple[bool, bool]] = []
    model_pairs: list[tuple[bool, bool]] = []
    for card in cards:
        truth = coded.get(card.complaint.id, card.complaint.coded_safety)
        final_pairs.append((card.priority is Priority.SAFETY, truth))
        model_pairs.append((card.extraction.safety_relevant, truth))

    final_recall, final_precision = _safety_metric(final_pairs)
    model_recall, model_precision = _safety_metric(model_pairs)
    return {
        "final_recall": final_recall,
        "final_precision": final_precision,
        "model_recall": model_recall,
        "model_precision": model_precision,
    }


def quote_grounding(cards: Sequence[TriageCard]) -> Metric:
    """Share of extracted clues whose quote passed the verbatim check."""
    checked = sum(card.quote_check.checked for card in cards)
    passed = sum(card.quote_check.passed for card in cards)
    return _share_metric(passed, checked)


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    words = phrase.split()
    return re.compile(r"\s+".join(re.escape(word) for word in words), re.IGNORECASE)


def condition_kinds(text: str, keywords: Mapping[str, Sequence[str]]) -> set[str]:
    """The condition kinds the fixed keyword rule finds in ``text``."""
    found: set[str] = set()
    for kind, phrases in keywords.items():
        if any(_phrase_pattern(phrase).search(text) for phrase in phrases if phrase.strip()):
            found.add(kind)
    return found


def _kept_condition_kinds(card: TriageCard) -> set[str]:
    dropped = {
        (row.kind, row.quote) for row in card.quote_check.dropped if row.field == "conditions"
    }
    return {
        clue.kind for clue in card.extraction.conditions if (clue.kind, clue.quote) not in dropped
    }


def condition_agreement(
    cards: Sequence[TriageCard],
    keywords: Mapping[str, Sequence[str]],
) -> Metric:
    """Agreement between extracted condition kinds and the fixed keyword rule.

    For every condition kind named by either side, agreement is the share of cards on
    which both sides agree (present or absent). The score is the macro average over
    those kinds. This is agreement, not accuracy: there is no ground truth for a
    condition, and the file that stores it says so.
    """
    if not cards:
        return Metric()
    pairs = [
        (_kept_condition_kinds(card), condition_kinds(card.complaint.narrative, keywords))
        for card in cards
    ]
    kinds = sorted({kind for extracted, rule in pairs for kind in extracted | rule})
    if not kinds:
        return Metric()

    def macro(rows: np.ndarray) -> float:
        scores = []
        for kind in kinds:
            matches = sum(
                1
                for position in rows
                if (kind in pairs[int(position)][0]) == (kind in pairs[int(position)][1])
            )
            scores.append(matches / len(rows))
        return float(np.mean(scores))

    values = np.arange(len(pairs))
    if len(pairs) == 1:
        return Metric(value=macro(values), ci_low=None, ci_high=None)
    low, high = _bootstrap_stat(values.astype(np.float64).tolist(), macro)
    return Metric(value=macro(values), ci_low=low, ci_high=high)


def routing(cards: Sequence[TriageCard]) -> dict[str, Metric]:
    """The share of cards at priority 1 and the share sent to human reading."""
    safety = sum(1 for card in cards if card.priority is Priority.SAFETY)
    review = sum(1 for card in cards if card.needs_human_review)
    return {
        "priority_1_share": _share_metric(safety, len(cards)),
        "needs_human_share": _share_metric(review, len(cards)),
    }


def similar_precision(cards: Sequence[TriageCard], *, k: int = 5) -> Metric:
    """Precision@k from the neighbours already on each card (PLAN.md section 6)."""
    hits = 0
    total = 0
    for card in cards:
        neighbours = card.neighbours[:k]
        total += len(neighbours)
        hits += sum(
            1
            for neighbour in neighbours
            if neighbour.group == (card.complaint.group or UNCLEAR_GROUP)
        )
    return _share_metric(hits, total)


def _percentile(values: Sequence[float], quantile: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=np.float64), quantile))


def latency_ms(durations: Sequence[float]) -> dict[str, Metric]:
    """p50 and p95 of the measured call durations, each with a bootstrap interval."""
    if not durations:
        return {"p50": Metric(), "p95": Metric()}

    def make(quantile: float) -> Metric:
        value = _percentile(durations, quantile)
        if len(durations) == 1:
            return Metric(value=value)
        low, high = _bootstrap_stat(
            durations,
            lambda row: _percentile(row.tolist(), quantile),
        )
        return Metric(value=value, ci_low=low, ci_high=high)

    return {"p50": make(50.0), "p95": make(95.0)}


def cost_metrics(costs: Sequence[float]) -> dict[str, Metric]:
    """Total cost and cost per 1,000 items, from per-call USD costs."""
    total = float(sum(costs))
    if not costs:
        return {"total_usd": Metric(), "per_1000_usd": Metric()}
    per_item = np.asarray(costs, dtype=np.float64) * 1000.0
    low, high = bootstrap_ci(per_item.tolist())
    return {
        "total_usd": Metric(value=total, ci_low=total, ci_high=total),
        "per_1000_usd": Metric(
            value=float(per_item.mean()),
            ci_low=low,
            ci_high=high,
        ),
    }
