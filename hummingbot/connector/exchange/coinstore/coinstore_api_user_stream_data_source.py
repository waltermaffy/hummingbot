import asyncio
import time
from typing import TYPE_CHECKING, List, Optional, Any, Dict

from hummingbot.connector.exchange.coinstore import coinstore_constants as CONSTANTS, coinstore_web_utils as web_utils
from hummingbot.connector.exchange.coinstore.coinstore_auth import CoinstoreAuth
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger
from hummingbot.core.web_assistant.connections.data_types import WSJSONRequest
from hummingbot.connector.exchange.coinstore import coinstore_utils as utils

if TYPE_CHECKING:
    from hummingbot.connector.exchange.coinstore.coinstore_exchange import CoinstoreExchange


class CoinstoreAPIUserStreamDataSource(UserStreamTrackerDataSource):
    
    LISTEN_KEY_KEEP_ALIVE_INTERVAL = 1800  
    HEARTBEAT_TIME_INTERVAL = 30.0
    POLL_INTERVAL = 5.0
    ORDER_PAGE_LIMIT = 100

    _logger: Optional[HummingbotLogger] = None

    def __init__(self,
                 auth: CoinstoreAuth,
                 trading_pairs: List[str],
                 connector: 'CoinstoreExchange',
                 api_factory: WebAssistantsFactory,
                 domain: str = CONSTANTS.DEFAULT_DOMAIN):
        super().__init__()
        self._auth: CoinstoreAuth = auth
        self._current_listen_key = None
        self._domain = domain
        self._trading_pairs = trading_pairs
        self._connector = connector
        self._api_factory = api_factory
        self._listen_for_user_stream_task = None
        self._listen_key_initialized_event: asyncio.Event = asyncio.Event()
        self._last_listen_key_ping_ts = 0
        self._last_poll_timestamp = 0

        
    @property
    def last_recv_time(self) -> float:
        return self._last_poll_timestamp
    
    
    async def listen_for_user_stream(self, output: asyncio.Queue):
        """
        Polls the user stream endpoint and pushes the response to the output queue.
        """
        while True:
            try:
                await self._poll_user_stream(output)
                await asyncio.sleep(self.POLL_INTERVAL)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().exception("Unexpected error while polling user stream. Retrying after 5 seconds...")
                await asyncio.sleep(5.0)

    async def _poll_user_stream(self, output: asyncio.Queue):
        """
        Polls the user stream endpoint and pushes the response to the output queue.
        """
        current_timestamp = int(time.time() * 1000)
        if current_timestamp - self._last_poll_timestamp < self.POLL_INTERVAL * 1000:
            return

        try:
            open_orders = await self._get_open_orders()
            # Warn: an order could be both in open and completed orders
            completed_orders = await self._get_completed_orders()
            balance = await self._get_balance()

            user_stream_data = {
                "open_orders": open_orders,
                "completed_orders": completed_orders,
                "balance": balance,
                "timestamp": current_timestamp
            }

            output.put_nowait(user_stream_data)
            self._last_poll_timestamp = current_timestamp
        except Exception as e:
            self.logger().error(f"Error polling user stream: {str(e)}", exc_info=True)

    async def _get_open_orders(self) -> List[Dict[str, Any]]:
        """
        Fetches open orders from the exchange.
        """
        response = await self._connector._api_request(
            path_url=CONSTANTS.OPEN_ORDERS_PATH_URL,
            method=RESTMethod.GET,
            is_auth_required=True,
        )
        if not response or response.get("code") != 0:
            self.logger().error("Failed to fetch open orders. Retrying...")
            return []
        # self.logger().info(f"Open orders: {response}")
        return response.get("data", {}) or []

    async def _get_completed_orders(self) -> List[Dict[str, Any]]:
        """
        Fetches completed orders from the exchange.
        """
        completed_orders = []
        for trading_pair in self._trading_pairs:
            data = {
                "symbol": utils.convert_to_exchange_trading_pair(trading_pair),
                "pageSize": self.ORDER_PAGE_LIMIT
            }
            # self.logger().info(f"Making request to {CONSTANTS.COMPLETED_ORDERS_PATH_URL} with data {data}")
            response = await self._connector._api_request(
                path_url=CONSTANTS.COMPLETED_ORDERS_PATH_URL,
                method=RESTMethod.GET,
                params=data,
                is_auth_required=True,
            )
            # self.logger().info(f"Completed Response: {response}")
            if not response or response.get("code") != 0:
                self.logger().error(f"Failed to fetch completed orders for {trading_pair}. Retrying...")
                continue
            completed_orders.extend(response.get("data", {}) or [])
        return completed_orders

    async def _get_balance(self) -> List[Dict[str, Any]]:
        """
        Fetches account balance from the exchange.
        """
        data = {
            "timestamp": str(int(time.time()))
        }
        response = await self._connector._api_request(
            path_url=CONSTANTS.BALANCE_PATH_URL,
            method=RESTMethod.POST,
            data=data,
            is_auth_required=True,
        )
        # self.logger().info(f"Balance: {response}")
        if not response or response.get("code") != 0:
            self.logger().error("Failed to fetch balance. Retrying...")
            return []
        return response.get("data") or []

    async def _connected_websocket_assistant(self) -> None:
        """
        This method is not used in REST polling implementation.
        """
        pass

    async def _subscribe_channels(self, websocket_assistant: None):
        """
        This method is not used in REST polling implementation.
        """
        pass

