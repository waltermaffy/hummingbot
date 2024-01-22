from decimal import Decimal
from typing import Any, Dict

from pydantic import Field, SecretStr

from hummingbot.client.config.config_data_types import BaseConnectorConfigMap, ClientFieldData
from hummingbot.core.data_type.trade_fee import TradeFeeSchema

CENTRALIZED = True
EXAMPLE_PAIR = "BTC-USDT"

DEFAULT_FEES = TradeFeeSchema(
    maker_percent_fee_decimal=Decimal("0.001"),
    taker_percent_fee_decimal=Decimal("0.001"),
    buy_percent_fee_deducted_from_returns=True,
)


def is_exchange_information_valid(exchange_info: Dict[str, Any]) -> bool:
    """
    Verifies if a trading pair is enabled to operate with based on its exchange information
    :param exchange_info: the exchange information for a trading pair
    :return: True if the trading pair is enabled, False otherwise
    """
    return exchange_info.get("status", None) == "working" and exchange_info.get("type", None) == "spot"


class ChangellyConfigMap(BaseConnectorConfigMap):
    connector: str = Field(default="changelly", const=True, client_data=None)
    changelly_api_key: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: "Enter your Changelly API key",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        ),
    )
    changelly_api_secret: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: "Enter your Changelly API secret",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        ),
    )

    class Config:
        title = "changelly"


KEYS = ChangellyConfigMap.construct()

OTHER_DOMAINS = ["changelly"]
OTHER_DOMAINS_PARAMETER = {"changelly": "us"}
OTHER_DOMAINS_EXAMPLE_PAIR = {"changelly": "BTC-USDT"}
OTHER_DOMAINS_DEFAULT_FEES = {"changelly": DEFAULT_FEES}
OTHER_DOMAINS_KEYS = {"changelly": ChangellyConfigMap.construct()}
