from hummingbot.core.api_throttler.data_types import LinkedLimitWeightPair, RateLimit
from hummingbot.core.data_type.in_flight_order import OrderState

# Based on https://api.pro.changelly.com/#socket-api-reference
EXCHANGE_NAME = "changelly"
MAX_CONNECTIONS = 100
MAX_ORDER_ID_LEN = 32
HBOT_BROKER_ID = "hummingbot"
HBOT_ORDER_ID = "t-HBOT"
DEFAULT_DOMAIN = "com"

WS_HEARTBEAT_TIME_INTERVAL = 30

# Base URL
REST_URL = "https://api.pro.changelly.com/api/3/public"
WSS_MARKET_URL = "wss://api.pro.changelly.com/api/3/ws/public"
WSS_TRADING_URL = "wss://api.pro.changelly.com/api/3/ws/trading"
WSS_WALLET_URL = "wss://api.pro.changelly.com/api/3/ws/wallet"

PUBLIC_API_VERSION = "v3"

# REST API ENDPOINTS
ORDER_BOOK_PATH = "orderbook"
TRADING_PAIRS_PATH_URL = "symbol"


# SOCKET EVENTS
SNAPSHOT_EVENT_TYPE = "snapshot"
DIFF_EVENT_TYPE = "update"

TRADE_EVENT_TYPE = "trade"
ORDERBOOK_EVENT_TYPE = "orderbook"


# CHANNELS
TRADES_CHANNEL = "trades"
ORDER_BOOK_CHANNEL = "orderbook/full"

# SOCKET API TRADING ENDPOINTS
LOGIN = "login"
SPOT_SUBSCRIBE = "spot_subscribe"
SPOT_UNSUBSCRIBE = "spot_unsubscribe"
SPOT_BALANCE_SUBSCRIBE = "spot_balance_subscribe"
SPOT_BALANCE_UNSUBSCRIBE = "spot_balance_unsubscribe"
SPOT_BALANCES = "spot_balances"
SPOT_FEE = "spot_fee"
SPOT_FEES = "spot_fees"
SPOT_GET_ORDERS = "spot_get_orders"
SPOT_NEW_ORDER = "spot_new_order"
SPOT_NEW_ORDER_LIST = "spot_new_order_list"
SPOT_REPLACE_ORDER = "spot_replace_order"
SPOT_CANCEL_ORDER = "spot_cancel_order"
# SOCKET API WALLET ENDPOINTS
SUBSCRIBE_TRANSACTION = "subscribe_transaction"
UNSUBSCRIBE_TRANSACTION = "unsubscribe_transaction"
SUBSCRIBE_WALLET_BALANCES = "subscribe_wallet_balances"
UNSUBSCRIBE_WALLET_BALANCES = "unsubscribe_wallet_balances"
WALLET_BALANCES = "wallet_balances"
WALLET_BALANCE = "wallet_balance"
TRANSACTIONS = "transactions"


# Changelly params
SIDE_BUY = "buy"
SIDE_SELL = "sell"

# Rate Limit time intervals
ONE_MINUTE = 60
ONE_SECOND = 1
ONE_DAY = 86400

MAX_REQUEST = 5000

# Order States
ORDER_STATE = {
    "PENDING": OrderState.PENDING_CREATE,
    "new": OrderState.OPEN,
    "filled": OrderState.FILLED,
    "partiallyFilled": OrderState.PARTIALLY_FILLED,
    "PENDING_CANCEL": OrderState.OPEN,
    "canceled": OrderState.CANCELED,
    "expired": OrderState.CANCELED,
    "suspended": OrderState.FAILED,
}

TIME_IN_FORCE_GTC = "GTC"  # Good till cancelled
TIME_IN_FORCE_IOC = "IOC"  # Immediate or cancel
TIME_IN_FORCE_FOK = "FOK"  # Fill or kill

# Rate Limit Max request

MAX_REQUEST_LOGIN = 5
MAX_REQUEST_SPOT_BALANCE = 30
MAX_REQUEST_ORDERS = 500
MAX_REQUEST_WALLET = 15

REQUEST_WEIGHT = "REQUEST_WEIGHT"
RAW_REQUESTS = "RAW_REQUESTS"


RATE_LIMITS = [
    # Weighted Limits
    RateLimit(limit_id=ORDER_BOOK_PATH, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 20),
                             LinkedLimitWeightPair(RAW_REQUESTS, 30)]),
    RateLimit(limit_id=ORDER_BOOK_PATH, limit=MAX_REQUEST, time_interval=ONE_MINUTE,
              linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 20),
                             LinkedLimitWeightPair(RAW_REQUESTS, 30)]),
    # Pools
    RateLimit(limit_id=LOGIN, limit=MAX_REQUEST_LOGIN, time_interval=ONE_SECOND),
    RateLimit(limit_id=SPOT_SUBSCRIBE, limit=MAX_REQUEST_LOGIN, time_interval=ONE_SECOND),
    RateLimit(limit_id=SPOT_UNSUBSCRIBE, limit=MAX_REQUEST_LOGIN, time_interval=ONE_SECOND),
    RateLimit(limit_id=SPOT_BALANCE_SUBSCRIBE, limit=MAX_REQUEST_LOGIN, time_interval=ONE_SECOND),
    RateLimit(limit_id=SPOT_BALANCE_UNSUBSCRIBE, limit=MAX_REQUEST_LOGIN, time_interval=ONE_SECOND),
    RateLimit(limit_id=SPOT_BALANCES, limit=MAX_REQUEST_SPOT_BALANCE, time_interval=ONE_SECOND),
    RateLimit(limit_id=SPOT_FEE, limit=MAX_REQUEST_SPOT_BALANCE, time_interval=ONE_SECOND),
    RateLimit(limit_id=SPOT_FEES, limit=MAX_REQUEST_SPOT_BALANCE, time_interval=ONE_SECOND),
    RateLimit(limit_id=SPOT_NEW_ORDER, limit=MAX_REQUEST_ORDERS, time_interval=ONE_SECOND),
    RateLimit(limit_id=SPOT_NEW_ORDER_LIST, limit=MAX_REQUEST_ORDERS, time_interval=ONE_SECOND),
    RateLimit(limit_id=SPOT_REPLACE_ORDER, limit=MAX_REQUEST_ORDERS, time_interval=ONE_SECOND),
    RateLimit(limit_id=SUBSCRIBE_TRANSACTION, limit=MAX_REQUEST_WALLET, time_interval=ONE_SECOND),
    RateLimit(limit_id=UNSUBSCRIBE_TRANSACTION, limit=MAX_REQUEST_WALLET, time_interval=ONE_SECOND),
    RateLimit(limit_id=SUBSCRIBE_WALLET_BALANCES, limit=MAX_REQUEST_WALLET, time_interval=ONE_SECOND),
    RateLimit(limit_id=UNSUBSCRIBE_WALLET_BALANCES, limit=MAX_REQUEST_WALLET, time_interval=ONE_SECOND),
    RateLimit(limit_id=WALLET_BALANCE, limit=MAX_REQUEST_WALLET, time_interval=ONE_SECOND),
    RateLimit(limit_id=WALLET_BALANCES, limit=MAX_REQUEST_WALLET, time_interval=ONE_SECOND),
    RateLimit(limit_id=TRANSACTIONS, limit=MAX_REQUEST_WALLET, time_interval=ONE_SECOND),


]

ORDER_NOT_EXIST_ERROR_CODE = -2013
ORDER_NOT_EXIST_MESSAGE = "Order does not exist"
UNKNOWN_ORDER_ERROR_CODE = -2011
UNKNOWN_ORDER_MESSAGE = "Unknown order sent"
