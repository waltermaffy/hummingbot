import asyncio
import json
import time
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from bidict import bidict

from hummingbot.connector.exchange.changelly import (  # changelly_utils,
    changelly_constants as CONSTANTS,
    changelly_utils,
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

s_decimal_NaN = Decimal("nan")
s_decimal_0 = Decimal(0)


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

    @property
    def client_order_id_max_length(self):
        return CONSTANTS.MAX_ORDER_ID_LEN

    @property
    def check_network_request_path(self):
        return None

    @property
    def trading_rules_request_path(self):
        return web_utils.public_rest_url(path=CONSTANTS.TRADING_PAIRS_PATH_URL)

    @property
    def trading_pairs_request_path(self):
        return web_utils.public_rest_url(path=CONSTANTS.TRADING_PAIRS_PATH_URL)

    @property
    def client_order_id_prefix(self):
        return CONSTANTS.HBOT_ORDER_ID

    def supported_order_types(self):
        return [OrderType.LIMIT, OrderType.LIMIT_MAKER, OrderType.MARKET]
    
    async def get_all_pairs_prices(self) -> List[Dict[str, str]]:
        # TODO: Implement this
        pass

    def _create_web_assistants_factory(self) -> WebAssistantsFactory:
        return web_utils.build_api_factory(
            throttler=self._throttler,
            time_synchronizer=self._time_synchronizer,
            auth=self._auth)
    
    def _create_order_book_data_source(self) -> OrderBookTrackerDataSource:
        return ChangellyAPIOrderBookDataSource(
            trading_pairs=self._trading_pairs, 
            connector=self, 
            api_factory=self._web_assistants_factory
        )

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        return ChangellyAPIUserStreamDataSource(
            auth=self._auth, 
            trading_pairs=self._trading_pairs, 
            connector=self, 
            api_factory=self._web_assistants_factory
        )

    async def _place_order_via_websocket(self, order_request):
        # Construct the order placement message and send via websocket
        await self._ws_assistant.send(WSJSONRequest(payload=order_request))

    async def _cancel_order_via_websocket(self, order_id):
        # Construct the order cancellation message and send via websocket
        cancel_payload = {"method": CONSTANTS.SPOT_CANCEL_ORDER, "params": {"client_order_id": order_id}}
        await self._ws_assistant.send(WSJSONRequest(payload=cancel_payload))
        result = await self._ws_assistant.receive()

    # async def _listen_for_order_updates(self):
    #     # Continuously listen for messages from websocket and handle them
    #     while True:
    #         msg = await self._ws_assistant.receive()
    #         if msg is None:
    #             break
    #         await self._handle_websocket_message(msg)


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
        symbol = self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        side = "buy" if trade_type == TradeType.BUY else "sell"
        order_request = {
            "method": CONSTANTS.SPOT_NEW_ORDER,
            "params": {
                "client_order_id": order_id,
                "symbol": symbol,
                "side": side,
                "quantity": f"{amount:f}",
                "price": f"{price:f}"
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

    def _get_fee(
        self,
        base_currency: str,
        quote_currency: str,
        order_type: OrderType,
        order_side: TradeType,
        amount: Decimal,
        price: Decimal = s_decimal_NaN,
        is_maker: Optional[bool] = None,
    ) -> TradeFeeBase:
        is_maker = order_type is OrderType.LIMIT_MAKER
        trade_base_fee = build_trade_fee(
            exchange=self.name,
            is_maker=is_maker,
            order_side=order_side,
            order_type=order_type,
            amount=amount,
            price=price,
            base_currency=base_currency,
            quote_currency=quote_currency,
        )
        return trade_base_fee

    async def _subscribe_to_balance_updates(self):
        balance_subscription_payload = {
            "method": CONSTANTS.SPOT_BALANCE_SUBSCRIBE,
            "params": {"mode": "updates"},
            "id": self.ORDERS_STREAM_ID,
        }
        await self._ws_assistant.send(WSJSONRequest(payload=balance_subscription_payload))

    async def _place_cancel(self, order_id: str, tracked_order: InFlightOrder) -> bool:
        # TODO: Implement - Process the response and return the success status
        # Send the cancel request via WebSocket
        await self._cancel_order_via_websocket(order_id)
    

    def _is_order_not_found_during_status_update_error(self, status_update_exception: Exception) -> bool:
        # TODO: implement this method correctly for the connector
        return False

    def _is_order_not_found_during_cancelation_error(self, cancelation_exception: Exception) -> bool:
        # TODO: implement this method correctly for the connector
        return False

    def _is_request_exception_related_to_time_synchronizer(self, request_exception: Exception):
        # TODO: check error code and message of changelly
        error_description = str(request_exception)
        is_time_synchronizer_related = "-1021" in error_description and "Timestamp for the request" in error_description
        return is_time_synchronizer_related

    async def _update_trading_fees(self):
        try:
            fees_payload = {
                "method": CONSTANTS.SPOT_FEES,
                "params": {},
                "id": self.ORDERS_STREAM_ID
            }
            await self._ws_assistant.send(WSJSONRequest(payload=fees_payload))
            fees_response = await self._ws_assistant.receive()

            for fee_info in fees_response["result"]:
                trading_pair = fee_info["symbol"]
                self._trading_fees[trading_pair] = {
                    "maker": fee_info["make_rate"],
                    "taker": fee_info["take_rate"]
                }
        except Exception as e:
            self.logger().error(f"Error updating trading fees: {str(e)}", exc_info=True)

    async def _user_stream_event_listener(self):
        """
        This functions runs in background continuously processing the events received from the exchange by the user
        stream data source. It keeps reading events from the queue until the task is interrupted.
        The events received are balance updates, order updates and trade events.
        """
        async for event_message in self._iter_user_event_queue():
            try:
                if not event_message:
                    continue

                # TODO: Handle the order event 


            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error("Unexpected error in user stream listener loop.", exc_info=True)
                await self._sleep(5.0)

    async def _format_trading_rules(self, exchange_info_dict: Dict[str, Any]) -> List[TradingRule]:
        trading_rules_list = []
        for symbol_key in exchange_info_dict:
            try:
                symbol_data = exchange_info_dict[symbol_key]
                trading_pair = combine_to_hb_trading_pair(base=symbol_data["base_currency"], quote=symbol_data["quote_currency"])
                min_order_size = Decimal(symbol_data.get("tick_size", 0))
                min_price_increment = Decimal(symbol_data.get("tick_size", 0))
                min_base_amount_increment = Decimal(symbol_data.get("quantity_increment", 0))
                # Add more fields based on Changelly's response
                trading_rules_list.append(TradingRule(trading_pair, 
                                                      min_order_size=min_order_size,
                                                      min_price_increment=min_price_increment,
                                                      min_base_amount_increment=min_base_amount_increment
                                                    ))
            except Exception:
                self.logger().error(f"Error parsing the trading pair rule {symbol_key}. Skipping.", exc_info=True)
        return trading_rules_list


    async def _update_balances(self):
        try:
            balance_payload = {
                "method": CONSTANTS.SPOT_BALANCES,
                "params": {},
                "id": self.ORDERS_STREAM_ID
            }
            await self._ws_assistant.send(WSJSONRequest(payload=balance_payload))
            balance_response = await self._ws_assistant.receive()

            # Assuming balance_response is structured with balance details
            for balance in balance_response["result"]:
                currency = balance["currency"]
                self._account_balances[currency] = Decimal(balance["available"])
                self._account_available_balances[currency] = Decimal(balance["available"])
        except Exception as e:
            self.logger().error(f"Error updating balances: {str(e)}", exc_info=True)


    async def _all_trade_updates_for_order(self, order: InFlightOrder) -> List[TradeUpdate]:
        trade_updates = []
        try:
            if order.exchange_order_id is not None:
                all_fills_response = await self._request_order_fills(order=order)
                updates = self._create_order_fill_updates(order=order, fill_update=all_fills_response)
                trade_updates.extend(updates)
        except asyncio.CancelledError:
            raise
        except Exception as ex:
            is_error_caused_by_unexistent_order = '"code":"OrderNotFound"' in str(ex)
            if not is_error_caused_by_unexistent_order:
                raise

        return trade_updates

    async def _request_order_status(self, tracked_order: InFlightOrder) -> OrderUpdate:
        # Construct the request payload
        order_status_request = {
            "method": CONSTANTS.SPOT_GET_ORDERS,
            "params": {
                "client_order_id": tracked_order.client_order_id
            },
            "id": self.ORDERS_STREAM_ID
        }

        # Send the request via WebSocket
        await self._ws_assistant.send(WSJSONRequest(payload=order_status_request))

        # Wait for the response
        response = await self._ws_assistant.receive()

        # Check if the response is valid and contains order status
        if response and "result" in response and isinstance(response["result"], list):
            # Find the order with the matching client_order_id
            order_info = next((order for order in response["result"] if order["client_order_id"] == tracked_order.client_order_id), {})         
            new_state = CONSTANTS.ORDER_STATE[order_info["status"]]

            order_update = OrderUpdate(
                client_order_id=tracked_order.client_order_id,
                exchange_order_id=str(order_info["id"]),
                trading_pair=tracked_order.trading_pair,
                update_timestamp=int(order_info["updated_at"]),
                new_state=new_state,
            )

            return order_update

        return None



    def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: Dict[str, Any]):
        mapping = bidict()
        for symbol_key in exchange_info:
            symbol_data = exchange_info[symbol_key]
            if changelly_utils.is_exchange_information_valid(symbol_data):
                trading_pair = combine_to_hb_trading_pair(base=symbol_data["base_currency"],
                                                          quote=symbol_data["quote_currency"])
                mapping[symbol_key] = trading_pair

        self._set_trading_pair_symbol_map(mapping)

