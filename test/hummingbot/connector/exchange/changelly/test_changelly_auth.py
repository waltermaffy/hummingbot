import asyncio
import hashlib
import hmac
from copy import copy
from unittest import TestCase
from unittest.mock import MagicMock

from typing_extensions import Awaitable
from hummingbot.connector.exchange.changelly.changelly_auth import ChangellyAuth
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest
from websocket import create_connection
import websocket
import json
from hashlib import sha256
from hmac import HMAC
from time import time


class ChangellyAuthAuthTests(TestCase):

    def setUp(self) -> None:
        self._api_key = "testApiKey"
        self._secret = "testSecret"

    def async_run_with_timeout(self, coroutine: Awaitable, timeout: float = 1):
        ret = asyncio.get_event_loop().run_until_complete(asyncio.wait_for(coroutine, timeout))
        return ret

    def test_ws_authenticate(self):
        now = 1234567890.000
        mock_time_provider = MagicMock()
        mock_time_provider.time.return_value = now

        auth = ChangellyAuth(api_key=self._api_key, secret_key=self._secret, time_provider=mock_time_provider)
        configured_request = self.async_run_with_timeout(auth.ws_authenticate())

        print(configured_request)
        self.assertEqual(self._api_key, configured_request["params"]["api_key"])
        # check method login
        self.assertEqual("login", configured_request["method"])
        # check timestamp
        self.assertEqual(now * 1e3, float(configured_request["params"]["timestamp"]))
        # check signature
        expected_signature = hmac.new(
            self._secret.encode("utf-8"),
            configured_request["params"]["timestamp"].encode("utf-8"),
            hashlib.sha256).hexdigest()
        self.assertEqual(expected_signature, configured_request["params"]["signature"])

    def test_ws_login(self):
        now = int(time() * 1000)
        mock_time_provider = MagicMock()
        mock_time_provider.time.return_value = now
