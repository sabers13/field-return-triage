"""Cost from the gateway's per-response list cost, else tokens x ``config/prices.toml``.

PLAN §6 and §9: a call's cost is the gateway's own list cost when the response carries
one, otherwise ``input_tokens * input_price + output_tokens * output_price`` from the
committed price table. Prices are USD per 1,000,000 tokens.

The pre-run estimate is deliberately conservative: it assumes a fixed input length and
the full output allowance, and uses the peak price when a model has peak/off-peak
prices. R7 compares the estimate with the USD 3 cap before spending anything.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from field_return_triage.contracts import ModelSetting
from field_return_triage.llm.errors import ConfigurationError

__all__ = [
    "ESTIMATED_INPUT_TOKENS_PER_ITEM",
    "PRICES_PATH",
    "ModelPrice",
    "estimate_cost_usd",
    "load_prices",
    "price_for",
    "reply_cost_usd",
    "token_cost_usd",
]

PRICES_PATH: Path = Path("config/prices.toml")

#: Conservative prompt size per item used only by the pre-run estimate.
ESTIMATED_INPUT_TOKENS_PER_ITEM = 1_000

#: Response fields that can carry a USD list cost, most specific first.
_COST_KEYS: tuple[tuple[str, ...], ...] = (
    ("cost_usd",),
    ("list_cost",),
    ("total_cost",),
    ("usage", "cost_usd"),
    ("usage", "list_cost"),
    ("usage", "total_cost"),
    ("usage", "cost"),
    ("cost",),
)


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """One model's list price, USD per 1M tokens."""

    input: float
    output: float
    input_off_peak: float | None = None
    output_off_peak: float | None = None

    def conservative(self) -> tuple[float, float]:
        """The higher of the peak and off-peak prices, for an upper-bound estimate."""
        input_price = max(self.input, self.input_off_peak or 0.0)
        output_price = max(self.output, self.output_off_peak or 0.0)
        return input_price, output_price


def load_prices(path: Path = PRICES_PATH) -> dict[str, ModelPrice]:
    """Read ``[models."<id>"]`` entries with input/output prices."""
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except FileNotFoundError:
        msg = f"price table not found: {path}"
        raise ConfigurationError(msg) from None
    except (OSError, tomllib.TOMLDecodeError) as exc:
        msg = f"cannot read {path}: {exc.__class__.__name__}"
        raise ConfigurationError(msg) from None

    table = raw.get("models")
    if not isinstance(table, dict) or not table:
        msg = f"{path} must define a non-empty [models] table"
        raise ConfigurationError(msg)

    prices: dict[str, ModelPrice] = {}
    for model_id, entry in table.items():
        if not isinstance(entry, dict):
            msg = f"price entry {model_id!r} must be a table"
            raise ConfigurationError(msg)
        prices[model_id] = ModelPrice(
            input=_price(entry, "input", model_id),
            output=_price(entry, "output", model_id),
            input_off_peak=_optional_price(entry, "input_off_peak", model_id),
            output_off_peak=_optional_price(entry, "output_off_peak", model_id),
        )
    return prices


def _price(entry: dict[str, Any], key: str, model_id: str) -> float:
    value = entry.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        msg = f"price entry {model_id!r}.{key} must be a non-negative number"
        raise ConfigurationError(msg)
    return float(value)


def _optional_price(entry: dict[str, Any], key: str, model_id: str) -> float | None:
    if key not in entry:
        return None
    return _price(entry, key, model_id)


def price_for(model_id: str, prices: dict[str, ModelPrice]) -> ModelPrice | None:
    """The price entry for a gateway model id, or ``None`` when it is not listed."""
    return prices.get(model_id)


def token_cost_usd(
    settings: ModelSetting,
    input_tokens: int | None,
    output_tokens: int | None,
    prices_path: Path = PRICES_PATH,
) -> float | None:
    """Tokens x price, or ``None`` when the tokens or the price are unknown."""
    if input_tokens is None or output_tokens is None:
        return None
    price = price_for(settings.model_id, load_prices(prices_path))
    if price is None:
        return None
    return (input_tokens * price.input + output_tokens * price.output) / 1_000_000


def estimate_cost_usd(
    settings: ModelSetting,
    items: int,
    prices_path: Path = PRICES_PATH,
) -> float:
    """Upper-bound cost for ``items`` calls, before a run (PLAN §8).

    Assumes ``ESTIMATED_INPUT_TOKENS_PER_ITEM`` prompt tokens and the full
    ``max_output_tokens`` allowance per call, at the higher of the peak and
    off-peak prices. Raises when the model has no price entry, because a budget
    guard cannot honestly run without one.
    """
    if items < 0:
        msg = "items must not be negative"
        raise ConfigurationError(msg)
    price = price_for(settings.model_id, load_prices(prices_path))
    if price is None:
        msg = f"no price entry for model {settings.model_id!r} in {prices_path}"
        raise ConfigurationError(msg)
    input_price, output_price = price.conservative()
    input_tokens = items * ESTIMATED_INPUT_TOKENS_PER_ITEM
    output_tokens = items * settings.max_output_tokens
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


def _lookup(payload: Any, keys: tuple[str, ...]) -> Any:
    value = payload
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def _as_cost(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number < 0 or number != number:  # negative or NaN
        return None
    return number


def gateway_cost_usd(payload: Any, headers: Any | None = None) -> float | None:
    """The USD list cost the gateway reports for one response, when it reports one.

    The Go docs say each response reports ``opencode.allowance``, which is an
    allowance fraction, not a USD price, so it is not used here. A USD field or an
    ``x-opencode-cost-usd`` header is used when present.
    """
    for keys in _COST_KEYS:
        cost = _as_cost(_lookup(payload, keys))
        if cost is not None:
            return cost
    if headers is not None:
        header = headers.get("x-opencode-cost-usd")
        if header:
            try:
                return _as_cost(float(header))
            except (TypeError, ValueError):
                return None
    return None


def reply_cost_usd(
    payload: Any,
    headers: Any | None,
    settings: ModelSetting,
    *,
    prices_path: Path = PRICES_PATH,
) -> float | None:
    """Gateway list cost when present, else tokens x price, else ``None``."""
    reported = gateway_cost_usd(payload, headers)
    if reported is not None:
        return reported
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        return None
    input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
    output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
    input_count = input_tokens if isinstance(input_tokens, int) else None
    output_count = output_tokens if isinstance(output_tokens, int) else None
    return token_cost_usd(settings, input_count, output_count, prices_path)
