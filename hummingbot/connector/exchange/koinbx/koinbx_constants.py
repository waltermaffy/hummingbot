from hummingbot.core.api_throttler.data_types import LinkedLimitWeightPair, RateLimit
from hummingbot.core.data_type.in_flight_order import OrderState

HBOT_ORDER_ID_PREFIX = "x-XEKWYICX"
MAX_ORDER_ID_LEN = 32

TEST_PAIR = "ORBS_USDT"
TEST_MODE = True
DEFAULT_FEE = 0.0025
# Base URLs
DEFAULT_DOMAIN = "com"
PUBLIC_REST_URL = "https://api.koinbx.com"
PRIVATE_REST_URL = "https://trademmbx.koinbx.com"

MAX_RETRIES = 6
RETRY_INTERVAL = 10
EXPONENTIAL_BACKOFF = 0.1

# Public API endpoints
# PING_PATH_URL = "/orderbook?market_pair=ETH_BTC"
PING_PATH_URL = "/asset"
ASSET_PATH_URL = "/asset"
MAKETS_PATH_URL = "/markets"
TICKER_PATH_URL = "/ticker"

# Orderbook API endpoints
ORDERBOOK_PATH_URL = "/orderbook"
TRADES_PATH_URL = "/trades"

# Balance
BALANCE_PATH_URL = "/v1/mm/getbalance"

# Private API endpoints
ORDER_BOOK_PRIVATE_PATH_URL = "/v1/mm/orderbook"
TRADE_HISTORY_PATH_URL = "/v1/mm/tradehistory"
GET_ORDER_PATH_URL = "/v1/mm/getOrder"
ORDER_PATH_URL = "/v1/mm/placeorder"
OPEN_ORDERS_PATH_URL = "/v1/mm/openOrders"
COMPLETED_ORDERS_PATH_URL = "/v1/mm/getCompletedOrders"
CANCEL_ORDER_PATH_URL = "/v1/mm/cancelOrder"


# Order States
ORDER_STATE = {
    "active": OrderState.OPEN,
    "filled": OrderState.FILLED,
    "partially_filled": OrderState.PARTIALLY_FILLED,
    "cancelled": OrderState.CANCELED,
    "rejected": OrderState.FAILED,
}

# Rate Limit time intervals
MAX_REQUEST = 5000
ONE_MINUTE = 60
ONE_SECOND = 1
ONE_DAY = 86400
REQUEST_WEIGHT = "REQUEST_WEIGHT"
RAW_REQUESTS = "RAW_REQUESTS"

RATE_LIMITS = [
    RateLimit(limit_id="default", limit=30, time_interval=1),
    # Weighted Limits
    RateLimit(
        limit_id=PING_PATH_URL,
        limit=MAX_REQUEST,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 20), LinkedLimitWeightPair(RAW_REQUESTS, 30)],
    ),
    RateLimit(
        limit_id=MAKETS_PATH_URL,
        limit=MAX_REQUEST,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 20), LinkedLimitWeightPair(RAW_REQUESTS, 30)],
    ),
    RateLimit(
        limit_id=ORDERBOOK_PATH_URL,
        limit=MAX_REQUEST,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 20), LinkedLimitWeightPair(RAW_REQUESTS, 30)],
    ),
    RateLimit(
        limit_id=TRADES_PATH_URL,
        limit=MAX_REQUEST,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 20), LinkedLimitWeightPair(RAW_REQUESTS, 30)],
    ),
    RateLimit(
        limit_id=BALANCE_PATH_URL,
        limit=MAX_REQUEST,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 20), LinkedLimitWeightPair(RAW_REQUESTS, 30)],
    ),
    RateLimit(
        limit_id=ORDER_BOOK_PRIVATE_PATH_URL,
        limit=MAX_REQUEST,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 20), LinkedLimitWeightPair(RAW_REQUESTS, 30)],
    ),
    RateLimit(
        limit_id=TRADE_HISTORY_PATH_URL,
        limit=MAX_REQUEST,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 20), LinkedLimitWeightPair(RAW_REQUESTS, 30)],
    ),
    RateLimit(
        limit_id=GET_ORDER_PATH_URL,
        limit=MAX_REQUEST,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 20), LinkedLimitWeightPair(RAW_REQUESTS, 30)],
    ),
    RateLimit(
        limit_id=ORDER_PATH_URL,
        limit=MAX_REQUEST,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 20), LinkedLimitWeightPair(RAW_REQUESTS, 30)],
    ),
    RateLimit(
        limit_id=OPEN_ORDERS_PATH_URL,
        limit=MAX_REQUEST,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 20), LinkedLimitWeightPair(RAW_REQUESTS, 30)],
    ),
    RateLimit(
        limit_id=COMPLETED_ORDERS_PATH_URL,
        limit=MAX_REQUEST,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 20), LinkedLimitWeightPair(RAW_REQUESTS, 30)],
    ),
    RateLimit(
        limit_id=CANCEL_ORDER_PATH_URL,
        limit=MAX_REQUEST,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 20), LinkedLimitWeightPair(RAW_REQUESTS, 30)],
    ),
    RateLimit(
        limit_id=ASSET_PATH_URL,
        limit=MAX_REQUEST,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 20), LinkedLimitWeightPair(RAW_REQUESTS, 30)],
    ),
    RateLimit(
        limit_id=TICKER_PATH_URL,
        limit=MAX_REQUEST,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 20), LinkedLimitWeightPair(RAW_REQUESTS, 30)],
    ),
]
# RATE_LIMITS = []

DIFF_EVENT_TYPE = "depthUpdate"
TRADE_EVENT_TYPE = "trade"
