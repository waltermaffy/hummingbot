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
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.trade_fee import DeductedFromReturnsTradeFee, TokenAmount, TradeFeeBase
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.event.events import MarketEvent, OrderFilledEvent
from hummingbot.core.network_iterator import NetworkStatus
from hummingbot.core.utils.async_utils import safe_gather
from hummingbot.core.utils.estimate_fee import build_trade_fee
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant

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
        self._ws_assistant = None

        self.user_ws = None
        self.retry_left = CONSTANTS.MAX_RETRIES
        self.retry_left_ws = CONSTANTS.MAX_RETRIES

        self._api_factory = self._create_web_assistants_factory()

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
        return "changelly"

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
        return CONSTANTS.TRADING_PAIRS_PATH_URL

    @property
    def trading_rules_request_path(self):
        return CONSTANTS.TRADING_PAIRS_PATH_URL

    @property
    def trading_pairs_request_path(self):
        return CONSTANTS.TRADING_PAIRS_PATH_URL

    @property
    def client_order_id_prefix(self):
        return CONSTANTS.HBOT_ORDER_ID
    
    async def check_network(self) -> NetworkStatus:
        """
        This function is required by NetworkIterator base class and is called periodically to check
        the network connection. Ping the network (or call any lightweight public API).
        """
        try:
            self.logger().debug(f"Checking network status of {self.name}...")
            rest_assistant = await self._api_factory.get_rest_assistant()
            url = web_utils.public_rest_url(path=CONSTANTS.CURRENCY_PATH, domain=self.domain)
            result = await rest_assistant.execute_request(
                url=url,
                method=RESTMethod.GET,
                throttler_limit_id=CONSTANTS.CURRENCY_PATH
            )
            if not result:
                self.logger().warning("Changelly public API request failed. Please check network connection.")
                self.logger().warning(f"Request: {url}")
                return NetworkStatus.NOT_CONNECTED
            
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger().error(f"Unexpected error checking Changelly network status. {e}" , exc_info=True)
            if self.retry_left > 0:
                self.retry_left -= 1
                sleep_time = CONSTANTS.RETRY_INTERVAL * (1 + CONSTANTS.EXPONENTIAL_BACKOFF * (CONSTANTS.MAX_RETRIES - self.retry_left))
                self.logger().info(f"Retrying call GET to {url} in {sleep_time} seconds...")
                self.logger().info(f"Retries left: {self.retry_left}")
                await asyncio.sleep(sleep_time)
                self._api_factory = self._create_web_assistants_factory()
                await self.check_network()
            return NetworkStatus.NOT_CONNECTED
        self.retry_left = CONSTANTS.MAX_RETRIES
        return NetworkStatus.CONNECTED

    def supported_order_types(self):
        return [OrderType.LIMIT, OrderType.LIMIT_MAKER, OrderType.MARKET]

    async def get_all_pairs_prices(self) -> List[Dict[str, str]]:
        raise NotImplementedError

    def _create_web_assistants_factory(self) -> WebAssistantsFactory:
        return web_utils.build_api_factory(
            throttler=self._throttler, time_synchronizer=self._time_synchronizer, auth=self.authenticator
        )

    def _create_order_book_data_source(self) -> OrderBookTrackerDataSource:
        return ChangellyAPIOrderBookDataSource(
            trading_pairs=self.trading_pairs, connector=self, api_factory=self._web_assistants_factory
        )

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        return ChangellyAPIUserStreamDataSource(
            auth=self._auth, trading_pairs=self.trading_pairs, connector=self, api_factory=self._web_assistants_factory
        )
    
    @property
    def status_dict(self):
        status = super().status_dict
        status.update({
            "order_books_initialized": self._orderbook_ds.ready,
        })
        return status

    @property
    def ready(self) -> bool:
        """
        Returns True if the connector is ready to operate (all connections established with the exchange). If it is
        not ready it returns False.
        """
        ready = all(self.status_dict.values())
        if not ready:
            self.logger().info(f"Connector not ready. Status: {self.status_dict}")
        return ready
    
    async def _connected_websocket_assistant(self) -> WSAssistant:
        ws = None
        try:
            ws: WSAssistant = await self._web_assistants_factory.get_ws_assistant()
            await ws.connect(ws_url=CONSTANTS.WSS_TRADING_URL, ping_timeout=CONSTANTS.WS_HEARTBEAT_TIME_INTERVAL)
            auth_result = await self._authenticate_connection(ws)
            # self.logger().info(f"Authenticated to websocket: {auth_result}")
        except Exception as e:
            self.logger().error(f"Error connecting to websocket: {str(e)}", exc_info=True)
            # Retry connection
            if self.retry_left_ws > 0:
                self.retry_left_ws -= 1
                sleep_time = CONSTANTS.RETRY_INTERVAL * (1 + CONSTANTS.EXPONENTIAL_BACKOFF * (CONSTANTS.MAX_RETRIES - self.retry_left_ws))
                self.logger().info(f"Retrying connection to websocket in {sleep_time} seconds...")
                self.logger().info(f"Retries left: {self.retry_left_ws}")
                await asyncio.sleep(sleep_time)
                await self._connected_websocket_assistant()
            else:
                raise Exception("Maximum retries exceeded. Could not connect to websocket.")
        self.retry_left_ws = CONSTANTS.MAX_RETRIES
        return ws

    async def _authenticate_connection(self, ws: WSAssistant) -> bool:
        """
        Authenticates to the WebSocket service using the provided API key and secret.
        """
        login_payload = self.authenticator.ws_authenticate()
        auth_message: WSJSONRequest = WSJSONRequest(payload=login_payload)
        await ws.send(auth_message)
        ws_response = await ws.receive()
        auth_response = ws_response.data
        if not auth_response.get("result"):
            raise Exception(f"Authentication failed. Error: {auth_response}")
        return True

    async def _get_ws_assistant(self) -> WSAssistant:
        """
        Retrieves a websocket assistant.
        """
        if not self._ws_assistant:
            ws = await self._connected_websocket_assistant()
            self._ws_assistant = ws
        return self._ws_assistant

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
                "price": f"{price:f}",
            },
            "id": self.ORDERS_STREAM_ID,
        }
        try:
            ws_assistant = await self._connected_websocket_assistant()
            await ws_assistant.send(WSJSONRequest(payload=order_request))
        except Exception as e:
            self.logger().error(f"Error placing order: {str(e)}", exc_info=True)
            time.sleep(5.0)
            raise e
        return (order_id, time.time())

    # async def _get_spot_fees(self):
    #     ws: WSAssistant = await self._connected_websocket_assistant()
    #     fees_request_payload = {"method": CONSTANTS.SPOT_FEES, "params": {}, "id": self.ORDERS_STREAM_ID}
    #     await ws.send(WSJSONRequest(payload=fees_request_payload))

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

    async def _place_cancel(self, order_id: str, tracked_order: InFlightOrder) -> bool:
        # Construct the order cancellation message and send via websocket
        try:
            cancel_payload = {
                "method": CONSTANTS.SPOT_CANCEL_ORDER,
                "params": {"client_order_id": order_id},
                "id": self.ORDERS_STREAM_ID,
            }
            self.logger().info(f"Canceling order {order_id}...")
            ws_assistant = await self._connected_websocket_assistant()
            await ws_assistant.send(WSJSONRequest(payload=cancel_payload))
            message = await ws_assistant.receive()
            data = message.data
            if "result" in data:
                result = data["result"]
                if "status" in result and result["status"] == "canceled":
                    return True
            return False
        except Exception as e:
            self.logger().error(f"Error canceling order: {str(e)}", exc_info=True)
            time.sleep(5.0)
            # try reconnect
            
            return False
        
    def _is_order_not_found_during_status_update_error(self, status_update_exception: Exception) -> bool:
        # TODO: implement this method correctly for the connector
        self.logger().info(f"Error updating order status: {status_update_exception}")
        return False

    def _is_order_not_found_during_cancelation_error(self, cancelation_exception: Exception) -> bool:
        # TODO: implement this method correctly for the connector
        self.logger().info(f"Error canceling order: {cancelation_exception}")
        return False

    def _is_request_exception_related_to_time_synchronizer(self, request_exception: Exception):
        # TODO: check error code and message of changelly
        error_description = str(request_exception)
        is_time_synchronizer_related = "-1021" in error_description and "Timestamp for the request" in error_description
        return is_time_synchronizer_related

    async def _update_trading_fees(self):
        try:
            fees_payload = {"method": CONSTANTS.SPOT_FEES, "params": {}, "id": self.ORDERS_STREAM_ID}
            ws: WSAssistant = await self._connected_websocket_assistant()

            await ws.send(WSJSONRequest(payload=fees_payload))
            fees_response = await ws.receive()
            data = fees_response.data
            if not data or "result" not in data:
                self.logger().info(f"Error updating trading fees")
                return

            for fee_info in data["result"]:
                trading_pair = fee_info["symbol"]
                self._trading_fees[trading_pair] = {"maker": fee_info["make_rate"], "taker": fee_info["take_rate"]}
        except Exception as e:
            self.logger().error(f"Error updating trading fees: {str(e)}", exc_info=True)

    async def _user_stream_event_listener(self):
        """
        This function runs in the background, continuously processing the events received from the Changelly exchange by the user
        stream data source. It keeps reading events from the queue until the task is interrupted.
        The events received are order updates and trade events.
        """
        async for event_message in self._iter_user_event_queue():
            try:
                self.logger().debug(f"Processing user event message: {event_message}")
                method = event_message.get("method")

                # Handling order updates and trade events
                if method == CONSTANTS.SPOT_ORDER:
                    data = event_message.get("params", {})
                    client_order_id = data["client_order_id"]
                    tracked_order = self._order_tracker.all_updatable_orders.get(client_order_id)
                    update_timestamp = web_utils.convert_to_unix_timestamp(data["updated_at"])

                    # Check if it's a trade event
                    if data.get("report_type") == "trade":
                        if tracked_order is not None:
                            fee = TradeFeeBase.new_spot_fee(
                                fee_schema=self.trade_fee_schema(),
                                trade_type=tracked_order.trade_type,
                            )
                            trade_update = TradeUpdate(
                                trade_id=str(data["trade_id"]),
                                client_order_id=client_order_id,
                                exchange_order_id=str(data["id"]),
                                trading_pair=tracked_order.trading_pair,
                                fee=fee,
                                fill_base_amount=Decimal(data["trade_quantity"]),
                                fill_quote_amount=Decimal(data["trade_quantity"]) * Decimal(data["trade_price"]),
                                fill_price=Decimal(data["trade_price"]),
                                fill_timestamp=update_timestamp,
                            )
                            self._order_tracker.process_trade_update(trade_update)

                    # For all order updates (new, canceled, filled)
                    if tracked_order is not None:
                        order_update = OrderUpdate(
                            trading_pair=tracked_order.trading_pair,
                            update_timestamp=update_timestamp,
                            new_state=CONSTANTS.ORDER_STATE[data["status"]],
                            client_order_id=client_order_id,
                            exchange_order_id=str(data["id"]),
                        )
                        self._order_tracker.process_order_update(order_update)

                elif method == CONSTANTS.SPOT_BALANCE:
                    balances = event_message.get("params", [])
                    for balance in balances:
                        currency = balance["currency"]
                        self._account_balances[currency] = Decimal(balance["available"])
                        self._account_available_balances[currency] = Decimal(balance["available"])

            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error("Unexpected error in user stream listener loop.", exc_info=True)
                await self._sleep(5.0)

    async def _update_orders_fills(self, orders: List[InFlightOrder]):
        # This method in the base ExchangePyBase, makes an API call for each order.
        # Given the rate limit of the API method and the breadth of info provided by the method
        # the mitigation proposal is to collect all orders in one shot, then parse them
        active_orders = await self._get_active_orders()
        for order in orders:
            try:
                if order.exchange_order_id is not None:
                    order_info = next((o for o in active_orders if o["client_order_id"] == order.client_order_id), {})
                    if not order_info:
                        continue

                    trade_updates = await self._all_trade_updates_for_order(order=order)
                    for trade_update in trade_updates:
                        self._order_tracker.process_trade_update(trade_update)
            except asyncio.CancelledError:
                raise
            except Exception as request_error:
                self.logger().warning(
                    f"Failed to fetch trade updates for order {order.client_order_id}. Error: {request_error}",
                    exc_info=request_error,
                )

    async def _all_trade_updates_for_order(self, order: InFlightOrder) -> List[TradeUpdate]:
        """TODO: Return all trades updates for an order. 
        Since changelly does not provide REST api for it.  
        We need to buffer the trade updates from by subscribing to websocket events.
        """
        trade_updates = []
        return trade_updates

    async def _format_trading_rules(self, exchange_info_dict: Dict[str, Any]) -> List[TradingRule]:
        trading_rules_list = []
        for symbol_key in exchange_info_dict:
            try:
                symbol_data = exchange_info_dict[symbol_key]
                trading_pair = combine_to_hb_trading_pair(
                    base=symbol_data["base_currency"], quote=symbol_data["quote_currency"]
                )
                min_order_size = Decimal(symbol_data.get("quantity_increment", 0))
                min_price_increment = Decimal(symbol_data.get("tick_size", 0))
                min_base_amount_increment = Decimal(symbol_data.get("quantity_increment", 0))
                # Add more fields based on Changelly's response
                trading_rules_list.append(
                    TradingRule(
                        trading_pair,
                        min_order_size=min_order_size,
                        min_price_increment=min_price_increment,
                        min_base_amount_increment=min_base_amount_increment,
                    )
                )
            except Exception:
                self.logger().error(f"Error parsing the trading pair rule {symbol_key}. Skipping.", exc_info=True)
        return trading_rules_list

    async def _update_balances(self):
        try:
            ws: WSAssistant = await self._connected_websocket_assistant()

            balance_payload = {"method": CONSTANTS.SPOT_BALANCES, "params": {}, "id": self.ORDERS_STREAM_ID}
            await ws.send(WSJSONRequest(payload=balance_payload))
            balance_response = await ws.receive()
            data = balance_response.data
            # Assuming balance_response is structured with balance details
            if not data or "result" not in data:
                self.logger().info(f"Error updating balances: {data}")
                return

            for balance in data["result"]:
                currency = balance["currency"]
                self._account_balances[currency] = Decimal(balance["available"])
                self._account_available_balances[currency] = Decimal(balance["available"])
        except Exception as e:
            self.logger().error(f"Error updating balances: {str(e)}", exc_info=True)

    async def _get_active_orders(self):
        try:
            ws: WSAssistant = await self._connected_websocket_assistant()
            active_orders_payload = {"method": CONSTANTS.SPOT_GET_ORDERS, "params": {}, "id": self.ORDERS_STREAM_ID}
            # Get active orders
            await ws.send(WSJSONRequest(payload=active_orders_payload))
            active_orders_response = await ws.receive()
            data = active_orders_response.data
            if not data or "result" not in data:
                return []
            return data["result"]
        except Exception as e:
            self.logger().error(f"Error getting active orders: {str(e)}", exc_info=True)
            return []
        
    async def _request_order_status(self, tracked_order: InFlightOrder) -> OrderUpdate:
        # Construct the request payload
        active_orders = await self._get_active_orders()
        if not active_orders:
            return None
        # Find the order with the matching client_order_id
        order_info = next(
            (order for order in active_orders if order["client_order_id"] == tracked_order.client_order_id), {}
        )
        if not order_info:
            self.logger().warning(f"Order {tracked_order.client_order_id} not found in active orders in changelly.")
            new_state = CONSTANTS.ORDER_STATE["canceled"]
            update_timestamp = time.time()
        else:
            new_state = CONSTANTS.ORDER_STATE[order_info["status"]]
            update_timestamp = web_utils.convert_to_unix_timestamp(order_info["updated_at"])
        
        order_update = OrderUpdate(
            client_order_id=tracked_order.client_order_id,
            exchange_order_id=tracked_order.exchange_order_id,
            trading_pair=tracked_order.trading_pair,
            update_timestamp=update_timestamp,
            new_state=new_state,
        )

        return order_update

    def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: Dict[str, Any]):
        mapping = bidict()
        for symbol_key in exchange_info:
            symbol_data = exchange_info[symbol_key]
            if changelly_utils.is_exchange_information_valid(symbol_data):
                trading_pair = combine_to_hb_trading_pair(
                    base=symbol_data["base_currency"], quote=symbol_data["quote_currency"]
                )
                mapping[symbol_key] = trading_pair

        self._set_trading_pair_symbol_map(mapping)
