from datetime import timedelta
from decimal import Decimal


from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple

from .dev_many_orders import DevManyOrders
from .dev_many_orders_config_map import dev_many_orders_config_map as c_map


def start(self):
    try:
        exchange = c_map.get("exchange").value.lower()
        trading_pair = c_map.get("trading_pair").value
        self._initialize_markets([(exchange, [trading_pair])])
        exchange = self.markets[exchange]
        base_asset, quote_asset = trading_pair.split("-")
        market = MarketTradingPairTuple(
            market=exchange,
            trading_pair=trading_pair,
            base_asset=base_asset,
            quote_asset=quote_asset)
        n_levels_bid = c_map.get("n_levels_bid").value
        n_levels_ask = c_map.get("n_levels_ask").value
        price_level_pct_step_bid = Decimal(c_map.get("price_level_pct_step_bid").value) / Decimal("100")
        price_level_pct_step_ask = Decimal(c_map.get("price_level_pct_step_ask").value) / Decimal("100")
        bid_size = Decimal(c_map.get("bid_size").value)
        ask_size = Decimal(c_map.get("ask_size").value)
        bid_spread = Decimal(c_map.get("bid_spread").value) / Decimal("100")
        ask_spread = Decimal(c_map.get("ask_spread").value) / Decimal("100")
        refresh_time = int(c_map.get("refresh_time").value)
        self.strategy = DevManyOrders(
            market=market,
            n_levels_bid=n_levels_bid,
            n_levels_ask=n_levels_ask,
            price_level_pct_step_bid=price_level_pct_step_bid,
            price_level_pct_step_ask=price_level_pct_step_ask,
            bid_size=bid_size,
            ask_size=ask_size,
            bid_spread=bid_spread,
            ask_spread=ask_spread,
            refresh_time=refresh_time)
    except Exception as e:
        self.notify(str(e))
        self.logger().error("Error during initialization.", exc_info=True)
