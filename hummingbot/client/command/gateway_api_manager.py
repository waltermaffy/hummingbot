import json
from contextlib import contextmanager
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Generator, Optional

import aiohttp

from hummingbot.core.gateway.gateway_http_client import GatewayHttpClient

if TYPE_CHECKING:
    from hummingbot.client.hummingbot_application import HummingbotApplication


class Chain(Enum):
    ETHEREUM = 0
    AVALANCHE = 1
    POLYGON = 2
    SOLANA = 3

    @staticmethod
    def from_str(label: str) -> "Chain":
        label = label.lower()
        if label == "ethereum":
            return Chain.ETHEREUM
        elif label == "avalanche":
            return Chain.AVALANCHE
        elif label == "polygon":
            return Chain.POLYGON
        elif label == "solana":
            return Chain.SOLANA
        else:
            raise NotImplementedError

    @staticmethod
    def to_str(chain: "Chain") -> str:
        if chain == Chain.ETHEREUM:
            return "ethereum"
        if chain == Chain.POLYGON:
            return "polygon"
        elif chain == Chain.AVALANCHE:
            return "avalanche"
        elif chain == Chain.SOLANA:
            return "solana"
        else:
            raise NotImplementedError


@contextmanager
def begin_placeholder_mode(hb: "HummingbotApplication") -> Generator["HummingbotApplication", None, None]:
    hb.app.clear_input()
    hb.placeholder_mode = True
    hb.app.hide_input = True
    try:
        yield hb
    finally:
        hb.app.to_stop_config = False
        hb.placeholder_mode = False
        hb.app.hide_input = False
        hb.app.change_prompt(prompt=">>> ")


class GatewayChainApiManager:
    """
    Manage and test connections from gateway to chain APIs like Infura and
    Moralis.
    """

    async def _test_evm_node(self, url_with_api_key: str) -> bool:
        """
        Verify that the Infura API Key is valid. If it is an empty string,
        ignore it, but let the user know they cannot connect to ethereum.
        """
        async with aiohttp.ClientSession() as tmp_client:
            headers = {"Content-Type": "application/json"}
            data = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_blockNumber",
                "params": []
            }

            resp = await tmp_client.post(url=url_with_api_key,
                                         data=json.dumps(data),
                                         headers=headers)

            success = resp.status == 200
            if success:
                self.notify("The API Key works.")
            else:
                self.notify("Error occurred verifying the API Key. Please check your API Key and try again.")
            return success

    async def _test_sol_node(self, url_with_api_key: str) -> bool:
        """
        Verify that the Infura API Key is valid. If it is an empty string,
        ignore it, but let the user know they cannot connect to Solana.
        """
        async with aiohttp.ClientSession() as tmp_client:
            headers = {"Content-Type": "application/json"}
            data = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getHealth"
            }

            resp = await tmp_client.post(
                url=url_with_api_key,
                data=json.dumps(data),
                headers=headers
            )

            success = resp.status == 200
            if success:
                self.notify("The API Key works.")
            else:
                self.notify("Error occurred verifying the API Key. Please check your API Key and try again.")

            return success

    async def _get_api_key(self, chain: Chain, required=False) -> Optional[str]:
        """
        Get the API key from user input, then check that it is valid
        """
        with begin_placeholder_mode(self):
            while True:
                if chain == Chain.ETHEREUM:
                    service = 'Infura'
                    chain_name = 'Ethereum'
                    service_url = 'infura.io'
                elif chain == Chain.POLYGON:
                    service = 'Moralis'
                    chain_name = 'Polygon'
                    service_url = 'moralis.io'
                elif chain == Chain.AVALANCHE:
                    service = 'Moralis'
                    chain_name = 'Avalanche'
                    service_url = 'moralis.io'
                elif chain == Chain.SOLANA:
                    service = 'Syndica'
                    chain_name = 'Solana'
                    service_url = 'syndica.io'
                else:
                    raise ValueError(f"Unrecognized chain: {chain}.")

                api_key: str = await self.app.prompt(prompt=f"Enter {service} API Key (required for {chain_name} node, "
                                                            f"if you do not have one, make an account at {service_url})"
                                                            f", otherwise configure gateway after creation:  >>> ")

                self.app.clear_input()

                if self.app.to_stop_config:
                    self.app.to_stop_config = False
                    return None
                try:
                    api_key = api_key.strip()  # help check for an empty string which is valid input
                    if not required and (api_key is None or api_key == "" or api_key == "''" or api_key == "\"\""):
                        self.notify(f"Setting up gateway without an {chain_name} node.")
                        return None
                    else:
                        if chain == Chain.ETHEREUM:
                            api_url = f"https://mainnet.infura.io/v3/{api_key}"
                            success: bool = await self._test_evm_node(api_url)
                        if chain == Chain.POLYGON:
                            api_url = f"https://speedy-nodes-nyc.moralis.io/{api_key}/polygon/mainnet"
                            success: bool = await self._test_evm_node(api_url)
                        elif chain == Chain.AVALANCHE:
                            api_url = f"https://speedy-nodes-nyc.moralis.io/{api_key}/avalanche/mainnet"
                            success: bool = await self._test_evm_node(api_url)
                        elif chain == Chain.SOLANA:
                            api_url = f"https://solana-api.syndica.io/access-token/{api_key}/rpc"
                            success: bool = await self._test_sol_node(api_url)
                        else:
                            raise ValueError(f"Unrecognized chain: {chain}.")
                        if not success:
                            # the API key test was unsuccessful, try again
                            continue
                        return api_key
                except Exception:
                    self.notify(f"Error occur calling the API route: {api_url}.")
                    raise

    @staticmethod
    async def _update_gateway_api_key(chain: Chain, api_key: str):
        """
        Update a chain's API key in gateway
        """
        await GatewayHttpClient.get_instance().update_config(f"{Chain.to_str(chain)}.nodeAPIKey", api_key)

    @staticmethod
    async def _get_api_key_from_gateway_config(chain: Chain) -> Optional[str]:
        """
        Check if gateway has an API key for gateway
        """
        config_dict: Dict[str, Any] = await GatewayHttpClient.get_instance().get_configuration()
        chain_config: Optional[Dict[str, Any]] = config_dict.get(Chain.to_str(chain))
        if chain_config is not None:
            api_key: Optional[str] = chain_config.get("nodeAPIKey")
            if api_key is None or api_key == "" or api_key == "''" or api_key == "\"\"":
                return None
            else:
                return api_key
        else:
            return None
