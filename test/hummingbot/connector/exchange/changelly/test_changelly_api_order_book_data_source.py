import asyncio
import json
import re
import unittest
from typing import Awaitable, Dict
from unittest.mock import AsyncMock, MagicMock, patch

from aioresponses import aioresponses
from bidict import bidict

from hummingbot.client.config.client_config_map import ClientConfigMap
from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.connector.exchange.changelly import changelly_constants as CONSTANTS, changelly_web_utils as web_utils
from hummingbot.connector.exchange.changelly.changelly_api_order_book_data_source import ChangellyAPIOrderBookDataSource
from hummingbot.connector.exchange.changelly.changelly_exchange import ChangellyExchange
from hummingbot.connector.test_support.network_mocking_assistant import NetworkMockingAssistant
from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.data_type.order_book_message import OrderBookMessage


class TestChangellyAPIOrderBookDataSource(unittest.TestCase):
    # logging.Level required to receive logs from the data source logger
    level = 0

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.ev_loop = asyncio.get_event_loop()
        cls.base_asset = "BTC"
        cls.quote_asset = "USDT"
        cls.trading_pair = f"{cls.base_asset}-{cls.quote_asset}"
        cls.ex_trading_pair = cls.base_asset + cls.quote_asset
        cls.domain = "com"


    def setUp(self) -> None:
        super().setUp()
        self.log_records = []
        self.async_task = None
        self.mocking_assistant = NetworkMockingAssistant()
        self.listening_task = None

        client_config_map = ClientConfigAdapter(ClientConfigMap())
        self.connector = ChangellyExchange(
            client_config_map=client_config_map,
            changelly_api_key="",
            changelly_api_secret="",
            trading_pairs=[self.trading_pair],
        )

        self.throttler = AsyncThrottler(CONSTANTS.RATE_LIMITS)
        self.time_synchronnizer = TimeSynchronizer()
        self.time_synchronnizer.add_time_offset_ms_sample(1000)
        self.ob_data_source = ChangellyAPIOrderBookDataSource(
            trading_pairs=[self.trading_pair],
            connector=self.connector,
            api_factory=self.connector._web_assistants_factory,
        )

        self._original_full_order_book_reset_time = self.ob_data_source.FULL_ORDER_BOOK_RESET_DELTA_SECONDS
        self.ob_data_source.FULL_ORDER_BOOK_RESET_DELTA_SECONDS = -1

        self.ob_data_source.logger().setLevel(1)
        self.ob_data_source.logger().addHandler(self)

        self.resume_test_event = asyncio.Event()

        self.connector._set_trading_pair_symbol_map(bidict({self.ex_trading_pair: self.trading_pair}))

    def tearDown(self) -> None:
        self.listening_task and self.listening_task.cancel()
        self.ob_data_source.FULL_ORDER_BOOK_RESET_DELTA_SECONDS = self._original_full_order_book_reset_time
        super().tearDown()

    def handle(self, record):
        self.log_records.append(record)

    def _is_logged(self, log_level: str, message: str) -> bool:
        return any(record.levelname == log_level and record.getMessage() == message for record in self.log_records)

    def _create_exception_and_unlock_test_with_event(self, exception):
        self.resume_test_event.set()
        raise exception

    def async_run_with_timeout(self, coroutine: Awaitable, timeout: int = 1):
        ret = self.ev_loop.run_until_complete(asyncio.wait_for(coroutine, timeout))
        return ret

    # ORDER BOOK SNAPSHOT
    @staticmethod
    def _snapshot_response_ws() -> Dict:
        snapshot = {
            "ch": "orderbook/full",
            "snapshot": {
                "ETHBTC": {
                    "t": 1626866578796,
                    "s": 27617207,
                    "a": [["0.060506", "0"], ["0.060549", "12.6431"], ["0.060570", "0"], ["0.060612", "0"]],
                    "b": [["0.060439", "4.4095"], ["0.060414", "0"], ["0.060407", "7.3349"], ["0.060390", "0"]],
                }
            },
        }
        return snapshot

    @staticmethod
    def _snapshot_response_rest() -> Dict:
        snapshot = {
            "CHZUSDT": {
                "timestamp": "2024-01-22T19:23:48.904Z",
                "ask": [
                    ["0.0937817", "843"],
                    ["0.0937847", "112"],
                ],
                "bid": [
                    ["0.0937506", "108"],
                    ["0.0937399", "843"],
                ],
            },
            "NEODAI": {
                "timestamp": "2024-01-22T19:23:48.884Z",
                "ask": [
                    ["10.80462", "40.79"],
                    ["10.81521", "537.91"],
                ],
                "bid": [
                    ["10.76550", "36.80"],
                    ["10.75443", "477.86"],
                ],
            },
        }
        return snapshot

    @aioresponses()
    def test_request_order_book_snapshot(self, mock_api):
        path = CONSTANTS.ORDER_BOOK_PATH + "/" + self.ex_trading_pair
        url = web_utils.public_rest_url(path=path)
        mock_api.get(url)

        ret = self.async_run_with_timeout(coroutine=self.ob_data_source._request_order_book_snapshot(self.trading_pair))
        print("test_request_order_book_snapshot", ret)
        assert self._snapshot_response_rest() == ret
        

    @aioresponses()
    def test_get_new_order_book(self, mock_api):
        url = web_utils.public_rest_url(path=CONSTANTS.ORDER_BOOK_PATH)
        resp = self._snapshot_response_rest()
        mock_api.get(url, body=json.dumps(resp))

        ret = self.async_run_with_timeout(coroutine=self.ob_data_source.get_new_order_book(self.trading_pair))
        bid_entries = list(ret.bid_entries())
        ask_entries = list(ret.ask_entries())
        self.assertEqual(1, len(bid_entries))
        self.assertEqual(50005.12, bid_entries[0].price)
        self.assertEqual(403.0416, bid_entries[0].amount)
        self.assertEqual(int(resp["result"]["time"]), bid_entries[0].update_id)
        self.assertEqual(1, len(ask_entries))
        self.assertEqual(50006.34, ask_entries[0].price)
        self.assertEqual(0.2297, ask_entries[0].amount)
        self.assertEqual(int(resp["result"]["time"]), ask_entries[0].update_id)

    
    # TRADES
        
    def test_listen_for_trades_cancelled_when_listening(self):
        mock_queue = MagicMock()
        mock_queue.get.side_effect = asyncio.CancelledError()
        self.ob_data_source._message_queue[CONSTANTS.TRADE_EVENT_TYPE] = mock_queue

        msg_queue: asyncio.Queue = asyncio.Queue()

        with self.assertRaises(asyncio.CancelledError):
            self.listening_task = self.ev_loop.create_task(
                self.ob_data_source.listen_for_trades(self.ev_loop, msg_queue)
            )
            self.async_run_with_timeout(self.listening_task)

    def _trade_update_event(self):
        trade_event = {
                "ch": "trades",
                "update": {
                    "BTCUSDT": [{"t": 1626861123552, "i": 1555634969, "p": "30877.68", "q": "0.00006", "s": "sell"}]
                },
        }
        return trade_event

    def _order_diff_event(self):
        diff_event = {
            "ch": "orderbook/full",
            "update": {
                self.ex_trading_pair: {
                    "t": 1626866578902,
                    "s": 27617208,
                    "a": [["0.060508", "0"], ["0.060509", "2.5486"]],
                    "b": [["0.060501", "3.9000"], ["0.060500", "3.0459"]],
                }
            },
        }
        return diff_event

    def test_listen_for_trades_successful(self):
        mock_queue = AsyncMock()
        mock_queue.get.side_effect = [self._trade_update_event(), asyncio.CancelledError()]
        self.ob_data_source._message_queue[CONSTANTS.TRADE_EVENT_TYPE] = mock_queue

        msg_queue: asyncio.Queue = asyncio.Queue()
        self.listening_task = self.ev_loop.create_task(self.ob_data_source.listen_for_subscriptions())

        # await  self.ob_data_source._subscribe_channels()
        self.listening_task = self.ev_loop.create_task(
            self.ob_data_source.listen_for_trades(self.ev_loop, msg_queue)
        )
        msg: OrderBookMessage = self.async_run_with_timeout(msg_queue.get())
        self.assertEqual(1555634969, msg.trade_id)


    # ORDER BOOK
    def test_listen_for_order_book_diffs_cancelled(self):
        mock_queue = AsyncMock()
        mock_queue.get.side_effect = asyncio.CancelledError()
        self.ob_data_source._message_queue[CONSTANTS.DIFF_EVENT_TYPE] = mock_queue

        msg_queue: asyncio.Queue = asyncio.Queue()

        with self.assertRaises(asyncio.CancelledError):
            self.listening_task = self.ev_loop.create_task(
                self.ob_data_source.listen_for_order_book_diffs(self.ev_loop, msg_queue)
            )
            self.async_run_with_timeout(self.listening_task)

    def test_listen_for_order_book_diffs_logs_exception(self):
        incomplete_resp = {
            "ch": "orderbook/full",
            "snapshot": {
        
            }
        }

        mock_queue = AsyncMock()
        mock_queue.get.side_effect = [incomplete_resp, asyncio.CancelledError()]
        self.ob_data_source._message_queue[CONSTANTS.DIFF_EVENT_TYPE] = mock_queue

        msg_queue: asyncio.Queue = asyncio.Queue()

        self.listening_task = self.ev_loop.create_task(
            self.ob_data_source.listen_for_order_book_diffs(self.ev_loop, msg_queue)
        )

        try:
            self.async_run_with_timeout(self.listening_task)
        except asyncio.CancelledError:
            pass
        
        self.assertTrue(
            self._is_logged("ERROR", "Unexpected error when processing public order book updates from exchange")
        )

    def test_listen_for_order_book_diffs_successful(self):
        mock_queue = AsyncMock()
        diff_event = self._order_diff_event()

        mock_queue.get.side_effect = [diff_event, asyncio.CancelledError()]
        self.ob_data_source._message_queue[CONSTANTS.DIFF_EVENT_TYPE] = mock_queue

        msg_queue: asyncio.Queue = asyncio.Queue()

        try:
            self.listening_task = self.ev_loop.create_task(
                self.ob_data_source.listen_for_order_book_diffs(self.ev_loop, msg_queue)
            )
        except asyncio.CancelledError:
            pass

        msg: OrderBookMessage = self.async_run_with_timeout(msg_queue.get())
        self.assertTrue(1626866578902, msg.update_id)

    def test_listen_for_order_book_snapshots_successful_ws(self):
        mock_queue = AsyncMock()
        orderbook_snapshot = {
            "ch": "orderbook/full",
            "snapshot": {
                self.ex_trading_pair: {
                    "t": 1626866578796,
                    "s": 27617207,
                    "a": [["0.060506", "0"], ["0.060549", "12.6431"]],
                    "b": [["0.060439", "4.4095"], ["0.060414", "0"]],
                }
            },
        }
        mock_queue.get.side_effect = [orderbook_snapshot, asyncio.CancelledError()]
        self.ob_data_source._message_queue[CONSTANTS.ORDERBOOK_EVENT_TYPE] = mock_queue

        msg_queue: asyncio.Queue = asyncio.Queue()

        self.listening_task = self.ev_loop.create_task(
            self.ob_data_source.listen_for_order_book_snapshots(self.ev_loop, msg_queue)
        )

        msg: OrderBookMessage = self.async_run_with_timeout(msg_queue.get(), timeout=10)

        self.assertGreaterEqual(len(msg.bids), 0)