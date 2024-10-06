import hashlib
import hmac
import json
import math
import time
from typing import Any, Dict
from urllib.parse import urlencode

from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest, WSRequest

class CoinstoreAuth(AuthBase):
    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key.encode('utf-8')
        self.secret_key = secret_key.encode('utf-8')

    def _get_signature(self, payload: str) -> tuple:
        expires = int(time.time() * 1000)
        expires_key = str(math.floor(expires / 30000)).encode("utf-8")
        key = hmac.new(self.secret_key, expires_key, hashlib.sha256).hexdigest().encode("utf-8")
        signature = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return signature, expires

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        """
        Adds the server time and the signature to the request, required for authenticated interactions.
        """
        if request.method == RESTMethod.GET:
            payload = urlencode(request.params or {})
        else:
            payload = json.dumps(request.data or {})

        signature, expires = self._get_signature(payload)

        headers = {
            "X-CS-APIKEY": self.api_key,
            "X-CS-SIGN": signature,
            "X-CS-EXPIRES": str(expires),
            "Content-Type": "application/json",
            "exch-language": "en_US",
            "Accept": "*/*",
            "Connection": "keep-alive"
        }

        request.headers = {**request.headers, **headers}
        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        """
        CoinStore doesn't require WebSocket authentication based on the docs.
        """
        return request  # pass-through