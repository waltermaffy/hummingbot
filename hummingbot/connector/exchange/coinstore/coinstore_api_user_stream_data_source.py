import asyncio
import time
from typing import TYPE_CHECKING, List, Optional

from hummingbot.connector.exchange.coinstore import coinstore_constants as CONSTANTS, coinstore_web_utils as web_utils
from hummingbot.connector.exchange.coinstore.coinstore_auth import CoinstoreAuth
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.coinstore.coinstore_exchange import CoinstoreExchange


class CoinstoreAPIUserStreamDataSource(UserStreamTrackerDataSource):

    _logger: Optional[HummingbotLogger] = None

    def __init__(self,
                 auth: CoinstoreAuth,
                 trading_pairs: List[str],
                 connector: 'CoinstoreExchange',
                 api_factory: WebAssistantsFactory,
                 domain: str = CONSTANTS.DEFAULT_DOMAIN):
        super().__init__()
        self._auth: CoinstoreAuth = auth
        self._trading_pairs = trading_pairs
        self._connector = connector
        self._domain = domain
        self._api_factory = api_factory
        self._current_listen_key = None
        self._listen_for_user_stream_task = None
        self._last_listen_key_ping_ts = 0

    @property
    def last_recv_time(self) -> float:
        return self._last_recv_time

    async def listen_for_user_stream(self, output: asyncio.Queue):
        while True:
            try:
                ws: WSAssistant = await self._connected_websocket_assistant()
                await self._subscribe_channels(ws)
                await self._process_websocket_messages(websocket_assistant=ws, queue=output)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().exception("Unexpected error while listening to user stream. Retrying after 5 seconds...")
                await asyncio.sleep(5)

    async def _connected_websocket_assistant(self) -> WSAssistant:
        ws: WSAssistant = await self._api_factory.get_ws_assistant()
        await ws.connect(ws_url=CONSTANTS.WSS_URL, ping_timeout=CONSTANTS.WS_HEARTBEAT_TIME_INTERVAL)
        return ws

    async def _subscribe_channels(self, websocket_assistant: WSAssistant):
        try:
            payload = {
                "op": "SUB",
                "channel": ["outboundAccountPosition"],
                "id": 1
            }
            await websocket_assistant.send(payload)

            self.logger().info("Subscribed to private account position and orders channels...")
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().exception("Unexpected error occurred subscribing to account position and orders channels...")
            raise

    async def _process_websocket_messages(self, websocket_assistant: WSAssistant, queue: asyncio.Queue):
        async for ws_response in websocket_assistant.iter_messages():
            data = ws_response.data
            event_type = data.get("e")
            if event_type == "outboundAccountPosition":
                await self._process_account_position_event(event_data=data, queue=queue)
            elif event_type == "executionReport":
                await self._process_order_event(event_data=data, queue=queue)

    async def _process_account_position_event(self, event_data: dict, queue: asyncio.Queue):
        pass

    async def _process_order_event(self, event_data: dict, queue: asyncio.Queue):
        pass

    async def _get_listen_key(self):
        pass

    async def _ping_listen_key(self) -> bool:
        pass

    async def _manage_listen_key_task_loop(self):
        pass

    def _is_user_stream_initialized(self):
        pass

    async def _get_ws_assistant(self) -> WSAssistant:
        pass

    async def _on_user_stream_interruption(self, websocket_assistant: Optional[WSAssistant]):
        pass