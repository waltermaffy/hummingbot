import hashlib
import hmac
import json
import math
import time
from typing import Any, Dict
from urllib.parse import urlencode

from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest, WSRequest


class CoinstoreAuth(AuthBase):
    def __init__(self, api_key: str, secret_key: str, time_provider: TimeSynchronizer):
        self.api_key = api_key.encode() if isinstance(api_key, str) else api_key
        self.secret_key = secret_key.encode() if isinstance(secret_key, str) else secret_key
        self.time_provider = time_provider

    def _get_signature(self, payload: str) -> tuple:
        expires = int(time.time() * 1000)
        expires_key = str(math.floor(expires / 30000))
        expires_key = expires_key.encode("utf-8")
        key = hmac.new(self.secret_key, expires_key, hashlib.sha256).hexdigest()
        key = key.encode("utf-8")
        payload_bytes = payload.encode("utf-8")
        signature = hmac.new(key, payload_bytes, hashlib.sha256).hexdigest()
        return signature, expires

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        payload = json.dumps(request.data or {})
        signature, expires = self._get_signature(payload)

        headers = {
            'X-CS-APIKEY': self.api_key.decode('utf-8'),
            'X-CS-SIGN': signature,
            'X-CS-EXPIRES': str(expires),
            'exch-language': 'en_US',
            'Content-Type': 'application/json',
            'Accept': '*/*',
            'Connection': 'keep-alive'
        }

        request.headers = headers
        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        """
        CoinStore doesn't require WebSocket authentication based on the docs.
        """
        return request  # pass-through
