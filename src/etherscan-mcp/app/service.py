import json
import re
from typing import Any, Dict, List, Optional, Tuple

from .cache import ContractCache
from .config import Config, resolve_chain_id
from .etherscan_client import EtherscanClient

ADDRESS_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")


class ContractService:
    """Combine configuration, cache, and client to serve contract details."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.cache = ContractCache(config.cache_dir)
        self.client = EtherscanClient(
            api_key=config.api_key,
            base_url=config.base_url,
            chain_id=config.chain_id,
            timeout=config.request_timeout,
            max_retries=config.max_retries,
            backoff_seconds=config.backoff_seconds,
        )

    def fetch_contract(self, address: str, network: Optional[str] = None) -> Dict[str, Any]:
        normalized_address = self._normalize_address(address)
        network_label, chain_id = self._resolve_network_and_chain(network)
        self.client.chain_id = chain_id

        cached = self.cache.get(normalized_address, chain_id)
        if cached:
            return cached

        payload = self.client.get_contract_source(normalized_address)
        parsed = self._parse_response(payload, normalized_address, network_label, chain_id)
        self.cache.set(normalized_address, chain_id, parsed)
        return parsed

    def _normalize_address(self, address: str) -> str:
        if not isinstance(address, str):
            raise ValueError("Address must be a string.")

        candidate = address.strip()
        if not candidate.startswith("0x"):
            candidate = f"0x{candidate}"

        if not ADDRESS_PATTERN.match(candidate):
            raise ValueError("Invalid address format. Expected 0x-prefixed 40 hex characters.")

        return candidate.lower()

    def _resolve_network_and_chain(self, network: Optional[str]) -> Tuple[str, str]:
        if network:
            chain_id = resolve_chain_id(network)
            return network.lower(), chain_id

        return self.config.network, self.config.chain_id

    def _parse_response(
        self,
        payload: Dict[str, Any],
        address: str,
        network: str,
        chain_id: str,
    ) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Unexpected response from Etherscan.")

        status = str(payload.get("status", "")).strip()
        message = payload.get("message", "")
        result = payload.get("result", [])

        if status != "1" or not result:
            detail = ""
            if isinstance(result, str):
                detail = result
            elif isinstance(result, list) and result:
                detail = result[0] if isinstance(result[0], str) else ""
            raise ValueError(f"Etherscan error: {detail or message or 'unknown error'}.")

        entry = result[0]
        abi_raw = entry.get("ABI", "[]")
        abi = self._parse_abi(abi_raw)
        source_files = self._parse_source_code(entry.get("SourceCode", ""))
        compiler = entry.get("CompilerVersion") or ""

        return {
            "address": address,
            "network": network,
            "chain_id": chain_id,
            "abi": abi,
            "source_files": source_files,
            "compiler": compiler,
            "verified": True,
        }

    def _parse_abi(self, abi_raw: str) -> Any:
        try:
            return json.loads(abi_raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid ABI returned from Etherscan.") from exc

    def _parse_source_code(self, raw: str) -> List[Dict[str, str]]:
        if not raw:
            return []

        trimmed = raw.strip()
        if trimmed.startswith("{{") and trimmed.endswith("}}"):
            trimmed = trimmed[1:-1]

        if trimmed.startswith("{"):
            try:
                parsed = json.loads(trimmed)
                if isinstance(parsed, dict):
                    if "sources" in parsed and isinstance(parsed["sources"], dict):
                        sources = parsed["sources"]
                        files: List[Dict[str, str]] = []
                        for name, meta in sources.items():
                            if isinstance(meta, dict) and "content" in meta:
                                files.append({"filename": name, "content": meta.get("content", "")})
                        if files:
                            return files
                    if "content" in parsed:
                        filename = parsed.get("fileName", "Contract.sol")
                        return [{"filename": filename, "content": parsed.get("content", "")}]
            except json.JSONDecodeError:
                pass

        return [{"filename": "Contract.sol", "content": raw}]
