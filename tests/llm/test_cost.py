"""Price table, pre-run estimate and per-response cost."""

from __future__ import annotations

from pathlib import Path

import pytest

from field_return_triage.contracts import ModelSetting
from field_return_triage.llm.cost import (
    ESTIMATED_INPUT_TOKENS_PER_ITEM,
    estimate_cost_usd,
    gateway_cost_usd,
    load_prices,
    reply_cost_usd,
)
from field_return_triage.llm.errors import ConfigurationError


def test_price_table_covers_the_locked_candidates(prices_path: Path) -> None:
    prices = load_prices(prices_path)
    assert {"deepseek-v4.1-flash", "deepseek-v4-pro", "glm-5.3-flash"} <= set(prices)
    deepseek = prices["deepseek-v4.1-flash"]
    assert deepseek.input == 0.30
    assert deepseek.output == 1.20
    assert deepseek.input_off_peak == 0.15
    assert deepseek.conservative() == (0.30, 1.20)


def test_estimate_is_a_conservative_upper_bound(prices_path: Path) -> None:
    settings = ModelSetting(role="primary", model_id="deepseek-v4.1-flash")
    estimate = estimate_cost_usd(settings, 2, prices_path)
    expected = (2 * ESTIMATED_INPUT_TOKENS_PER_ITEM * 0.30 + 2 * 1024 * 1.20) / 1_000_000
    assert estimate == pytest.approx(expected)


def test_estimate_refuses_an_unpriced_model(prices_path: Path) -> None:
    settings = ModelSetting(role="primary", model_id="not-a-model")
    with pytest.raises(ConfigurationError):
        estimate_cost_usd(settings, 10, prices_path)


def test_gateway_cost_fields() -> None:
    assert gateway_cost_usd({"cost_usd": 0.5}) == 0.5
    assert gateway_cost_usd({"usage": {"cost": 0.25}}) == 0.25
    assert gateway_cost_usd({"usage": {"total_cost": 0.125}}) == 0.125
    assert gateway_cost_usd({"cost": -1}) is None
    assert gateway_cost_usd({}) is None
    assert gateway_cost_usd({}, {"x-opencode-cost-usd": "0.01"}) == 0.01


def test_reply_cost_falls_back_to_tokens(prices_path: Path) -> None:
    settings = ModelSetting(role="primary", model_id="deepseek-v4.1-flash")
    payload = {"usage": {"prompt_tokens": 30, "completion_tokens": 60}}
    cost = reply_cost_usd(payload, None, settings, prices_path=prices_path)
    assert cost == pytest.approx((30 * 0.30 + 60 * 1.20) / 1_000_000)


def test_reply_cost_is_none_when_tokens_are_missing(prices_path: Path) -> None:
    settings = ModelSetting(role="primary", model_id="deepseek-v4.1-flash")
    assert reply_cost_usd({"usage": {}}, None, settings, prices_path=prices_path) is None
