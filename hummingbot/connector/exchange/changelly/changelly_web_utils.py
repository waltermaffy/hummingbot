from typing import Callable, Optional

import hummingbot.connector.exchange.changelly.changelly_constants as CONSTANTS
from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.connector.utils import TimeSynchronizerRESTPreProcessor
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from datetime import datetime 
import time
import calendar


def public_rest_url(path: str, domain: Optional[str] = None) -> str:
    """
    Creates a full URL for provided public REST endpoint
    :param path: a public REST endpoint
    :return: the full URL to the endpoint
    """
    return CONSTANTS.REST_URL + "/" + path


def build_api_factory(
    throttler: Optional[AsyncThrottler] = None,
    time_synchronizer: Optional[TimeSynchronizer] = None,
    auth: Optional[AuthBase] = None,
) -> WebAssistantsFactory:
    throttler = throttler or create_throttler()
    api_factory = WebAssistantsFactory(
        throttler=throttler,
        auth=auth,
    )
    return api_factory


def build_api_factory_without_time_synchronizer_pre_processor(throttler: AsyncThrottler) -> WebAssistantsFactory:
    api_factory = WebAssistantsFactory(throttler=throttler)
    return api_factory


def create_throttler() -> AsyncThrottler:
    return AsyncThrottler(CONSTANTS.RATE_LIMITS)

def convert_to_unix_timestamp(iso_time):
    dt = datetime.strptime(iso_time, "%Y-%m-%dT%H:%M:%S.%fZ")
    unix_timestamp = calendar.timegm(dt.utctimetuple())
    return unix_timestamp

async def get_current_server_time(
        throttler: Optional[AsyncThrottler] = None,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
) -> float:
    throttler = throttler or create_throttler()
    api_factory = build_api_factory_without_time_synchronizer_pre_processor(throttler=throttler)
    rest_assistant = await api_factory.get_rest_assistant()
    response = await rest_assistant.execute_request(
        url=public_rest_url(path=CONSTANTS.ORDER_BOOK_PATH, domain=domain),
        method=RESTMethod.GET,
        throttler_limit_id=CONSTANTS.ORDER_BOOK_PATH,
    )
    try:
        first_symbol = list(response.keys())[0]
        exchange_timestamp = response[first_symbol]["timestamp"]
        server_time = convert_to_unix_timestamp(exchange_timestamp)
    except Exception as e:
        server_time = time.time()
    return server_time
