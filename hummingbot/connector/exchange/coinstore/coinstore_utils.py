import re
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from pydantic import Field, SecretStr

from hummingbot.client.config.config_data_types import BaseConnectorConfigMap, ClientFieldData
from hummingbot.client.config.config_methods import using_exchange
from hummingbot.connector.exchange.coinstore.coinstore_constants import EXCHANGE_NAME
from hummingbot.core.data_type.trade_fee import TradeFeeSchema

CENTRALIZED = True
EXAMPLE_PAIR = "ZRX-ETH"

DEFAULT_FEES = TradeFeeSchema(
    maker_percent_fee_decimal=Decimal("0.001"),
    taker_percent_fee_decimal=Decimal("0.001"),
    buy_percent_fee_deducted_from_returns=True
)

def split_trading_pair(trading_pair: str) -> Optional[Tuple[str, str]]:
    try:
        # separate the base asset from the quote asset using - as a delimiter
        m = re.match(r"(\w+)-(\w+)", trading_pair)
        if m is None:
            return None
        base_asset, quote_asset = m.group(1), m.group(2)
        return base_asset, quote_asset
    except Exception:
        return None
    
def convert_from_exchange_to_trading_pair(exchange_pair_data: Dict[str, Any]) -> Optional[str]:
    if exchange_pair_data.get("tradeCurrencyCode") is None or exchange_pair_data.get("quoteCurrencyCode") is None:
        return None
    return f"{exchange_pair_data['tradeCurrencyCode'].upper()}-{exchange_pair_data['quoteCurrencyCode'].upper()}"


def convert_to_exchange_trading_pair(hb_trading_pair: str) -> str:
    return hb_trading_pair.replace("-", "")

def is_exchange_information_valid(exchange_info: dict) -> bool:
    """
    Verifies if a trading pair is enabled to operate with based on its exchange information
    :param exchange_info: the exchange information for a trading pair
    :return: True if the trading pair is enabled, False otherwise
    """
    return exchange_info.get("openTrade", False)


class CoinstoreConfigMap(BaseConnectorConfigMap):
    connector: str = Field(default="coinstore", const=True, client_data=None)
    coinstore_api_key: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: "Enter your Coinstore API key",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        )
    )
    coinstore_api_secret: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: "Enter your Coinstore API secret",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        )
    )

    class Config:
        title = "coinstore"


KEYS = CoinstoreConfigMap.construct()