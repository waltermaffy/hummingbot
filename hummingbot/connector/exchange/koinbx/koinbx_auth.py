import hashlib
import hmac
import json

from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTRequest, WSRequest


class KoinbxAuth(AuthBase):
    def __init__(self, api_key: str, secret_key: str, time_provider: TimeSynchronizer):
        self.api_key = api_key
        self.secret_key = secret_key
        self.time_provider = time_provider

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        """
        Adds the authentication headers to the request, required for authenticated interactions.
        """
        if request.data is not None:
            payload = json.dumps(request.data)
        else:
            payload = ""

        signature = self._generate_signature(payload)

        headers = {
            "X-AUTH-APIKEY": self.api_key,
            "X-AUTH-SIGNATURE": signature,
        }

        if request.headers is not None:
            headers.update(request.headers)
        request.headers = headers

        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        """
        Koinbx doesn't require WebSocket authentication based on the docs.
        """
        return request  # pass-through

    def _generate_signature(self, payload: str) -> str:
        return hmac.new(self.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
