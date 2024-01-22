import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from hummingbot.connector.exchange.changelly.changelly_api_user_stream_data_source import (
    ChangellyAPIUserStreamDataSource,
)
from hummingbot.connector.exchange.changelly.changelly_auth import ChangellyAuth
from hummingbot.connector.test_support.network_mocking_assistant import NetworkMockingAssistant
from hummingbot.core.web_assistant.connections.data_types import WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory


class TestChangellyAPIUserStreamDataSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ev_loop = asyncio.get_event_loop()
        cls.api_key = "test_api_key"
        cls.secret_key = "test_secret_key"

    def setUp(self) -> None:
        super().setUp()
        self.log_records = []
        self.mocking_assistant = NetworkMockingAssistant()
        self.mock_time_provider = MagicMock()
        self.mock_time_provider.time.return_value = 1000
        self.auth = ChangellyAuth(
            api_key=self.api_key, secret_key=self.secret_key, time_provider=self.mock_time_provider
        )

        self.api_factory = MagicMock(WebAssistantsFactory)
        self.trading_pairs = ["BTC-USDT"]

        self.data_source = ChangellyAPIUserStreamDataSource(
            auth=self.auth,
            trading_pairs=self.trading_pairs,
            connector=MagicMock(),
            api_factory=self.api_factory,
        )
        self.data_source.logger().setLevel(1)
        self.data_source.logger().addHandler(self)

    def handle(self, record):
        self.log_records.append(record)

    def async_run_with_timeout(self, coroutine, timeout=5):
        return self.ev_loop.run_until_complete(asyncio.wait_for(coroutine, timeout))

    @patch("aiohttp.ClientSession.ws_connect", new_callable=AsyncMock)
    def test_listen_for_user_stream_authenticates(self, mock_ws_connect):
        mock_ws = self.mocking_assistant.create_websocket_mock()
        mock_ws_connect.return_value = mock_ws
        test_queue = asyncio.Queue()
        self.async_run_with_timeout(self.data_source.listen_for_user_stream(test_queue))
        sent_messages = self.mocking_assistant.json_messages_sent_through_websocket(mock_ws)

        # Replace with actual authentication message expected
        expected_payload = {
            "method": "login",
            "params": {"type": "BASIC", "api_key": self.api_key, "secret_key": self.secret_key},
        }
        self.assertEqual(WSJSONRequest(payload=expected_payload), sent_messages[0])

    @patch("aiohttp.ClientSession.ws_connect", new_callable=AsyncMock)
    def test_listen_for_user_stream_handles_connection_error(self, mock_ws_connect):
        mock_ws_connect.side_effect = Exception("TEST ERROR")
        msg_queue = asyncio.Queue()
        self.data_source._ws_assistant = self.mocking_assistant.create_websocket_mock()

        with self.assertRaises(Exception):
            self.ev_loop.run_until_complete(self.data_source.listen_for_user_stream(msg_queue))

    @patch("aiohttp.ClientSession.ws_connect", new_callable=AsyncMock)
    def test_listen_for_user_stream_queues_valid_messages(self, mock_ws_connect):
        mock_ws = self.mocking_assistant.create_websocket_mock()
        mock_ws_connect.return_value = mock_ws
        valid_message = {"type": "valid_message"}
        self.mocking_assistant.add_websocket_aiohttp_message(mock_ws, json.dumps(valid_message))
        msg_queue = asyncio.Queue()

        self.ev_loop.create_task(self.data_source.listen_for_user_stream(msg_queue))
        message = self.ev_loop.run_until_complete(msg_queue.get())
        print(message)
        self.assertEqual(json.loads(message), valid_message)

    @patch("aiohttp.ClientSession.ws_connect", new_callable=AsyncMock)
    def test_listen_for_user_stream_ignores_empty_messages(self, mock_ws_connect):
        mock_ws = self.mocking_assistant.create_websocket_mock()
        mock_ws_connect.return_value = mock_ws
        self.mocking_assistant.add_websocket_aiohttp_message(mock_ws, "")

        msg_queue = asyncio.Queue()

        self.ev_loop.create_task(self.data_source.listen_for_user_stream(msg_queue))
        try:
            self.ev_loop.run_until_complete(asyncio.wait_for(msg_queue.get_nowait(), timeout=0.5))
            self.fail("Empty message was queued")
        except asyncio.QueueEmpty:
            pass
