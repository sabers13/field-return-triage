"""The recall join, the base rate and the report body."""

from __future__ import annotations

import pytest
from trend_support import START, counts, key, mondays, recall, weekly

from field_return_triage.contracts import TrendAlert
from field_return_triage.trend.backtest import (
    MAX_LEAD_DAYS,
    WEAK_JOIN_MIN,
    pick_example_series,
    preceding_recall,
    recall_index,
    run_backtest,
    wilson_interval,
)
from field_return_triage.trend.series import group_weeks
from field_return_triage.trend.spike import detect_alerts


def _alert(
    *,
    week=START,
    count: int = 6,
    series=None,
) -> TrendAlert:
    return TrendAlert(
        series=series or key(),
        week=week,
        count=count,
        trailing_mean=0.5,
        threshold=4.0,
    )


def test_the_recall_window_includes_both_edges() -> None:
    series = key()
    on_the_alert = recall(START, 0, recall_id="day-0")
    index = recall_index([on_the_alert])
    assert preceding_recall(series, START, index) is on_the_alert
    assert (on_the_alert.report_date - START).days == 0

    last_day = recall(START, MAX_LEAD_DAYS, recall_id="day-365")
    assert preceding_recall(series, START, recall_index([last_day])) is last_day
    assert (last_day.report_date - START).days == MAX_LEAD_DAYS


def test_recalls_outside_the_window_do_not_match() -> None:
    series = key()
    before = recall(START, -1, recall_id="day-minus-1")
    after = recall(START, MAX_LEAD_DAYS + 1, recall_id="day-366")
    index = recall_index([before, after])
    assert preceding_recall(series, START, index) is None


def test_the_earliest_recall_in_the_window_wins() -> None:
    series = key()
    late = recall(START, 200, recall_id="late")
    early = recall(START, 30, recall_id="early")
    assert preceding_recall(series, START, recall_index([late, early])) is early


def test_a_recall_only_joins_its_own_series() -> None:
    index = recall_index([recall(START, 10, series=key(make="Beta"))])
    assert preceding_recall(key(make="Acme"), START, index) is None


def test_run_backtest_reports_share_and_median_lead() -> None:
    series = key()
    weeks = mondays(30)
    alerts = [
        _alert(week=weeks[27]),
        _alert(week=weeks[28]),
        _alert(week=weeks[29]),
    ]
    recalls = [
        recall(weeks[27], 3, recall_id="r-early"),
        recall(weeks[28], 3, recall_id="r-mid"),
    ]
    result = run_backtest(alerts, group_weeks(weekly(series, [0] * 30)), recalls)
    assert result.preceding == 2
    assert result.share == pytest.approx(2 / 3)
    assert result.median_lead_days == pytest.approx(3.0)
    assert result.weak_join is True


def test_the_report_body_keeps_the_alerts_when_the_join_is_weak() -> None:
    body = run_backtest([_alert()], {key(): counts([0] * 30)}, []).as_dict()
    assert body["alerts"]["total"] == 1
    assert body["alerts"]["preceding_recall"] == 0
    assert body["alerts"]["weak_join"] is True
    assert "too weak" in body["alerts"]["note"]
    assert body["per_alert"][0]["recall_id"] is None


def test_a_strong_join_has_no_weak_note() -> None:
    series_map = {}
    alerts = []
    recalls = []
    for number in range(WEAK_JOIN_MIN):
        item = key(make=f"Make{number:02d}")
        rows = weekly(item, [0] * 26 + [5])
        series_map.update(group_weeks(rows))
        alerts.extend(detect_alerts(group_weeks(rows)))
        recalls.append(recall(rows[-1].week, 10, series=item, recall_id=f"r-{number}"))
    assert len(alerts) == WEAK_JOIN_MIN
    result = run_backtest(alerts, series_map, recalls)
    assert result.preceding == WEAK_JOIN_MIN
    assert result.weak_join is False
    assert result.as_dict()["alerts"]["note"] is None


def test_base_rate_draws_only_evaluated_weeks() -> None:
    series = key()
    weeks = mondays(40)
    alerts = [_alert(week=weeks[index]) for index in range(26, 34)]
    result = run_backtest(alerts, group_weeks(weekly(series, [0] * 40)), [])
    assert {draw.week for draw in result.draws} <= set(weeks[26:])
    assert len(result.draws) == len(alerts)


def test_base_rate_is_deterministic_for_a_fixed_seed() -> None:
    series = key()
    weeks = mondays(60)
    alerts = [_alert(week=weeks[index]) for index in range(26, 56)]
    series_map = group_weeks(weekly(series, [0] * 60))
    first = run_backtest(alerts, series_map, [], seed=7)
    second = run_backtest(alerts, series_map, [], seed=7)
    assert [draw.week for draw in first.draws] == [draw.week for draw in second.draws]
    other = run_backtest(alerts, series_map, [], seed=8)
    assert [draw.week for draw in first.draws] != [draw.week for draw in other.draws]


def test_base_rate_share_counts_drawn_recalls() -> None:
    series = key()
    weeks = mondays(40)
    alerts = [_alert(week=weeks[index]) for index in range(26, 36)]
    recalls = [recall(weeks[26], 3, recall_id="r-26")]
    result = run_backtest(alerts, group_weeks(weekly(series, [0] * 40)), recalls)
    assert result.base_rate_hits == sum(1 for draw in result.draws if draw.recall is not None)
    assert result.base_rate_share == pytest.approx(result.base_rate_hits / len(result.draws))


def test_wilson_interval_known_values() -> None:
    assert wilson_interval(0, 10)[0] == 0.0
    assert wilson_interval(0, 10)[1] == pytest.approx(0.2775, abs=5e-4)
    assert wilson_interval(10, 10)[0] == pytest.approx(0.7225, abs=5e-4)
    assert wilson_interval(10, 10)[1] == pytest.approx(1.0)
    low, high = wilson_interval(5, 10)
    assert low == pytest.approx(0.2366, abs=5e-4)
    assert high == pytest.approx(0.7634, abs=5e-4)


def test_wilson_interval_rejects_bad_counts() -> None:
    with pytest.raises(ValueError, match="draws must be positive"):
        wilson_interval(0, 0)
    with pytest.raises(ValueError, match="between 0 and draws"):
        wilson_interval(2, 1)


def test_no_alerts_still_produces_a_report() -> None:
    body = run_backtest([], {}, []).as_dict()
    assert body["alerts"]["total"] == 0
    assert body["alerts"]["share"] is None
    assert body["alerts"]["median_lead_days"] is None
    assert body["base_rate"]["draws"] == 0
    assert body["base_rate"]["ci95"] is None
    assert body["per_alert"] == []
    assert "No alerts" in body["alerts"]["note"]


def test_example_series_rule_prefers_the_longest_lead_with_enough_complaints() -> None:
    short = key(make="Short")
    long = key(make="Long")
    short_rows = weekly(short, [1] * 26 + [6])
    long_rows = weekly(long, [3] * 26 + [20])
    series_map = {**group_weeks(short_rows), **group_weeks(long_rows)}
    short_alert = detect_alerts(group_weeks(short_rows))[0]
    long_alert = detect_alerts(group_weeks(long_rows))[0]
    alerts = [short_alert, long_alert]
    recalls = [
        recall(short_alert.week, 300, series=short, recall_id="short-300"),
        recall(long_alert.week, 100, series=long, recall_id="long-100"),
    ]
    result = run_backtest(alerts, series_map, recalls)
    example = pick_example_series(result, series_map)
    assert example is not None
    assert example["series"]["make"] == "Short"
    assert example["recall"]["lead_days"] == 300


def test_example_series_needs_at_least_20_complaints() -> None:
    item = key()
    series_map = group_weeks(weekly(item, [0] * 26 + [5]))
    alert = detect_alerts(group_weeks(weekly(item, [0] * 26 + [5])))[0]
    result = run_backtest([alert], series_map, [recall(alert.week, 10)])
    assert pick_example_series(result, series_map) is None


def test_example_series_returns_none_without_a_recall_match() -> None:
    item = key()
    series_map = group_weeks(weekly(item, [5] * 27))
    result = run_backtest([_alert(week=mondays(27)[26])], series_map, [])
    assert pick_example_series(result, series_map) is None
