"""``results/SUMMARY.md`` and ``results/MANIFEST.sha256`` (``PLAN.md`` section 11).

The summary states every headline number together with the committed file it came from.
It is generated from the run, baseline and trend files, never from memory, and it says
plainly when a run used the fake fixture models.

The manifest hashes every committed results file except itself, sorted by relative path,
so a rerun that changes one byte changes one line.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

__all__ = ["MANIFEST_NAME", "build_summary", "write_manifest", "write_summary"]

MANIFEST_NAME: Final = "MANIFEST.sha256"
_PREFERRED_RUNS: Final = ("live", "fixture")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def _pick_run(runs_dir: Path) -> Path | None:
    candidates = sorted(path for path in runs_dir.glob("*") if (path / "metrics.json").is_file())
    if not candidates:
        return None
    by_name = {path.name: path for path in candidates}
    for name in _PREFERRED_RUNS:
        if name in by_name:
            return by_name[name]
    return candidates[-1]


def _score(value: Any) -> str:
    if not isinstance(value, Mapping):
        return "n/a"
    number = value.get("value")
    if not isinstance(number, (int, float)):
        return "n/a"
    low, high = value.get("ci_low"), value.get("ci_high")
    if isinstance(low, (int, float)) and isinstance(high, (int, float)):
        return f"{number:.3f} ({low:.3f}-{high:.3f})"
    return f"{number:.3f}"


def _cost(value: Any) -> str:
    if not isinstance(value, Mapping):
        return "n/a"
    number = value.get("value")
    if not isinstance(number, (int, float)):
        return "n/a"
    low, high = value.get("ci_low"), value.get("ci_high")
    if isinstance(low, (int, float)) and isinstance(high, (int, float)):
        return f"${number:.4f} (${low:.4f}-${high:.4f})"
    return f"${number:.4f}"


def _latency(value: Any) -> str:
    if not isinstance(value, Mapping):
        return "n/a"
    number = value.get("value")
    if not isinstance(number, (int, float)):
        return "n/a"
    low, high = value.get("ci_low"), value.get("ci_high")
    if isinstance(low, (int, float)) and isinstance(high, (int, float)):
        return f"{number:.1f} ms ({low:.1f}-{high:.1f})"
    return f"{number:.1f} ms"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _model_rows(metrics: Mapping[str, Any]) -> list[str]:
    models = _mapping(metrics.get("models"))
    lines = [
        "| Model | Role | Items | Macro-F1 (95% CI) | Accuracy | Coverage | Answered accuracy |",
        "| --- | --- | ---: | --- | --- | --- | --- |",
    ]
    for model_id in sorted(models):
        entry = _mapping(models.get(model_id))
        group = _mapping(entry.get("group"))
        lines.append(
            "| `{model}` | {role} | {items} | {f1} | {acc} | {cov} | {ans} |".format(
                model=model_id,
                role=entry.get("role", ""),
                items=entry.get("items_evaluated", 0),
                f1=_score(group.get("macro_f1")),
                acc=_score(group.get("accuracy")),
                cov=_score(group.get("coverage")),
                ans=_score(group.get("answered_accuracy")),
            )
        )
    return lines


def _safety_rows(metrics: Mapping[str, Any]) -> list[str]:
    models = _mapping(metrics.get("models"))
    lines = [
        "| Model | Final recall | Final precision | Model-only recall | Model-only precision |",
        "| --- | --- | --- | --- | --- |",
    ]
    for model_id in sorted(models):
        entry = _mapping(models.get(model_id))
        safety = _mapping(entry.get("safety"))
        lines.append(
            "| `{model}` | {fr} | {fp} | {mr} | {mp} |".format(
                model=model_id,
                fr=_score(safety.get("final_recall")),
                fp=_score(safety.get("final_precision")),
                mr=_score(safety.get("model_recall")),
                mp=_score(safety.get("model_precision")),
            )
        )
    return lines


def _quality_rows(metrics: Mapping[str, Any]) -> list[str]:
    models = _mapping(metrics.get("models"))
    lines = [
        "| Model | Quote grounding | Condition agreement | Precision@5 | "
        "Priority 1 share | Needs human share | Invalid answers |",
        "| --- | --- | --- | --- | --- | --- | ---: |",
    ]
    for model_id in sorted(models):
        entry = _mapping(models.get(model_id))
        routing = _mapping(entry.get("routing"))
        lines.append(
            "| `{model}` | {quote} | {condition} | {similar} | {p1} | {human} | {bad} |".format(
                model=model_id,
                quote=_score(entry.get("quote_grounding")),
                condition=_score(entry.get("condition_agreement")),
                similar=_score(entry.get("similar_precision_at_5")),
                p1=_score(routing.get("priority_1_share")),
                human=_score(routing.get("needs_human_share")),
                bad=entry.get("invalid_answers", 0),
            )
        )
    return lines


def _cost_rows(metrics: Mapping[str, Any]) -> list[str]:
    models = _mapping(metrics.get("models"))
    lines = [
        "| Model | Cost per 1,000 (95% CI) | Total cost | Latency p50 | Latency p95 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for model_id in sorted(models):
        entry = _mapping(models.get(model_id))
        cost = _mapping(entry.get("cost"))
        latency = _mapping(entry.get("latency_ms"))
        total = _mapping(cost.get("total_usd"))
        total_number = total.get("value")
        lines.append(
            "| `{model}` | {per} | {total} | {p50} | {p95} |".format(
                model=model_id,
                per=_cost(cost.get("per_1000_usd")),
                total=f"${total_number:.4f}" if isinstance(total_number, (int, float)) else "n/a",
                p50=_latency(latency.get("p50")),
                p95=_latency(latency.get("p95")),
            )
        )
    return lines


def _baseline_rows(baseline_dir: Path) -> list[str]:
    group = _read_json(baseline_dir / "group.json")
    safety = _read_json(baseline_dir / "safety.json")
    lines: list[str] = []
    if group is not None:
        metrics = _mapping(group.get("metrics"))
        lines.append(
            "- Component group ({method}): macro-F1 {f1}, accuracy {acc}, coverage "
            "{cov}, answered accuracy {ans} - `results/baseline/group.json`".format(
                method=group.get("method", "baseline"),
                f1=_score(metrics.get("macro_f1")),
                acc=_score(metrics.get("accuracy")),
                cov=_score(metrics.get("coverage")),
                ans=_score(metrics.get("answered_accuracy")),
            )
        )
    if safety is not None:
        metrics = _mapping(safety.get("metrics"))
        lines.append(
            "- Safety ({method}): recall {recall}, precision {precision} - "
            "`results/baseline/safety.json`".format(
                method=safety.get("method", "baseline"),
                recall=_score(metrics.get("recall")),
                precision=_score(metrics.get("precision")),
            )
        )
    conditions = _read_json(baseline_dir / "conditions.json")
    if conditions is not None:
        lines.append(
            "- Conditions ({method}): {items} items, {hit} with any condition "
            "(share {share}); agreement only, never accuracy - "
            "`results/baseline/conditions.json`".format(
                method=conditions.get("method", "baseline"),
                items=conditions.get("evaluation_items", 0),
                hit=conditions.get("items_with_any_condition", 0),
                share=_score(conditions.get("any_condition_share")),
            )
        )
    return lines


def _trend_lines(trend_dir: Path) -> list[str]:
    backtest = _read_json(trend_dir / "backtest.json")
    if backtest is None:
        return ["No trend files committed yet - run `make trend`."]
    alerts = _mapping(backtest.get("alerts"))
    base = _mapping(backtest.get("base_rate"))
    share = alerts.get("share")
    base_share = base.get("share")
    interval: Any = base.get("ci95")
    interval_low = (
        f"{interval[0]:.1%}" if isinstance(interval, list) and len(interval) > 0 else "n/a"
    )
    interval_high = (
        f"{interval[1]:.1%}" if isinstance(interval, list) and len(interval) > 1 else "n/a"
    )
    lines = [
        "- Alerts: {total}; preceding a recall: {hits} (share {share}) - "
        "`results/trend/backtest.json`".format(
            total=alerts.get("total", 0),
            hits=alerts.get("preceding_recall", 0),
            share=f"{share:.1%}" if isinstance(share, (int, float)) else "n/a",
        ),
        "- Base rate for random same-series weeks: {share} (95% CI {low}-{high}) - "
        "`results/trend/backtest.json`".format(
            share=f"{base_share:.1%}" if isinstance(base_share, (int, float)) else "n/a",
            low=interval_low,
            high=interval_high,
        ),
    ]
    if alerts.get("weak_join"):
        lines.append("- The recall join is weak; the backtest file says so plainly.")
    return lines


def build_summary(
    runs_dir: Path = Path("results/runs"),
    results_dir: Path = Path("results"),
) -> str:
    """Render ``results/SUMMARY.md`` from the committed results files."""
    run = _pick_run(runs_dir)
    metrics = _read_json(run / "metrics.json") if run is not None else None
    manifest = _read_json(run / "manifest.json") if run is not None else None
    lines = [
        "# Field Return Triage - results summary",
        "",
        "Generated by `make results` in replay mode: no key, no network. Every number",
        "below names the committed file it came from.",
        "",
    ]
    if metrics is None or run is None:
        lines.append("No run metrics yet - run `make results`.")
        lines.append("")
    else:
        fixture = bool(metrics.get("fixture"))
        if fixture:
            lines.extend(
                [
                    "> **Fixture run.** `config/models.lock.toml` and `recordings/` do not",
                    "> exist yet, so this run used two fake models and the 20 fake",
                    "> recordings in `tests/fixtures/recordings/`. These are not model",
                    "> results and must not be quoted as such.",
                    "",
                ]
            )
        models = manifest.get("models", []) if manifest else []
        model_names = ", ".join(
            f"`{entry.get('model_id')}` ({entry.get('role')})"
            for entry in models
            if isinstance(entry, Mapping)
        )
        lines.extend(
            [
                "## Run",
                "",
                f"- Run id: `{metrics.get('run_id')}` - `results/runs/{metrics.get('run_id')}/manifest.json`",
                f"- Metrics file: `results/runs/{metrics.get('run_id')}/metrics.json`",
                f"- Mode: {metrics.get('mode')}",
                f"- Models: {model_names or 'n/a'}",
                f"- Evaluation items: {metrics.get('item_count')}",
                f"- Sample sha256: `{manifest.get('sample_hash') if manifest else 'n/a'}`",
                f"- Run cost: USD {manifest.get('cost_usd') if manifest else 'n/a'} - "
                f"`results/runs/{metrics.get('run_id')}/manifest.json`",
                "",
                "## Component group",
                "",
                "Macro-F1 is the primary metric; `unclear` counts as wrong.",
                "",
                *_model_rows(metrics),
                "",
                "## Safety",
                "",
                "Final is the hard-rule decision; model-only is the model's own flag. "
                "Both are scored against the coded crash/fire/injury fields.",
                "",
                *_safety_rows(metrics),
                "",
                "## Quality, routing and speed",
                "",
                *_quality_rows(metrics),
                "",
                *_cost_rows(metrics),
                "",
            ]
        )
    lines.extend(
        [
            "## Baselines (cost 0)",
            "",
            "See `results/baseline/`.",
            "",
            *_baseline_rows(results_dir / "baseline"),
            "",
            "## Trend watch",
            "",
            *_trend_lines(results_dir / "trend"),
            "",
            "## Files",
            "",
            "- `results/runs/<id>/{manifest.json,cards.jsonl,metrics.json}`",
            "- `results/baseline/{group,safety,conditions}.json`",
            "- `results/trend/{alerts,backtest,example_series}.json`",
            "- `results/MANIFEST.sha256`",
            "",
            "A technician decides every case. No result here closes, scraps or returns a",
            "part.",
            "",
        ]
    )
    return "\n".join(lines)


def write_summary(
    *,
    runs_dir: Path = Path("results/runs"),
    results_dir: Path = Path("results"),
) -> Path:
    """Write ``results/SUMMARY.md`` and return its path."""
    path = results_dir / "SUMMARY.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_summary(runs_dir, results_dir), encoding="utf-8")
    return path


def _tree_files(results_dir: Path) -> Sequence[Path]:
    return sorted(
        path for path in results_dir.rglob("*") if path.is_file() and path.name != MANIFEST_NAME
    )


def write_manifest(results_dir: Path = Path("results")) -> Path:
    """Write ``results/MANIFEST.sha256`` over every other results file, sorted."""
    results_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(results_dir).as_posix()}"
        for path in _tree_files(results_dir)
    ]
    target = results_dir / MANIFEST_NAME
    target.write_text(("\n".join(lines) + ("\n" if lines else "")), encoding="utf-8")
    return target
