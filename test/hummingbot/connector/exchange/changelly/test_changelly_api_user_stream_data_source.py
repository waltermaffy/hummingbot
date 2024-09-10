import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Awaitable, Dict, Optional

from hummingbot.connector.exchange.changelly.changelly_api_user_stream_data_source import (
    ChangellyAPIUserStreamDataSource,
)
from aioresponses import aioresponses
from hummingbot.connector.exchange.changelly import (  
    changelly_constants as CONSTANTS,
    changelly_utils,
    changelly_web_utils as web_utils,
)
from hummingbot.connector.exchange.changelly.changelly_auth import ChangellyAuth
from hummingbot.connector.test_support.network_mocking_assistant import NetworkMockingAssistant
from hummingbot.core.web_assistant.connections.data_types import WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.client.config.client_config_map import ClientConfigMap
from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.connector.exchange.changelly.changelly_exchange import ChangellyExchange
from bidict import bidict

class TestChangellyAPIUserStreamDataSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ev_loop = asyncio.get_event_loop()
        cls.api_key = "test_api_key"
        cls.secret_key = "test_secret_key"
        cls.base_asset = "BTC"
        cls.quote_asset = "USDT"
        cls.trading_pair = f"{cls.base_asset}-{cls.quote_asset}"
        cls.ex_trading_pair = cls.base_asset + cls.quote_asset
        cls.trading_pairs = [cls.trading_pair]
        cls.domain = "com"


    def setUp(self) -> None:
        super().setUp()
        self.log_records = []
        self.log_records = []
        self.listening_task: Optional[asyncio.Task] = None
        self.mocking_assistant = NetworkMockingAssistant()

        self.throttler = AsyncThrottler(rate_limits=CONSTANTS.RATE_LIMITS)
        self.mock_time_provider = MagicMock()   
        self.mock_time_provider.time.return_value = 1000
        self.auth = ChangellyAuth(api_key=self.api_key, secret_key=self.secret_key, time_provider=self.mock_time_provider)
        self.time_synchronizer = TimeSynchronizer()
        self.time_synchronizer.add_time_offset_ms_sample(0)

        client_config_map = ClientConfigAdapter(ClientConfigMap())
        self.connector = ChangellyExchange(
            client_config_map=client_config_map,
            changelly_api_key=self.api_key,
            changelly_api_secret=self.secret_key,
            trading_pairs=[],
            trading_required=False,
            domain=self.domain)
        self.connector._web_assistants_factory._auth = self.auth
        
        self.data_source = ChangellyAPIUserStreamDataSource(
            auth=self.auth,
            trading_pairs=self.trading_pairs,
            connector=self.connector,
            api_factory=self.connector._web_assistants_factory,
        )
        self.data_source.logger().setLevel(1)
        self.data_source.logger().addHandler(self)

        self.resume_test_event = asyncio.Event()

        self.connector._set_trading_pair_symbol_map(bidict({self.ex_trading_pair: self.trading_pair}))

    def tearDown(self) -> None:
        self.listening_task and self.listening_task.cancel()
        super().tearDown()

    def handle(self, record):
        self.log_records.append(record)
    
    def _is_logged(self, log_level: str, message: str) -> bool:
        return any(record.levelname == log_level and record.getMessage() == message
                   for record in self.log_records)

    def _raise_exception(self, exception_class):
        raise exception_class

    def _create_exception_and_unlock_test_with_event(self, exception):
        self.resume_test_event.set()
        raise exception

    def _create_return_value_and_unlock_test_with_event(self, value):
        self.resume_test_event.set()
        return value

    def async_run_with_timeout(self, coroutine: Awaitable, timeout: float = 1):
        ret = self.ev_loop.run_until_complete(asyncio.wait_for(coroutine, timeout))
        return ret

    @patch("aiohttp.ClientSession.ws_connect", new_callable=AsyncMock)
    def test_listen_for_user_stream_authenticates(self, mock_ws):
        mock_ws.return_value = self.mocking_assistant.create_websocket_mock()

        # Simulate a successful authentication response
        successful_auth_response = {
            "jsonrpc": "2.0",
            "result": {"authenticated": True},
            "id": 1
        }
        self.mocking_assistant.add_websocket_aiohttp_message(mock_ws.return_value, json.dumps(successful_auth_response))

        # Run the authentication method and capture the response
        self.async_run_with_timeout(self.data_source._authenticate_connection(mock_ws))

        # Retrieve sent messages to verify authentication request
        sent_messages = self.mocking_assistant.json_messages_sent_through_websocket(
            websocket_mock=mock_ws.return_value)
        print(sent_messages)
        # Verify that the authentication request was sent
        self.assertEqual(1, len(sent_messages))

    
    @aioresponses()
    @patch("aiohttp.ClientSession.ws_connect", new_callable=AsyncMock)
    def test_listen_for_user_stream_iter_message_throws_exception(self, mock_api, mock_ws):

        msg_queue: asyncio.Queue = asyncio.Queue()
        mock_ws.return_value = self.mocking_assistant.create_websocket_mock()
        mock_ws.return_value.receive.side_effect = (lambda *args, **kwargs:
                                                    self._create_exception_and_unlock_test_with_event(
                                                        Exception("TEST ERROR")))
        mock_ws.close.return_value = None

        self.listening_task = self.ev_loop.create_task(
            self.data_source.listen_for_user_stream(msg_queue)
        )

        self.async_run_with_timeout(self.resume_test_event.wait())

        self.assertTrue(
            self._is_logged(
                "ERROR",
                "Unexpected error while listening to user stream. Retrying after 5 seconds..."))
