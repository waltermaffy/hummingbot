# File: hummingbot/connector/exchange/coinstore/coinstore_constants.py

from hummingbot.core.api_throttler.data_types import RateLimit, LinkedLimitWeightPair
from hummingbot.core.data_type.in_flight_order import OrderState

EXCHANGE_NAME = "coinstore"
DEFAULT_DOMAIN = "com"

REST_URL = "https://api.coinstore.com/api"
WSS_URL = "wss://ws.coinstore.com/s/ws"
API_VERSION = "v2"

# REST API endpoints
# PING_PATH_URL = "/fi/v1/common/currency"
PING_PATH_URL = "/fi/v1/common/currency&symbol=btcusdt"
TICKER_PRICE_CHANGE_PATH_URL = "/v1/market/tickers"
EXCHANGE_INFO_PATH_URL = "/v2/public/config/spot/symbols"
SNAPSHOT_PATH_URL = "/v1/market/depth/{symbol}"
ACCOUNTS_PATH_URL = "/spot/accountList"
ORDER_PATH_URL = "/trade/order/place"
CANCEL_ORDER_PATH_URL = "/trade/order/cancel"
GET_ORDER_PATH_URL = "/trade/order/orderInfo"
MY_TRADES_PATH_URL = "/trade/match/accountMatches"

# WebSocket channels
DIFF_EVENT_TYPE = "depth"
TRADE_EVENT_TYPE = "trade"

# Order States
ORDER_STATE = {
    "PENDING": OrderState.PENDING_CREATE,
    "SUBMITTING": OrderState.OPEN,
    "SUBMITTED": OrderState.OPEN,
    "PARTIAL_FILLED": OrderState.PARTIALLY_FILLED,
    "CANCELING": OrderState.OPEN,
    "CANCELED": OrderState.CANCELED,
    "EXPIRED": OrderState.FAILED,
    "STOPPED": OrderState.CANCELED,
    "FILLED": OrderState.FILLED,
}

# Rate Limits
RATE_LIMITS = [
    RateLimit(limit_id=PING_PATH_URL, limit=10, time_interval=1),
    RateLimit(limit_id=TICKER_PRICE_CHANGE_PATH_URL, limit=10, time_interval=1),
    RateLimit(limit_id=EXCHANGE_INFO_PATH_URL, limit=10, time_interval=1),
    RateLimit(limit_id=SNAPSHOT_PATH_URL, limit=10, time_interval=1),
    RateLimit(limit_id=ACCOUNTS_PATH_URL, limit=10, time_interval=1),
    RateLimit(limit_id=ORDER_PATH_URL, limit=100, time_interval=3),
    RateLimit(limit_id=CANCEL_ORDER_PATH_URL, limit=100, time_interval=3),
    RateLimit(limit_id=GET_ORDER_PATH_URL, limit=10, time_interval=1),
    RateLimit(limit_id=MY_TRADES_PATH_URL, limit=10, time_interval=1),
]

MAX_ORDER_ID_LEN = 32