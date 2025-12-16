import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .cache import ContractCache
from .config import Config, resolve_chain_id
from .etherscan_client import EtherscanClient

ADDRESS_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")
EIP1967_IMPLEMENTATION_SLOT = "0x360894A13BA1A3210667C828492DB98DCA3E2076CC3735A920A3CA505D382BBC"
EIP1967_ADMIN_SLOT = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"
MAX_BLOCK = 99999999
DEFAULT_PAGE = 1
DEFAULT_OFFSET = 100


class ContractService:
    """Combine configuration, cache, and client to serve contract details."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.cache = ContractCache(config.cache_dir)
        self.creation_cache = ContractCache(config.cache_dir, namespace="creation")
        self.client = EtherscanClient(
            api_key=config.api_key,
            base_url=config.base_url,
            chain_id=config.chain_id,
            timeout=config.request_timeout,
            max_retries=config.max_retries,
            backoff_seconds=config.backoff_seconds,
        )

    def fetch_contract(self, address: str, network: Optional[str] = None) -> Dict[str, Any]:
        normalized_address, network_label, chain_id = self._prepare_context(address, network)

        cached = self.cache.get(normalized_address, chain_id)
        if cached:
            return cached

        payload = self.client.get_contract_source(normalized_address)
        parsed = self._parse_contract_response(payload, normalized_address, network_label, chain_id)
        self.cache.set(normalized_address, chain_id, parsed)
        return parsed

    def get_contract_creation(self, address: str, network: Optional[str] = None) -> Dict[str, Any]:
        normalized_address, network_label, chain_id = self._prepare_context(address, network)

        cached = self.creation_cache.get(normalized_address, chain_id)
        if cached:
            return cached

        payload = self.client.get_contract_creation(normalized_address)
        result = self._extract_result_list(payload, require_non_empty=True)
        entry = result[0]

        creator = entry.get("contractCreator") or entry.get("ContractCreator") or ""
        tx_hash = entry.get("txHash") or entry.get("TxHash") or ""
        block_number = entry.get("blockNumber") or entry.get("BlockNumber") or ""
        timestamp = entry.get("timeStamp") or entry.get("timestamp")

        data = {
            "address": normalized_address,
            "network": network_label,
            "chain_id": chain_id,
            "creator": creator,
            "tx_hash": tx_hash,
            "block_number": block_number,
            "timestamp": timestamp,
        }
        self.creation_cache.set(normalized_address, chain_id, data)
        return data

    def detect_proxy(self, address: str, network: Optional[str] = None) -> Dict[str, Any]:
        normalized_address, network_label, chain_id = self._prepare_context(address, network)

        impl_word = self._read_storage_word(normalized_address, EIP1967_IMPLEMENTATION_SLOT)
        admin_word = self._read_storage_word(normalized_address, EIP1967_ADMIN_SLOT)

        implementation = self._storage_word_to_address(impl_word)
        admin = self._storage_word_to_address(admin_word)

        evidence: List[str] = []
        if impl_word:
            evidence.append(f"implementation slot {EIP1967_IMPLEMENTATION_SLOT} -> {impl_word}")
        if admin_word:
            evidence.append(f"admin slot {EIP1967_ADMIN_SLOT} -> {admin_word}")

        is_proxy = bool(implementation or admin)

        return {
            "address": normalized_address,
            "network": network_label,
            "chain_id": chain_id,
            "is_proxy": is_proxy,
            "implementation": implementation,
            "admin": admin,
            "proxy_type": "eip1967" if is_proxy else None,
            "evidence": evidence,
        }

    def list_transactions(
        self,
        address: str,
        network: Optional[str] = None,
        start_block: Optional[int] = None,
        end_block: Optional[int] = None,
        page: Optional[int] = None,
        offset: Optional[int] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_address, network_label, chain_id = self._prepare_context(address, network)
        start, end = self._normalize_block_range(start_block, end_block)
        page_num = self._normalize_positive_int(page, DEFAULT_PAGE, "page")
        page_size = self._normalize_positive_int(offset, DEFAULT_OFFSET, "offset")
        sort_order = self._normalize_sort(sort)

        payload = self.client.get_transactions(
            normalized_address, start, end, page_num, page_size, sort_order
        )
        result = self._extract_result_list(payload, require_non_empty=False)
        transactions = [self._map_transaction(tx) for tx in result if isinstance(tx, dict)]

        return {
            "address": normalized_address,
            "network": network_label,
            "chain_id": chain_id,
            "transactions": transactions,
            "page": page_num,
            "offset": page_size,
            "sort": sort_order,
        }

    def list_token_transfers(
        self,
        address: str,
        network: Optional[str] = None,
        token_type: str = "erc20",
        start_block: Optional[int] = None,
        end_block: Optional[int] = None,
        page: Optional[int] = None,
        offset: Optional[int] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_address, network_label, chain_id = self._prepare_context(address, network)
        start, end = self._normalize_block_range(start_block, end_block)
        page_num = self._normalize_positive_int(page, DEFAULT_PAGE, "page")
        page_size = self._normalize_positive_int(offset, DEFAULT_OFFSET, "offset")
        sort_order = self._normalize_sort(sort)
        normalized_token_type = (token_type or "erc20").lower()

        payload = self.client.get_token_transfers(
            normalized_address,
            start,
            end,
            page_num,
            page_size,
            sort_order,
            normalized_token_type,
        )
        result = self._extract_result_list(payload, require_non_empty=False)
        transfers = [
            self._map_token_transfer(transfer, normalized_token_type)
            for transfer in result
            if isinstance(transfer, dict)
        ]

        return {
            "address": normalized_address,
            "network": network_label,
            "chain_id": chain_id,
            "token_type": normalized_token_type,
            "transfers": transfers,
            "page": page_num,
            "offset": page_size,
            "sort": sort_order,
        }

    def query_logs(
        self,
        address: str,
        network: Optional[str] = None,
        topics: Optional[Sequence[Optional[str]]] = None,
        from_block: Optional[int] = None,
        to_block: Optional[int] = None,
        page: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Dict[str, Any]:
        normalized_address, network_label, chain_id = self._prepare_context(address, network)
        start, end = self._normalize_block_range(from_block, to_block)
        page_num = self._normalize_positive_int(page, DEFAULT_PAGE, "page")
        page_size = self._normalize_positive_int(offset, DEFAULT_OFFSET, "offset")
        topic_params = self._normalize_topics(topics)

        payload = self.client.get_logs(
            normalized_address, start, end, topic_params, page_num, page_size
        )
        result = self._extract_result_list(payload, require_non_empty=False)
        logs = [self._map_log(entry) for entry in result if isinstance(entry, dict)]

        return {
            "address": normalized_address,
            "network": network_label,
            "chain_id": chain_id,
            "logs": logs,
            "page": page_num,
            "offset": page_size,
        }

    def get_storage_at(
        self,
        address: str,
        slot: str,
        network: Optional[str] = None,
        block_tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_address, network_label, chain_id = self._prepare_context(address, network)
        normalized_slot = self._normalize_slot(slot)
        tag = self._normalize_block_tag(block_tag)

        word = self._read_storage_word(normalized_address, normalized_slot, tag)

        return {
            "address": normalized_address,
            "network": network_label,
            "chain_id": chain_id,
            "slot": normalized_slot,
            "data": word,
            "block_tag": tag,
        }

    def call_function(
        self,
        address: str,
        data: str,
        network: Optional[str] = None,
        block_tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_address, network_label, chain_id = self._prepare_context(address, network)
        normalized_data = self._normalize_hex_string(data, "data")
        tag = self._normalize_block_tag(block_tag)

        payload = self.client.call(normalized_address, normalized_data, tag)
        result = self._extract_proxy_result(payload)

        return {
            "address": normalized_address,
            "network": network_label,
            "chain_id": chain_id,
            "block_tag": tag,
            "data": result,
        }

    def _prepare_context(self, address: str, network: Optional[str]) -> Tuple[str, str, str]:
        normalized_address = self._normalize_address(address)
        network_label, chain_id = self._resolve_network_and_chain(network)
        self.client.chain_id = chain_id
        return normalized_address, network_label, chain_id

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

    def _parse_contract_response(
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

    def _extract_result_list(self, payload: Dict[str, Any], require_non_empty: bool) -> List[Any]:
        if not isinstance(payload, dict):
            raise ValueError("Unexpected response from Etherscan.")

        status = str(payload.get("status", "")).strip()
        message = payload.get("message", "")
        result = payload.get("result")

        if not status and isinstance(result, list):
            if result or not require_non_empty:
                return result
            raise ValueError("Etherscan returned an empty result.")

        if status == "1":
            if isinstance(result, list):
                if result:
                    return result
                if require_non_empty:
                    raise ValueError("Etherscan returned an empty result.")
                return []
            raise ValueError("Unexpected response from Etherscan.")

        # Etherscan commonly returns status=0 with "No ... found" (or empty list) for empty sets.
        if status == "0":
            if isinstance(message, str) and message.lower().startswith("no"):
                if require_non_empty:
                    raise ValueError(f"Etherscan error: {message}.")
                return []
            if result == [] and not require_non_empty:
                return []

        detail = ""
        if isinstance(result, str):
            detail = result
        elif isinstance(result, list) and result:
            detail = result[0] if isinstance(result[0], str) else ""
        raise ValueError(f"Etherscan error: {detail or message or 'unknown error'}.")

    def _extract_proxy_result(self, payload: Dict[str, Any]) -> str:
        if not isinstance(payload, dict):
            raise ValueError("Unexpected response from Etherscan.")

        if "result" in payload and isinstance(payload.get("result"), str):
            return payload["result"]

        # JSON-RPC style error object from Etherscan proxy endpoints
        error_obj = payload.get("error")
        if isinstance(error_obj, dict):
            code = error_obj.get("code")
            message = error_obj.get("message")
            data = error_obj.get("data")
            parts = []
            if code is not None:
                parts.append(f"code {code}")
            if message:
                parts.append(str(message))
            if data:
                parts.append(str(data))
            detail = ": ".join(parts) if parts else "unknown error"
            raise ValueError(f"Etherscan error: {detail}.")

        status = str(payload.get("status", "")).strip()
        message = payload.get("message", "")
        result = payload.get("result")
        if status == "1" and isinstance(result, str):
            return result

        detail = ""
        if isinstance(result, str):
            detail = result
        raise ValueError(f"Etherscan error: {detail or message or 'unknown error'}.")

    def _normalize_block_range(self, start: Optional[int], end: Optional[int]) -> Tuple[int, int]:
        start_block = self._normalize_positive_int(start, 0, "start_block")
        end_block = self._normalize_positive_int(end, MAX_BLOCK, "end_block")
        if start_block > end_block:
            raise ValueError("start_block cannot be greater than end_block.")
        return start_block, end_block

    def _normalize_positive_int(self, value: Optional[int], default: int, field: str) -> int:
        if value is None:
            return default
        if isinstance(value, bool):
            raise ValueError(f"{field} must be a non-negative integer.")
        if isinstance(value, (int, float)):
            ivalue = int(value)
        elif isinstance(value, str) and value.strip().isdigit():
            ivalue = int(value.strip())
        else:
            raise ValueError(f"{field} must be a non-negative integer.")
        if ivalue < 0:
            raise ValueError(f"{field} must be a non-negative integer.")
        return ivalue

    def _normalize_sort(self, sort: Optional[str]) -> str:
        if sort is None:
            return "asc"
        normalized = sort.lower()
        if normalized not in {"asc", "desc"}:
            raise ValueError("sort must be 'asc' or 'desc'.")
        return normalized

    def _normalize_topics(self, topics: Optional[Sequence[Optional[str]]]) -> Dict[str, str]:
        if not topics:
            return {}
        if len(topics) > 4:
            raise ValueError("At most 4 topics are supported.")

        params: Dict[str, str] = {}
        for idx, topic in enumerate(topics):
            if topic is None or topic == "":
                continue
            params[f"topic{idx}"] = self._normalize_hex_string(topic, f"topic{idx}")
        return params

    def _normalize_slot(self, slot: str) -> str:
        return self._normalize_hex_string(slot, "slot", pad_to=64)

    def _normalize_block_tag(self, tag: Optional[str]) -> str:
        if tag is None:
            return "latest"

        if isinstance(tag, (int, float)):
            ivalue = int(tag)
            if ivalue < 0:
                raise ValueError("block_tag must be non-negative.")
            return hex(ivalue)

        if not isinstance(tag, str):
            raise ValueError("block_tag must be a string or integer.")

        candidate = tag.strip().lower()
        if candidate in {"latest", "earliest", "pending"}:
            return candidate

        if candidate.isdigit():
            ivalue = int(candidate)
            return hex(ivalue)

        if candidate.startswith("0x"):
            # assume already hex-encoded block number
            int(candidate, 16)  # validate hex
            return candidate

        raise ValueError("block_tag must be latest|pending|earliest|block number.")

    def _normalize_hex_string(self, value: str, field: str, pad_to: Optional[int] = None) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a hex string.")
        candidate = value.strip().lower()
        if not candidate.startswith("0x"):
            candidate = f"0x{candidate}"

        hex_body = candidate[2:]
        if not re.fullmatch(r"[0-9a-fA-F]*", hex_body):
            raise ValueError(f"{field} must be a hex string.")

        if pad_to:
            candidate = f"0x{hex_body.rjust(pad_to, '0')}"
        return candidate

    def _read_storage_word(self, address: str, slot: str, tag: str = "latest") -> str:
        payload = self.client.get_storage_at(address, slot, tag)
        return self._extract_proxy_result(payload)

    def _storage_word_to_address(self, word: Optional[str]) -> Optional[str]:
        if not word or not isinstance(word, str):
            return None
        normalized = self._normalize_hex_string(word, "storage_word", pad_to=64)
        try:
            value_int = int(normalized, 16)
        except ValueError as exc:
            raise ValueError("Invalid storage word returned from Etherscan.") from exc
        if value_int == 0:
            return None
        # last 20 bytes as address
        return f"0x{normalized[-40:]}"

    def _map_transaction(self, tx: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "hash": tx.get("hash"),
            "from": tx.get("from"),
            "to": tx.get("to"),
            "value": tx.get("value"),
            "gas": tx.get("gas"),
            "gas_price": tx.get("gasPrice"),
            "block_number": tx.get("blockNumber"),
            "timestamp": tx.get("timeStamp"),
            "input": tx.get("input"),
        }

    def _map_token_transfer(self, transfer: Dict[str, Any], token_type: str) -> Dict[str, Any]:
        base = {
            "token_address": transfer.get("contractAddress") or transfer.get("tokenAddress"),
            "token_symbol": transfer.get("tokenSymbol"),
            "from": transfer.get("from"),
            "to": transfer.get("to"),
            "tx_hash": transfer.get("hash"),
            "block_number": transfer.get("blockNumber"),
            "timestamp": transfer.get("timeStamp"),
            "token_type": token_type,
        }

        if token_type == "erc20":
            base["value"] = transfer.get("value")
            base["decimals"] = transfer.get("tokenDecimal")
        elif token_type == "erc721":
            base["token_id"] = transfer.get("tokenID") or transfer.get("tokenId")
        elif token_type == "erc1155":
            base["token_id"] = transfer.get("tokenID") or transfer.get("tokenId")
            base["value"] = transfer.get("tokenValue") or transfer.get("value")
        return base

    def _map_log(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "address": entry.get("address"),
            "topics": entry.get("topics"),
            "data": entry.get("data"),
            "block_number": entry.get("blockNumber"),
            "tx_hash": entry.get("transactionHash"),
            "log_index": entry.get("logIndex"),
            "time_stamp": entry.get("timeStamp"),
        }
