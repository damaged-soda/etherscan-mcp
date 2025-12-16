import time
from typing import Any, Dict, Optional

import requests


class EtherscanClient:
    """Thin wrapper around Etherscan API with basic retry."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        chain_id: str,
        timeout: int = 10,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.chain_id = chain_id
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.session = requests.Session()
        self.session.headers.update({"X-API-Key": api_key})

    def get_contract_source(self, address: str) -> Dict[str, Any]:
        params = {
            "module": "contract",
            "action": "getsourcecode",
            "address": address,
            "chainid": self.chain_id,
        }
        return self._request(params)

    def get_contract_creation(self, address: str) -> Dict[str, Any]:
        params = {
            "module": "contract",
            "action": "getcontractcreation",
            "contractaddresses": address,
            "chainid": self.chain_id,
        }
        return self._request(params)

    def get_transactions(
        self,
        address: str,
        start_block: int,
        end_block: int,
        page: int,
        offset: int,
        sort: str,
    ) -> Dict[str, Any]:
        params = {
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": start_block,
            "endblock": end_block,
            "page": page,
            "offset": offset,
            "sort": sort,
            "chainid": self.chain_id,
        }
        return self._request(params)

    def get_token_transfers(
        self,
        address: str,
        start_block: int,
        end_block: int,
        page: int,
        offset: int,
        sort: str,
        token_type: str,
    ) -> Dict[str, Any]:
        action_map = {
            "erc20": "tokentx",
            "erc721": "tokennfttx",
            "erc1155": "token1155tx",
        }
        action = action_map.get(token_type.lower())
        if not action:
            raise ValueError(f"Unsupported token_type '{token_type}'. Expected erc20|erc721|erc1155.")

        params = {
            "module": "account",
            "action": action,
            "address": address,
            "startblock": start_block,
            "endblock": end_block,
            "page": page,
            "offset": offset,
            "sort": sort,
            "chainid": self.chain_id,
        }
        return self._request(params)

    def get_logs(
        self,
        address: str,
        from_block: int,
        to_block: int,
        topics: Dict[str, str],
        page: int,
        offset: int,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "module": "logs",
            "action": "getLogs",
            "address": address,
            "fromBlock": from_block,
            "toBlock": to_block,
            "page": page,
            "offset": offset,
            "chainid": self.chain_id,
        }
        params.update(topics)
        return self._request(params)

    def get_storage_at(self, address: str, slot: str, tag: str) -> Dict[str, Any]:
        params = {
            "module": "proxy",
            "action": "eth_getStorageAt",
            "address": address,
            "position": slot,
            "tag": tag,
            "chainid": self.chain_id,
        }
        return self._request(params)

    def call(self, address: str, data: str, tag: str) -> Dict[str, Any]:
        params = {
            "module": "proxy",
            "action": "eth_call",
            "to": address,
            "data": data,
            "tag": tag,
            "chainid": self.chain_id,
        }
        return self._request(params)

    def _request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        merged = {**params, "apikey": self.api_key}
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(
                    self.base_url,
                    params=merged,
                    timeout=self.timeout,
                )
                if response.status_code >= 500 and attempt < self.max_retries:
                    time.sleep(self.backoff_seconds * attempt)
                    continue

                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(self.backoff_seconds * attempt)
                else:
                    raise
            except ValueError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(self.backoff_seconds * attempt)
                else:
                    raise ValueError("Failed to parse response from Etherscan.") from exc

        if last_error:
            raise last_error

        raise RuntimeError("Request failed without raising an exception.")
