import unittest
from unittest.mock import MagicMock
from hummingbot.connector.exchange.changelly.changelly_auth import ChangellyAuth
from hummingbot.connector.exchange.changelly.changelly_api_user_stream_data_source import ChangellyAPIUserStreamDataSource

class TestChangellyAPIUserStreamDataSource(unittest.TestCase):
    def setUp(self):
        self.auth = MagicMock(spec=ChangellyAuth)
        self.trading_pairs = ["BTC-USDT"]
        self.connector = MagicMock()
        self.api_factory = MagicMock()
        self.data_source = ChangellyAPIUserStreamDataSource(
            auth=self.auth,
            trading_pairs=self.trading_pairs,
            connector=self.connector,
            api_factory=self.api_factory
        )

    def test_initialization(self):
        self.assertEqual(self.data_source._auth, self.auth)
        self.assertEqual(self.data_source._trading_pairs, self.trading_pairs)

    @unittest.mock.patch("hummingbot.connector.exchange.changelly.changelly_api_user_stream_data_source.WSAssistant")
    async def test_connection_established(self, mock_ws_assistant):
        ws = mock_ws_assistant.return_value
        ws.connect = MagicMock()

        await self.data_source._connected_websocket_assistant()

        ws.connect.assert_called_once()
