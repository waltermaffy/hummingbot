import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from bidict import bidict

from hummingbot.connector.constants import s_decimal_NaN
from hummingbot.connector.exchange.coinstore import (
    coinstore_constants as CONSTANTS,
    coinstore_utils,
    coinstore_web_utils as web_utils,
)
from hummingbot.connector.exchange.coinstore.coinstore_api_order_book_data_source import CoinstoreAPIOrderBookDataSource
from hummingbot.connector.exchange.coinstore.coinstore_api_user_stream_data_source import (
    CoinstoreAPIUserStreamDataSource,
)
from hummingbot.connector.exchange.coinstore.coinstore_auth import CoinstoreAuth
from hummingbot.connector.exchange_py_base import ExchangePyBase
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import TradeFillOrderDetails, combine_to_hb_trading_pair
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderState, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.trade_fee import DeductedFromReturnsTradeFee, TokenAmount, TradeFeeBase
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.event.events import MarketEvent, OrderFilledEvent
from hummingbot.core.utils.async_utils import safe_gather
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
import aiohttp
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest
import json

if TYPE_CHECKING:
    from hummingbot.client.config.config_helpers import ClientConfigAdapter
from urllib.parse import urlencode

s_decimal_NaN = Decimal("nan")
s_decimal_0 = Decimal(0)


class CoinstoreExchange(ExchangePyBase):
    web_utils = web_utils

    
    def __init__(self,
                 client_config_map: "ClientConfigAdapter",
                 coinstore_api_key: str,
                 coinstore_api_secret: str,
                 trading_pairs: Optional[List[str]] = None,
                 trading_required: bool = True,
                 domain: str = CONSTANTS.DEFAULT_DOMAIN
    ):
        self.api_key = coinstore_api_key
        self.secret_key = coinstore_api_secret
        self._domain = domain    
        self._trading_required = trading_required
        self._trading_pairs = trading_pairs
        self._price_precision_map: Dict[str, int] = {}
        self._amount_precision_map: Dict[str, int] = {}
        self.ORDER_PAGE_LIMIT = 100
        self.SHORT_POLL_INTERVAL = 2.0
        self.LONG_POLL_INTERVAL = 10.0
        self.TICK_INTERVAL_LIMIT = 5.0
        
        self._http_client = aiohttp.ClientSession()
        super().__init__(client_config_map)
        

    @property
    def name(self) -> str:
        return "coinstore"
    
    @property
    def authenticator(self) -> CoinstoreAuth:
        return CoinstoreAuth(api_key=self.api_key, secret_key=self.secret_key, time_provider=self._time_synchronizer)

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
        return CONSTANTS.EXCHANGE_INFO_PATH_URL

    @property
    def trading_pairs_request_path(self):
        return CONSTANTS.EXCHANGE_INFO_PATH_URL

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
        return CoinstoreAPIOrderBookDataSource(
            trading_pairs=self._trading_pairs,
            connector=self,
            api_factory=self._web_assistants_factory
        )

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        return CoinstoreAPIUserStreamDataSource(
            auth=self.authenticator,
            trading_pairs=self._trading_pairs,
            connector=self,
            api_factory=self._web_assistants_factory,
            domain=self._domain
        )

    async def _initialize_trading_pair_symbol_map(self):
        try:
            exchange_info = await self._make_trading_pairs_request()
            self._initialize_trading_pair_symbols_from_exchange_info(exchange_info=exchange_info)
            self._update_precision_maps(exchange_info)
        except Exception:
            self.logger().exception("There was an error requesting exchange info.")

    def _update_precision_maps(self, exchange_info: Dict[str, Any]):
        for symbol_data in filter(coinstore_utils.is_exchange_information_valid, exchange_info["data"]):
            trading_pair = coinstore_utils.convert_from_exchange_to_trading_pair(symbol_data)
            if trading_pair is not None:
                self._price_precision_map[trading_pair] = int(symbol_data["tickSz"])
                self._amount_precision_map[trading_pair] = int(symbol_data["lotSz"])


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
            throttler=self._throttler, auth=self._auth
        )

    async def _format_trading_rules(self, exchange_info: Dict[str, Any]) -> List[TradingRule]:
        trading_rules = []
        for symbol_data in filter(coinstore_utils.is_exchange_information_valid, exchange_info["data"]):
            try:
                trading_pair = coinstore_utils.convert_from_exchange_to_trading_pair(symbol_data)
                if trading_pair is None:
                    self.logger().error(f"Error parsing the trading pair rule {symbol_data}. Skipping.")
                    continue
                trading_rules.append(
                    TradingRule(
                        trading_pair=trading_pair,
                        min_order_size=Decimal("1e-4"),
                        min_price_increment=Decimal("1e-8"),
                        min_base_amount_increment=Decimal("1e-8"),
                        min_notional_size=Decimal("0"),
                        supports_market_orders=False,
                    )
                )
            except Exception:
                self.logger().error(f"Error parsing the trading pair rule {symbol_data}. Skipping.", exc_info=True)
        return trading_rules
    
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
        path_url = CONSTANTS.ORDER_PATH_URL
        side = "BUY" if trade_type is TradeType.BUY else "SELL"
        order_type_str = CONSTANTS.ORDER_TYPE_MAP[order_type]
        symbol = coinstore_utils.convert_to_exchange_trading_pair(trading_pair)
        timestamp = int(self._time_synchronizer.time() * 1000)

        # Handle precision for price and amount
        price_precision = self.get_price_precision(trading_pair)
        amount_precision = self.get_amount_precision(trading_pair)
        price_str = f"{price:.{price_precision}f}"
        amount_str = f"{amount:.{amount_precision}f}"

        data = {
            "symbol": symbol,
            "side": side,
            "ordType": order_type_str,
            "ordQty": amount_str,
            "ordPrice": price_str,
            "timestamp": timestamp,
        }

        # if order_type is OrderType.LIMIT:
        #     data["ordPrice"] = price_str
        # elif order_type is OrderType.MARKET:
        #     if trade_type is TradeType.BUY:
        #         data["ordAmt"] = amount_str
        # For SELL, we keep ordQty

        if order_id:
            data["clOrdId"] = order_id

        # self.logger().info(f"Placing order: {data}")
        
        exchange_order = await self._api_post(
            path_url=path_url,
            data=data,
            is_auth_required=True
        )
        
        # self.logger().info(f"Order placed: {exchange_order}")
        
        if "data" in exchange_order and "ordId" in exchange_order["data"]:
            return str(exchange_order["data"]["ordId"]), self.current_timestamp
        else:
            raise ValueError(f"Unexpected response format: {exchange_order}")

    # Helper methods for precision (implement these in your class)
    def get_price_precision(self, trading_pair: str) -> int:
        return self._price_precision_map.get(trading_pair, 8)  # Default to 8 if not found

    def get_amount_precision(self, trading_pair: str) -> int:
        return self._amount_precision_map.get(trading_pair, 8)  # Default to 8 if not found


    async def _place_cancel(self, order_id: str, tracked_order: InFlightOrder):
        symbol = coinstore_utils.convert_to_exchange_trading_pair(tracked_order.trading_pair)
        cancel_result = await self._api_post(
            path_url=CONSTANTS.CANCEL_ORDER_PATH_URL,
            data={
                "symbol": symbol,
                "ordId": tracked_order.exchange_order_id,
            },
            is_auth_required=True
        )
        return cancel_result.get("code", None) == 0

    async def _user_stream_event_listener(self):
        async for event_message in self._iter_user_event_queue():
            try:
                await self._process_user_stream_event(event_message)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().exception("Unexpected error in user stream listener loop.")
                await asyncio.sleep(1)

    async def _process_user_stream_event(self, event: Dict[str, Any]):
        try:
            if "open_orders" in event:
                await self._process_open_orders_event(event["open_orders"])
            if "completed_orders" in event:
                await self._process_completed_orders_event(event["completed_orders"])
            if "balance" in event:
                self._process_balance_event(event["balance"])
        except Exception:
            self.logger().error("Unexpected error in user stream event processing.", exc_info=True)


    async def _process_open_orders_event(self, open_orders: List[Dict[str, Any]]):
        for order_data in open_orders:
            exchange_order_id = str(order_data.get("ordId"))
            client_order_id = order_data.get("clOrdId")
            # self.logger().info(f"Processing open orders event for {client_order_id} with exchange order ID {exchange_order_id}")
            if client_order_id is not None:
                tracked_order = self._order_tracker.all_updatable_orders.get(client_order_id)
                if tracked_order is not None:
                    order_update = OrderUpdate(
                        client_order_id=client_order_id,
                        exchange_order_id=exchange_order_id,
                        trading_pair=tracked_order.trading_pair,
                        update_timestamp=self.current_timestamp,
                        new_state=self._get_order_state(order_data),
                    )
                    self._order_tracker.process_order_update(order_update)

    async def _process_completed_orders_event(self, completed_orders: List[Dict[str, Any]]):
        for order_data in completed_orders:
            exchange_order_id = str(order_data.get("ordId"))
            client_order_id = order_data.get("clOrdId")

            if client_order_id is not None:
                tracked_order = self._order_tracker.all_updatable_orders.get(client_order_id)
                if tracked_order is not None:
                    # self.logger().info(f"Processing completed orders event for {client_order_id} with exchange order ID {exchange_order_id}")
                    order_update = OrderUpdate(
                        client_order_id=client_order_id,
                        exchange_order_id=exchange_order_id,
                        trading_pair=tracked_order.trading_pair,
                        update_timestamp=self.current_timestamp,
                        new_state=self._get_order_state(order_data),
                    )
                    self._order_tracker.process_order_update(order_update)

                    trade_update = TradeUpdate(
                        trade_id=str(order_data.get("tradeId")),
                        client_order_id=client_order_id,
                        exchange_order_id=exchange_order_id,
                        trading_pair=tracked_order.trading_pair,
                        fee=self.get_fee(
                            base_currency=tracked_order.base_asset,
                            quote_currency=tracked_order.quote_asset,
                            order_type=tracked_order.order_type,
                            trade_type=tracked_order.trade_type,
                            price=Decimal(order_data.get("ordPrice", "0")),
                            amount=Decimal(order_data.get("ordQty", "0")),
                        ),
                        fill_price=Decimal(order_data.get("ordPrice", "0")),
                        fill_base_amount=Decimal(order_data.get("ordQty", "0")),
                        fill_quote_amount=Decimal(order_data.get("ordQty", "0")) * Decimal(order_data.get("ordPrice", "0")),
                        fill_timestamp=int(order_data.get("timestamp", self.current_timestamp)),
                    )
                    self._order_tracker.process_trade_update(trade_update)

    def _process_balance_event(self, balance_data: List[Dict[str, Any]]):
        for balance_entry in balance_data:
            asset_name = balance_entry["currency"]
            self._account_balances[asset_name] = Decimal(balance_entry["balance"])
            self._account_available_balances[asset_name] = Decimal(balance_entry["balance"]) - Decimal(balance_entry.get("locked_amount", "0"))

    async def _update_trading_rules(self):
        exchange_info = await self._make_trading_rules_request()
        trading_rules_list = await self._format_trading_rules(exchange_info)
        self._trading_rules.clear()
        for trading_rule in trading_rules_list:
            self._trading_rules[trading_rule.trading_pair] = trading_rule
        self._initialize_trading_pair_symbols_from_exchange_info(exchange_info=exchange_info)
        self._update_precision_maps(exchange_info)


    async def _update_trading_fees(self):
        """
        Update fees information from the exchange
        """
        for trading_pair in self._trading_pairs:
            self._trading_fees[trading_pair] = {"maker": CONSTANTS.DEFAULT_FEE, "taker": CONSTANTS.DEFAULT_FEE}


    async def _process_account_position(self, account_position: Dict[str, Any]):
        for balance_entry in account_position.get("B", []):
            asset_name = balance_entry["a"]
            free_balance = Decimal(balance_entry["f"])
            total_balance = Decimal(balance_entry["f"]) + Decimal(balance_entry["l"])
            self._account_balances[asset_name] = total_balance
            self._account_available_balances[asset_name] = free_balance

    def _get_order_state(self, order_data: Dict[str, Any]) -> OrderState:
        status = order_data.get("ordStatus", "").upper()
        if status == "FILLED":
            return OrderState.COMPLETED # or FILLED?
        elif status == "CANCELED":
            return OrderState.CANCELED
        elif status == "REJECTED":
            return OrderState.FAILED
        elif status == "PARTIAL_FILLED":
            return OrderState.PARTIALLY_FILLED
        elif status == "SUBMITTED":
            return OrderState.OPEN
        else:
            return OrderState.OPEN

    async def _all_trade_updates_for_order(self, order: InFlightOrder) -> List[TradeUpdate]:
        trade_updates = []
        # self.logger().info(f"Fetching trade updates for order {order.client_order_id}")
        try:
            exchange_order_id = await order.get_exchange_order_id()
            symbol = coinstore_utils.convert_to_exchange_trading_pair(order.trading_pair)
            
            all_fills_response = await self._api_get(
                path_url=CONSTANTS.MY_TRADES_PATH_URL,
                params={
                    "symbol": symbol,
                    "ordId": exchange_order_id,
                    "pageSize": self.ORDER_PAGE_LIMIT
                },
                is_auth_required=True
            )
            
            if "data" not in all_fills_response:
                self.logger().error(f"Error fetching trades for order {exchange_order_id}: {all_fills_response}")
                
            for trade in all_fills_response["data"]:
                fee = TradeFeeBase.new_spot_fee(
                    fee_schema=self.trade_fee_schema(),
                    trade_type=order.trade_type,
                    percent_token="",
                    flat_fees=[]
                )
                trade_update = TradeUpdate(
                    trade_id=str(trade["id"]),
                    client_order_id=order.client_order_id,
                    exchange_order_id=exchange_order_id,
                    trading_pair=order.trading_pair,
                    fee=fee,
                    fill_base_amount=Decimal(trade["execQty"]),
                    fill_quote_amount=Decimal(trade["execAmt"]),
                    fill_price=Decimal(trade["execAmt"]) / Decimal(trade["execQty"]),
                    fill_timestamp=int(trade["matchTime"] * 1e-3),
                )
                trade_updates.append(trade_update)
                        

        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger().error(f"Failed to fetch trade updates for order {order.client_order_id}. Error: {str(e)}")
            self.logger().network(
                "Unexpected error while fetching trade updates.",
                exc_info=True,
                app_warning_msg=f"Failed to fetch trade updates for order {order.client_order_id}. "
                                f"Check API key and network connection."
            )
        
        return trade_updates

    async def _request_order_status(self, tracked_order: InFlightOrder) -> OrderUpdate:
        exchange_order_id = await tracked_order.get_exchange_order_id()
        updated_order_data = await self._api_get(
            path_url=CONSTANTS.GET_ORDER_PATH_URL,
            params={
                "ordId": exchange_order_id
            },
            is_auth_required=True
        )
        if not "data" in updated_order_data:
            self.logger().error(f"No data found in the response for order status update.")
            return
        
        new_state = CONSTANTS.ORDER_STATE[updated_order_data["data"]["ordStatus"].upper()]

        order_update = OrderUpdate(
            client_order_id=tracked_order.client_order_id,
            exchange_order_id=exchange_order_id,
            trading_pair=tracked_order.trading_pair,
            update_timestamp=self.current_timestamp,
            new_state=new_state,
        )

        return order_update

    async def _make_trading_pairs_request(self) -> Any:
        exchange_info = await self._api_post(path_url=self.trading_pairs_request_path, is_auth_required=True)
        return exchange_info
    
    async def _make_trading_rules_request(self) -> Any:
        exchange_info = await self._api_post(path_url=self.trading_pairs_request_path, is_auth_required=True)
        return exchange_info
    
    async def _api_request(
            self,
            path_url,
            overwrite_url: Optional[str] = None,
            method: RESTMethod = RESTMethod.GET,
            params: Optional[Dict[str, Any]] = None,
            data: Optional[Dict[str, Any]] = None,
            is_auth_required: bool = False,
            return_err: bool = False,
            limit_id: Optional[str] = None,
            headers: Optional[Dict[str, Any]] = None,
            **kwargs,
    ) -> Dict[str, Any]:
        url = overwrite_url or await self._api_request_url(path_url=path_url, is_auth_required=is_auth_required)
        # self.logger().info(f"URL: {url} - headers: {headers} - params: {params} - data: {data} - method: {method} - is_auth_required: {is_auth_required} - return_err: {return_err} - limit_id: {limit_id}") 
        
        try:
            headers = headers or {}
            
            local_headers = {
            "Content-Type": ("application/json" if method != RESTMethod.GET else "application/x-www-form-urlencoded")}

            local_headers.update(headers)

            payload = json.dumps(data or {})

            request = RESTRequest(
                method=method,
                url=url,
                params=params,
                data=data,
                headers=local_headers,
                is_auth_required=is_auth_required,
                throttler_limit_id=limit_id
            )
            if is_auth_required:
                request = await self.authenticator.rest_authenticate(request)

            async with aiohttp.ClientSession() as session:
                if method == RESTMethod.POST:
                    async with session.post(
                        url=request.url,
                        headers=request.headers,
                        data=payload
                    ) as response:
                        # self.logger().info(f"Status: {response.status}")
                        if response.status != 200:
                            error_response = await response.text()
                            self.logger().error(f"Error response: {error_response}")
                            raise Exception(f"Error response: {error_response}")
                        return await response.json()
                elif method == RESTMethod.GET:
                    request_url = request.url + "?" + urlencode(request.params or {})
                    async with session.get(
                        url=request_url,
                        headers=request.headers
                    ) as response:
                        # self.logger().info(f"Status: {response.status}")
                        if response.status != 200:
                            error_response = await response.text()
                            self.logger().error(f"Error response: {error_response}")
                            raise Exception(f"Error response: {error_response}")
                        return await response.json()

        except IOError as request_exception:
            last_exception = request_exception
            if self._is_request_exception_related_to_time_synchronizer(request_exception=request_exception):
                self._time_synchronizer.clear_time_offset_ms_samples()
                await self._update_time_synchronizer()
            else:
                raise

    async def _update_balances(self):
        local_asset_names = set(self._account_balances.keys())
        remote_asset_names = set()
        try:
            account_info = await self._api_post(
                path_url=CONSTANTS.ACCOUNTS_PATH_URL,
                is_auth_required=True
            )
            
            if account_info.get("code") != 0:
                self.logger().error(f"Error updating balances: {account_info.get('message')}")
                return

            balance_dict = {}

            for balance_entry in account_info["data"]:
                asset_name = balance_entry["currency"]
                balance_type = balance_entry["typeName"]
                balance = Decimal(balance_entry["balance"])

                if asset_name not in balance_dict:
                    balance_dict[asset_name] = {"FROZEN": Decimal("0"), "AVAILABLE": Decimal("0")}

                balance_dict[asset_name][balance_type] = balance
                        
            for asset_name, balances in balance_dict.items():
                free_balance = balances["AVAILABLE"]
                frozen_balance = balances["FROZEN"]
                total_balance = free_balance + frozen_balance

                self._account_available_balances[asset_name] = free_balance
                self._account_balances[asset_name] = total_balance
                remote_asset_names.add(asset_name)

            asset_names_to_remove = local_asset_names.difference(remote_asset_names)
            for asset_name in asset_names_to_remove:
                del self._account_available_balances[asset_name]
                del self._account_balances[asset_name]
        except Exception as e:
            self.logger().error(f"Error updating balances: {str(e)}", exc_info=True)
            
    def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: Dict[str, Any]):
        mapping = bidict()
        for symbol_data in filter(coinstore_utils.is_exchange_information_valid, exchange_info["data"]):
            trading_pair = coinstore_utils.convert_from_exchange_to_trading_pair(symbol_data)
            if trading_pair is None:
                continue
            mapping[symbol_data["symbolCode"]] = trading_pair
        self._set_trading_pair_symbol_map(mapping)

    async def _get_last_traded_price(self, trading_pair: str) -> float:
        params = {
            "symbol": trading_pair,
        }

        resp_json = await self._api_get(
            path_url=CONSTANTS.TICKER_PRICE_CHANGE_PATH_URL,
            params=params,
        )

        return float(resp_json["data"][0]["close"])
    
    async def stop_network(self):
        await super().stop_network()
        await self._http_client.close()