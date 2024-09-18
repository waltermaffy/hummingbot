import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from pydantic import Field, SecretStr

from hummingbot.client.config.config_data_types import BaseConnectorConfigMap, ClientFieldData
from hummingbot.core.data_type.trade_fee import TradeFeeSchema
from hummingbot.core.utils.tracking_nonce import get_tracking_nonce

CENTRALIZED = True

EXAMPLE_PAIR = "BTC-USDT"

DEFAULT_FEES = TradeFeeSchema(
    maker_percent_fee_decimal=Decimal("0.25"),
    taker_percent_fee_decimal=Decimal("0.25"),
    buy_percent_fee_deducted_from_returns=True,
)


def convert_from_exchange_trading_pair(exchange_trading_pair: str) -> Optional[str]:
    # Koinbx uses "_" as separator in trading pairs, substitute with "-"
    return exchange_trading_pair.replace("_", "-")


def convert_to_exchange_trading_pair(hb_trading_pair: str) -> str:
    # Koinbx uses "_" as separator in trading pairs
    return hb_trading_pair.replace("-", "_")


def get_new_client_order_id(is_buy: bool, trading_pair: str) -> str:
    side = "B" if is_buy else "S"
    return f"{side}-{trading_pair}-{get_tracking_nonce()}"


def is_exchange_information_valid(trading_pair: Dict[str, Any]) -> bool:
    """
    Verifies if a trading pair is enabled to operate with based on its exchange information
    :param exchange_info: the exchange information for a trading pair
    :return: True if the trading pair is enabled, False otherwise
    """
    return trading_pair.get("isFrozen", 0) == 0

def convert_iso_date_to_timestamp(iso_date: str) -> float:
    return datetime.datetime.strptime(iso_date, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()


class KoinbxConfigMap(BaseConnectorConfigMap):
    connector: str = Field(default="koinbx", const=True, client_data=None)
    koinbx_api_key: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: "Enter your Koinbx API key",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        ),
    )
    koinbx_api_secret: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: "Enter your Koinbx API secret",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        ),
    )

    class Config:
        title = "koinbx"


KEYS = KoinbxConfigMap.construct()
