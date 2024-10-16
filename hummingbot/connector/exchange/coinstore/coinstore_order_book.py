from typing import Dict, Optional

from hummingbot.core.data_type.common import TradeType
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import (
    OrderBookMessage,
    OrderBookMessageType
)
from decimal import Decimal

class CoinstoreOrderBook(OrderBook):
    @classmethod
    def snapshot_message_from_exchange(cls,
                                       msg: Dict[str, any],
                                       timestamp: float,
                                       metadata: Optional[Dict] = None) -> OrderBookMessage:
        if metadata:
            msg.update(metadata)
        
        data = msg["data"]
        return OrderBookMessage(
            message_type=OrderBookMessageType.SNAPSHOT,
            content={
                "trading_pair": msg["trading_pair"],
                "update_id": timestamp,
                "bids": data["b"],
                "asks": data["a"]
            },
            timestamp=timestamp
        )

    @classmethod
    def diff_message_from_exchange(cls,
                                   msg: Dict[str, any],
                                   timestamp: Optional[float] = None,
                                   metadata: Optional[Dict] = None) -> OrderBookMessage:
        if metadata:
            msg.update(metadata)
        return OrderBookMessage(
            message_type=OrderBookMessageType.DIFF,
            content={
                "trading_pair": msg["symbol"],
                "update_id": msg.get("lastUpdateId", 0),
                "bids": msg["b"],
                "asks": msg["a"]
            },
            timestamp=timestamp
        )

    @classmethod
    def trade_message_from_exchange(cls, msg: Dict[str, any], metadata: Optional[Dict] = None):
        if metadata:
            msg.update(metadata)
        return OrderBookMessage(
            message_type=OrderBookMessageType.TRADE,
            content={
                "trading_pair": msg["symbol"],
                "trade_type": msg["takerSide"].upper(),
                "trade_id": msg["tradeId"],
                "update_id": msg["seq"],
                "price": Decimal(msg["price"]),
                "amount": Decimal(msg["volume"])
            },
            timestamp=msg["time"]
        )