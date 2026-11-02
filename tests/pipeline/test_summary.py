"""``results/SUMMARY.md``: numbers with their source files, and no invented values."""

from __future__ import annotations

import json
from pathlib import Path

from field_return_triage.pipeline.summary import build_summary, write_summary


def _metrics(root: Path, *, fixture: bool) -> None:
    run = root / "runs" / "live"
    run.mkdir(parents=True)
    (run / "metrics.json").write_text(
        json.dumps(
            {
                "run_id": "live",
                "mode": "replay",
                "fixture": fixture,
                "item_count": 400,
                "models": {
                    "model-a": {
                        "role": "primary",
                        "items_evaluated": 400,
                        "invalid_answers": 2,
                        "group": {
                            "macro_f1": {"value": 0.812, "ci_low": 0.79, "ci_high": 0.83},
                            "accuracy": {"value": 0.85},
                            "coverage": {"value": 0.94},
                            "answered_accuracy": {"value": 0.9},
                        },
                        "safety": {
                            "final_recall": {"value": 0.7},
                            "final_precision": {"value": 0.5},
                            "model_recall": {"value": 0.6},
                            "model_precision": {"value": 0.4},
                        },
                        "quote_grounding": {"value": 0.99},
                        "condition_agreement": {"value": 0.8},
                        "similar_precision_at_5": {"value": 0.6},
                        "routing": {
                            "priority_1_share": {"value": 0.2},
                            "needs_human_share": {"value": 0.15},
                        },
                        "cost": {
                            "total_usd": {"value": 0.5},
                            "per_1000_usd": {"value": 1.25},
                        },
                        "latency_ms": {
                            "p50": {"value": 800.0},
                            "p95": {"value": 1500.0},
                        },
                    }
                },
                "budget": {"cap_usd": 3.0, "spent_usd": 0.5, "models": []},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (run / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "live",
                "models": [{"model_id": "model-a", "role": "primary"}],
                "sample_hash": "a" * 64,
                "cost_usd": 0.5,
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_empty_results_say_what_to_run(tmp_path: Path) -> None:
    text = build_summary(tmp_path / "runs", tmp_path)
    assert "No run metrics yet" in text
    assert "make results" in text


def test_summary_states_numbers_with_their_files(tmp_path: Path) -> None:
    _metrics(tmp_path, fixture=False)
    text = build_summary(tmp_path / "runs", tmp_path)
    assert "model-a" in text
    assert "0.812 (0.790-0.830)" in text
    assert "USD 0.5" in text
    assert "results/runs/live/metrics.json" in text
    assert "Fixture run" not in text
    assert build_summary(tmp_path / "runs", tmp_path) == text


def test_fixture_runs_are_labelled_plainly(tmp_path: Path) -> None:
    _metrics(tmp_path, fixture=True)
    text = build_summary(tmp_path / "runs", tmp_path)
    assert "Fixture run" in text
    assert "not model" in text


def test_the_trend_lines_read_the_written_interval_and_median_lead(tmp_path: Path) -> None:
    _metrics(tmp_path, fixture=False)
    trend = tmp_path / "trend"
    trend.mkdir()
    (trend / "backtest.json").write_text(
        json.dumps(
            {
                "alerts": {
                    "total": 93,
                    "preceding_recall": 35,
                    "share": 0.376344,
                    "median_lead_days": 70.0,
                },
                "base_rate": {
                    "share": 0.322581,
                    "ci95": {"low": 0.236249, "high": 0.422987},
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    text = build_summary(tmp_path / "runs", tmp_path)
    assert "32.3% (95% CI 23.6%-42.3%)" in text
    assert "median lead 70.0 days" in text
    assert "n/a-n/a" not in text


def test_write_summary_returns_the_file(tmp_path: Path) -> None:
    path = write_summary(runs_dir=tmp_path / "runs", results_dir=tmp_path)
    assert path == tmp_path / "SUMMARY.md"
    assert path.read_text(encoding="utf-8").startswith("# Field Return Triage")
