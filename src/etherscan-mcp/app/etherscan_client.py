import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests


class EtherscanClient:
    """Thin wrapper around Etherscan-compatible explorer APIs with basic retry."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        chain_id: str,
        timeout: int = 10,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
        chain_api_urls: Optional[Dict[str, str]] = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.chain_id = chain_id
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.chain_api_urls = {
            str(chain_id): str(url).rstrip("/")
            for chain_id, url in (chain_api_urls or {}).items()
            if str(url).strip()
        }
        self.session = requests.Session()

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

    def get_transaction(self, tx_hash: str) -> Dict[str, Any]:
        params = {
            "module": "proxy",
            "action": "eth_getTransactionByHash",
            "txhash": tx_hash,
            "chainid": self.chain_id,
        }
        return self._request(params)

    def get_transaction_receipt(self, tx_hash: str) -> Dict[str, Any]:
        params = {
            "module": "proxy",
            "action": "eth_getTransactionReceipt",
            "txhash": tx_hash,
            "chainid": self.chain_id,
        }
        return self._request(params)

    def get_block_by_number(self, tag: str, full_transactions: bool) -> Dict[str, Any]:
        params = {
            "module": "proxy",
            "action": "eth_getBlockByNumber",
            "tag": tag,
            "boolean": str(full_transactions).lower(),
            "chainid": self.chain_id,
        }
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

    def get_chainlist(self, chainlist_url: str) -> Dict[str, Any]:
        return self._request_url(chainlist_url, params={})

    def api_url(self, chain_id: Optional[str] = None) -> str:
        return self.chain_api_urls.get(str(chain_id or self.chain_id), self.base_url)

    def indexer_name(self, chain_id: Optional[str] = None) -> str:
        hostname = (urlparse(self.api_url(chain_id)).hostname or "").lower()
        if "blockscout" in hostname or hostname.endswith("chain.robinhood.com"):
            return "blockscout"
        return "etherscan"

    @staticmethod
    def _origin(url: str) -> tuple[str, str, Optional[int]]:
        parsed = urlparse(url)
        return parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port

    def _uses_etherscan_credentials(self, url: str) -> bool:
        # ETHERSCAN_API_KEY is scoped to the configured Etherscan base origin.
        # Chain-specific Blockscout/custom indexers never receive it implicitly.
        return self._origin(url) == self._origin(self.base_url)

    @staticmethod
    def _safe_request_error(url: str, exc: requests.RequestException) -> ValueError:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        display_host = f"[{hostname}]" if ":" in hostname else hostname
        if parsed.port is not None:
            display_host = f"{display_host}:{parsed.port}"
        safe_target = (
            f"{parsed.scheme}://{display_host}/***" if display_host else "explorer API"
        )
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        reason = getattr(response, "reason", None)
        detail = " ".join(str(value) for value in (status, reason) if value)
        suffix = f" ({detail})" if detail else ""
        return ValueError(f"Explorer API request failed for {safe_target}{suffix}.")

    def _is_rate_limit_payload(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False

        candidates: list[str] = []
        for key in ("message", "result"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                candidates.append(value)

        error_obj = payload.get("error")
        if isinstance(error_obj, dict):
            for key in ("message", "data"):
                value = error_obj.get(key)
                if isinstance(value, str) and value:
                    candidates.append(value)

        haystack = " ".join(candidates).lower()
        if not haystack:
            return False

        return (
            "rate limit" in haystack
            or "max calls per sec" in haystack
            or "max calls per second" in haystack
            or "too many requests" in haystack
        )

    def _request_url(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(params or {})
        headers: Dict[str, str] = {}
        if self.api_key and self._uses_etherscan_credentials(url):
            merged["apikey"] = self.api_key
            headers["X-API-Key"] = self.api_key
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(
                    url,
                    params=merged,
                    headers=headers,
                    timeout=self.timeout,
                )
                if response.status_code >= 500 and attempt < self.max_retries:
                    time.sleep(self.backoff_seconds * attempt)
                    continue

                response.raise_for_status()
                payload = response.json()
                if self._is_rate_limit_payload(payload) and attempt < self.max_retries:
                    time.sleep(self.backoff_seconds * attempt)
                    continue
                return payload
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(self.backoff_seconds * attempt)
                else:
                    raise self._safe_request_error(url, exc) from None
            except ValueError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(self.backoff_seconds * attempt)
                else:
                    label = self.indexer_name() if url == self.api_url() else "etherscan"
                    raise ValueError(
                        f"Failed to parse response from {label.capitalize()}."
                    ) from exc

        if last_error:
            raise last_error

        raise RuntimeError("Request failed without raising an exception.")

    def _request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return self._request_url(self.api_url(), params)
