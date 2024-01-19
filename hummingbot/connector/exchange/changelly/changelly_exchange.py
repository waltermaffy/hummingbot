import json
import time
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional, Tuple

from hummingbot.connector.exchange.changelly import (  # changelly_utils,
    changelly_constants as CONSTANTS,
    changelly_web_utils as web_utils,
)
from hummingbot.connector.exchange.changelly.changelly_api_order_book_data_source import ChangellyAPIOrderBookDataSource
from hummingbot.connector.exchange.changelly.changelly_api_user_stream_data_source import (
    ChangellyAPIUserStreamDataSource,
)
from hummingbot.connector.exchange.changelly.changelly_auth import ChangellyAuth
from hummingbot.connector.exchange_py_base import ExchangePyBase
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import TradeFillOrderDetails, combine_to_hb_trading_pair
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.trade_fee import DeductedFromReturnsTradeFee, TokenAmount, TradeFeeBase
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.event.events import MarketEvent, OrderFilledEvent
from hummingbot.core.utils.async_utils import safe_gather
from hummingbot.core.utils.estimate_fee import build_trade_fee
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory

if TYPE_CHECKING:
    from hummingbot.client.config.config_helpers import ClientConfigAdapter


class ChangellyExchange(ExchangePyBase):
    UPDATE_ORDER_STATUS_MIN_INTERVAL = 10.0

    ORDERS_STREAM_ID = 123

    web_utils = web_utils

    def __init__(
        self,
        client_config_map: "ClientConfigAdapter",
        changelly_api_key: str,
        changelly_api_secret: str,
        trading_pairs: Optional[List[str]] = None,
        trading_required: bool = True,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        self.api_key = changelly_api_key
        self.secret_key = changelly_api_secret
        self._domain = domain
        self._trading_required = trading_required
        self._trading_pairs = trading_pairs
        self._last_trades_poll_changelly_timestamp = 1.0
        super().__init__(client_config_map)

    @staticmethod
    def changelly_order_type(order_type: OrderType) -> str:
        return order_type.name.upper()

    @staticmethod
    def to_hb_order_type(changelly_type: str) -> OrderType:
        return OrderType[changelly_type]

    @property
    def authenticator(self):
        return ChangellyAuth(api_key=self.api_key, secret_key=self.secret_key, time_provider=self._time_synchronizer)

    @property
    def name(self) -> str:
        if self._domain == "com":
            return "changelly"
        else:
            return f"changelly_{self._domain}"

    @property
    def rate_limits_rules(self):
        return CONSTANTS.RATE_LIMITS

    @property
    def domain(self):
        return self._domain

    @property
    def trading_pairs(self):
        return self._trading_pairs

    @property
    def is_cancel_request_in_exchange_synchronous(self) -> bool:
        return True

    @property
    def is_trading_required(self) -> bool:
        return self._trading_required

    def supported_order_types(self):
        return [OrderType.LIMIT, OrderType.LIMIT_MAKER, OrderType.MARKET]

    async def _place_order_via_websocket(self, order_request):
        # Construct the order placement message and send via websocket
        await self._ws_assistant.send(WSJSONRequest(payload=order_request))

    async def _cancel_order_via_websocket(self, order_id):
        # Construct the order cancellation message and send via websocket
        cancel_payload = {"method": CONSTANTS.SPOT_CANCEL_ORDER, "params": {"client_order_id": order_id}}
        await self._ws_assistant.send(WSJSONRequest(payload=cancel_payload))

    async def _listen_for_order_updates(self):
        # Continuously listen for messages from websocket and handle them
        while True:
            msg = await self._ws_assistant.receive()
            if msg is None:
                break
            await self._handle_websocket_message(msg)

    async def _handle_websocket_message(self, msg):
        #TODO Handle different types of messages like order updates, trade updates etc.
        raise NotImplementedError


    async def _place_order(
        self,
        order_id: str,
        trading_pair: str,
        amount: Decimal,
        trade_type: TradeType,
        order_type: OrderType,
        price: Decimal,
        **kwargs,
    ) -> Tuple[str, float]:
        # Construct the order request
        symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        side = "buy" if trade_type == TradeType.BUY else "sell"
        order_request = {
            "method": CONSTANTS.SPOT_NEW_ORDER,
            "params": {
                "client_order_id": order_id,
                "symbol": symbol,
                "side": side,
                "quantity": f"{amount:f}",
                "price": f"{price:f}" if order_type != "market" else None
            },
            "id": self.ORDERS_STREAM_ID,
        }
        await self._place_order_via_websocket(order_request)
        return (order_id, time.time())

    async def _subscribe_to_spot_trading(self):
        subscription_payload = {"method": CONSTANTS.SPOT_SUBSCRIBE, "params": {}, "id": self.ORDERS_STREAM_ID}
        await self._ws_assistant.send(WSJSONRequest(payload=subscription_payload))

    async def _create_new_spot_order(self, order_params):
        new_order_payload = {"method": CONSTANTS.SPOT_NEW_ORDER, "params": order_params, "id": self.ORDERS_STREAM_ID}
        await self._ws_assistant.send(WSJSONRequest(payload=new_order_payload))

    async def _cancel_spot_order(self, order_id):
        cancel_order_payload = {
            "method": CONSTANTS.SPOT_CANCEL_ORDER,
            "params": {"client_order_id": order_id},
            "id": self.ORDERS_STREAM_ID,
        }
        await self._ws_assistant.send(WSJSONRequest(payload=cancel_order_payload))

    async def _get_spot_fees(self):
        fees_request_payload = {"method": CONSTANTS.SPOT_FEES, "params": {}, "id": self.ORDERS_STREAM_ID}
        await self._ws_assistant.send(WSJSONRequest(payload=fees_request_payload))

    async def _subscribe_to_balance_updates(self):
        balance_subscription_payload = {
            "method": CONSTANTS.SPOT_BALANCE_SUBSCRIBE,
            "params": {"mode": "updates"},
            "id": self.ORDERS_STREAM_ID,
        }
        await self._ws_assistant.send(WSJSONRequest(payload=balance_subscription_payload))

    # Override the _place_cancel method
    async def _place_cancel(self, order_id: str, tracked_order: InFlightOrder) -> bool:
        # Send the cancel request via WebSocket
        await self._cancel_order_via_websocket(order_id)
        #TODO: Process the response and return the success status
