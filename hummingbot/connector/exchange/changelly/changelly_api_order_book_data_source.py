import asyncio
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Tuple

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
    ):
        super().__init__(trading_pairs)
        self._connector = connector
        self._trade_messages_queue_key = CONSTANTS.TRADE_EVENT_TYPE
        self._diff_messages_queue_key = CONSTANTS.DIFF_EVENT_TYPE
        self._snapshot_messages_queue_key = CONSTANTS.SNAPSHOT_EVENT_TYPE
        self._domain = domain
        self._api_factory = api_factory

    async def get_last_traded_prices(self, trading_pairs: List[str], domain: Optional[str] = None) -> Dict[str, float]:
        return await self._connector.get_last_traded_prices(trading_pairs=trading_pairs)

    async def _request_order_book_snapshot(self, trading_pair: str) -> Dict[str, Any]:
        """
        Retrieves a copy of the full order book from the exchange, for a particular trading pair.

        :param trading_pair: the trading pair for which the order book will be retrieved

        :return: the response from the exchange (JSON dictionary)

        """
        params = {"depth": "1000"}
        symbol = await self._connector.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        path = CONSTANTS.ORDER_BOOK_PATH + "/" + symbol
        rest_assistant = await self._api_factory.get_rest_assistant()
        url = web_utils.public_rest_url(path)
        self.logger().debug(f"Requesting order book snapshot for {trading_pair} at {url}...")
        data = await rest_assistant.execute_request(
            url=url,
            method=RESTMethod.GET,
            throttler_limit_id=CONSTANTS.ORDER_BOOK_PATH,
        )
        return data

    async def _subscribe_channels(self, websocket_assistant: WSAssistant):
        """
        Subscribes to the trade events and diff orders events through the provided websocket connection.
        """
        # self.logger().info("Subscribing to public order book and trade channels...")
        # print trading pairs
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
                self.logger().info(f"Subscribing to public order book and trade channels of {trading_pair}...")
                await websocket_assistant.subscribe(subscribe_trade_request)
                await websocket_assistant.subscribe(subscribe_orderbook_request)

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
        await ws.connect(ws_url=CONSTANTS.WSS_MARKET_URL, ping_timeout=CONSTANTS.WS_HEARTBEAT_TIME_INTERVAL)
        return ws

    async def _order_book_snapshot(self, trading_pair: str) -> OrderBookMessage:
        snapshot: Dict[str, Any] = await self._request_order_book_snapshot(trading_pair)
        snapshot_timestamp = web_utils.convert_to_unix_timestamp(snapshot["timestamp"])
        snapshot_msg: OrderBookMessage = ChangellyOrderBook.snapshot_message_from_exchange(
            snapshot, snapshot_timestamp, metadata={"trading_pair": trading_pair}
        )
        return snapshot_msg

    async def _parse_trade_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        channel = raw_message.get("ch")
        if channel == CONSTANTS.TRADES_CHANNEL:
            data = {}
            if "update" in raw_message:
                data = raw_message.get("update", {})
            elif "snapshot" in raw_message:
                data = raw_message.get("snapshot", {})
            elif "result" in raw_message:
                # not a trade message return
                return
            else:
                self.logger().warning(f"Unexpected response from exchange: {raw_message}")

            symbol = list(data.keys())[0]
            trading_pair = await self._connector.trading_pair_associated_to_exchange_symbol(symbol=symbol)
            trade_message = ChangellyOrderBook.trade_message_from_exchange(raw_message, {"trading_pair": trading_pair})
            message_queue.put_nowait(trade_message)

    async def _parse_order_book_diff_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        try:
            channel = raw_message.get("ch")
            if channel == CONSTANTS.ORDER_BOOK_CHANNEL:
                data = {}
                if "update" in raw_message:
                    data = raw_message.get("update", {})
                elif "snapshot" in raw_message:
                    data = raw_message.get("snapshot", {})

                symbol = list(data.keys())[0]
                trading_pair = await self._connector.trading_pair_associated_to_exchange_symbol(symbol=symbol)
                order_book_message: OrderBookMessage = ChangellyOrderBook.diff_message_from_exchange(
                    raw_message, time.time(), {"trading_pair": trading_pair}
                )

                message_queue.put_nowait(order_book_message)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().exception("Unexpected error when processing public order book updates from exchange")

    def _channel_originating_message(self, event_message: Dict[str, Any]) -> str:
        channel = ""
        ws_channel = event_message.get("ch")
        if ws_channel == CONSTANTS.TRADES_CHANNEL:
            channel = self._trade_messages_queue_key
        elif ws_channel == CONSTANTS.ORDER_BOOK_CHANNEL:
            channel = self._diff_messages_queue_key
        return channel
