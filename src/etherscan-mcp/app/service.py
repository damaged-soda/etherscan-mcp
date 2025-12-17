import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import hashlib

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
        self.proxy_cache = ContractCache(config.cache_dir, namespace="proxy")
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
        start_block: Optional[Union[int, str]] = None,
        end_block: Optional[Union[int, str]] = None,
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
        from_block: Optional[Union[int, str]] = None,
        to_block: Optional[Union[int, str]] = None,
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
        data: Optional[str] = None,
        network: Optional[str] = None,
        block_tag: Optional[str] = None,
        function: Optional[str] = None,
        args: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        normalized_address, network_label, chain_id = self._prepare_context(address, network)
        normalized_data = self._prepare_call_data(
            data=data, function=function, args=args, address=normalized_address, chain_id=chain_id, network_label=network_label
        )
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

    def encode_function_data(self, function: str, args: Optional[List[Any]] = None) -> Dict[str, str]:
        selector, data = self._encode_function_call(function, args or [])
        return {"function": function, "selector": selector, "data": data}

    def _prepare_context(self, address: str, network: Optional[str]) -> Tuple[str, str, str]:
        normalized_address = self._normalize_address(address)
        network_label, chain_id = self._resolve_network_and_chain(network)
        self.client.chain_id = chain_id
        return normalized_address, network_label, chain_id

    def _prepare_call_data(
        self,
        data: Optional[str],
        function: Optional[str],
        args: Optional[List[Any]],
        address: str,
        chain_id: str,
        network_label: Optional[str],
    ) -> str:
        """Build or normalize call data; if ABI is cached (proxy-aware), validate selector and length."""
        if function:
            if data:
                raise ValueError("Provide either function+args or data, not both.")
            selector_hex, encoded_data = self._encode_function_call(function, args or [])
            normalized = encoded_data
        else:
            if not data:
                raise ValueError("Either data or function+args is required.")
            normalized = self._normalize_hex_string(data, "data")

        # data must include at least 4-byte selector (8 hex chars after 0x)
        if len(normalized) < 10:
            raise ValueError("data must include 4-byte function selector.")

        selector = normalized[2:10]
        selector_maps: List[Tuple[Dict[str, Dict[str, Any]], str]] = []

        def add_selector_map(abi_obj: Any, source: str) -> None:
            if not isinstance(abi_obj, list):
                return
            functions = [
                entry for entry in abi_obj if isinstance(entry, dict) and entry.get("type") == "function"
            ]
            selector_map: Dict[str, Dict[str, Any]] = {}
            for entry in functions:
                name = entry.get("name")
                inputs = entry.get("inputs", [])
                if not name or not isinstance(inputs, list):
                    continue
                try:
                    sig = self._function_signature(name, inputs)
                    sel = self._selector_hex(sig)
                    if sel:
                        selector_map[sel] = entry
                except Exception:
                    continue
            if selector_map:
                selector_maps.append((selector_map, source))

        # 1) cached ABI on the address itself
        cached = self.cache.get(address, chain_id)
        if cached:
            add_selector_map(cached.get("abi"), "contract")

        # 2) proxy-aware: if selector not found yet, try detect proxy and implementation ABI
        need_proxy_lookup = True
        for selector_map, _ in selector_maps:
            if selector in selector_map:
                need_proxy_lookup = False
                break

        proxy_info = None
        if need_proxy_lookup:
            proxy_info = self.proxy_cache.get(address, chain_id)
            if proxy_info is None:
                try:
                    proxy_info = self.detect_proxy(address, network_label)
                except Exception:
                    proxy_info = {"is_proxy": False}
                self.proxy_cache.set(address, chain_id, proxy_info)

            if proxy_info.get("is_proxy") and proxy_info.get("implementation"):
                impl_address = proxy_info["implementation"]
                impl_cached = self.cache.get(impl_address, chain_id)
                impl_data = impl_cached
                if not impl_data:
                    try:
                        impl_data = self.fetch_contract(impl_address, network_label)
                    except Exception:
                        impl_data = None
                if impl_data:
                    add_selector_map(impl_data.get("abi"), "implementation")

        # Validate against available selector maps (prefer implementation if present by insertion order)
        available_selectors: List[str] = []
        for selector_map, source in selector_maps:
            available_selectors.extend(selector_map.keys())
            if selector not in selector_map:
                continue
            func_entry = selector_map[selector]
            inputs = func_entry.get("inputs", [])
            if not isinstance(inputs, list):
                return normalized

            static_words = 0
            for inp in inputs:
                typ = inp.get("type")
                if not isinstance(typ, str):
                    continue
                if self._is_dynamic_type(typ):
                    continue
                static_words += 1

            min_length = 10 + static_words * 64  # 0x + selector(8 hex) + 32 bytes per static arg
            if len(normalized) < min_length:
                raise ValueError(
                    f"data too short for function {func_entry.get('name','?')}: "
                    f"expected at least {min_length - 2} hex chars (selector + {static_words} static args)."
                )

            # For dynamic args we only validate head length; tail length cannot be validated without decoding.
            return normalized

        # If we have ABI info but selector not found:
        if available_selectors:
            # If proxy and no implementation ABI, allow call to proceed (avoid blocking proxies with missing impl ABI)
            if proxy_info and proxy_info.get("is_proxy") and not any(
                src == "implementation" for _, src in selector_maps
            ):
                return normalized
            available = ", ".join(sorted(set(available_selectors)))
            raise ValueError(
                f"Function selector 0x{selector} not found in cached ABI. Known selectors: {available or 'none'}."
            )

        return normalized

    def _encode_function_call(self, function: str, args: List[Any]) -> Tuple[str, str]:
        """Encode function selector + arguments into hex data."""
        fn_name, input_types = self._parse_function_signature(function)
        if len(input_types) != len(args):
            raise ValueError(f"Argument count mismatch: expected {len(input_types)}, got {len(args)}.")

        selector = self._selector_hex(f"{fn_name}({','.join(input_types)})")
        if not selector:
            raise ValueError("Failed to compute function selector.")

        head_parts: List[bytes] = []
        tail_parts: List[bytes] = []
        dynamic_offset = 32 * len(input_types)

        for typ, value in zip(input_types, args):
            enc, dynamic = self._encode_abi_value(typ, value)
            if dynamic:
                # head contains offset to current tail start
                head_parts.append(self._pad32(dynamic_offset.to_bytes(32, "big")))
                tail_parts.append(enc)
                dynamic_offset += len(enc)
            else:
                head_parts.append(enc)

        data_bytes = b"".join(head_parts + tail_parts)
        return selector, "0x" + selector + data_bytes.hex()

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

    def _normalize_block_range(
        self, start: Optional[Union[int, str]], end: Optional[Union[int, str]]
    ) -> Tuple[int, int]:
        start_block = self._parse_block_number(start, 0, "start_block")
        end_block = self._parse_block_number(end, MAX_BLOCK, "end_block")
        if start_block > end_block:
            raise ValueError("start_block cannot be greater than end_block.")
        return start_block, end_block

    def _parse_block_number(
        self, value: Optional[Union[int, str]], default: int, field: str
    ) -> int:
        if value is None:
            return default
        message = f"{field} must be a non-negative block number in decimal or 0x-prefixed hexadecimal."
        if isinstance(value, bool):
            raise ValueError(message)
        if isinstance(value, (int, float)):
            ivalue = int(value)
        elif isinstance(value, str):
            candidate = value.strip().lower()
            if candidate.startswith("0x"):
                try:
                    ivalue = int(candidate, 16)
                except ValueError as exc:
                    raise ValueError(message) from exc
            elif candidate.isdigit():
                ivalue = int(candidate)
            else:
                raise ValueError(message)
        else:
            raise ValueError(message)

        if ivalue < 0:
            raise ValueError(message)
        return ivalue

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

    def _function_signature(self, name: str, inputs: List[Dict[str, Any]]) -> str:
        types: List[str] = []
        for inp in inputs:
            typ = inp.get("type")
            if not isinstance(typ, str):
                raise ValueError("Invalid ABI input type.")
            types.append(typ)
        return f"{name}({','.join(types)})"

    def _selector_hex(self, signature: str) -> Optional[str]:
        try:
            import sha3  # type: ignore

            hasher = sha3.keccak_256()  # correct keccak-256 for Ethereum
            hasher.update(signature.encode())
            return hasher.hexdigest()[:8]
        except Exception:
            pass

        try:
            hasher = hashlib.new("keccak256")
            hasher.update(signature.encode())
            return hasher.hexdigest()[:8]
        except Exception:
            pass

        try:
            digest = self._keccak256(signature.encode())
            return digest.hex()[:8]
        except Exception:
            return None

    def _is_dynamic_type(self, typ: str) -> bool:
        if typ == "bytes" or typ == "string":
            return True
        if typ.endswith("[]"):
            return True
        if typ.startswith("tuple"):
            return True
        return False

    def _keccak256(self, data: bytes) -> bytes:
        """Pure-Python Keccak-256 (for environments without keccak bindings)."""
        # Parameters for Keccak-256
        rate_bits = 1088
        rate_bytes = rate_bits // 8  # 136
        capacity_bits = 512  # noqa: F841
        output_bytes = 32

        # Padding: pad10*1
        padded = bytearray(data)
        padded.append(0x01)
        while (len(padded) % rate_bytes) != rate_bytes - 1:
            padded.append(0x00)
        padded.append(0x80)

        state = [0] * 25  # 5x5 of 64-bit lanes

        def _rot(x: int, n: int) -> int:
            return ((x << n) | (x >> (64 - n))) & ((1 << 64) - 1)

        # Round constants
        RC = [
            0x0000000000000001,
            0x0000000000008082,
            0x800000000000808A,
            0x8000000080008000,
            0x000000000000808B,
            0x0000000080000001,
            0x8000000080008081,
            0x8000000000008009,
            0x000000000000008A,
            0x0000000000000088,
            0x0000000080008009,
            0x000000008000000A,
            0x000000008000808B,
            0x800000000000008B,
            0x8000000000008089,
            0x8000000000008003,
            0x8000000000008002,
            0x8000000000000080,
            0x000000000000800A,
            0x800000008000000A,
            0x8000000080008081,
            0x8000000000008080,
            0x0000000080000001,
            0x8000000080008008,
        ]

        # Rotation offsets
        r = [
            [0, 36, 3, 41, 18],
            [1, 44, 10, 45, 2],
            [62, 6, 43, 15, 61],
            [28, 55, 25, 21, 56],
            [27, 20, 39, 8, 14],
        ]

        def keccak_f():
            nonlocal state
            for rc in RC:
                # Theta
                C = [state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20] for x in range(5)]
                D = [C[(x - 1) % 5] ^ _rot(C[(x + 1) % 5], 1) for x in range(5)]
                state = [state[i] ^ D[i % 5] for i in range(25)]

                # Rho and Pi
                B = [0] * 25
                for x in range(5):
                    for y in range(5):
                        B[y + ((2 * x + 3 * y) % 5) * 5] = _rot(state[x + 5 * y], r[x][y])

                # Chi
                for x in range(5):
                    for y in range(5):
                        state[x + 5 * y] = B[x + 5 * y] ^ ((~B[(x + 1) % 5 + 5 * y]) & B[(x + 2) % 5 + 5 * y])

                # Iota
                state[0] ^= rc

        # Absorb
        for offset in range(0, len(padded), rate_bytes):
            block = padded[offset : offset + rate_bytes]
            for i in range(0, rate_bytes, 8):
                lane = int.from_bytes(block[i : i + 8], "little")
                state[i // 8] ^= lane
            keccak_f()

        # Squeeze
        out = bytearray()
        while len(out) < output_bytes:
            for i in range(rate_bytes // 8):
                out.extend(state[i].to_bytes(8, "little"))
            if len(out) >= output_bytes:
                break
            keccak_f()

        return bytes(out[:output_bytes])

    def _parse_function_signature(self, signature: str) -> Tuple[str, List[str]]:
        text = signature.strip()
        if "(" not in text or not text.endswith(")"):
            raise ValueError("function must be in the form name(type1,type2,...)")
        name, rest = text.split("(", 1)
        fn = name.strip()
        if not fn or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", fn):
            raise ValueError("Invalid function name.")
        params = rest[:-1]  # drop trailing ')'
        types: List[str] = []
        if params.strip():
            depth = 0
            buf = ""
            for ch in params:
                if ch == "," and depth == 0:
                    types.append(buf.strip())
                    buf = ""
                    continue
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                buf += ch
            if buf:
                types.append(buf.strip())
        for t in types:
            if not t:
                raise ValueError("Empty type in function signature.")
        return fn, types

    def _encode_abi_value(self, typ: str, value: Any) -> Tuple[bytes, bool]:
        base_type, dimensions = self._split_array_dimensions(typ)
        if dimensions:
            return self._encode_array(base_type, dimensions, value)

        if base_type == "address":
            if not isinstance(value, str):
                raise ValueError("address value must be a string.")
            v = value.lower()
            if v.startswith("0x"):
                v = v[2:]
            if len(v) != 40 or not re.fullmatch(r"[0-9a-fA-F]{40}", v):
                raise ValueError("Invalid address value.")
            return self._pad32(bytes.fromhex(v)), False

        if base_type.startswith("uint"):
            bits = 256
            suffix = base_type[4:]
            if suffix:
                bits = int(suffix)
            if bits <= 0 or bits > 256 or bits % 8 != 0:
                raise ValueError(f"Unsupported uint size {bits}.")
            if not isinstance(value, int):
                raise ValueError("uint value must be an integer.")
            if value < 0 or value >= 2**bits:
                raise ValueError("uint value out of range.")
            return value.to_bytes(32, "big"), False

        if base_type.startswith("int"):
            bits = 256
            suffix = base_type[3:]
            if suffix:
                bits = int(suffix)
            if bits <= 0 or bits > 256 or bits % 8 != 0:
                raise ValueError(f"Unsupported int size {bits}.")
            if not isinstance(value, int):
                raise ValueError("int value must be an integer.")
            min_val = -(2 ** (bits - 1))
            max_val = 2 ** (bits - 1) - 1
            if value < min_val or value > max_val:
                raise ValueError("int value out of range.")
            return int(value & (2**256 - 1)).to_bytes(32, "big"), False

        if base_type == "bool":
            if isinstance(value, bool):
                iv = 1 if value else 0
            elif isinstance(value, int):
                if value not in (0, 1):
                    raise ValueError("bool must be 0 or 1.")
                iv = value
            else:
                raise ValueError("bool value must be bool or 0/1.")
            return self._pad32(iv.to_bytes(32, "big")), False

        if base_type == "bytes":
            data_bytes = self._to_bytes(value, "bytes")
            return self._encode_dynamic_bytes(data_bytes), True

        if base_type == "string":
            if not isinstance(value, str):
                raise ValueError("string value must be a string.")
            data_bytes = value.encode()
            return self._encode_dynamic_bytes(data_bytes), True

        if base_type.startswith("bytes"):
            size_part = base_type[5:]
            if not size_part.isdigit():
                raise ValueError(f"Unsupported bytes type {base_type}.")
            size = int(size_part)
            if size <= 0 or size > 32:
                raise ValueError("bytesN size must be between 1 and 32.")
            data_bytes = self._to_bytes(value, base_type)
            if len(data_bytes) != size:
                raise ValueError(f"{base_type} requires {size} bytes.")
            padded = data_bytes.ljust(32, b"\x00")
            return padded, False

        raise ValueError(f"Unsupported ABI type '{base_type}'.")

    def _encode_array(self, base_type: str, dimensions: List[Optional[int]], value: Any) -> Tuple[bytes, bool]:
        if not dimensions:
            return self._encode_abi_value(base_type, value)
        if not isinstance(value, (list, tuple)):
            raise ValueError("Array value must be a list or tuple.")

        dim = dimensions[0]
        remaining = dimensions[1:]
        values = list(value)

        if dim is None:
            # dynamic array
            length_bytes = self._pad32(len(values).to_bytes(32, "big"))
            head_parts: List[bytes] = []
            tail_parts: List[bytes] = []
            offset = 32 * len(values)
            for v in values:
                enc, dynamic = self._encode_array(base_type, remaining, v)
                if dynamic:
                    head_parts.append(self._pad32(offset.to_bytes(32, "big")))
                    tail_parts.append(enc)
                    offset += len(enc)
                else:
                    head_parts.append(enc)
            payload = b"".join([length_bytes] + head_parts + tail_parts)
            return payload, True

        # static array
        if len(values) != dim:
            raise ValueError(f"Expected array of length {dim}, got {len(values)}.")

        element_encodings: List[Tuple[bytes, bool]] = [self._encode_array(base_type, remaining, v) for v in values]
        if any(dynamic for _, dynamic in element_encodings):
            # static array of dynamic elements -> overall dynamic
            head_parts: List[bytes] = []
            tail_parts: List[bytes] = []
            offset = 32 * len(element_encodings)
            for enc, dynamic in element_encodings:
                if dynamic:
                    head_parts.append(self._pad32(offset.to_bytes(32, "big")))
                    tail_parts.append(enc)
                    offset += len(enc)
                else:
                    head_parts.append(enc)
            payload = b"".join(head_parts + tail_parts)
            return payload, True

        payload = b"".join(enc for enc, _ in element_encodings)
        return payload, False

    def _encode_dynamic_bytes(self, data: bytes) -> bytes:
        length_bytes = self._pad32(len(data).to_bytes(32, "big"))
        padded_data = data + b"\x00" * ((32 - (len(data) % 32)) % 32)
        return length_bytes + padded_data

    def _to_bytes(self, value: Any, field: str) -> bytes:
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            v = value.strip().lower()
            if v.startswith("0x"):
                v = v[2:]
            if len(v) % 2 != 0:
                v = "0" + v
            if not re.fullmatch(r"[0-9a-fA-F]*", v):
                raise ValueError(f"{field} must be hex string or bytes.")
            return bytes.fromhex(v)
        raise ValueError(f"{field} must be hex string or bytes.")

    def _split_array_dimensions(self, typ: str) -> Tuple[str, List[Optional[int]]]:
        base = typ.strip()
        dims: List[Optional[int]] = []
        while base.endswith("]"):
            lidx = base.rfind("[")
            dim_str = base[lidx + 1 : -1]
            if dim_str == "":
                dims.insert(0, None)
            else:
                dims.insert(0, int(dim_str))
            base = base[:lidx]
        return base, dims

    def _pad32(self, b: bytes) -> bytes:
        if len(b) == 32:
            return b
        if len(b) > 32:
            raise ValueError("Encoded value exceeds 32 bytes.")
        return b.rjust(32, b"\x00")

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
