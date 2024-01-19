import asyncio
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional
import datetime
import hummingbot.connector.exchange.changelly.changelly_constants as CONSTANTS
from hummingbot.connector.exchange.changelly import changelly_web_utils as web_utils
from hummingbot.connector.exchange.changelly.changelly_order_book import ChangellyOrderBook
from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.data_type.order_book_message import OrderBookMessage
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.changelly.changelly_exchange import ChangellyExchange


class ChangellyAPIOrderBookDataSource(OrderBookTrackerDataSource):
    HEARTBEAT_TIME_INTERVAL = 30.0
    TRADE_STREAM_ID = 1
    DIFF_STREAM_ID = 2
    ONE_HOUR = 60 * 60

    _logger: Optional[HummingbotLogger] = None
    _trading_pair_symbol_map: Dict[str, Mapping[str, str]] = {}
    _mapping_initialization_lock = asyncio.Lock()

    def __init__(
        self,
        trading_pairs: List[str],
        connector: "ChangellyExchange",
        api_factory: Optional[WebAssistantsFactory] = None,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
        throttler: Optional[AsyncThrottler] = None,
        time_synchronizer: Optional[TimeSynchronizer] = None,
    ):
        super().__init__(trading_pairs)
        self._connector = connector
        self._diff_messages_queue_key = CONSTANTS.DIFF_EVENT_TYPE
        self._domain = domain
        self._time_synchronizer = time_synchronizer
        self._throttler = throttler
        self._api_factory = api_factory or web_utils.build_api_factory(
            throttler=self._throttler,
            time_synchronizer=self._time_synchronizer,
        )
        self._message_queue: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self._last_ws_message_sent_timestamp = 0

    async def get_last_traded_prices(self, trading_pairs: List[str], domain: Optional[str] = None) -> Dict[str, float]:
        return await self._connector.get_last_traded_prices(trading_pairs=trading_pairs)

    async def _request_order_book_snapshot(self, trading_pair: str) -> Dict[str, Any]:
        """
        Retrieves a copy of the full order book from the exchange, for a particular trading pair.

        :param trading_pair: the trading pair for which the order book will be retrieved

        :return: the response from the exchange (JSON dictionary)
        """
        params = {"depth": "1000"}
        path_url = CONSTANTS.REST_URL + CONSTANTS.ORDER_BOOK + "/" + trading_pair
        data = await self._connector._api_request(path_url=path_url, method=RESTMethod.GET, params=params)
        return data

    async def _parse_order_book_diff_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        trading_pair = await self._connector.trading_pair_associated_to_exchange_symbol(symbol=raw_message["symbol"])
        for diff_message in raw_message["data"]:
            order_book_message: OrderBookMessage = ChangellyOrderBook.diff_message_from_exchange(
                diff_message, diff_message["t"], {"trading_pair": trading_pair}
            )
            message_queue.put_nowait(order_book_message)

    async def listen_for_subscriptions(self):
        """
        Connects to the trade events and order diffs websocket endpoints and listens to the messages sent by the
        exchange. Each message is stored in its own queue.
        """
        ws = None
        while True:
            try:
                ws: WSAssistant = await self._api_factory.get_ws_assistant()
                await ws.connect(ws_url=CONSTANTS.WSS_MARKET_URL)
                await self._subscribe_channels(ws)
                self._last_ws_message_sent_timestamp = self._time()

                while True:
                    try:
                        seconds_until_next_ping = CONSTANTS.WS_HEARTBEAT_TIME_INTERVAL - (
                            self._time() - self._last_ws_message_sent_timestamp
                        )
                        await asyncio.wait_for(self._process_ws_messages(ws=ws), timeout=seconds_until_next_ping)
                    except asyncio.TimeoutError:
                        ping_time = self._time()
                        # payload = {
                        #     "ping": int(ping_time * 1e3)
                        # }
                        # ping_request = WSJSONRequest(payload=payload)
                        # await ws.send(request=ping_request)
                        self._last_ws_message_sent_timestamp = ping_time
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error(
                    "Unexpected error occurred when listening to order book streams. Retrying in 5 seconds...",
                    exc_info=True,
                )
                await self._sleep(5.0)
            finally:
                ws and await ws.disconnect()

    async def _subscribe_channels(self, ws: WSAssistant):
        """
        Subscribes to the trade events and diff orders events through the provided websocket connection.
        """
        try:
            for trading_pair in self._trading_pairs:
                symbol = await self._connector.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
                trade_payload = {
                    "method": "subscribe",
                    "ch": CONSTANTS.TRADES_CHANNEL,
                    "params": {"symbols": [symbol], "limit": 0},  # Optional (0 -> no history returned)
                    "id": self.TRADE_STREAM_ID,
                }
                subscribe_trade_request: WSJSONRequest = WSJSONRequest(payload=trade_payload)

                depth_payload = {
                    "method": "subscribe",
                    "ch": CONSTANTS.ORDER_BOOK_CHANNEL,
                    "params": {"symbols": [symbol]},
                    "id": self.DIFF_STREAM_ID,
                }
                subscribe_orderbook_request: WSJSONRequest = WSJSONRequest(payload=depth_payload)

                await ws.send(subscribe_trade_request)
                await ws.send(subscribe_orderbook_request)

                self.logger().info(f"Subscribed to public order book and trade channels of {trading_pair}...")
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().error(
                "Unexpected error occurred subscribing to order book trading and delta streams...", exc_info=True
            )
            raise

    async def _process_ws_messages(self, ws: WSAssistant):
        """
        Process incoming WebSocket messages.
        """
        async for ws_response in ws.iter_messages():
            data = ws_response.data
            if not "id" in data:
                # NOTIFICATION
                channel = data.get("ch")
                # if channel == CONSTANTS.TRADES_CHANNEL:
                #     pass
                # elif channel == CONSTANTS.ORDER_BOOK_CHANNEL:
                #     pass
                # elif channel == CONSTANTS.ORDER_BOOK_CHANNEL:
                #     pass
                # else:
                #     self.logger().warning(f"Unexpected response from exchange: {data}")
                if CONSTANTS.DIFF_EVENT_TYPE in data:
                    self._message_queue[CONSTANTS.DIFF_EVENT_TYPE].put_nowait(data)
                elif CONSTANTS.SNAPSHOT_EVENT_TYPE in data:
                    self._message_queue[CONSTANTS.SNAPSHOT_EVENT_TYPE].put_nowait(data)

            if "result" in data:
                if data["id"] == self.TRADE_STREAM_ID:
                    self.logger().info("Successfully subscribed to trade events.")
                elif data["id"] == self.DIFF_STREAM_ID:
                    self.logger().info("Successfully subscribed to order book events.")
                else:
                    self.logger().warning(f"Unexpected response from exchange: {data}")
            elif "error" in data:
                self.logger().error(f"Error response from exchange: {data}")

    # async def _process_ob_snapshot(self, snapshot_queue: asyncio.Queue):
    #     message_queue = self._message_queue[CONSTANTS.SNAPSHOT_EVENT_TYPE]
    #     while True:
    #         try:
    #             json_msg = await message_queue.get()
    #             trading_pair = await self._connector.trading_pair_associated_to_exchange_symbol(
    #                 symbol=json_msg["symbol"])
    #             order_book_message: OrderBookMessage = ChangellyOrderBook.snapshot_message_from_exchange_websocket(
    #                 json_msg["data"][0], json_msg["data"][0], {"trading_pair": trading_pair})
    #             snapshot_queue.put_nowait(order_book_message)
    #         except asyncio.CancelledError:
    #             raise
    #         except Exception:
    #             self.logger().error("Unexpected error when processing public order book updates from exchange")
    #             raise

    # async def _take_full_order_book_snapshot(self, trading_pairs: List[str], snapshot_queue: asyncio.Queue):
    #     for trading_pair in trading_pairs:
    #         try:
    #             snapshot: Dict[str, Any] = await self._request_order_book_snapshot(trading_pair=trading_pair)
    #             snapshot_timestamp: float = float(datetime.datetime.strptime(snapshot["timestamp"], "%Y-%m-%dT%H:%M:%S.%fZ").timestamp())
    #             snapshot_msg: OrderBookMessage = ChangellyOrderBook.snapshot_message_from_exchange_rest(
    #                 snapshot,
    #                 snapshot_timestamp,
    #                 metadata={"trading_pair": trading_pair}
    #             )
    #             snapshot_queue.put_nowait(snapshot_msg)
    #             self.logger().debug(f"Saved order book snapshot for {trading_pair}")
    #         except asyncio.CancelledError:
    #             raise
    #         except Exception:
    #             self.logger().error(f"Unexpected error fetching order book snapshot for {trading_pair}.",
    #                                 exc_info=True)
    #             await self._sleep(5.0)

    def _time(self):
        return time.time()
