import asyncio
from typing import TYPE_CHECKING, List, Optional

from hummingbot.connector.exchange.changelly import changelly_constants as CONSTANTS, changelly_web_utils as web_utils
from hummingbot.connector.exchange.changelly.changelly_auth import ChangellyAuth
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.core.web_assistant.connections.data_types import WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.changelly.changelly_exchange import ChangellyExchange


class ChangellyAPIUserStreamDataSource(UserStreamTrackerDataSource):
    LISTEN_KEY_KEEP_ALIVE_INTERVAL = 1800  # Recommended to Ping/Update listen key to keep connection alive
    HEARTBEAT_TIME_INTERVAL = 30.0
    SPOT_STREAM_ID = 21

    _logger: Optional[HummingbotLogger] = None

    def __init__(
        self,
        auth: ChangellyAuth,
        trading_pairs: List[str],
        connector: "ChangellyExchange",
        api_factory: WebAssistantsFactory,
    ):
        super().__init__()
        self._auth: ChangellyAuth = auth
        self._current_listen_key = None
        self._api_factory = api_factory
        self._connector = connector
        self._trading_pairs = trading_pairs
        self._listen_key_initialized_event: asyncio.Event = asyncio.Event()
        self._last_listen_key_ping_ts = 0

    async def _connected_websocket_assistant(self) -> WSAssistant:
        """
        Connects to the exchange's WebSocket service.
        """
        ws: WSAssistant = await self._get_ws_assistant()
        await ws.connect(ws_url=CONSTANTS.WSS_TRADING_URL, ping_timeout=CONSTANTS.WS_HEARTBEAT_TIME_INTERVAL)
        await self._authenticate_connection(ws)
        return ws
    
    async def _authenticate_connection(self, ws: WSAssistant):
        """
        Authenticates to the WebSocket service using the provided API key and secret.
        """
        auth_message: WSJSONRequest = WSJSONRequest(payload=self._auth.ws_authenticate())
        await ws.send(auth_message)
        # expected successful_auth_response = {   "jsonrpc": "2.0", "result": {"authenticated": True}, "id": 1}
        auth_response = await ws.receive()
        print(auth_response)
        

    async def _subscribe_channels(self, ws: WSAssistant):
        subscribe_payload = {"method": CONSTANTS.SPOT_SUBSCRIBE, "params": {}, "id": self.SPOT_STREAM_ID}
        payload: WSJSONRequest = WSJSONRequest(payload=subscribe_payload)
        await ws.send(payload)
        
        # check result message
        result_message = await ws.receive()
        print(result_message)
    
    async def _on_user_stream_interruption(self, websocket_assistant: Optional[WSAssistant]):
        """
        Handles reconnection on user stream interruption.
        """
        await super()._on_user_stream_interruption(websocket_assistant=websocket_assistant)
        await self._sleep(5)  # Wait for a few seconds before reconnecting

    async def _get_ws_assistant(self) -> WSAssistant:
        """
        Retrieves a websocket assistant.
        """
        if self._ws_assistant is None:
            self._ws_assistant = await self._api_factory.get_ws_assistant()
        return self._ws_assistant
