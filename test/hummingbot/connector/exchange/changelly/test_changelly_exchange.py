from unittest.mock import AsyncMock, patch
from aioresponses import aioresponses
import asyncio
from decimal import Decimal

import asyncio
import json
import re
from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, patch

from aioresponses import aioresponses
from aioresponses.core import RequestCall

from hummingbot.client.config.client_config_map import ClientConfigMap
from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.connector.exchange.changelly.changelly_exchange import ChangellyExchange
from hummingbot.connector.exchange.changelly import changelly_constants as CONSTANTS, changelly_web_utils as web_utils

from hummingbot.connector.test_support.exchange_connector_test import AbstractExchangeConnectorTests
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import get_new_client_order_id
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderState
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.trade_fee import DeductedFromReturnsTradeFee, TokenAmount, TradeFeeBase
from hummingbot.core.event.events import MarketOrderFailureEvent, OrderFilledEvent



class ChangellyExchangeTests(AbstractExchangeConnectorTests.ExchangeConnectorTests):
    # Define properties and methods required for setup and utility functions

    @property
    def trading_pairs_url(self):
        # Return the URL for fetching trading pairs
        return web_utils.public_rest_url(path=CONSTANTS.TRADING_PAIRS_PATH_URL)

    @property
    def network_status_request_successful_mock_response(self):
        return {}
    

    @property
    def expected_latest_price(self):
        return 9999.9

    @property
    def expected_supported_order_types(self):
        return [OrderType.LIMIT, OrderType.LIMIT_MAKER, OrderType.MARKET]

    @property
    def is_order_fill_http_update_included_in_status_update(self) -> bool:
        return True

    @property
    def is_order_fill_http_update_executed_during_websocket_order_event_processing(self) -> bool:
        return False

    @property
    def expected_partial_fill_price(self) -> Decimal:
        return Decimal(10500)

    @property
    def expected_partial_fill_amount(self) -> Decimal:
        return Decimal("0.5")

    @property
    def expected_fill_fee(self) -> TradeFeeBase:
        return DeductedFromReturnsTradeFee(
            percent_token=self.quote_asset,
            flat_fees=[TokenAmount(token=self.quote_asset, amount=Decimal("30"))])

    @property
    def expected_fill_trade_id(self) -> str:
        return str(30000)

    def exchange_symbol_for_tokens(self, base_token: str, quote_token: str) -> str:
        return f"{base_token}{quote_token}"

    def create_exchange_instance(self):
        client_config_map = ClientConfigAdapter(ClientConfigMap())
        return ChangellyExchange(
            client_config_map=client_config_map,
            changelly_api_key="testAPIKey",
            changelly_api_secret="testSecret",
            trading_pairs=[self.trading_pair],
        )
    

    # Test cases

    def test_initialization(self):
        exchange = self.create_exchange_instance()
        self.assertIsInstance(exchange, ChangellyExchange)
        self.assertEqual(exchange.api_key, "testAPIKey")
        self.assertEqual(exchange.secret_key, "testSecret")

    @aioresponses()
    def test_fetch_trading_pairs(self, mock_api):
        url = self.trading_pairs_url
        mock_api.get(url, body=json.dumps({"result": ["BTC-ETH", "ETH-BTC"]}))
        
        exchange = self.create_exchange_instance()
        result = self.async_run_with_timeout(exchange.get_trading_pairs())

        self.assertIn("BTC-ETH", result)
        self.assertIn("ETH-BTC", result)

    @aioresponses()
    def test_fetch_balance(self, mock_api):
        url = self.balance_url
        mock_api.get(url, body=json.dumps({"result": {"BTC": {"free": 1.0, "locked": 0.1}}}))
        
        exchange = self.create_exchange_instance()
        result = self.async_run_with_timeout(exchange.get_balance("BTC"))

        self.assertEqual(result, Decimal("1.0"))

    # ... other test cases for different functionalities

    # Utility methods for setting up mock responses and other repetitive tasks
