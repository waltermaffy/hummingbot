import asyncio
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from bidict import bidict

from hummingbot.connector.exchange.koinbx import (
    koinbx_constants as CONSTANTS,
    koinbx_utils as utils,
    koinbx_web_utils as web_utils,
)
from hummingbot.connector.exchange.koinbx.koinbx_api_order_book_data_source import KoinbxAPIOrderBookDataSource
from hummingbot.connector.exchange.koinbx.koinbx_api_user_stream_data_source import KoinbxAPIUserStreamDataSource
from hummingbot.connector.exchange.koinbx.koinbx_auth import KoinbxAuth
from hummingbot.connector.exchange_py_base import ExchangePyBase
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderState, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.trade_fee import DeductedFromReturnsTradeFee, TokenAmount, TradeFeeBase
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.network_iterator import NetworkStatus
from hummingbot.core.utils.async_utils import safe_ensure_future, safe_gather
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory

s_decimal_0 = Decimal(0)
s_decimal_NaN = Decimal("nan")

if TYPE_CHECKING:
    from hummingbot.client.config.config_helpers import ClientConfigAdapter


class KoinbxExchange(ExchangePyBase):
    _logger = None
    UPDATE_ORDER_STATUS_MIN_INTERVAL = 10.0
    web_utils = web_utils

    def __init__(
        self,
        client_config_map: "ClientConfigAdapter",
        koinbx_api_key: str,
        koinbx_api_secret: str,
        trading_pairs: Optional[List[str]] = None,
        trading_required: bool = True,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        self.api_key = koinbx_api_key
        self.secret_key = koinbx_api_secret
        self._domain = domain
        self._trading_required = trading_required
        self._trading_pairs = trading_pairs
        self._last_trades_poll_koinbx_timestamp = 1.0
        self.retry_left = CONSTANTS.MAX_RETRIES
        self.real_time_balance_update = False

        super().__init__(client_config_map)
        self._api_factory = self._create_web_assistants_factory()
        self._ws_lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "koinbx"

    @property
    def authenticator(self):
        return KoinbxAuth(api_key=self.api_key, secret_key=self.secret_key, time_provider=self._time_synchronizer)

    @property
    def rate_limits_rules(self):
        return CONSTANTS.RATE_LIMITS

    @property
    def domain(self):
        return self._domain

    @property
    def client_order_id_max_length(self):
        return CONSTANTS.MAX_ORDER_ID_LEN

    @property
    def client_order_id_prefix(self):
        return CONSTANTS.HBOT_ORDER_ID_PREFIX

    @property
    def trading_rules_request_path(self):
        return CONSTANTS.MAKETS_PATH_URL

    @property
    def trading_pairs_request_path(self):
        return CONSTANTS.MAKETS_PATH_URL

    @property
    def check_network_request_path(self):
        return CONSTANTS.PING_PATH_URL

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

    def _create_order_book_data_source(self) -> OrderBookTrackerDataSource:
        return KoinbxAPIOrderBookDataSource(
            trading_pairs=self._trading_pairs, connector=self, api_factory=self._web_assistants_factory
        )

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        return KoinbxAPIUserStreamDataSource(
            auth=self._auth,
            trading_pairs=self._trading_pairs,
            connector=self,
            api_factory=self._web_assistants_factory,
            domain=self.domain,
        )

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
        return DeductedFromReturnsTradeFee(percent=self.estimate_fee_pct(is_maker))

    def _is_request_exception_related_to_time_synchronizer(self, request_exception: Exception):
        error_description = str(request_exception)
        is_time_synchronizer_related = (
            "-1021" in error_description and "Timestamp for this request" in error_description
        )
        return is_time_synchronizer_related

    def _is_order_not_found_during_status_update_error(self, status_update_exception: Exception) -> bool:
        return str(CONSTANTS.ORDER_NOT_EXIST_ERROR_CODE) in str(
            status_update_exception
        ) and CONSTANTS.ORDER_NOT_EXIST_MESSAGE in str(status_update_exception)

    def _is_order_not_found_during_cancelation_error(self, cancelation_exception: Exception) -> bool:
        return str(CONSTANTS.UNKNOWN_ORDER_ERROR_CODE) in str(
            cancelation_exception
        ) and CONSTANTS.UNKNOWN_ORDER_MESSAGE in str(cancelation_exception)

    def _create_web_assistants_factory(self) -> WebAssistantsFactory:
        return web_utils.build_api_factory_without_time_synchronizer_pre_processor(
            throttler=self._throttler, auth=self.authenticator
        )

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
        """
        Places an order on the exchange.
        """
        symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        side = "buy" if trade_type == TradeType.BUY else "sell"

        data = {
            "quantity": str(amount),
            "price": str(price),
            "pair": symbol,
            "type": side,
            "timestamp": str(int(self._time_synchronizer.time() * 1000)),
        }
        response = await self._api_post(path_url=CONSTANTS.ORDER_PATH_URL, data=data, is_auth_required=True)
        self.logger().info(f"Placed order on {self.name}. - {response=}")
        if not response:
            self.logger().error(f"Failed to place order on {self.name}. - {response=}")
            raise ValueError(f"Failed to place order on {self.name}. - {response=}")
        order_id = response.get("data", {}).get("orderId")
        if order_id is None:
            self.logger().error(f"Failed to place order on {self.name}. - {response=}")
            raise ValueError(f"Failed to place order on {self.name}. - {response=}")
        
        return str(order_id), self._time_synchronizer.time()

    async def _place_cancel(self, order_id: str, tracked_order: InFlightOrder):
        """
        Cancels an order on the exchange.
        """
        data = {"orderId": tracked_order.exchange_order_id, "timestamp": str(int(self._time_synchronizer.time() * 1000))}
        self.logger().info(f"Cancelling order {order_id} on {self.name} - {data=}")
        response = await self._api_post(path_url=CONSTANTS.CANCEL_ORDER_PATH_URL, data=data, is_auth_required=True)
        self.logger().info(f"Cancelled order on {self.name}. - {response=}")
        # if not response.get("status"):
            # TODO: An order already does not mean its not cancelled, need to check the status
            # Check if order already executed
            # if response.get("message") == "Order already executed":
            #     return True
        return response["status"]

    async def _format_trading_rules(self, exchange_info_dict: Dict[str, Any]) -> List[TradingRule]:
        """
        Formats the raw trading pair info into TradingRule instances.
        """

        markets = exchange_info_dict.get("markets", [])
        trading_rules = []
        if CONSTANTS.TEST_MODE:
            return [
                TradingRule(
                    trading_pair=await self.trading_pair_associated_to_exchange_symbol(symbol=CONSTANTS.TEST_PAIR),
                    min_order_size=Decimal("0.1"),
                    min_price_increment=Decimal("1e-8"),
                    min_base_amount_increment=Decimal("1e-8"),
                    min_notional_size=Decimal("0"),
                    supports_market_orders=False,
                )
            ]
        for pair_info in markets:
            try:
                symbol = pair_info["trading_pairs"]
                trading_pair = await self.trading_pair_associated_to_exchange_symbol(symbol=symbol)
                trading_rules.append(
                    TradingRule(
                        trading_pair=trading_pair,
                        min_order_size=Decimal(pair_info["min_withdraw"]),
                        min_price_increment=Decimal("1e-8"),  # Assuming 8 decimal places, adjust if needed
                        min_base_amount_increment=Decimal("1e-8"),  # Assuming 8 decimal places, adjust if needed
                        min_notional_size=Decimal("0"),
                        supports_market_orders=False,  # Assuming market orders are supported, adjust if needed
                    )
                )
            except Exception:
                self.logger().error(f"Error parsing the trading pair rule {pair_info}. Skipping.", exc_info=True)
        return trading_rules

    async def _status_polling_loop_fetch_updates(self):
        await self._update_order_fills_from_trades()
        await super()._status_polling_loop_fetch_updates()

    async def _update_trading_fees(self):
        """
        Update fees information from the exchange
        """
        # For each pair set 0.25% fee
        for trading_pair in self._trading_pairs:
            self._trading_fees[trading_pair] = {"maker": CONSTANTS.DEFAULT_FEE, "taker": CONSTANTS.DEFAULT_FEE}

    async def _user_stream_event_listener(self):
        """
        This function runs in the background continuously processing the events received from the exchange
        by the user stream data source. It uses polling instead of websockets.
        """
        async for event_message in self._iter_user_event_queue():
            try:
                await self._process_user_stream_event(event_message)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().exception("Unexpected error in user stream listener loop.")
                await asyncio.sleep(5.0)

    async def _process_user_stream_event(self, event: Dict[str, Any]):
        """
        Process a user stream event received from the exchange.
        """
        if "open_orders" in event:
            await self._process_open_orders_event(event["open_orders"])
        if "balance" in event:
            self._process_balance_event(event["balance"])

    async def _process_open_orders_event(self, open_orders: List[Dict[str, Any]]):
        """
        Process open orders update from the user stream.
        """
        for order_data in open_orders:
            client_order_id = order_data.get("clientOrderId")
            if client_order_id is None:
                continue
            tracked_order = self._order_tracker.all_updatable_orders.get(client_order_id)
            if tracked_order is None:
                continue

            order_update = OrderUpdate(
                client_order_id=client_order_id,
                exchange_order_id=order_data["orderId"],
                trading_pair=tracked_order.trading_pair,
                update_timestamp=int(order_data["time"]),
                new_state=self._get_order_state(order_data),
            )
            self._order_tracker.process_order_update(order_update)

    def _get_order_state(self, order_data: Dict[str, Any]) -> OrderState:
        """
        Determine the order state based on the order data.
        """
        status = order_data["status"].lower()
        if status == "cancelled":
            return OrderState.CANCELED
        elif Decimal(str(order_data["filledamount"])) >= Decimal(str(order_data["amount"])):
            return OrderState.FILLED
        elif Decimal(str(order_data["filledamount"])) > Decimal("0"):
            return OrderState.PARTIALLY_FILLED
        else:
            return OrderState.OPEN

    async def _update_order_fills_from_trades(self):
        """
        This is intended to be a backup measure to get filled events with trade ID for orders,
        in case Binance's user stream events are not working.
        NOTE: It is not required to copy this functionality in other connectors.
        This is separated from _update_order_status which only updates the order status without producing filled
        events, since Binance's get order endpoint does not return trade IDs.
        The minimum poll interval for order status is 10 seconds.
        """
        pass

    async def _all_trade_updates_for_order(self, order: InFlightOrder) -> List[TradeUpdate]:
        """
        Fetches all trade updates for a given order using the getOrder API.
        """
        data = {
            "orderId": order.exchange_order_id,
            "timestamp": str(int(self._time_synchronizer.time() * 1000)),
        }
        response = await self._api_post(path_url=CONSTANTS.GET_ORDER_PATH_URL, data=data, is_auth_required=True)
        self.logger().info(f"KOINBX Order update: {response}")
        
        trade_updates = []
        if response["status"] and response["data"]["data"]:
            order_data = response["data"]["data"][0]
            
            # Check if the order is filled or partially filled
            if Decimal(str(order_data["filledamount"])) > Decimal("0"):
                trade_update = TradeUpdate(
                    trade_id=str(order_data["orderId"]),
                    client_order_id=order.client_order_id,
                    exchange_order_id=order.exchange_order_id,
                    trading_pair=order.trading_pair,
                    fill_price=Decimal(str(order_data["price"])),
                    fill_base_amount=Decimal(str(order_data["filledamount"])),
                    fill_quote_amount=Decimal(str(order_data["price"])) * Decimal(str(order_data["filledamount"])),
                    fee=TradeFeeBase.new_spot_fee(
                        fee_schema=self.trade_fee_schema(),
                        trade_type=TradeType.BUY if order_data["type"] == "buy" else TradeType.SELL,
                        percent_token="",
                        flat_fees=[],  # The API doesn't provide fee information, so we leave it empty
                    ),
                    fill_timestamp=int(datetime.strptime(order_data["createdAt"], "%Y-%m-%d %H:%M:%S").timestamp()),
                )
                trade_updates.append(trade_update)

        return trade_updates

    async def _request_order_status(self, tracked_order: InFlightOrder) -> OrderUpdate:
        """
        Requests the status of an order from the exchange.
        """
        # url = web_utils.private_rest_url(CONSTANTS.GET_ORDER_PATH_URL)
        data = {
            "orderId": tracked_order.exchange_order_id,
            "timestamp": str(int(self._time_synchronizer.time() * 1000)),
        }
        response = await self._api_post(path_url=CONSTANTS.GET_ORDER_PATH_URL, data=data, is_auth_required=True)
        self.logger().info(f"KOINBX Order update: {response}")
        order_data = response["data"]["data"][0]
        new_state = OrderState.OPEN
        if order_data["status"] == "cancelled":
            new_state = OrderState.CANCELED
        elif Decimal(str(order_data["filledamount"])) >= Decimal(str(order_data["amount"])):
            new_state = OrderState.FILLED
        elif Decimal(str(order_data["filledamount"])) > Decimal("0"):
            new_state = OrderState.PARTIALLY_FILLED

        return OrderUpdate(
            client_order_id=tracked_order.client_order_id,
            exchange_order_id=order_data["orderId"],
            trading_pair=tracked_order.trading_pair,
            update_timestamp=int(datetime.strptime(order_data["createdAt"], "%Y-%m-%d %H:%M:%S").timestamp()),
            new_state=new_state,
        )

    async def _update_balances(self):
        """
        Fetches and updates the user's balances.
        """
        local_asset_names = set(self._account_balances.keys())
        remote_asset_names = set()

        data = {"timestamp": str(int(self._time_synchronizer.time() * 1000))}
        response = await self._api_post(path_url=CONSTANTS.BALANCE_PATH_URL, data=data, is_auth_required=True)

        self._account_available_balances.clear()
        self._account_balances.clear()

        for balance_entry in response["data"]:
            asset_name = balance_entry["currency"]
            self._account_balances[asset_name] = Decimal(balance_entry["balance"])
            self._account_available_balances[asset_name] = Decimal(balance_entry["balance"]) - Decimal(balance_entry["locked_amount"])
            remote_asset_names.add(asset_name)

        asset_names_to_remove = local_asset_names.difference(remote_asset_names)
        for asset_name in asset_names_to_remove:
            del self._account_available_balances[asset_name]
            del self._account_balances[asset_name]

    def _process_balance_event(self, balance_data: List[Dict[str, Any]]):
        """
        Process balance update from the user stream.
        """
        for balance_entry in balance_data:
            asset_name = balance_entry["currency"]
            self._account_balances[asset_name] = Decimal(balance_entry["balance"])
            self._account_available_balances[asset_name] = (
                Decimal(balance_entry["balance"]) - Decimal(balance_entry["locked_amount"])
            )
            
    def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: Dict[str, Any]):
        mapping = bidict()

        if not CONSTANTS.TEST_MODE:
            markets = exchange_info.get("markets", [])
            for market in markets:
                symbol = market["trading_pairs"]
                trading_pair = utils.convert_from_exchange_trading_pair(symbol)
                mapping[symbol] = trading_pair
        else:
            mapping[CONSTANTS.TEST_PAIR] = utils.convert_from_exchange_trading_pair(CONSTANTS.TEST_PAIR)

        self._set_trading_pair_symbol_map(mapping)

    async def _get_last_traded_price(self, trading_pair: str) -> float:
        """
        Fetches the last traded price for a given trading pair.
        """
        symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        # url = web_utils.public_rest_url(public_rest_url=CONSTANTS.TICKER_PATH_URL)
        params = {"market_pair": symbol}
        response = await self._api_get(path_url=CONSTANTS.TICKER_PATH_URL, params=params, is_auth_required=False)
        return float(response["tickers"][symbol]["last_price"])
