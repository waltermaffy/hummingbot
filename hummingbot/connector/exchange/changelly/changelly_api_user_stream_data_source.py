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
        self._user_stream_data_source_initialized = False
        self.retry_left = CONSTANTS.MAX_RETRIES


    @property
    def last_recv_time(self) -> float:
        if self._ws_assistant:
            return self._ws_assistant.last_recv_time
        return 0
    
    async def _connected_websocket_assistant(self) -> WSAssistant:
        ws = None
        
        try:
            ws: WSAssistant = await self._get_ws_assistant()
            await ws.connect(ws_url=CONSTANTS.WSS_TRADING_URL, ping_timeout=CONSTANTS.WS_HEARTBEAT_TIME_INTERVAL)
            auth_result = await self._authenticate_connection(ws)
            self._last_ws_message_sent_timestamp = self._time()
            self.logger().info(f"User stream Authenticated to websocket: {auth_result}")
            self.retry_left = CONSTANTS.MAX_RETRIES
        except Exception as e:
            self.logger().error(f"Error connecting to websocket: {str(e)}", exc_info=True)
            # Retry connection
            if self.retry_left > 0:
                self.retry_left -= 1
                self.logger().info(f"Retrying connection to websocket in {CONSTANTS.RETRY_INTERVAL} seconds...")
                self.logger().info(f"Retries left: {self.retry_left}")
                await asyncio.sleep(CONSTANTS.RETRY_INTERVAL)
                await self._connected_websocket_assistant()
            else:
                raise Exception("Maximum retries exceeded. Could not connect to websocket.")
        return ws

    async def _authenticate_connection(self, ws: WSAssistant):
        """
        Authenticates to the WebSocket service using the provided API key and secret.
        """
        auth_message: WSJSONRequest = WSJSONRequest(payload=self._auth.ws_authenticate())
        await ws.send(auth_message)
        ws_response = await ws.receive()
        auth_response = ws_response.data
        if not auth_response.get("result"):
            raise Exception(f"Authentication failed. Error: {auth_response}")
        return True

    async def _subscribe_channels(self, websocket_assistant: WSAssistant):
        # Subscribe to spot channel
        try:
            subscribe_payload = {"method": CONSTANTS.SPOT_SUBSCRIBE, "params": {}, "id": self.SPOT_STREAM_ID}
            payload: WSJSONRequest = WSJSONRequest(payload=subscribe_payload)
            await websocket_assistant.subscribe(payload)
            # sub_result = await websocket_assistant.receive()
            # Subscribe to spot balances
            balance_payload = {"method": CONSTANTS.SPOT_BALANCE_SUBSCRIBE, "params": {"mode": "updates"}, "id": 3}
            await websocket_assistant.subscribe(WSJSONRequest(payload=balance_payload))
            self.logger().info("Successfully subscribed to spot balances")
            self._user_stream_data_source_initialized = True
        except Exception as e:
            self.logger().error(f"Error subscribing to websocket channels: {str(e)}", exc_info=True)
            raise e
        
        
    async def listen_for_user_stream(self, output: asyncio.Queue):
        """
        Connects to the user private channel in the exchange using a websocket connection. With the established
        connection listens to all balance events and order updates provided by the exchange, and stores them in the
        output queue

        :param output: the queue to use to store the received messages
        """
        while True:
            try:
                self._ws_assistant = await self._connected_websocket_assistant()
                await self._subscribe_channels(websocket_assistant=self._ws_assistant)
                await self._send_ping(websocket_assistant=self._ws_assistant)  # to update last_recv_timestamp
                await self._process_websocket_messages(websocket_assistant=self._ws_assistant, queue=output)
            except asyncio.CancelledError:
                raise
            except ConnectionError as connection_exception:
                self.logger().warning(f"The websocket connection was closed ({connection_exception})")
            except Exception:
                self.logger().exception("Unexpected error while listening to user stream. Retrying after 5 seconds...")
                await self._sleep(1.0)
            finally:
                await self._on_user_stream_interruption(websocket_assistant=self._ws_assistant)
                

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
            self._user_stream_data_source_initialized = True
        return self._ws_assistant
