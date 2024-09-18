import time
from http import server
from typing import Any, Callable, Dict, Optional

from hummingbot.connector.exchange.koinbx import koinbx_constants as CONSTANTS
from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.connector.utils import TimeSynchronizerRESTPreProcessor
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import EndpointRESTRequest, RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory


def public_rest_url(path_url: str, domain: str = CONSTANTS.DEFAULT_DOMAIN) -> str:
    """
    Creates a full URL for provided public REST endpoint
    :param path_url: a public REST endpoint
    :param domain: the Koinbx domain to connect to ("com" or "testnet"). The default value is "com"
    :return: the full URL to the endpoint
    """
    return CONSTANTS.PUBLIC_REST_URL + path_url


def private_rest_url(path_url: str, domain: str = CONSTANTS.DEFAULT_DOMAIN) -> str:
    """
    Creates a full URL for provided private REST endpoint
    :param path_url: a private REST endpoint
    :param domain: the Koinbx domain to connect to ("com" or "testnet"). The default value is "com"
    :return: the full URL to the endpoint
    """
    return CONSTANTS.PRIVATE_REST_URL + path_url


def build_api_factory(
    throttler: Optional[AsyncThrottler] = None,
    time_synchronizer: Optional[TimeSynchronizer] = None,
    domain: str = CONSTANTS.DEFAULT_DOMAIN,
    time_provider: Optional[Callable] = None,
    auth: Optional[AuthBase] = None,
) -> WebAssistantsFactory:
    throttler = throttler or create_throttler()
    time_synchronizer = time_synchronizer or TimeSynchronizer()
    time_provider = time_provider or (
        lambda: get_current_server_time(
            throttler=throttler,
            domain=domain,
        )
    )
    api_factory = WebAssistantsFactory(
        throttler=throttler,
        auth=auth,
        rest_pre_processors=[
            TimeSynchronizerRESTPreProcessor(synchronizer=time_synchronizer, time_provider=time_provider),
        ],
    )
    return api_factory


def build_api_factory_without_time_synchronizer_pre_processor(
    throttler: AsyncThrottler, auth: Optional[AuthBase] = None
) -> WebAssistantsFactory:
    api_factory = WebAssistantsFactory(throttler=throttler, auth=auth)
    return api_factory


def create_throttler() -> AsyncThrottler:
    return AsyncThrottler(CONSTANTS.RATE_LIMITS)


async def api_request(
    path: str,
    api_factory: WebAssistantsFactory,
    throttler: AsyncThrottler,
    domain: str = CONSTANTS.DEFAULT_DOMAIN,
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    method: str = "GET",
    is_auth_required: bool = False,
    limit_id: Optional[str] = None,
    timeout: Optional[float] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    try:
        rest_assistant = await api_factory.get_rest_assistant()
        request = EndpointRESTRequest(
            method=method.upper(),
            url=public_rest_url(path, domain) if not is_auth_required else private_rest_url(path, domain),
            params=params,
            data=data,
            headers=headers,
            is_auth_required=is_auth_required,
        )
        async with throttler.execute_task(limit_id=limit_id if limit_id else path):
            response = await rest_assistant.call(request=request, timeout=timeout)
        return await response.json()
    except Exception as e:
        raise IOError(f"Error requesting {path} on {domain}. Error: {str(e)}")


def get_request_id(client_id: str) -> str:
    """
    Creates unique request identifier. The client_id should be unique for each client.
    """
    return f"hbot:{client_id}"


async def get_current_server_time(
    throttler: Optional[AsyncThrottler] = None,
    domain: str = CONSTANTS.DEFAULT_DOMAIN,
) -> float:
    # throttler = throttler or create_throttler()
    # api_factory = build_api_factory_without_time_synchronizer_pre_processor(throttler=throttler)
    # rest_assistant = await api_factory.get_rest_assistant()
    # response = await rest_assistant.execute_request(
    #     url=public_rest_url(path_url=CONSTANTS.SERVER_TIME_PATH_URL, domain=domain),
    #     method=RESTMethod.GET,
    #     throttler_limit_id=CONSTANTS.SERVER_TIME_PATH_URL,
    # )
    # server_time = response["serverTime"]
    server_time = time.time()
    return server_time
