from typing import Dict, Optional

from hummingbot.core.data_type.common import TradeType
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType


class KoinbxOrderBook(OrderBook):

    @classmethod
    def snapshot_message_from_exchange(
        cls, msg: Dict[str, any], timestamp: float, metadata: Optional[Dict] = None
    ) -> OrderBookMessage:
        """
        Creates a snapshot message with the order book snapshot message
        :param msg: the response from the exchange when requesting the order book snapshot
        :param timestamp: the snapshot timestamp
        :param metadata: a dictionary with extra information to add to the snapshot data
        :return: a snapshot message with the snapshot information received from the exchange
        """
        if metadata:
            msg.update(metadata)

        data = msg.get('data', {})
        bids = data.get('bids', [])
        asks = data.get('asks', [])
        update_id = data.get('timestamp', timestamp)
        trading_pair = msg.get('trading_pair')
        content = {
            "trading_pair": trading_pair,
            "update_id": update_id,
            "bids": bids,
            "asks": asks,
        }

        return OrderBookMessage(OrderBookMessageType.SNAPSHOT, content, timestamp)

    @classmethod
    def diff_message_from_exchange(
        cls, msg: Dict[str, any], timestamp: Optional[float] = None, metadata: Optional[Dict] = None
    ) -> OrderBookMessage:
        """
        Creates a diff message with the changes in the order book received from the exchange
        :param msg: the changes in the order book
        :param timestamp: the timestamp of the difference
        :param metadata: a dictionary with extra information to add to the difference data
        :return: a diff message with the changes in the order book notified by the exchange
        """
        if metadata:
            msg.update(metadata)
        return OrderBookMessage(
            OrderBookMessageType.DIFF,
            {"trading_pair": msg["trading_pair"], "update_id": timestamp, "bids": msg["bids"], "asks": msg["asks"]},
            timestamp=timestamp,
        )

    @classmethod
    def trade_message_from_exchange(cls, msg: Dict[str, any], metadata: Optional[Dict] = None):
        """
        Creates a trade message with the information from the trade event sent by the exchange
        :param msg: the trade event details sent by the exchange
        :param metadata: a dictionary with extra information to add to trade message
        :return: a trade message with the details of the trade as provided by the exchange
        """
        if metadata:
            msg.update(metadata)
        trade_id = msg.get('trade_id')
        price = msg.get('price', 0)
        amount = msg.get('amount', 0)
        timestamp = msg.get('timestamp')
        trading_pair = msg.get('trading_pair')

        # Handle missing 'type' field
        trade_type_str = msg.get('type')
        if trade_type_str is None:
            trade_type = TradeType.UNKNOWN
        else:
            trade_type = TradeType.BUY if trade_type_str.lower() == 'buy' else TradeType.SELL

        content = {
            "trade_id": trade_id,
            "trading_pair": trading_pair,
            "trade_type": float(trade_type.value),
            "amount": float(amount),
            "price": float(price),
            "timestamp": timestamp,
        }

        return OrderBookMessage(OrderBookMessageType.TRADE, content, timestamp)
