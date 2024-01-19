import hashlib
import hmac
import json
from base64 import b64encode
from collections import OrderedDict
from typing import Any, Dict, List
from urllib.parse import urlencode, urlsplit

from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest, WSRequest


class ChangellyAuth(AuthBase):
    def __init__(self, api_key: str, secret_key: str, time_provider: TimeSynchronizer):
        self.api_key = api_key
        self.secret_key = secret_key
        self.time_provider = time_provider

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        """
        Adds the server time and the signature to the request, required for authenticated interactions. It also adds
        the required parameter in the request header.
        :param request: the request to be configured for authenticated interaction
        """
        headers = {}
        if request.headers is not None:
            headers.update(request.headers)
        headers.update(self.header_for_authentication(request))
        request.headers = headers
        return request

    async def ws_authenticate(self) -> str:
        """
        This method return the event that needs to be sent to the exchange to authenticate the user.
        """
        timestamp = str(int(self.time_provider.time() * 1e3))

        sign = hmac.new(self.secret_key.encode("utf8"), timestamp.encode("utf8"), hashlib.sha256).hexdigest()

        return json.dumps(
            {
                "method": "login",
                "params": {"type": "HS256", "api_key": self.api_key, "timestamp": timestamp, "signature": sign},
            }
        )

    def header_for_authentication(self, request: RESTRequest) -> Dict[str, str]:
        # add HS256 authentication as here https://api.pro.changelly.com/#hs256
        url = urlsplit(request.url)
        message = [request.method, url.path]
        if url.query:
            message.append("?")
            message.append(url.query)
        if request.data:
            message.append(request.data)

        timestamp = str(int(self.time_provider.time() * 1e3))
        message.append(timestamp)

        signature = self._generate_signature(message)
        data = [self.api_key, signature, timestamp]
        base64_encoded = b64encode(":".join(data).encode("utf8")).decode("utf8")
        return {"Authorization": f"HS256 {base64_encoded}"}

    def _generate_signature(self, message: List[str]) -> str:
        digest = hmac.new(self.secret_key.encode("utf8"), "".join(message).encode("utf8"), hashlib.sha256).hexdigest()
        return digest
