import json
from decimal import Decimal
from typing import Dict, Optional

from hummingbot.client.config.config_validators import (
    validate_decimal,
    validate_exchange,
    validate_int,
    validate_market_trading_pair)
from hummingbot.client.config.config_var import ConfigVar
from hummingbot.client.settings import AllConnectorSettings, required_exchanges


def trading_pair_prompt():
    exchange = dev_many_orders_config_map.get("exchange").value
    example = AllConnectorSettings.get_example_pairs().get(exchange)
    return "Enter the trading pair you would like to trade on %s%s >>> " \
           % (exchange, f" (e.g. {example})" if example else "")


def validate_trading_pair(value: str) -> Optional[str]:
    exchange = dev_many_orders_config_map.get("exchange").value
    return validate_market_trading_pair(exchange, value)


def validate_logging_options(value: str) -> Optional[Dict]:
    value = json.loads(value)

    return value


def bid_order_amount_prompt() -> str:
    trading_pair = dev_many_orders_config_map["trading_pair"].value
    base_asset, quote_asset = trading_pair.split("-")
    return f"What is the amount of {base_asset} per bid order? >>> "


def ask_order_amount_prompt() -> str:
    trading_pair = dev_many_orders_config_map["trading_pair"].value
    base_asset, quote_asset = trading_pair.split("-")
    return f"What is the amount of {base_asset} per ask order? >>> "


dev_many_orders_config_map = {
    "strategy": ConfigVar(
        key="strategy",
        prompt="",
        default="dev_many_orders"
    ),
    "exchange": ConfigVar(
        key="exchange",
        prompt="Enter the name of the exchange >>> ",
        validator=validate_exchange,
        on_validated=lambda value: required_exchanges.add(value),
        prompt_on_new=True
    ),
    "trading_pair": ConfigVar(
        key="trading_pair",
        prompt=trading_pair_prompt,
        validator=validate_trading_pair,
        prompt_on_new=True
    ),
    "n_levels_bid": ConfigVar(
        key="n_levels_bid",
        prompt="How many levels do you want on the bid side? >>> ",
        type_str="int",
        validator=lambda v: validate_int(v, min_value=-1, inclusive=False),
        default=3,
        prompt_on_new=True
    ),
    "n_levels_ask": ConfigVar(
        key="n_levels_ask",
        prompt="How many levels do you want on the ask side? >>> ",
        type_str="int",
        validator=lambda v: validate_int(v, min_value=-1, inclusive=False),
        default=3,
        prompt_on_new=True
    ),
    "bid_size": ConfigVar(
        key="bid_size",
        prompt=bid_order_amount_prompt,
        type_str="decimal",
        validator=lambda v: validate_decimal(v, min_value=Decimal("0"), inclusive=False),
        prompt_on_new=True
    ),
    "ask_size": ConfigVar(
        key="ask_size",
        prompt=ask_order_amount_prompt,
        type_str="decimal",
        validator=lambda v: validate_decimal(v, min_value=Decimal("0"), inclusive=False),
        prompt_on_new=True
    ),
    "bid_spread": ConfigVar(
        key="bid_spread",
        prompt="How far away from the mid price do you want to place the first order used to rebalance the bid side of the book? (Enter 1 to indicate 1%) >>> ",
        type_str="decimal",
        default=Decimal("0.5"),
        validator=lambda v: validate_decimal(v, min_value=Decimal("0"), inclusive=False),
        prompt_on_new=True
    ),
    "ask_spread": ConfigVar(
        key="ask_spread",
        prompt="How far away from the mid price do you want to place the first order used to rebalance the ask side of the book? (Enter 1 to indicate 1%) >>> ",
        type_str="decimal",
        default=Decimal("0.5"),
        validator=lambda v: validate_decimal(v, min_value=Decimal("0"), inclusive=False),
        prompt_on_new=True
    ),
    "price_level_pct_step_bid": ConfigVar(
        key="price_level_pct_step_bid",
        prompt="How far away you want to place bids from each other in %? (Enter 1 to indicate 1%) >>> ",
        type_str="decimal",
        default=Decimal("0.5"),
        validator=lambda v: validate_decimal(v, min_value=Decimal("0"), inclusive=False),
        prompt_on_new=True
    ),
    "price_level_pct_step_ask": ConfigVar(
        key="price_level_pct_step_ask",
        prompt="How far away you want to place asks from each other in %? (Enter 1 to indicate 1%) >>> ",
        type_str="decimal",
        default=Decimal("0.5"),
        validator=lambda v: validate_decimal(v, min_value=Decimal("0"), inclusive=False),
        prompt_on_new=True
    ),
    "refresh_time": ConfigVar(
        key="refresh_time",
        prompt="How often do you want to cancel and replace bids and asks (in seconds)? >>> ",
        type_str="int",
        default=30,
        validator=lambda v: validate_int(v, 0, inclusive=False),
        prompt_on_new=True
    )
}
