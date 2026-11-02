"""Build ``results/page/page-data.json`` from the committed results (PLAN.md §6).

The page is a pure view of ``results/``. This module reads one replay run (cards,
metrics and manifest), the three baseline files and the trend files, and shapes them
for the template. It never recomputes a score: every number is copied, rounded to the
precision the page shows, or formatted from a copied value.

The queue rule is fixed by the brief: the primary model's replay cards, four at
priority 1, four at priority 2 and four at priority 3, lowest complaint id first inside
each priority. There is no sampling and no hand-picking, so a rerun of the same results
produces the same twelve cards. Dependencies: the standard library only.
"""

from __future__ import annotations

import json
import tomllib
from collections import defaultdict
from pathlib import Path
from typing import Any, Final

__all__ = [
    "MODELS_LOCK",
    "PAGE_DATA",
    "QUEUE_PER_PRIORITY",
    "QUEUE_PRIORITIES",
    "QUEUE_RULE",
    "RESULTS",
    "build_page_data",
    "write_page_data",
]

RESULTS: Final[Path] = Path("results")
PAGE_DATA: Final[Path] = RESULTS / "page" / "page-data.json"
MODELS_LOCK: Final[Path] = Path("config/models.lock.toml")

#: Four cards per priority, in this order, from the primary model's replay cards.
QUEUE_PRIORITIES: Final = (1, 2, 3)
QUEUE_PER_PRIORITY: Final = 4

QUEUE_RULE: Final = (
    "The primary model's replay cards: four at priority 1, four at priority 2 and four "
    "at priority 3. Inside each priority the lowest complaint id comes first. The queue "
    "is fixed by that rule; it is not a live feed and nothing in it was hand-picked."
)

_RUN_PREFERENCE: Final = ("live", "fixture")
_NEIGHBOURS_SHOWN: Final = 3
_PICK_BY_ROLE: Final[dict[str, str]] = {
    "primary": "cheapest",
    "comparison": "most_accurate",
}


def _mapping(value: Any) -> dict[str, Any]:
    """A JSON object as a string-keyed dict, or an empty dict for anything else."""
    if not isinstance(value, dict):
        return {}
    return {key: item for key, item in value.items() if isinstance(key, str)}


def _sequence(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _number(value: Any, digits: int = 4) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value), digits)


def _metric(raw: Any, key: str, *, digits: int = 4) -> dict[str, float | None] | None:
    """One ``{value, ci_low, ci_high}`` block, rounded, or ``None`` when absent."""
    block = _mapping(_mapping(raw).get(key))
    value = _number(block.get("value"), digits)
    if value is None:
        return None
    return {
        "value": value,
        "ci_low": _number(block.get("ci_low"), digits),
        "ci_high": _number(block.get("ci_high"), digits),
    }


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"page: missing results file {path}; run `make results` first"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"page: {path} is not valid JSON: {exc}") from exc


def _find_run(runs_dir: Path) -> Path:
    """The run the summary uses: ``live`` first, then ``fixture``, then the last one."""
    candidates = sorted(path for path in runs_dir.glob("*") if (path / "metrics.json").is_file())
    by_name = {path.name: path for path in candidates}
    for name in _RUN_PREFERENCE:
        if name in by_name:
            return by_name[name]
    if candidates:
        return candidates[-1]
    raise FileNotFoundError(f"page: no run with metrics.json under {runs_dir}")


def _load_cards(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"page: missing {path}; run `make results` first") from exc
    cards: list[dict[str, Any]] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"page: {path}:{number} is not valid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"page: {path}:{number} is not a JSON object")
        cards.append(row)
    return cards


def _load_lock(path: Path) -> dict[str, Any]:
    """The model lock as a plain dict; an absent file means no provenance to quote."""
    try:
        with path.open("rb") as handle:
            return _mapping(tomllib.load(handle))
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"page: cannot read {path}: {exc.__class__.__name__}") from exc


def _id_key(card: dict[str, Any]) -> tuple[int, int, str]:
    """Sort by numeric complaint id, with any non-numeric id last and by text."""
    raw = _text(_mapping(card.get("complaint")).get("id"))
    if raw.isdigit():
        return (0, int(raw), raw)
    return (1, 0, raw)


def _select_queue(cards: list[dict[str, Any]], model_id: str) -> list[dict[str, Any]]:
    """Apply the fixed queue rule and refuse to ship a partial queue."""
    by_priority: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for card in cards:
        if card.get("model_id") != model_id:
            continue
        priority = _integer(card.get("priority"))
        if priority in QUEUE_PRIORITIES:
            by_priority[priority].append(card)

    selected: list[dict[str, Any]] = []
    for priority in QUEUE_PRIORITIES:
        picks = sorted(by_priority[priority], key=_id_key)[:QUEUE_PER_PRIORITY]
        if len(picks) < QUEUE_PER_PRIORITY:
            raise ValueError(
                f"page: priority {priority} has only {len(picks)} cards for {model_id}; "
                f"the queue needs {QUEUE_PER_PRIORITY}"
            )
        selected.extend(picks)
    return selected


def _clues(card: dict[str, Any]) -> list[dict[str, str]]:
    """Every clue that passed the quote check, in extraction order, with its field."""
    extraction = _mapping(card.get("extraction"))
    check = _mapping(card.get("quote_check"))
    dropped = {
        (_text(row.get("field")), _text(row.get("kind")), _text(row.get("quote")))
        for row in _sequence(check.get("dropped"))
        if isinstance(row, dict)
    }

    clues: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(field: str, kind: str, quote: Any) -> None:
        if not isinstance(quote, str) or not quote:
            return
        key = (field, kind, quote)
        if key in dropped or key in seen:
            return
        seen.add(key)
        clues.append({"field": field, "kind": kind, "text": quote})

    if extraction.get("safety_relevant"):
        add("safety", "safety", extraction.get("safety_quote"))
    for field in ("symptoms", "conditions"):
        for item in _sequence(extraction.get(field)):
            clue = _mapping(item)
            add(field, _text(clue.get("kind")), clue.get("quote"))
    for item in _sequence(extraction.get("fault_codes")):
        add("fault_codes", "fault_code", _mapping(item).get("quote"))
    mileage = _mapping(extraction.get("mileage"))
    if mileage:
        add("mileage", "mileage", mileage.get("quote"))
    return clues


def _reasons(value: Any) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    for item in _sequence(value):
        reason = _mapping(item)
        text = _text(reason.get("text"))
        if not text:
            continue
        quotes = [
            quote for quote in _sequence(reason.get("quotes")) if isinstance(quote, str) and quote
        ]
        reasons.append({"text": text, "quotes": quotes})
    return reasons


def _queue_card(card: dict[str, Any]) -> dict[str, Any]:
    complaint = _mapping(card.get("complaint"))
    suggestion = _mapping(card.get("suggestion"))
    check = _mapping(card.get("quote_check"))
    extraction = _mapping(card.get("extraction"))
    neighbours: list[dict[str, Any]] = []
    for rank, item in enumerate(_sequence(card.get("neighbours"))[:_NEIGHBOURS_SHOWN], start=1):
        neighbour = _mapping(item)
        if not _text(neighbour.get("complaint_id")):
            continue
        neighbours.append(
            {
                "rank": rank,
                "complaint_id": _text(neighbour.get("complaint_id")),
                "group": _text(neighbour.get("group")),
                "received": _text(neighbour.get("received")),
                "safety_relevant": bool(neighbour.get("safety_relevant")),
                "excerpt": _text(neighbour.get("excerpt")),
                "score": _number(neighbour.get("score"), 4),
            }
        )

    return {
        "card_id": _text(card.get("card_id")),
        "complaint_id": _text(complaint.get("id")),
        "priority": _integer(card.get("priority")),
        "needs_human_review": bool(card.get("needs_human_review")),
        "group": _text(extraction.get("component_group"), "unclear"),
        "coded_safety": bool(
            complaint.get("crash") or complaint.get("fire") or complaint.get("injury")
        ),
        "coded_flags": [
            name
            for name, key in (("crash", "crash"), ("fire", "fire"), ("injury", "injury"))
            if bool(complaint.get(key))
        ],
        "vehicle": {
            "make": _text(complaint.get("make")) or None,
            "model": _text(complaint.get("model")) or None,
            "model_year": _integer(complaint.get("model_year")),
        },
        "received": _text(complaint.get("received")),
        "narrative": _text(complaint.get("narrative")),
        "clues": _clues(card),
        "reasons": _reasons(card.get("reasons")),
        "suggestion": {
            "tests": [item for item in _sequence(suggestion.get("tests")) if isinstance(item, str)],
            "inspect": [
                item for item in _sequence(suggestion.get("inspect")) if isinstance(item, str)
            ],
            "request": [
                item for item in _sequence(suggestion.get("request")) if isinstance(item, str)
            ],
            "reasons": _reasons(suggestion.get("reasons")),
        },
        "neighbours": neighbours,
        "quote_check": {
            "checked": _integer(check.get("checked")) or 0,
            "passed": _integer(check.get("passed")) or 0,
            "dropped": len(_sequence(check.get("dropped"))),
        },
        "versions": {
            "model": _text(card.get("model_id")),
            "prompt": _text(card.get("prompt_version")),
            "rulebook": _text(card.get("rulebook_version")),
            "hard_rules": _text(card.get("hard_rule_version")),
            "schema": _text(card.get("schema_version")),
        },
    }


def _model_metrics(entry: dict[str, Any]) -> dict[str, Any]:
    safety = _mapping(entry.get("safety"))
    routing = _mapping(entry.get("routing"))
    group = _mapping(entry.get("group"))
    cost = _mapping(entry.get("cost"))
    latency = _mapping(entry.get("latency_ms"))
    return {
        "group": {
            "macro_f1": _metric(group, "macro_f1"),
            "accuracy": _metric(group, "accuracy"),
            "coverage": _metric(group, "coverage"),
            "answered_accuracy": _metric(group, "answered_accuracy"),
        },
        "safety": {
            "final_recall": _metric(safety, "final_recall"),
            "final_precision": _metric(safety, "final_precision"),
            "model_recall": _metric(safety, "model_recall"),
            "model_precision": _metric(safety, "model_precision"),
        },
        "quote_grounding": _metric(entry, "quote_grounding"),
        "condition_agreement": _metric(entry, "condition_agreement"),
        "similar_precision_at_5": _metric(entry, "similar_precision_at_5"),
        "routing": {
            "needs_human_share": _metric(routing, "needs_human_share"),
            "priority_1_share": _metric(routing, "priority_1_share"),
        },
        "cost": {
            "per_1000_usd": _metric(cost, "per_1000_usd"),
            "total_usd": _metric(cost, "total_usd"),
        },
        "latency_ms": {
            "p50": _metric(latency, "p50", digits=1),
            "p95": _metric(latency, "p95", digits=1),
        },
        "invalid_answers": _integer(entry.get("invalid_answers")),
    }


def _model_rows(
    metrics: dict[str, Any], lock: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """One row per locked model, plus the shared card-provenance block."""
    metrics_models = _mapping(metrics.get("models"))
    budget_rows = _mapping(metrics.get("budget"))
    budget_by_model = {
        _text(row.get("model_id")): row
        for row in _sequence(budget_rows.get("models"))
        if isinstance(row, dict)
    }

    settings: list[dict[str, Any]] = []
    for entry in _sequence(lock.get("models")):
        setting = _mapping(entry)
        model_id = _text(setting.get("model_id"))
        role = _text(setting.get("role"))
        if model_id and role in _PICK_BY_ROLE:
            settings.append({"model_id": model_id, "role": role})
    if not settings:
        for model_id, entry in sorted(metrics_models.items()):
            role = _text(_mapping(entry).get("role"))
            if role in _PICK_BY_ROLE:
                settings.append({"model_id": model_id, "role": role})

    models: list[dict[str, Any]] = []
    for setting in settings:
        model_id = setting["model_id"]
        role = setting["role"]
        entry = _mapping(metrics_models.get(model_id))
        budget = _mapping(budget_by_model.get(model_id))
        pick = _PICK_BY_ROLE[role]
        picked_model = _text(lock.get(f"card_{pick}"))
        models.append(
            {
                "model_id": model_id,
                "role": role,
                "pick": pick,
                "picked_on_the_card": picked_model or None,
                "items_evaluated": _integer(entry.get("items_evaluated")),
                "items_available": _integer(budget.get("items_available")),
                "reduced": bool(budget.get("reduced")),
                "invalid_answers": _integer(entry.get("invalid_answers")),
                "metrics": _model_metrics(entry),
            }
        )

    source = {
        "repo": _text(lock.get("source_repo")) or None,
        "card": _text(lock.get("source_card")) or None,
        "commit": _text(lock.get("source_commit")) or None,
        "rule": _text(lock.get("rule")) or None,
        "picker_rule": _text(lock.get("card_picker_rule")) or None,
        "cheapest": _text(lock.get("card_cheapest")) or None,
        "most_accurate": _text(lock.get("card_most_accurate")) or None,
        "no_model_meets_floor": lock.get("card_no_model_meets_floor"),
    }
    return models, source


def _baselines(results_dir: Path) -> dict[str, Any]:
    group = _mapping(_read_json(results_dir / "baseline" / "group.json"))
    safety = _mapping(_read_json(results_dir / "baseline" / "safety.json"))
    conditions = _mapping(_read_json(results_dir / "baseline" / "conditions.json"))
    group_metrics = _mapping(group.get("metrics"))
    safety_metrics = _mapping(safety.get("metrics"))
    return {
        "group": {
            "available": bool(group.get("available")),
            "method": _text(group.get("method")),
            "evaluation_items": _integer(group.get("evaluation_items")),
            "training_items": _integer(group.get("training_items")),
            "vocabulary_size": _integer(group.get("vocabulary_size")),
            "macro_f1": _metric(group_metrics, "macro_f1"),
            "accuracy": _metric(group_metrics, "accuracy"),
            "coverage": _metric(group_metrics, "coverage"),
        },
        "safety": {
            "available": bool(safety.get("available")),
            "method": _text(safety.get("method")),
            "evaluation_items": _integer(safety.get("evaluation_items")),
            "coded_safety_items": _integer(safety.get("coded_safety_items")),
            "predicted_safety_items": _integer(safety.get("predicted_safety_items")),
            "recall": _metric(safety_metrics, "recall"),
            "precision": _metric(safety_metrics, "precision"),
        },
        "conditions": {
            "available": bool(conditions.get("available")),
            "method": _text(conditions.get("method")),
            "note": _text(conditions.get("note")),
            "evaluation_items": _integer(conditions.get("evaluation_items")),
            "items_with_any_condition": _integer(conditions.get("items_with_any_condition")),
            "any_condition_share": _metric(conditions, "any_condition_share"),
            "per_kind": {
                key: value
                for key, value in _mapping(conditions.get("per_kind")).items()
                if isinstance(value, int) and not isinstance(value, bool)
            },
        },
    }


def _trend(results_dir: Path) -> dict[str, Any]:
    example = _mapping(_read_json(results_dir / "trend" / "example_series.json"))
    backtest = _mapping(_read_json(results_dir / "trend" / "backtest.json"))
    alerts = _mapping(backtest.get("alerts"))
    base = _mapping(backtest.get("base_rate"))
    method = _mapping(backtest.get("method"))
    ci = _mapping(base.get("ci95"))

    share = _number(alerts.get("share"), 4)
    base_share = _number(base.get("share"), 4)
    low = _number(ci.get("low"), 4)
    high = _number(ci.get("high"), 4)
    total = _integer(alerts.get("total"))
    preceding = _integer(alerts.get("preceding_recall"))
    window = _integer(method.get("recall_window_days"))

    if share is None or base_share is None or low is None or high is None:
        verdict = "unknown"
        reading = "The backtest file does not carry the shares this reading needs."
    elif low <= share <= high:
        verdict = "overlaps"
        reading = (
            f"{_pct(share)} of {total} alerts preceded a recall within {window} days, "
            f"against a {_pct(base_share)} base rate for random same-series weeks. The "
            f"base-rate interval ({_pct(low)} to {_pct(high)}) overlaps it, so this backtest "
            "does not show the spike rule beating chance."
        )
    elif share > high:
        verdict = "above"
        reading = (
            f"{_pct(share)} of alerts preceded a recall within {window} days, above the "
            f"{_pct(low)} to {_pct(high)} base-rate interval ({_pct(base_share)}). That is a "
            "signal worth testing on more data, not a result yet."
        )
    else:
        verdict = "below"
        reading = (
            f"{_pct(share)} of alerts preceded a recall within {window} days, below the "
            f"{_pct(low)} to {_pct(high)} base-rate interval ({_pct(base_share)}), so the rule "
            "did not beat chance in this backtest."
        )

    weeks = [
        {"week": _text(_mapping(row).get("week")), "count": _integer(_mapping(row).get("count"))}
        for row in _sequence(example.get("weeks"))
        if _text(_mapping(row).get("week"))
    ]
    example_alert = _mapping(example.get("alert"))
    example_recall = _mapping(example.get("recall"))
    series = _mapping(example.get("series"))
    series_label = " ".join(
        part
        for part in (
            _text(series.get("make")),
            _text(series.get("model")),
            str(_integer(series.get("model_year")) or ""),
        )
        if part
    )
    group_label = _text(series.get("group")).replace("_", " ")
    threshold = _number(example_alert.get("threshold"), 1)
    example_reading = (
        f"Example series: {series_label}, {group_label}. "
        f"{_integer(example.get('total_complaints')) or 0} complaints across "
        f"{len(weeks)} weeks; the week of {_text(example_alert.get('week'))} counted "
        f"{_integer(example_alert.get('count')) or 0} against a threshold of "
        f"{threshold if threshold is not None else 'n/a'}, and a recall for the same make, "
        f"model, year and group followed "
        f"{_integer(example_recall.get('lead_days')) or 0} days later."
    )

    return {
        "example": {
            "series": {
                "make": _text(series.get("make")),
                "model": _text(series.get("model")),
                "model_year": _integer(series.get("model_year")),
                "group": _text(series.get("group")),
            },
            "series_label": series_label,
            "group_label": group_label,
            "total_complaints": _integer(example.get("total_complaints")),
            "weeks": weeks,
            "alert": {
                "week": _text(example_alert.get("week")),
                "count": _integer(example_alert.get("count")),
                "trailing_mean": _number(example_alert.get("trailing_mean"), 3),
                "threshold": threshold,
            },
            "recall": {
                "recall_id": _text(example_recall.get("recall_id")),
                "report_date": _text(example_recall.get("report_date")),
                "lead_days": _integer(example_recall.get("lead_days")),
            },
            "reading": example_reading,
        },
        "backtest": {
            "alerts": {
                "total": total,
                "preceding_recall": preceding,
                "share": share,
                "median_lead_days": _number(alerts.get("median_lead_days"), 1),
            },
            "base_rate": {
                "share": base_share,
                "ci_low": low,
                "ci_high": high,
                "draws": _integer(base.get("draws")),
                "preceding_recall": _integer(base.get("preceding_recall")),
            },
            "method": {
                "rule": _text(method.get("rule")),
                "base_rate": _text(method.get("base_rate")),
                "recall_window_days": window,
            },
            "verdict": verdict,
            "reading": reading,
        },
    }


def build_page_data(
    results_dir: Path = RESULTS,
    *,
    models_path: Path = MODELS_LOCK,
) -> dict[str, Any]:
    """Shape the committed results into the page's JSON payload."""
    run_dir = _find_run(results_dir / "runs")
    metrics = _mapping(_read_json(run_dir / "metrics.json"))
    manifest = _mapping(_read_json(run_dir / "manifest.json"))
    cards = _load_cards(run_dir / "cards.jsonl")
    lock = _load_lock(models_path)

    models, source = _model_rows(metrics, lock)
    primary = next((model for model in models if model["role"] == "primary"), None)
    if primary is None:
        raise ValueError("page: metrics.json has no primary model; run `make results` first")

    selected = _select_queue(cards, primary["model_id"])
    queue_cards = [_queue_card(card) for card in selected]
    counts = {
        str(priority): sum(1 for card in queue_cards if card["priority"] == priority)
        for priority in QUEUE_PRIORITIES
    }

    return {
        "run": {
            "id": _text(manifest.get("run_id")) or run_dir.name,
            "mode": _text(manifest.get("mode")),
            "item_count": _integer(manifest.get("item_count")),
            "cost_usd": _number(manifest.get("cost_usd"), 6),
            "sample_hash": _text(manifest.get("sample_hash")),
            "started_at": _text(manifest.get("started_at")),
            "finished_at": _text(manifest.get("finished_at")),
            "prompt_version": _text(manifest.get("prompt_version")),
            "rulebook_version": _text(manifest.get("rulebook_version")),
            "hard_rule_version": _text(manifest.get("hard_rule_version")),
            "schema_version": _text(manifest.get("schema_version")),
        },
        "queue": {
            "rule": QUEUE_RULE,
            "model_id": primary["model_id"],
            "per_priority": QUEUE_PER_PRIORITY,
            "counts": counts,
            "cards": queue_cards,
        },
        "results": {
            "models": models,
            "baselines": _baselines(results_dir),
            "source": source,
        },
        "trend": _trend(results_dir),
    }


def write_page_data(
    path: Path = PAGE_DATA,
    *,
    results_dir: Path = RESULTS,
    models_path: Path = MODELS_LOCK,
) -> Path:
    """Write ``page-data.json`` deterministically and return the path."""
    payload = build_page_data(results_dir, models_path=models_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path
