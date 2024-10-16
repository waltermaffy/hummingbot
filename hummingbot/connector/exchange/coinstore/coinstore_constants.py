# File: hummingbot/connector/exchange/coinstore/coinstore_constants.py

from hummingbot.core.api_throttler.data_types import RateLimit, LinkedLimitWeightPair
from hummingbot.core.data_type.in_flight_order import OrderState
from hummingbot.core.data_type.common import OrderType, TradeType

EXCHANGE_NAME = "coinstore"
DEFAULT_DOMAIN = "com"

REST_URL = "https://api.coinstore.com/api"
WSS_URL = "wss://ws.coinstore.com/s/ws"
WS_HEARTBEAT_TIME_INTERVAL = 30
DEFAULT_FEE = 0.0025
API_VERSION = "v2"

# REST API endpoints
PING_PATH_URL = "/fi/v1/common/currency"
TICKER_PRICE_CHANGE_PATH_URL = "/v1/market/tickers"
EXCHANGE_INFO_PATH_URL = "/v2/public/config/spot/symbols"
SNAPSHOT_PATH_URL = "/v1/market/depth/{symbol}"
ACCOUNTS_PATH_URL = "/spot/accountList"
ORDER_PATH_URL = "/trade/order/place"
CANCEL_ORDER_PATH_URL = "/trade/order/cancel"
GET_ORDER_PATH_URL = "/trade/order/orderInfo"
MY_TRADES_PATH_URL = "/trade/match/accountMatches"

# New endpoints based on the documentation
BALANCE_PATH_URL = "/spot/accountList"
OPEN_ORDERS_PATH_URL = "/v2/trade/order/active"
COMPLETED_ORDERS_PATH_URL = "/trade/match/accountMatches"

# WebSocket channels (not used in this implementation, but kept for reference)
DIFF_EVENT_TYPE = "depth"
TRADE_EVENT_TYPE = "trade"

# Order States
ORDER_STATE = {
    "REJECTED": OrderState.FAILED,
    "SUBMITTING": OrderState.PENDING_CREATE,
    "SUBMITTED": OrderState.OPEN,
    "PARTIAL_FILLED": OrderState.PARTIALLY_FILLED,
    "CANCELING": OrderState.OPEN,
    "CANCELED": OrderState.CANCELED,
    "EXPIRED": OrderState.FAILED,
    "STOPPED": OrderState.CANCELED,
    "FILLED": OrderState.FILLED,
}

ORDER_TYPE_MAP = {
    OrderType.LIMIT: "LIMIT",
    OrderType.MARKET: "MARKET",
    OrderType.LIMIT_MAKER: "POST_ONLY",
}

# Rate Limits
RATE_LIMITS = [
    RateLimit(limit_id=PING_PATH_URL, limit=100, time_interval=3),
    RateLimit(limit_id=TICKER_PRICE_CHANGE_PATH_URL, limit=100, time_interval=3),
    RateLimit(limit_id=EXCHANGE_INFO_PATH_URL, limit=100, time_interval=3),
    RateLimit(limit_id=SNAPSHOT_PATH_URL, limit=100, time_interval=3),
    RateLimit(limit_id=ACCOUNTS_PATH_URL, limit=100, time_interval=3),
    RateLimit(limit_id=ORDER_PATH_URL, limit=100, time_interval=3),
    RateLimit(limit_id=CANCEL_ORDER_PATH_URL, limit=100, time_interval=3),
    RateLimit(limit_id=GET_ORDER_PATH_URL, limit=100, time_interval=3),
    RateLimit(limit_id=MY_TRADES_PATH_URL, limit=100, time_interval=3),
    RateLimit(limit_id=BALANCE_PATH_URL, limit=100, time_interval=3),
    RateLimit(limit_id=OPEN_ORDERS_PATH_URL, limit=100, time_interval=3),
    RateLimit(limit_id=COMPLETED_ORDERS_PATH_URL, limit=100, time_interval=3),
]

MAX_ORDER_ID_LEN = 32

# Additional constants
HBOT_ORDER_ID_PREFIX = "hbot"
DEFAULT_DOMAIN = "coinstore.com"
DEFAULT_FEE = 0.001  # 0.1% default fee

# Error codes
ORDER_NOT_EXIST_ERROR_CODE = "-2013"
ORDER_NOT_EXIST_MESSAGE = "Order does not exist"
UNKNOWN_ORDER_ERROR_CODE = "-2011"
UNKNOWN_ORDER_MESSAGE = "Unknown order sent"

# Polling intervals
ORDER_UPDATE_INTERVAL = 10  # seconds
BALANCE_UPDATE_INTERVAL = 30  # seconds
TRADING_FEES_POLLING_INTERVAL = 60 * 60  # 1 hour

# Other constants
TEST_PAIR = "BTCUSDT"
TEST_MODE = False