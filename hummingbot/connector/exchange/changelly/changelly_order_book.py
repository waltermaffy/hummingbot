from typing import Dict, Optional, Any

from hummingbot.core.data_type.common import TradeType
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType


class ChangellyOrderBook(OrderBook):
    @classmethod
    def snapshot_message_from_exchange(
        cls, msg: Dict[str, Any], timestamp: float, metadata: Optional[Dict] = None
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

        snapshot = msg.get("snapshot", {})
        symbol = list(snapshot.keys())[0]
        data = snapshot[symbol]

        return OrderBookMessage(
            OrderBookMessageType.SNAPSHOT,
            {"trading_pair": symbol, "update_id": data["t"], "bids": data["b"], "asks": data["a"]},
            timestamp=timestamp,
        )

    @classmethod
    def snapshot_message_from_exchange_rest(
        cls, msg: Dict[str, Any], timestamp: float, metadata: Optional[Dict] = None
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

        return OrderBookMessage(
            OrderBookMessageType.SNAPSHOT,
            {
                "trading_pair": msg.get("trading_pair"),
                "update_id": timestamp,
                "bids": msg.get("bid"),
                "asks": msg.get["ask"],
            },
            timestamp=timestamp,
        )

    @classmethod
    def diff_message_from_exchange(
        cls, msg: Dict[str, Any], timestamp: Optional[float] = None, metadata: Optional[Dict] = None
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

        # Assuming 'update' key contains the diff data
        update = msg.get("update", {})
        symbol = list(update.keys())[0]
        data = update[symbol][0]

        return OrderBookMessage(
            OrderBookMessageType.DIFF,
            {"trading_pair": symbol, "update_id": data["t"], "bids": data["b"], "asks": data["a"]},
            timestamp=data["t"],
        )

    @classmethod
    def trade_message_from_exchange(cls, msg: Dict[str, Any], metadata: Optional[Dict] = None):
        """
        Creates a trade message with the information from the trade event sent by the exchange
        :param msg: the trade event details sent by the exchange
        :param metadata: a dictionary with extra information to add to trade message
        :return: a trade message with the details of the trade as provided by the exchange
        """
        if metadata:
            msg.update(metadata)

        # Extracting trade data from the message
        update = msg.get("update", {})
        symbol = list(update.keys())[0]
        trade_data = update[symbol][0]
        ts = trade_data["t"]
        trade_type = TradeType.BUY if trade_data["s"] == "buy" else TradeType.SELL

        return OrderBookMessage(
            OrderBookMessageType.TRADE,
            {
                "trading_pair": symbol,
                "trade_type": trade_type,
                "trade_id": trade_data["i"],
                "update_id": ts,
                "price": trade_data["p"],
                "amount": trade_data["q"],
            },
            timestamp=ts,
        )
