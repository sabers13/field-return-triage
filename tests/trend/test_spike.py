"""The spike rule: Poisson limit, trailing mean and the alert boundary."""

from __future__ import annotations

import math
from datetime import timedelta

import pytest
from trend_support import START, key, weekly

from field_return_triage.trend.series import group_weeks
from field_return_triage.trend.spike import (
    MEAN_FLOOR,
    MIN_COUNT,
    TRAILING_WEEKS,
    detect_alerts,
    is_spike,
    poisson_upper_limit,
    trailing_mean,
)


def _cdf(mean: float, k: int) -> float:
    return math.fsum(math.exp(-mean) * mean**i / math.factorial(i) for i in range(k + 1))


@pytest.mark.parametrize(
    ("mean", "limit"),
    [(0.0, 0), (0.5, 4), (1.0, 5), (2.0, 8), (5.0, 13), (10.0, 21)],
)
def test_poisson_upper_limit_known_values(mean: float, limit: int) -> None:
    assert poisson_upper_limit(mean) == limit


def test_poisson_limit_is_the_smallest_qualifying_integer() -> None:
    for mean in (0.5, 1.0, 2.0, 3.5, 5.0, 10.0):
        limit = poisson_upper_limit(mean)
        assert _cdf(mean, limit) >= 0.999
        assert _cdf(mean, limit - 1) < 0.999


def test_poisson_limit_large_mean_does_not_underflow() -> None:
    limit = poisson_upper_limit(1000.0)
    assert 1000 < limit < 1200


def test_poisson_limit_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="mean must be >= 0"):
        poisson_upper_limit(-1.0)
    with pytest.raises(ValueError, match="quantile must be in"):
        poisson_upper_limit(1.0, quantile=1.0)


def test_trailing_mean_uses_exactly_26_weeks() -> None:
    assert trailing_mean([1] * TRAILING_WEEKS) == pytest.approx(1.0)
    assert trailing_mean([0] * TRAILING_WEEKS) == MEAN_FLOOR
    with pytest.raises(ValueError, match="must hold 26 weeks"):
        trailing_mean([1] * (TRAILING_WEEKS - 1))


def test_spike_needs_the_minimum_count_and_strictly_above_the_limit() -> None:
    assert is_spike(2, MEAN_FLOOR) is False  # below MIN_COUNT
    assert is_spike(MIN_COUNT, 100.0) is False  # above the floor, below the limit
    assert is_spike(4, MEAN_FLOOR) is False  # the limit itself
    assert is_spike(5, MEAN_FLOOR) is True  # one above the limit


def test_a_spike_is_detected_and_quiet_weeks_are_not() -> None:
    series = key()
    rows = weekly(series, [1] * TRAILING_WEEKS + [12])
    alerts = detect_alerts(group_weeks(rows))
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.series == series
    assert alert.week == rows[-1].week
    assert alert.count == 12
    assert alert.trailing_mean == pytest.approx(1.0)
    assert alert.threshold == float(poisson_upper_limit(1.0))


def test_a_steady_series_stays_quiet() -> None:
    rows = weekly(key(), [0, 1, 2, 1, 0, 2, 1, 0, 1, 2] * 5)
    assert detect_alerts(group_weeks(rows)) == []


def test_no_alert_before_a_full_26_week_history() -> None:
    short = weekly(key(), [5] * TRAILING_WEEKS)
    assert detect_alerts(group_weeks(short)) == []
    long = weekly(key(), [5] * TRAILING_WEEKS + [50])
    assert len(detect_alerts(group_weeks(long))) == 1


def test_the_limit_boundary_in_a_real_series() -> None:
    at_limit = weekly(key(), [0] * TRAILING_WEEKS + [4])
    assert detect_alerts(group_weeks(at_limit)) == []
    over_limit = weekly(key(), [0] * TRAILING_WEEKS + [5])
    assert [alert.count for alert in detect_alerts(group_weeks(over_limit))] == [5]


def test_a_two_count_week_never_alerts_even_for_a_quiet_series() -> None:
    rows = weekly(key(), [0] * TRAILING_WEEKS + [2])
    assert detect_alerts(group_weeks(rows)) == []


def test_missing_weeks_count_as_zero() -> None:
    series = key()
    week = START + timedelta(weeks=27)
    rows = weekly(series, [5]) + weekly(series, [5], start=week)
    alerts = detect_alerts(group_weeks(rows))
    assert len(alerts) == 1
    assert alerts[0].week == week
    assert alerts[0].trailing_mean == MEAN_FLOOR


def test_alerts_are_ordered_by_series_then_week() -> None:
    second = key(make="Beta")
    first = key(make="Acme")
    rows = weekly(second, [0] * TRAILING_WEEKS + [9]) + weekly(first, [0] * TRAILING_WEEKS + [6, 6])
    alerts = detect_alerts(group_weeks(rows))
    assert [alert.series.make for alert in alerts] == ["Acme", "Acme", "Beta"]
    assert alerts[0].week < alerts[1].week
