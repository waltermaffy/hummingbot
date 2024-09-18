import asyncio

# import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional

from hummingbot.connector.exchange.koinbx import (
    koinbx_constants as CONSTANTS,
    koinbx_utils as utils,
    koinbx_web_utils as web_utils,
)
from hummingbot.connector.exchange.koinbx.koinbx_order_book import KoinbxOrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant

# from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.koinbx.koinbx_exchange import KoinbxExchange


class KoinbxAPIOrderBookDataSource(OrderBookTrackerDataSource):
    MESSAGE_TIMEOUT = 30.0
    PING_TIMEOUT = 10.0
    POLLING_INTERVAL = 5.0

    _logger: Optional[HummingbotLogger] = None
    _trading_pair_symbol_map: Dict[str, Mapping[str, str]] = {}
    _mapping_initialization_lock = asyncio.Lock()

    def __init__(
        self,
        trading_pairs: List[str],
        connector: "KoinbxExchange",
        api_factory: WebAssistantsFactory,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        super().__init__(trading_pairs)
        self._connector = connector
        self._domain = domain
        self._api_factory = api_factory

    
    async def get_last_traded_prices(self, trading_pairs: List[str], domain: Optional[str] = None) -> Dict[str, float]:
        return await self._connector.get_last_traded_prices(trading_pairs=trading_pairs)

    async def _request_order_book_snapshot(self, trading_pair: str) -> Dict[str, Any]:
        exchange_symbol = await self._connector.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        params = {"market_pair": exchange_symbol}
        
        rest_assistant = await self._api_factory.get_rest_assistant()
        data = await rest_assistant.execute_request(
            url=web_utils.public_rest_url(path_url=CONSTANTS.ORDERBOOK_PATH_URL, domain=self._domain),
            params=params,
            method=RESTMethod.GET,
            throttler_limit_id=CONSTANTS.ORDERBOOK_PATH_URL,
        )
        return data
    
    async def _request_trades(self, trading_pair: str) -> Dict[str, Any]:
        exchange_symbol = await self._connector.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        params = {"market_pair": exchange_symbol}
        
        rest_assistant = await self._api_factory.get_rest_assistant()
        data = await rest_assistant.execute_request(
            url=web_utils.public_rest_url(path_url=CONSTANTS.TRADES_PATH_URL, domain=self._domain),
            params=params,
            method=RESTMethod.GET,
            throttler_limit_id=CONSTANTS.TRADES_PATH_URL,
        )
        return data
    

    async def _subscribe_channels(self, websocket_assistant: WSAssistant):
        """
        Since KoinBX does not support WebSockets, this method does nothing.
        """
        pass

    async def _connected_websocket_assistant(self) -> Optional[WSAssistant]:
        """
        Since KoinBX does not support WebSockets, return None.
        """
        return None

    async def _order_book_snapshot(self, trading_pair: str) -> OrderBookMessage:
        snapshot: Dict[str, Any] = await self._request_order_book_snapshot(trading_pair)
        snapshot_timestamp: float = time.time()
        # self.logger().info(f"snapshot: {snapshot}")
        snapshot_msg: OrderBookMessage = KoinbxOrderBook.snapshot_message_from_exchange(
            snapshot, snapshot_timestamp, metadata={"trading_pair": trading_pair}
        )
        return snapshot_msg

    async def listen_for_subscriptions(self):
        """
        Polls the order book data and trade API since KoinBX doesn't support WebSockets
        """
        while True:
            try:
                for trading_pair in self._trading_pairs:
                    await self._fetch_and_process_order_book(trading_pair)
                    await self._fetch_and_process_trades(trading_pair)
                self.logger().debug(f"Completed order book polling for {len(self._trading_pairs)} trading pairs")
                await asyncio.sleep(self.POLLING_INTERVAL)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().network(
                    "Unexpected error occurred fetching order book snapshot and trade updates.",
                    exc_info=True,
                    app_warning_msg="Failed to fetch order book data. Check network connection.",
                )
                await asyncio.sleep(5.0)

    async def _fetch_and_process_order_book(self, trading_pair: str):
        try:
            snapshot: Dict[str, Any] = await self._request_order_book_snapshot(trading_pair)
            snapshot_timestamp: float = time.time()
            snapshot_msg: OrderBookMessage = KoinbxOrderBook.snapshot_message_from_exchange(
                snapshot,
                snapshot_timestamp,
                metadata={"trading_pair": trading_pair}
            )
            output = self._message_queue[self._snapshot_messages_queue_key]
            await self._parse_order_book_snapshot_message(snapshot_msg, output)
        except Exception:
            self.logger().error(f"Failed to fetch and process order book for {trading_pair}", exc_info=True)

    async def _fetch_and_process_trades(self, trading_pair: str):
        try:
            trades: Dict[str, Any] = await self._request_trades(trading_pair)
            trade_messages = self._parse_trade_messages(trades, trading_pair)
            for trade_message in trade_messages:
                output = self._message_queue[self._trade_messages_queue_key]
                await self._parse_trade_message(trade_message, output)
            # if trade_messages:
            #     latest_trade = trade_messages[-1]
                # self._last_traded_prices[trading_pair] = float(latest_trade["price"])
        except Exception:
            self.logger().error(f"Failed to fetch and process trades for {trading_pair}", exc_info=True)


    def _parse_trade_messages(self, trades: Dict[str, Any], trading_pair: str) -> List[Dict[str, Any]]:
        trade_messages = []
        for trade in trades.get("data", []):
            trade_message = {
                "trade_id": trade.get("trade_id"),
                "price": trade.get("price"),
                "amount": trade.get("base_volume"),
                "timestamp": trade.get("timestamp"),
                "type": trade.get("type"),  # Handle missing 'type' appropriately
                "trading_pair": trading_pair,
            }
            trade_messages.append(trade_message)
        return trade_messages

    async def _parse_order_book_snapshot_message(self, raw_message: OrderBookMessage, message_queue: asyncio.Queue):
        # self.logger().info(f"snapshot raw_message: {raw_message}")
        message_queue.put_nowait(raw_message)


    async def _parse_trade_message(self, raw_message: Any, message_queue: asyncio.Queue):
        """
        Parses a trade message and adds it to the message queue.
        
        :param raw_message: The raw trade message, either a dict or OrderBookMessage
        :param message_queue: The queue to which the parsed message will be added
        """
        try:
            # Check if raw_message is an OrderBookMessage and extract its content
            if isinstance(raw_message, OrderBookMessage):
                msg = raw_message.content
                return
            else:
                msg = raw_message

            trade_message = KoinbxOrderBook.trade_message_from_exchange(msg)
            message_queue.put_nowait(trade_message)
        except Exception:
            self.logger().error("Failed to parse trade message.", exc_info=True)