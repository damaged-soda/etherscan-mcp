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
