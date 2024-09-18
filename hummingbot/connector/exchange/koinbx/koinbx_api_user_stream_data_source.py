import asyncio
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from hummingbot.connector.exchange.koinbx import (  # koinbx_utils as utils,; koinbx_web_utils as web_utils,
    koinbx_constants as CONSTANTS,
    koinbx_web_utils as web_utils,
)
from hummingbot.connector.exchange.koinbx.koinbx_auth import KoinbxAuth
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.koinbx.koinbx_exchange import KoinbxExchange


class KoinbxAPIUserStreamDataSource(UserStreamTrackerDataSource):
    LISTEN_KEY_KEEP_ALIVE_INTERVAL = 1800  # Recommended to Ping/Update listen key to keep connection alive
    HEARTBEAT_TIME_INTERVAL = 30.0
    POLL_INTERVAL = .5  
    web_utils = web_utils

    _logger: Optional[HummingbotLogger] = None

    def __init__(
        self,
        auth: KoinbxAuth,
        trading_pairs: List[str],
        connector: "KoinbxExchange",
        api_factory: WebAssistantsFactory,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        super().__init__()
        self._auth: KoinbxAuth = auth
        self._current_listen_key = None
        self._domain = domain
        self._api_factory = api_factory
        self._connector = connector
        self._trading_pairs = trading_pairs
        self._listen_key_initialized_event: asyncio.Event = asyncio.Event()
        self._last_listen_key_ping_ts = 0
        self._user_stream_data_source_initialized = False
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
            balance = await self._get_balance()

            user_stream_data = {
                "open_orders": open_orders,
                "balance": balance,
                "timestamp": current_timestamp
            }

            output.put_nowait(user_stream_data)
            self._last_poll_timestamp = current_timestamp
        except Exception as e:
            self.logger().error(f"Error polling user stream: {str(e)}", exc_info=True)

    async def _get_open_orders(self) -> List[Dict[str, Any]]:
        """
        Fetches open orders from the exchange by making two requests:
        one for buy orders and one for sell orders.
        """
        rest_assistant = await self._api_factory.get_rest_assistant()
        url = web_utils.private_rest_url(CONSTANTS.OPEN_ORDERS_PATH_URL)

        # Define the request data for buy and sell orders
        data_buy = {
            "pageNumber": 1,
            "pageLimit": 100,  # Adjust as needed
            "type": "buy",
            "timestamp": str(int(time.time()))
        }

        data_sell = {
            "pageNumber": 1,
            "pageLimit": 100,  # Adjust as needed
            "type": "sell",
            "timestamp": str(int(time.time()))
        }

        async def fetch_orders(data):
            response = await rest_assistant.execute_request(
                url=url,
                data=data,
                method=RESTMethod.POST,
                is_auth_required=True,
                throttler_limit_id=CONSTANTS.OPEN_ORDERS_PATH_URL
            )
            return response["data"]["data"]

        # Fetch buy and sell orders concurrently
        orders_buy, orders_sell = await asyncio.gather(
            fetch_orders(data_buy),
            fetch_orders(data_sell)
        )

        # Combine the orders into a single list
        open_orders = orders_buy + orders_sell

        return open_orders

    async def _get_balance(self) -> List[Dict[str, Any]]:
        """
        Fetches account balance from the exchange.
        """
        rest_assistant = await self._api_factory.get_rest_assistant()
        url = web_utils.private_rest_url(CONSTANTS.BALANCE_PATH_URL)
        data = {
            "timestamp": str(int(time.time()))
        }
        response = await rest_assistant.execute_request(
            url=url,
            data=data,
            method=RESTMethod.POST,
            is_auth_required=True,
            throttler_limit_id=CONSTANTS.BALANCE_PATH_URL
        )
        return response["data"]

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