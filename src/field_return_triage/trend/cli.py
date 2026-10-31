"""``frt trend`` / ``make trend``: write the alerts, backtest and example series.

The command reads the committed trend tables, applies the fixed rule and writes three
JSON files under ``results/trend/``. It makes no network call and no model call. The
paths can be overridden with ``FRT_TREND_WEEKLY``, ``FRT_TREND_RECALLS`` and
``FRT_TREND_RESULTS`` so a test or a scratch run can point at its own tables.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Final

import typer

from field_return_triage.contracts import TrendAlert
from field_return_triage.trend.backtest import (
    BASE_RATE_SEED,
    MAX_LEAD_DAYS,
    pick_example_series,
    run_backtest,
)
from field_return_triage.trend.series import (
    group_weeks,
    load_recalls,
    load_weekly,
    series_key_dict,
    series_sort_key,
)
from field_return_triage.trend.spike import (
    MEAN_FLOOR,
    MIN_COUNT,
    QUANTILE,
    TRAILING_WEEKS,
    detect_alerts,
)

__all__ = ["DEFAULT_RECALLS", "DEFAULT_RESULTS", "DEFAULT_WEEKLY", "trend_main"]

DEFAULT_WEEKLY: Final = Path("data/trend/weekly.csv.gz")
DEFAULT_RECALLS: Final = Path("data/trend/recalls.csv")
DEFAULT_RESULTS: Final = Path("results/trend")

_RULE = (
    "count >= 3 and count > the Poisson 99.9% upper limit of the trailing 26-week "
    "mean, with the mean floored at 0.5"
)


def _path_from_env(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value) if value else default


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _alerts_payload(alerts: list[TrendAlert]) -> dict[str, Any]:
    series = {series_sort_key(alert.series) for alert in alerts}
    return {
        "rule": _RULE,
        "parameters": {
            "trailing_weeks": TRAILING_WEEKS,
            "min_count": MIN_COUNT,
            "mean_floor": MEAN_FLOOR,
            "quantile": QUANTILE,
        },
        "count": len(alerts),
        "series_with_alerts": len(series),
        "alerts": [
            {
                "series": series_key_dict(alert.series),
                "week": alert.week.isoformat(),
                "count": alert.count,
                "trailing_mean": alert.trailing_mean,
                "threshold": alert.threshold,
            }
            for alert in alerts
        ],
    }


def trend_main(
    *,
    weekly_path: Path | None = None,
    recalls_path: Path | None = None,
    results_dir: Path | None = None,
) -> None:
    """Run the rule and the backtest, then write the three results files."""
    weekly = weekly_path or _path_from_env("FRT_TREND_WEEKLY", DEFAULT_WEEKLY)
    recalls_file = recalls_path or _path_from_env("FRT_TREND_RECALLS", DEFAULT_RECALLS)
    results = results_dir or _path_from_env("FRT_TREND_RESULTS", DEFAULT_RESULTS)

    try:
        rows = load_weekly(weekly)
        recalls = load_recalls(recalls_file)
    except FileNotFoundError as exc:
        typer.echo(f"frt trend: {exc.filename} is missing; run `make data` first", err=True)
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        typer.echo(f"frt trend: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        series = group_weeks(rows)
    except ValueError as exc:
        typer.echo(f"frt trend: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if not series:
        typer.echo(f"frt trend: {weekly} holds no weekly rows", err=True)
        raise typer.Exit(code=1)

    alerts = detect_alerts(series)
    backtest = run_backtest(alerts, series, recalls, seed=BASE_RATE_SEED)
    example = pick_example_series(backtest, series)

    results.mkdir(parents=True, exist_ok=True)
    _write(results / "alerts.json", _alerts_payload(alerts))
    _write(results / "backtest.json", backtest.as_dict())
    if example is None:
        _write(
            results / "example_series.json",
            {
                "available": False,
                "reason": ("No alert precedes a recall in a series with at least 20 complaints."),
                "series": None,
                "weeks": [],
            },
        )
    else:
        _write(results / "example_series.json", {"available": True, **example})

    typer.echo(f"frt trend: {len(alerts)} alerts in {len(series)} series -> {results}")
    share = backtest.share
    base = backtest.base_rate_share
    interval = backtest.base_rate_interval
    if share is None:
        typer.echo("frt trend: no alerts; nothing to backtest")
    elif base is not None and interval is not None:
        typer.echo(
            f"frt trend: {backtest.preceding}/{len(alerts)} alerts precede a recall "
            f"({share:.1%}); base rate {base:.1%} "
            f"(95% CI {interval[0]:.1%}-{interval[1]:.1%}), window {MAX_LEAD_DAYS} days"
        )
    else:
        typer.echo("frt trend: no base-rate draws")
    if backtest.weak_join:
        typer.echo(
            f"frt trend: weak recall join ({backtest.preceding} alerts precede a recall); "
            "the backtest file says so"
        )


if __name__ == "__main__":  # pragma: no cover - `make trend` entry point
    trend_main()
