from unittest import TestCase
from hummingbot.connector.exchange.changelly.changelly_order_book import ChangellyOrderBook
from hummingbot.core.data_type.common import TradeType
from hummingbot.core.data_type.order_book_message import OrderBookMessageType


class ChangellyOrderBookTests(TestCase):
    def test_snapshot_message_from_exchange(self):
        snapshot_message = ChangellyOrderBook.snapshot_message_from_exchange(
            msg={
                "ch": "orderbook/full",
                "snapshot": {
                    "ETHBTC": {
                        "t": 1626866578796,
                        "s": 27617207,
                        "a": [["0.060506", "0"], ["0.060549", "12.6431"], ["0.060570", "0"], ["0.060612", "0"]],
                        "b": [["0.060439", "4.4095"], ["0.060414", "0"], ["0.060407", "7.3349"], ["0.060390", "0"]],
                    }
                },
            },
            timestamp=1626866578.796,
            metadata={"trading_pair": "BTC-USDT"},
        )

        self.assertEqual("BTC-USDT", snapshot_message.trading_pair)
        self.assertEqual(OrderBookMessageType.SNAPSHOT, snapshot_message.type)
        self.assertEqual(1626866578.796, snapshot_message.timestamp)
        self.assertEqual(4, len(snapshot_message.bids))
        self.assertEqual(0.060439, snapshot_message.bids[0].price)
        self.assertEqual(4.4095, snapshot_message.bids[0].amount)
        self.assertEqual(4, len(snapshot_message.asks))
        self.assertEqual(0.060506, snapshot_message.asks[0].price)
        self.assertEqual(0.0, snapshot_message.asks[0].amount)

    def test_diff_message_from_exchange(self):
        diff_message = ChangellyOrderBook.diff_message_from_exchange(
            msg={
                "update": {"BTCUSDT": [{"t": 1626861123552, "b": [["0.060439", "4.4095"]], "a": [["0.060506", "0"]]}]}
            },
            timestamp=1626861123.552,
            metadata={"trading_pair": "BTC-USDT"},
        )

        self.assertEqual("BTC-USDT", diff_message.trading_pair)
        self.assertEqual(OrderBookMessageType.DIFF, diff_message.type)
        self.assertEqual(1626861123.552, diff_message.timestamp)
        self.assertEqual(1, len(diff_message.bids))
        self.assertEqual(0.060439, diff_message.bids[0].price)
        self.assertEqual(4.4095, diff_message.bids[0].amount)
        self.assertEqual(1, len(diff_message.asks))
        self.assertEqual(0.060506, diff_message.asks[0].price)
        self.assertEqual(0.0, diff_message.asks[0].amount)

    def test_trade_message_from_exchange(self):
        trade_message = ChangellyOrderBook.trade_message_from_exchange(
            msg={
                "ch": "trades",
                "update": {
                    "BTCUSDT": [{"t": 1626861123552, "i": 1555634969, "p": "30877.68", "q": "0.00006", "s": "sell"}]
                },
            },
            metadata={"trading_pair": "BTC-USDT"},
        )

        self.assertEqual("BTC-USDT", trade_message.trading_pair)
        self.assertEqual(OrderBookMessageType.TRADE, trade_message.type)
        self.assertEqual(1626861123552, trade_message.timestamp)
        self.assertEqual(1555634969, trade_message.content["trade_id"])
        self.assertEqual(TradeType.SELL, trade_message.content["trade_type"])
        self.assertEqual(30877.68, float(trade_message.content["price"]))
        self.assertEqual(0.00006, float(trade_message.content["amount"]))
