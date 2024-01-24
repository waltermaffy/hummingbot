from typing import Any, Dict, Optional

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

        # snapshot = msg.get("snapshot", {})
        # symbol = list(snapshot.keys())[0]
        # data = snapshot[symbol]

        return OrderBookMessage(
            OrderBookMessageType.SNAPSHOT,
            {
                "trading_pair": msg.get("trading_pair"),
                "update_id": timestamp, 
                "bids": msg["bid"], 
                "asks": msg["ask"]
            },
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

        data = cls._get_data_from_message(msg)
        symbol = list(data.keys())[0]
        data = data[symbol]
        
        ts = data["t"] if not timestamp else timestamp
        return OrderBookMessage(
            OrderBookMessageType.DIFF,
            {
                "trading_pair": msg.get("trading_pair"),
                "update_id": data["s"],
                "bids": data["b"],
                "asks": data["a"],
            },
            timestamp=ts,
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
        data = cls._get_data_from_message(msg)

        symbol = list(data.keys())[0]
        trade_data = data[symbol][0]
        ts = trade_data["t"]
        seq_num = trade_data["s"]
        trade_type = TradeType.BUY if trade_data["s"] == "buy" else TradeType.SELL

        return OrderBookMessage(
            OrderBookMessageType.TRADE,
            {
                "trading_pair": msg.get("trading_pair"),
                "trade_type": trade_type,
                "trade_id": trade_data["i"],
                "update_id": seq_num,
                "price": trade_data["p"],
                "amount": trade_data["q"],
            },
            timestamp=ts,
        )

    @classmethod
    def _get_data_from_message(cls, msg: Dict[str, Any]) -> Dict[str, Any]:
        data = {}
        if "update" in msg:
            data = msg.get("update", {})
        elif "snapshot" in msg:
            data = msg.get("snapshot", {})
        else:
            data = msg
        return data