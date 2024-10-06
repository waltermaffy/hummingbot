import asyncio
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from hummingbot.connector.exchange.coinstore import coinstore_constants as CONSTANTS, coinstore_web_utils as web_utils
from hummingbot.connector.exchange.coinstore.coinstore_order_book import CoinstoreOrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.coinstore.coinstore_exchange import CoinstoreExchange


class CoinstoreAPIOrderBookDataSource(OrderBookTrackerDataSource):
    _logger: Optional[HummingbotLogger] = None

    def __init__(
        self,
        trading_pairs: List[str],
        connector: 'CoinstoreExchange',
        api_factory: WebAssistantsFactory,
        domain: str = CONSTANTS.DEFAULT_DOMAIN
    ):
        super().__init__(trading_pairs)
        self._connector = connector
        self._domain = domain
        self._api_factory = api_factory

    async def get_last_traded_prices(self, trading_pairs: List[str], domain: Optional[str] = None) -> Dict[str, float]:
        return await self._connector.get_last_traded_prices(trading_pairs=trading_pairs)

    async def _order_book_snapshot(self, trading_pair: str) -> OrderBookMessage:
        snapshot_response: Dict[str, Any] = await self._request_order_book_snapshot(trading_pair)
        snapshot_timestamp: float = time.time()
        snapshot_msg: OrderBookMessage = CoinstoreOrderBook.snapshot_message_from_exchange(
            snapshot_response,
            snapshot_timestamp,
            metadata={"trading_pair": trading_pair}
        )
        return snapshot_msg

    async def _request_order_book_snapshot(self, trading_pair: str) -> Dict[str, Any]:
        """
        Requests full order book snapshot for a specific trading pair.
        """
        symbol = await self._connector.exchange_symbol_associated_to_pair(trading_pair=trading_pair)

        params = {
            "symbol": symbol,
            "depth": "100"  # You may need to adjust this based on Coinstore's API
        }

        rest_assistant = await self._api_factory.get_rest_assistant()
        data = await rest_assistant.execute_request(
            url=web_utils.public_rest_url(path_url=CONSTANTS.SNAPSHOT_PATH_URL.format(symbol=symbol), domain=self._domain),
            params=params,
            method=RESTMethod.GET,
            throttler_limit_id=CONSTANTS.SNAPSHOT_PATH_URL,
        )

        return data

    async def _parse_trade_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        trading_pair = raw_message["symbol"]
        trade_message = CoinstoreOrderBook.trade_message_from_exchange(
            raw_message,
            {"trading_pair": trading_pair}
        )
        message_queue.put_nowait(trade_message)

    async def _parse_order_book_diff_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        trading_pair = raw_message["symbol"]
        order_book_message: OrderBookMessage = CoinstoreOrderBook.diff_message_from_exchange(
            raw_message,
            time.time(),
            {"trading_pair": trading_pair}
        )
        message_queue.put_nowait(order_book_message)

    async def _subscribe_channels(self, ws: WSAssistant):
        """
        Subscribes to the trade events and diff orders events through the provided websocket connection.
        """
        try:
            for trading_pair in self._trading_pairs:
                symbol = await self._connector.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
                payload = {
                    "op": "SUB",
                    "channel": [f"{symbol}@trade", f"{symbol}@depth"],
                    "id": 1
                }
                subscribe_request: WSJSONRequest = WSJSONRequest(payload=payload)

                await ws.send(subscribe_request)

            self.logger().info("Subscribed to public order book and trade channels...")
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().error(
                "Unexpected error occurred subscribing to order book trading and delta streams...",
                exc_info=True
            )
            raise

    def _channel_originating_message(self, event_message: Dict[str, Any]) -> str:
        channel = ""
        if "e" in event_message:
            event_type = event_message["e"]
            channel = (self._diff_messages_queue_key if event_type == CONSTANTS.DIFF_EVENT_TYPE
                       else self._trade_messages_queue_key)
        return channel

    async def _connected_websocket_assistant(self) -> WSAssistant:
        ws: WSAssistant = await self._api_factory.get_ws_assistant()
        await ws.connect(ws_url=CONSTANTS.WSS_URL, ping_timeout=CONSTANTS.WS_HEARTBEAT_TIME_INTERVAL)
        return ws