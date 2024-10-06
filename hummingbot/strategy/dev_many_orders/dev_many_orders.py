import logging
from decimal import Decimal
from typing import List, Tuple

import numpy as np
import pandas as pd

from hummingbot.core.clock import Clock
from hummingbot.core.data_type.common import OrderType, PriceType, TradeType
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.core.data_type.order_candidate import OrderCandidate
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from hummingbot.strategy.strategy_py_base import StrategyPyBase

dev_logger = None


class DevManyOrders(StrategyPyBase):

    _price_levels_to_display = 15

    @classmethod
    def logger(cls):
        global dev_logger
        if dev_logger is None:
            dev_logger = logging.getLogger(__name__)
        return dev_logger

    def __init__(
            self,
            market: MarketTradingPairTuple,
            n_levels_bid: int,
            n_levels_ask: int,
            price_level_pct_step_bid: Decimal,
            price_level_pct_step_ask: Decimal,
            bid_size: Decimal,
            ask_size: Decimal,
            bid_spread: Decimal,
            ask_spread: Decimal,
            refresh_time: int) -> None:
        super().__init__()
        self._market = market
        self._trading_pair = self._market.trading_pair
        self._base_asset, self._quote_asset = self._trading_pair.split("-")
        self._exchange = self._market.market
        self._n_levels_bid = n_levels_bid
        self._n_levels_ask = n_levels_ask
        self._price_level_pct_step_bid = price_level_pct_step_bid
        self._price_level_pct_step_ask = price_level_pct_step_ask
        self._bid_size = bid_size
        self._ask_size = ask_size
        self._bid_spread = bid_spread
        self._ask_spread = ask_spread
        self._next_timestamp_to_replace_orders = 0
        self._refresh_time = refresh_time
        self._expiration_seconds = refresh_time * 2
        self._ready = False
        self.add_markets([self._market.market])

    @property
    def active_orders(self) -> List[LimitOrder]:
        return [o[1] for o in self.order_tracker.active_limit_orders]

    def _quantize_amount(self, amount: Decimal) -> Decimal:
        return self._market.market.quantize_order_amount(self._market.trading_pair, amount)

    def _quantize_price(self, price: Decimal) -> Decimal:
        return self._market.market.quantize_order_price(self._market.trading_pair, price)

    def start(self, clock: Clock, timestamp: float):
        self._next_timestamp_to_replace_orders = timestamp

    def tick(self, timestamp: float) -> None:
        if self._ready:
            self._execute_strategy(timestamp=timestamp)
        else:
            self._check_exchange_status()

    def _check_exchange_status(self) -> None:
        exchange = self._market.market
        if not exchange.ready:
            self.logger().warning(f"{exchange.name} is not ready. Please wait...")
        else:
            self._ready = True
            self.logger().warning(f"{exchange.name} is ready!")

    def _execute_strategy(self, timestamp: float) -> None:
        if timestamp >= self._next_timestamp_to_replace_orders:
            self._cancel_all_orders()
            self._open_new_orders()
            self._next_timestamp_to_replace_orders = timestamp + self._refresh_time

    def _open_new_orders(self) -> None:
        order_candidates = self._create_orders()
        self._send_orders(order_candidates=order_candidates)

    def _create_orders(self) -> List[OrderCandidate]:
        best_bid = self._market.get_price_by_type(PriceType.BestBid)
        best_ask = self._market.get_price_by_type(PriceType.BestAsk)
        mid_price = Decimal((best_bid + best_ask) / 2)
        bid_orders = [
            OrderCandidate(
                trading_pair=self._market.trading_pair,
                is_maker=True,
                order_type=OrderType.LIMIT_MAKER,
                order_side=TradeType.BUY,
                amount=self._quantize_amount(amount=self._bid_size),
                price=self._quantize_price(
                    price=mid_price * (Decimal(1 - self._bid_spread - Decimal(i) * self._price_level_pct_step_bid))))
            for i in range(self._n_levels_bid)]
        ask_orders = [
            OrderCandidate(
                trading_pair=self._market.trading_pair,
                is_maker=True,
                order_type=OrderType.LIMIT_MAKER,
                order_side=TradeType.SELL,
                amount=self._quantize_amount(amount=self._bid_size),
                price=self._quantize_price(
                    price=mid_price * (Decimal(1 + self._bid_spread + Decimal(i) * self._price_level_pct_step_bid))))
            for i in range(self._n_levels_ask)]
        return bid_orders + ask_orders

    def _send_orders(self, order_candidates: List[OrderCandidate]) -> None:
        for order_candidate in order_candidates:
            if order_candidate.order_side == TradeType.BUY:
                _ = self.buy_with_specific_market(
                    self._market,
                    amount=order_candidate.amount,
                    order_type=order_candidate.order_type,
                    price=order_candidate.price,
                    expiration_seconds=self._expiration_seconds)
            elif order_candidate.order_side == TradeType.SELL:
                _ = self.sell_with_specific_market(
                    self._market,
                    amount=order_candidate.amount,
                    order_type=order_candidate.order_type,
                    price=order_candidate.price,
                    expiration_seconds=self._expiration_seconds)

    def _cancel_all_orders(self) -> None:
        active_orders = self.active_orders
        for order in active_orders:
            self.cancel_order(self._market, order.client_order_id)

    def format_status(self, *args, **kwargs) -> str:
        """
        Returns a summary view of the current orderbook and of the provided liquidity. Price levels
        including active orders are starred (*); their size is indicated after the "-->" symbol.

        :return: orderbook view and information on the provided liquidity
        :rtype: string
        """
        orderbook = self._market.market.get_order_book(self._market.trading_pair).snapshot
        active_orders: List[LimitOrder] = [o[1] for o in self.order_tracker.active_limit_orders]
        msg = "```\nOrderbook:\n" + "\n" + self._display_orderbook(orderbook=orderbook, active_orders=active_orders)
        buy_orders = [order for order in active_orders if order.is_buy]
        number_of_active_buy_orders = len(buy_orders)
        liquidity_in_buy = sum([order.quantity for order in buy_orders])
        volume_in_buy = sum([order.quantity * order.price for order in buy_orders])
        sell_orders = [order for order in active_orders if not order.is_buy]
        number_of_active_sell_orders = len(sell_orders)
        liquidity_in_sell = sum([order.quantity for order in sell_orders])
        volume_in_sell = sum([order.quantity * order.price for order in sell_orders])
        best_ask = self._market.get_price_by_type(PriceType.BestAsk)
        best_bid = self._market.get_price_by_type(PriceType.BestBid)
        spread = self._market.market.quantize_order_price(self._market.trading_pair, (best_ask - best_bid) / best_ask * Decimal("100"))
        msg += "\nSummary:\n" \
               f"spread: {str(spread).rstrip('0')}%\n" \
               f"active orders in buy: {number_of_active_buy_orders}\nliquidity in bid: {str(liquidity_in_buy).rstrip('0')} {self._base_asset} --- {str(volume_in_buy).rstrip('0')} {self._quote_asset}\n" \
               f"active orders in sell: {number_of_active_sell_orders}\nliquidity in ask: {str(liquidity_in_sell).rstrip('0')} {self._base_asset} --- {str(volume_in_sell).rstrip('0')} {self._quote_asset}\n" + "```"
        return msg

    def _display_orderbook(self, orderbook: Tuple[pd.DataFrame, pd.DataFrame], active_orders: [LimitOrder]) -> str:
        """
        Formats the orderbook for the format_status method.

        :param orderbook: A tuple of dataframes returned by self._market.market.get_order_book(self._market.trading_pair).snapshot,
            -- bids, asks = orderbook[0], orderbook[1]
        :type orderbook: tuple of pd.DataFrame
        :param active_orders: A list of active limit orders
        :type active_orders: list of LimitOrder
        :return: Formatted orderbook ready to be displayed by the format_status method
        :rtype: str
        """
        selling_orders = [order for order in active_orders if not order.is_buy]
        bids: pd.DataFrame = orderbook[0].iloc[:self._price_levels_to_display, :].copy()
        asks: pd.DataFrame = orderbook[1].iloc[:self._price_levels_to_display, :].copy()
        asks.drop("update_id", inplace=True, axis=1)
        asks["total"] = asks["amount"].cumsum()
        asks[""] = asks["price"].isin([float(order.price) for order in selling_orders])
        asks[""] = np.where(asks[""], "*", "")
        asks = self._add_order_size_to_orderbook_side(orderbook_side=asks, orders=selling_orders)
        buying_orders = [order for order in active_orders if order.is_buy]
        bids.drop("update_id", inplace=True, axis=1)
        bids["total"] = bids["amount"].cumsum()
        bids[""] = bids["price"].isin([float(order.price) for order in buying_orders])
        bids[""] = np.where(bids[""], "*", "")
        bids = self._add_order_size_to_orderbook_side(orderbook_side=bids, orders=buying_orders)
        bids.columns = [" " * 5, " " * 6, " " * 5, " ", "  "]
        msg = asks.reindex(index=asks.index[::-1]).to_string(index=False) + "\n" + bids.to_string(index=False) + "\n"
        return msg

    @staticmethod
    def _add_order_size_to_orderbook_side(orderbook_side: pd.DataFrame, orders: List) -> pd.DataFrame:
        own_size_column = []
        for idx, row in orderbook_side.iterrows():
            if row[""] == "*":
                price = row["price"]
                own_size = Decimal("0")
                for order in orders:
                    if float(order.price) == price:
                        own_size += order.quantity
                        if not order.filled_quantity.is_nan():
                            own_size -= order.filled_quantity
                own_size_column.append(f"--> {str(own_size).rstrip('0')}")
            else:
                own_size_column.append("")
        orderbook_side[" "] = own_size_column
        return orderbook_side
