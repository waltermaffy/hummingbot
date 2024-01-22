import asyncio
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional

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
    ORDERBOOK_STREAM_ID = 2
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
        self.TRADE_KEY = CONSTANTS.TRADE_EVENT_TYPE
        self.ODERBOOK_KEY = CONSTANTS.ORDERBOOK_EVENT_TYPE

        self._domain = domain
        self._time_synchronizer = time_synchronizer
        self._throttler = throttler
        self._api_factory = api_factory or web_utils.build_api_factory(
            throttler=self._throttler,
            time_synchronizer=self._time_synchronizer,
        )
        self._message_queue: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self._last_ws_message_sent_timestamp = 0

    async def get_last_traded_prices(self, 
                                     trading_pairs: List[str], 
                                     domain: Optional[str] = None) -> Dict[str, float]:
        return await self._connector.get_last_traded_prices(trading_pairs=trading_pairs)

    async def _request_order_book_snapshot(self, trading_pair: str) -> Dict[str, Any] :
        """
        Retrieves a copy of the full order book from the exchange, for a particular trading pair.

        :param trading_pair: the trading pair for which the order book will be retrieved

        :return: the response from the exchange (JSON dictionary)
        """
        params = {"depth": "1000"}
        symbol = self._connector.exchange_symbol_associated_to_pair(trading_pair=trading_pair)  
        path = CONSTANTS.ORDER_BOOK_PATH + "/" + symbol
        rest_assistant = await self._api_factory.get_rest_assistant()
        data = await rest_assistant.execute_request(
            url=web_utils.public_rest_url(path),
            params=params,
            method=RESTMethod.GET,
            throttler_limit_id=CONSTANTS.ORDER_BOOK_PATH,
        )
        return data

    async def _order_book_snapshot(self, trading_pair: str) -> OrderBookMessage:
        snapshot: Dict[str, Any] = await self._request_order_book_snapshot(trading_pair)
        snapshot_timestamp: float = time.time()
        snapshot_msg: OrderBookMessage = ChangellyOrderBook.snapshot_message_from_exchange(
            snapshot,
            snapshot_timestamp,
            metadata={"trading_pair": trading_pair}
        )
        return snapshot_msg
    
    async def _parse_order_book_diff_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        trading_pair = self._connector.trading_pair_associated_to_exchange_symbol(symbol=raw_message["symbol"])
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
                    "id": self.ORDERBOOK_STREAM_ID,
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
    
    async def _connected_websocket_assistant(self) -> WSAssistant:
        ws: WSAssistant = await self._api_factory.get_ws_assistant()
        await ws.connect(ws_url=CONSTANTS.WSS_MARKET_URL.format(self._domain),
                            ping_timeout=CONSTANTS.WS_HEARTBEAT_TIME_INTERVAL)
        return ws

    async def _process_ws_messages(self, ws: WSAssistant):
        """
        Process incoming WebSocket messages.
        """
        async for ws_response in ws.iter_messages():
            data = ws_response.data
            self.logger().info(f"Data received: {data}")

            if "result" in data:
                # SUBSCRIPTION RESPONSE
                if data["id"] == self.TRADE_STREAM_ID:
                    self.logger().info("Successfully subscribed to trade events.")
                elif data["id"] == self.ORDERBOOK_STREAM_ID:
                    self.logger().info("Successfully subscribed to order book events.")
                else:
                    self.logger().warning(f"Unexpected response from exchange: {data}")
            elif "error" in data:
                self.logger().error(f"Error response from exchange: {data}")

            if "id" not in data:
                # NOTIFICATION
                self.logger().info(f"Notification received: {data}")
                channel = data.get("ch")
                if channel == CONSTANTS.TRADES_CHANNEL:
                    self._message_queue[self.TRADE_KEY].put_nowait(data)
                elif channel == CONSTANTS.ORDER_BOOK_CHANNEL:
                    self._message_queue[self.ODERBOOK_KEY].put_nowait(data)

                if CONSTANTS.SNAPSHOT_EVENT_TYPE in data:
                    self._message_queue[CONSTANTS.SNAPSHOT_EVENT_TYPE].put_nowait(data)

    async def listen_for_trades(self, ev_loop: asyncio.AbstractEventLoop, output: asyncio.Queue):
        while True:
            try:
                msg = await self._message_queue[self.TRADE_KEY].get()
                if "update" in msg:
                    trade_msg: OrderBookMessage = ChangellyOrderBook.trade_message_from_exchange(msg)
                    output.put_nowait(trade_msg)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().error(f"Error in listen_for_trades: {str(e)}", exc_info=True)
                await asyncio.sleep(5)

    async def listen_for_order_book_diffs(self, ev_loop: asyncio.AbstractEventLoop, output: asyncio.Queue):
        while True:
            try:
                msg = await self._message_queue[self.ODERBOOK_KEY].get()
                channel = msg.get("ch")
                if "update" in msg and channel == CONSTANTS.ORDER_BOOK_CHANNEL:
                    diff_msg: OrderBookMessage = ChangellyOrderBook.diff_message_from_exchange(msg)
                    output.put_nowait(diff_msg)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().error(f"Error in listen_for_order_book_diffs: {str(e)}", exc_info=True)
                await asyncio.sleep(5)

    async def listen_for_order_book_snapshots(self, ev_loop: asyncio.AbstractEventLoop, output: asyncio.Queue):
        while True:
            try:
                for trading_pair in self._trading_pairs:
                    snapshot: Dict[str, Any] = await self._request_order_book_snapshot(trading_pair)
                    snapshot_timestamp = time.time()
                    snapshot_msg: OrderBookMessage = ChangellyOrderBook.snapshot_message_from_exchange(
                        snapshot, snapshot_timestamp, metadata={"trading_pair": trading_pair}
                    )
                    output.put_nowait(snapshot_msg)
                await asyncio.sleep(60)  # Wait for 60 seconds before the next snapshot
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().error(f"Error in listen_for_order_book_snapshots: {str(e)}", exc_info=True)
                await asyncio.sleep(5)

    def _time(self):
        return time.time()
