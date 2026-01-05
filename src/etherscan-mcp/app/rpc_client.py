import time
from typing import Any, Dict, List, Optional

import requests


class RpcClient:
    """Minimal JSON-RPC 2.0 client for EVM nodes (HTTP POST)."""

    def __init__(
        self,
        rpc_url: str,
        timeout: int = 10,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        url = (rpc_url or "").strip()
        if not url:
            raise ValueError("rpc_url must be a non-empty string.")

        self.rpc_url = url
        self.timeout = timeout
        self.max_retries = max(1, int(max_retries))
        self.backoff_seconds = float(backoff_seconds)
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        if headers:
            self.session.headers.update(dict(headers))
        self._next_id = 1

    def call(self, method: str, params: Optional[List[Any]] = None) -> Any:
        if not isinstance(method, str) or not method.strip():
            raise ValueError("method must be a non-empty string.")
        if params is None:
            params = []
        if not isinstance(params, list):
            raise ValueError("params must be a list.")

        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": method,
            "params": params,
        }
        self._next_id += 1

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.post(
                    self.rpc_url,
                    json=payload,
                    timeout=self.timeout,
                )
                if response.status_code in {429} or response.status_code >= 500:
                    if attempt < self.max_retries:
                        time.sleep(self.backoff_seconds * attempt)
                        continue

                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("Unexpected JSON-RPC response (non-object).")

                error_obj = data.get("error")
                if isinstance(error_obj, dict):
                    code = error_obj.get("code")
                    message = error_obj.get("message")
                    err_data = error_obj.get("data")
                    parts: list[str] = []
                    if code is not None:
                        parts.append(f"code {code}")
                    if message:
                        parts.append(str(message))
                    if err_data:
                        parts.append(str(err_data))
                    detail = ": ".join(parts) if parts else "unknown error"
                    raise ValueError(f"RPC error: {detail}.")

                if "result" not in data:
                    raise ValueError("Unexpected JSON-RPC response (missing result).")
                return data.get("result")
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(self.backoff_seconds * attempt)
                    continue
                raise
            except ValueError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(self.backoff_seconds * attempt)
                    continue
                raise

        if last_error:
            raise last_error
        raise RuntimeError("RPC request failed without raising an exception.")

    def get_block_number(self) -> int:
        result = self.call("eth_blockNumber", [])
        if not isinstance(result, str) or not result.startswith("0x"):
            raise ValueError("RPC error: eth_blockNumber returned unexpected result.")
        return int(result, 16)

