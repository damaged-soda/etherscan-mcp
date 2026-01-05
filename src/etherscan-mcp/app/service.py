import copy
import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import hashlib
from decimal import Decimal, getcontext

from .cache import ContractCache
from .chains import ChainRegistry
from .config import Config, resolve_chain_id
from .etherscan_client import EtherscanClient
from .rpc_client import RpcClient

ADDRESS_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")
EIP1967_IMPLEMENTATION_SLOT = "0x360894A13BA1A3210667C828492DB98DCA3E2076CC3735A920A3CA505D382BBC"
EIP1967_ADMIN_SLOT = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"
MAX_BLOCK = 99999999
DEFAULT_PAGE = 1
DEFAULT_OFFSET = 100
DEFAULT_INLINE_SOURCE_LIMIT = 20000
RPC_LOGS_BLOCK_STEP = 2000

# Increase precision for Decimal-based formatting
getcontext().prec = 100


class ContractService:
    """Combine configuration, cache, and client to serve contract details."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.cache = ContractCache()
        self.creation_cache = ContractCache()
        self.proxy_cache = ContractCache()
        self._rpc_clients: Dict[str, RpcClient] = {}
        self.client = EtherscanClient(
            api_key=config.api_key,
            base_url=config.base_url,
            chain_id=config.chain_id,
            timeout=config.request_timeout,
            max_retries=config.max_retries,
            backoff_seconds=config.backoff_seconds,
        )
        self.chains = ChainRegistry(
            client=self.client,
            chainlist_url=config.chainlist_url,
            ttl_seconds=config.chainlist_ttl_seconds,
        )

        # Best-effort: if NETWORK is not in the static fallback map and CHAIN_ID is not set,
        # resolve the default chain via /v2/chainlist once at startup.
        if not self.config.chain_id_override:
            try:
                _ = resolve_chain_id(self.config.network)
            except Exception:
                try:
                    label, cid, _meta = self.chains.resolve(self.config.network)
                    self.config.chain_id = cid
                    self.config.network = label
                except Exception:
                    pass

    def fetch_contract(
        self,
        address: str,
        network: Optional[str] = None,
        inline_limit: Optional[int] = None,
        force_inline: bool = False,
    ) -> Dict[str, Any]:
        normalized_address, network_label, chain_id = self._prepare_context(address, network)

        limit = self._normalize_inline_limit(inline_limit)
        contract = self._get_full_contract(normalized_address, network_label, chain_id)
        return self._apply_inline_policy(contract, limit, force_inline)

    def get_source_file(
        self,
        address: str,
        filename: str,
        network: Optional[str] = None,
        offset: Optional[int] = None,
        length: Optional[int] = None,
    ) -> Dict[str, Any]:
        normalized_address, network_label, chain_id = self._prepare_context(address, network)

        if not isinstance(filename, str) or not filename.strip():
            raise ValueError("filename must be a non-empty string.")
        target_name = filename.strip()
        slice_offset = self._normalize_positive_int(offset, 0, "offset")
        slice_length = self._normalize_optional_positive_int(length, "length")

        contract = self._get_full_contract(normalized_address, network_label, chain_id)
        source_files = contract.get("source_files") or []

        match = None
        for entry in source_files:
            if not isinstance(entry, dict):
                continue
            if entry.get("filename") == target_name:
                match = entry
                break

        if match is None:
            raise ValueError(f"filename '{target_name}' not found for contract {normalized_address}.")

        content = match.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        total_length = len(content)
        if slice_offset > total_length:
            raise ValueError("offset exceeds file length.")

        if slice_length is None:
            end = total_length
        else:
            end = min(total_length, slice_offset + slice_length)

        chunk = content[slice_offset:end]
        sha256_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        return {
            "address": normalized_address,
            "network": network_label,
            "chain_id": chain_id,
            "filename": target_name,
            "offset": slice_offset,
            "returned_length": len(chunk),
            "total_length": total_length,
            "sha256": sha256_hash,
            "content": chunk,
            "truncated": end < total_length,
        }

    def get_contract_creation(self, address: str, network: Optional[str] = None) -> Dict[str, Any]:
        normalized_address, network_label, chain_id = self._prepare_context(address, network)

        cached = self.creation_cache.get(normalized_address, chain_id)
        if cached:
            return cached

        allow_default_rpc = network is None
        rpc = self._get_rpc_client(chain_id, allow_default_rpc)

        try:
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
                "creator": str(creator).lower() if creator else "",
                "tx_hash": str(tx_hash).lower() if tx_hash else "",
                "block_number": str(block_number) if block_number is not None else "",
                "timestamp": str(timestamp) if timestamp is not None else None,
                "source": "etherscan",
                "complete": bool(creator and tx_hash),
            }
            self.creation_cache.set(normalized_address, chain_id, data)
            return data
        except Exception as exc:
            if not rpc:
                raise ValueError(
                    f"{exc} "
                    f"(RPC fallback unavailable; set RPC_URL_{chain_id} or RPC_{chain_id} "
                    "to enable best-effort creation lookup.)"
                ) from exc

            try:
                data = self._get_contract_creation_via_rpc(normalized_address, network_label, chain_id, rpc)
            except Exception as rpc_exc:
                raise ValueError(f"{exc} (RPC fallback failed: {rpc_exc})") from rpc_exc

            self.creation_cache.set(normalized_address, chain_id, data)
            return data

    def _get_contract_creation_via_rpc(
        self,
        address: str,
        network_label: str,
        chain_id: str,
        rpc: RpcClient,
    ) -> Dict[str, Any]:
        code_latest = rpc.call("eth_getCode", [address, "latest"])
        if not isinstance(code_latest, str):
            raise ValueError("RPC error: eth_getCode returned unexpected result.")
        if code_latest.lower() in {"0x", "0x0"}:
            raise ValueError("RPC error: address has no contract code at latest.")

        latest_block = rpc.get_block_number()

        def has_code(block_number: int) -> bool:
            try:
                code = rpc.call("eth_getCode", [address, hex(block_number)])
            except Exception as exc:
                raise ValueError(
                    "RPC error: failed to query historical contract code; an archive/full-history node may be required."
                ) from exc
            if not isinstance(code, str):
                raise ValueError("RPC error: eth_getCode returned unexpected result.")
            return code.lower() not in {"0x", "0x0"}

        lo = 0
        hi = latest_block
        while lo < hi:
            mid = (lo + hi) // 2
            if has_code(mid):
                hi = mid
            else:
                lo = mid + 1

        deployment_block = lo

        block = rpc.call("eth_getBlockByNumber", [hex(deployment_block), True])
        if not isinstance(block, dict):
            raise ValueError("RPC error: eth_getBlockByNumber returned unexpected result.")

        timestamp_hex = block.get("timestamp")
        timestamp: Optional[str] = None
        if isinstance(timestamp_hex, str) and timestamp_hex:
            try:
                timestamp = str(int(timestamp_hex, 16))
            except Exception as exc:
                raise ValueError("RPC error: block timestamp is not a valid hex value.") from exc

        creator = ""
        tx_hash = ""

        txs = block.get("transactions")
        if isinstance(txs, list):
            for tx in txs:
                if not isinstance(tx, dict):
                    continue
                if tx.get("to") is not None:
                    continue
                tx_hash_candidate = tx.get("hash")
                if not isinstance(tx_hash_candidate, str) or not tx_hash_candidate:
                    continue
                receipt = rpc.call("eth_getTransactionReceipt", [tx_hash_candidate])
                if not isinstance(receipt, dict):
                    continue
                created = receipt.get("contractAddress")
                if isinstance(created, str) and created.lower() == address.lower():
                    tx_hash = tx_hash_candidate.lower()
                    creator_candidate = tx.get("from")
                    creator = str(creator_candidate).lower() if creator_candidate else ""
                    break

        return {
            "address": address,
            "network": network_label,
            "chain_id": chain_id,
            "creator": creator,
            "tx_hash": tx_hash,
            "block_number": str(deployment_block),
            "timestamp": timestamp,
            "source": "rpc",
            "complete": bool(creator and tx_hash),
        }

    def detect_proxy(self, address: str, network: Optional[str] = None) -> Dict[str, Any]:
        normalized_address, network_label, chain_id = self._prepare_context(address, network)

        allow_default_rpc = network is None
        impl_word = self._read_storage_word(
            normalized_address,
            EIP1967_IMPLEMENTATION_SLOT,
            "latest",
            chain_id=chain_id,
            allow_default_rpc=allow_default_rpc,
        )
        admin_word = self._read_storage_word(
            normalized_address,
            EIP1967_ADMIN_SLOT,
            "latest",
            chain_id=chain_id,
            allow_default_rpc=allow_default_rpc,
        )

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
        page_num = self._normalize_positive_int(page, DEFAULT_PAGE, "page")
        page_size = self._normalize_positive_int(offset, DEFAULT_OFFSET, "offset")

        allow_default_rpc = network is None
        rpc = self._get_rpc_client(chain_id, allow_default_rpc)
        if rpc:
            start_block = self._parse_block_number(from_block, 0, "from_block")
            if to_block is None:
                end_block = rpc.get_block_number()
            else:
                end_block = self._parse_block_number(to_block, 0, "to_block")
            if start_block > end_block:
                raise ValueError("from_block cannot be greater than to_block.")

            topics_list = self._normalize_topics_list(topics)
            needed = page_num * page_size
            raw_logs: List[Dict[str, Any]] = []

            current = start_block
            while current <= end_block and len(raw_logs) < needed:
                seg_end = min(end_block, current + RPC_LOGS_BLOCK_STEP - 1)
                filt: Dict[str, Any] = {
                    "address": normalized_address,
                    "fromBlock": hex(current),
                    "toBlock": hex(seg_end),
                }
                if topics_list is not None:
                    filt["topics"] = topics_list

                chunk = rpc.call("eth_getLogs", [filt])
                if not isinstance(chunk, list):
                    raise ValueError("RPC error: eth_getLogs returned unexpected result.")
                for entry in chunk:
                    if isinstance(entry, dict):
                        raw_logs.append(entry)
                        if len(raw_logs) >= needed:
                            break
                current = seg_end + 1

            start_idx = (page_num - 1) * page_size
            end_idx = start_idx + page_size
            logs = [self._map_log(entry) for entry in raw_logs[start_idx:end_idx] if isinstance(entry, dict)]
        else:
            start, end = self._normalize_block_range(from_block, to_block)
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

        allow_default_rpc = network is None
        word = self._read_storage_word(
            normalized_address,
            normalized_slot,
            tag,
            chain_id=chain_id,
            allow_default_rpc=allow_default_rpc,
        )

        return {
            "address": normalized_address,
            "network": network_label,
            "chain_id": chain_id,
            "slot": normalized_slot,
            "data": word,
            "block_tag": tag,
        }

    def get_transaction(self, tx_hash: str, network: Optional[str] = None) -> Dict[str, Any]:
        network_label, chain_id = self._resolve_network_and_chain(network)
        self.client.chain_id = chain_id
        normalized_hash = self._normalize_tx_hash(tx_hash)

        allow_default_rpc = network is None
        rpc = self._get_rpc_client(chain_id, allow_default_rpc)
        if rpc:
            tx_result = rpc.call("eth_getTransactionByHash", [normalized_hash])
            if tx_result is not None and not isinstance(tx_result, dict):
                raise ValueError("RPC error: eth_getTransactionByHash returned unexpected result.")

            receipt_result = rpc.call("eth_getTransactionReceipt", [normalized_hash])
            if receipt_result is not None and not isinstance(receipt_result, dict):
                raise ValueError("RPC error: eth_getTransactionReceipt returned unexpected result.")
        else:
            tx_payload = self.client.get_transaction(normalized_hash)
            tx_result = self._extract_proxy_result(tx_payload, allow_none=True)

            receipt_payload = self.client.get_transaction_receipt(normalized_hash)
            receipt_result = self._extract_proxy_result(receipt_payload, allow_none=True)

        tx_obj = self._map_transaction_detail(tx_result) if tx_result else None
        receipt_obj = self._map_receipt(receipt_result) if receipt_result else None

        return {
            "tx_hash": normalized_hash,
            "network": network_label,
            "chain_id": chain_id,
            "transaction": tx_obj,
            "receipt": receipt_obj,
        }

    def get_block_by_number(
        self,
        block: Union[int, str],
        network: Optional[str] = None,
        full_transactions: bool = False,
        tx_hashes_only: bool = False,
    ) -> Dict[str, Any]:
        network_label, chain_id = self._resolve_network_and_chain(network)
        self.client.chain_id = chain_id
        tag = self._normalize_block_tag(block)

        include_full_txs = bool(full_transactions)
        if tx_hashes_only:
            include_full_txs = False

        allow_default_rpc = network is None
        rpc = self._get_rpc_client(chain_id, allow_default_rpc)
        if rpc:
            result = rpc.call("eth_getBlockByNumber", [tag, include_full_txs])
        else:
            payload = self.client.get_block_by_number(tag, include_full_txs)
            result = self._extract_proxy_result(payload)
        if not isinstance(result, dict):
            raise ValueError("Unexpected block response.")

        block_obj = self._map_block(result, force_hashes_only=tx_hashes_only)
        return {
            "network": network_label,
            "chain_id": chain_id,
            "block": block_obj,
            "full_transactions": include_full_txs,
            "tx_hashes_only": bool(tx_hashes_only),
        }

    def get_block_time_by_number(
        self, block: Union[int, str], network: Optional[str] = None
    ) -> Dict[str, Any]:
        block_data = self.get_block_by_number(block, network, full_transactions=False, tx_hashes_only=True)
        blk = block_data.get("block") or {}
        number_hex = blk.get("number")
        timestamp_hex = blk.get("timestamp")

        number_int = self._hex_to_int(number_hex, "block_number") if number_hex else None
        timestamp_int = self._hex_to_int(timestamp_hex, "timestamp") if timestamp_hex else None
        iso_time: Optional[str] = None
        if timestamp_int is not None:
            try:
                import datetime

                iso_time = datetime.datetime.utcfromtimestamp(timestamp_int).isoformat() + "Z"
            except Exception:
                iso_time = None

        return {
            "network": block_data.get("network"),
            "chain_id": block_data.get("chain_id"),
            "block_number": number_int,
            "block_number_hex": number_hex,
            "timestamp": timestamp_int,
            "timestamp_hex": timestamp_hex,
            "timestamp_iso": iso_time,
        }

    def call_function(
        self,
        address: str,
        data: Optional[str] = None,
        network: Optional[str] = None,
        block_tag: Optional[str] = None,
        function: Optional[str] = None,
        args: Optional[List[Any]] = None,
        decimals: Optional[Any] = None,
    ) -> Dict[str, Any]:
        normalized_address, network_label, chain_id = self._prepare_context(address, network)
        normalized_data, func_meta = self._prepare_call_data(
            data=data, function=function, args=args, address=normalized_address, chain_id=chain_id, network_label=network_label
        )
        tag = self._normalize_block_tag(block_tag)

        allow_default_rpc = network is None
        rpc = self._get_rpc_client(chain_id, allow_default_rpc)
        if rpc:
            raw_result = rpc.call(
                "eth_call",
                [{"to": normalized_address, "data": normalized_data}, tag],
            )
            if not isinstance(raw_result, str):
                raise ValueError("RPC error: eth_call returned unexpected result.")
            result = self._normalize_hex_string(raw_result, "result")
        else:
            payload = self.client.call(normalized_address, normalized_data, tag)
            result = self._extract_proxy_result(payload)
        decoded = self._decode_call_result(result, func_meta, decimals)

        response: Dict[str, Any] = {
            "address": normalized_address,
            "network": network_label,
            "chain_id": chain_id,
            "block_tag": tag,
            "data": result,
            "decoded": decoded,
        }
        if function:
            response["function"] = function
        if args is not None:
            response["args"] = args
        return response

    def encode_function_data(self, function: str, args: Optional[List[Any]] = None) -> Dict[str, str]:
        selector, data = self._encode_function_call(function, args or [])
        return {"function": function, "selector": selector, "data": data}

    def convert(
        self,
        value: Any,
        from_unit: str,
        to_unit: str,
        decimals: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Convert between hex/dec/human/wei/gwei/eth with optional decimals (default 18).
        Returns JSON with original/converted/explain.
        """
        from_norm = (from_unit or "").lower()
        to_norm = (to_unit or "").lower()
        allowed = {"hex", "dec", "human", "wei", "gwei", "eth"}
        if from_norm not in allowed or to_norm not in allowed:
            raise ValueError("from/to must be one of: hex, dec, human, wei, gwei, eth.")

        decimals_val = self._parse_decimals_int(decimals, default=18)
        base_int = self._convert_to_int(value, from_norm, decimals_val)
        converted = self._convert_from_int(base_int, to_norm, decimals_val)

        explain = self._build_explain(value, from_norm, to_norm, decimals_val, base_int, converted)

        resp: Dict[str, Any] = {
            "original": {"value": self._stringify(value, from_norm), "unit": from_norm},
            "converted": {"value": converted["value"], "unit": to_norm},
            "from": from_norm,
            "to": to_norm,
            "decimals": decimals_val,
            "explain": explain,
        }
        if "thousands" in converted:
            resp["converted"]["thousands"] = converted["thousands"]
        if "scientific" in converted:
            resp["converted"]["scientific"] = converted["scientific"]
        return resp

    def _stringify(self, value: Any, unit: str) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float)):
            return str(value)
        return str(value)

    def _convert_to_int(self, value: Any, unit: str, decimals: int) -> int:
        if unit == "hex":
            if not isinstance(value, str):
                raise ValueError("For from=hex, value must be a hex string.")
            normalized = self._normalize_hex_string(value, "value")
            return int(normalized, 16)
        if unit == "dec":
            return self._parse_integer_string(str(value), "value")
        if unit in {"wei", "gwei", "eth"}:
            scale = 18 if unit == "eth" else 9 if unit == "gwei" else 0
            return self._decimal_to_int(str(value), scale, unit, allow_fraction=True)
        if unit == "human":
            return self._decimal_to_int(str(value), decimals, "human", allow_fraction=True)
        raise ValueError("Unsupported from unit.")

    def _convert_from_int(self, value: int, unit: str, decimals: int) -> Dict[str, str]:
        if unit == "hex":
            if value < 0:
                return {"value": "-" + hex(-value)[2:]}
            return {"value": hex(value)[2:]}
        if unit == "dec":
            return {"value": str(value)}
        if unit in {"wei", "gwei", "eth"}:
            scale = 18 if unit == "eth" else 9 if unit == "gwei" else 0
            if scale == 0:
                return {"value": str(value)}
            return {"value": self._format_scaled_int(value, scale)}
        if unit == "human":
            plain = self._format_scaled_int(value, decimals)
            return {
                "value": plain,
                "thousands": self._format_thousands(plain),
                "scientific": self._format_scientific_int(value, decimals),
            }
        raise ValueError("Unsupported to unit.")

    def _format_thousands(self, text: str) -> str:
        negative = text.startswith("-")
        body = text[1:] if negative else text
        if "." in body:
            whole, frac = body.split(".", 1)
            formatted = f"{int(whole or 0):,}.{frac}"
        else:
            formatted = f"{int(body or 0):,}"
        return f"-{formatted}" if negative else formatted

    def _format_scientific_int(self, value: int, decimals: int) -> str:
        dec_value = Decimal(value) / (Decimal(10) ** decimals)
        return format(dec_value, ".6E")

    def _decimal_to_int(self, text: str, scale: int, field: str, allow_fraction: bool) -> int:
        candidate = text.strip().replace("_", "")
        if not candidate:
            raise ValueError(f"{field} must be a decimal number.")
        negative = candidate.startswith("-")
        if candidate[0] in "+-":
            candidate = candidate[1:]
        if not candidate:
            raise ValueError(f"{field} must be a decimal number.")
        if "." in candidate:
            whole, frac = candidate.split(".", 1)
        else:
            whole, frac = candidate, ""
        if not whole.isdigit() or (frac and not frac.isdigit()):
            raise ValueError(f"{field} must be a decimal number.")
        if not allow_fraction and frac:
            raise ValueError(f"{field} must be an integer.")
        if len(frac) > scale:
            raise ValueError(f"{field} has more fractional digits than allowed ({scale}).")
        whole_int = int(whole) if whole else 0
        frac_int = int(frac.ljust(scale, "0")) if frac else 0
        scaled = whole_int * (10**scale) + frac_int
        return -scaled if negative else scaled

    def _parse_integer_string(self, text: str, field: str) -> int:
        candidate = text.strip().replace("_", "")
        if not re.fullmatch(r"[+-]?\d+", candidate):
            raise ValueError(f"For {field}, value must be an integer.")
        try:
            return int(candidate, 10)
        except Exception:
            raise ValueError(f"For {field}, value must be an integer.")

    def _parse_decimals_int(self, decimals: Any, default: int = 18) -> int:
        if decimals is None:
            return default
        if isinstance(decimals, bool):
            raise ValueError("decimals must be a non-negative integer.")
        if isinstance(decimals, (int, float)):
            ivalue = int(decimals)
        elif isinstance(decimals, str):
            stripped = decimals.strip()
            if not stripped.lstrip("+-").isdigit():
                raise ValueError("decimals must be a non-negative integer.")
            ivalue = int(stripped)
        else:
            raise ValueError("decimals must be a non-negative integer.")
        if ivalue < 0:
            raise ValueError("decimals must be a non-negative integer.")
        return ivalue

    def _build_explain(
        self,
        original: Any,
        from_unit: str,
        to_unit: str,
        decimals: int,
        base_int: int,
        converted: Dict[str, Any],
    ) -> str:
        parts = [f"{from_unit} -> {to_unit}", f"value={self._stringify(original, from_unit)}"]
        if from_unit in {"human", "dec"} or to_unit == "human":
            parts.append(f"decimals={decimals}")
        parts.append(f"base_int={base_int}")
        parts.append(f"result={converted.get('value')}")
        return " | ".join(parts)

    def keccak(self, value: Any, input_type: Optional[str] = None) -> Dict[str, str]:
        """Compute keccak-256; input_type: text|hex|bytes (default text, UTF-8). Supports list/tuple by concatenating elements in order."""
        normalized_type = (input_type or "text").lower()
        if normalized_type not in {"text", "hex", "bytes"}:
            raise ValueError("input_type must be one of: text, hex, bytes.")

        is_sequence = isinstance(value, (list, tuple))
        items = value if is_sequence else [value]
        parts: List[bytes] = []

        for idx, item in enumerate(items):
            prefix = f"value[{idx}]" if is_sequence else "value"
            if normalized_type == "text":
                if not isinstance(item, str):
                    raise ValueError(f"For input_type=text, {prefix} must be a string.")
                part = item.encode("utf-8")
            elif normalized_type == "hex":
                if not isinstance(item, str):
                    raise ValueError(f"For input_type=hex, {prefix} must be a hex string.")
                normalized = self._normalize_hex_string(item, prefix)
                hex_body = normalized[2:]
                if len(hex_body) % 2 != 0:
                    raise ValueError(
                        f"For input_type=hex, {prefix} length must be even (for bytes32[] use 64 hex chars = 32 bytes)."
                    )
                part = self._hex_to_bytes(normalized)
            else:  # bytes
                if isinstance(item, (bytes, bytearray)):
                    part = bytes(item)
                elif isinstance(item, str):
                    part = item.encode("utf-8")
                else:
                    raise ValueError(
                        f"For input_type=bytes, {prefix} must be bytes-like or string."
                    )
            parts.append(part)

        data = b"".join(parts)

        digest = self._keccak256(data)
        return {"input_type": normalized_type, "data": "0x" + digest.hex()}

    def _prepare_context(self, address: str, network: Optional[str]) -> Tuple[str, str, str]:
        normalized_address = self._normalize_address(address)
        network_label, chain_id = self._resolve_network_and_chain(network)
        self.client.chain_id = chain_id
        return normalized_address, network_label, chain_id

    def _rpc_url_for(self, chain_id: str, allow_default: bool) -> Optional[str]:
        url = self.config.rpc_urls.get(str(chain_id))
        if url:
            return url
        if allow_default and self.config.rpc_url_default:
            return self.config.rpc_url_default
        return None

    def _get_rpc_client(self, chain_id: str, allow_default: bool) -> Optional[RpcClient]:
        url = self._rpc_url_for(chain_id, allow_default)
        if not url:
            return None
        client = self._rpc_clients.get(url)
        if client is None:
            client = RpcClient(
                rpc_url=url,
                timeout=self.config.request_timeout,
                max_retries=self.config.max_retries,
                backoff_seconds=self.config.backoff_seconds,
            )
            self._rpc_clients[url] = client
        return client

    def _prepare_call_data(
        self,
        data: Optional[str],
        function: Optional[str],
        args: Optional[List[Any]],
        address: str,
        chain_id: str,
        network_label: Optional[str],
    ) -> Tuple[str, Dict[str, Any]]:
        """Build or normalize call data; if ABI is cached (proxy-aware), validate selector and length. Returns data + function metadata."""
        if function:
            if data:
                raise ValueError("Provide either function+args or data, not both.")
            selector_hex, encoded_data = self._encode_function_call(function, args or [])
            normalized = encoded_data
            fn_name, input_types = self._parse_function_signature(function)
            fn_signature = f"{fn_name}({','.join(input_types)})"
            func_meta: Dict[str, Any] = {
                "selector": selector_hex,
                "name": fn_name,
                "signature": fn_signature,
                "source": "provided",
                "entry": None,
            }
        else:
            if not data:
                raise ValueError("Either data or function+args is required.")
            normalized = self._normalize_hex_string(data, "data")
            func_meta = {"selector": normalized[2:10], "name": None, "signature": None, "source": None, "entry": None}

        # data must include at least 4-byte selector (8 hex chars after 0x)
        if len(normalized) < 10:
            raise ValueError("data must include 4-byte function selector.")

        selector = normalized[2:10]
        selector_maps: List[Tuple[Dict[str, Dict[str, Any]], str]] = []
        implementation_hint: Optional[str] = None
        loaded_impl_address: Optional[str] = None
        proxy_info: Optional[Dict[str, Any]] = None

        def add_selector_map(abi_obj: Any, source: str, prefer: bool = False) -> None:
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
                if prefer:
                    selector_maps.insert(0, (selector_map, source))
                else:
                    selector_maps.append((selector_map, source))

        def load_contract_abi(target: str, source: str, prefer: bool = False) -> Optional[Dict[str, Any]]:
            impl_cached = self.cache.get(target, chain_id)
            impl_data = impl_cached
            if not impl_data:
                try:
                    impl_data = self.fetch_contract(target, network_label)
                except Exception:
                    impl_data = None
            if impl_data:
                add_selector_map(impl_data.get("abi"), source, prefer=prefer)
            return impl_data

        # 1) cached ABI on the address itself
        cached = self.cache.get(address, chain_id)
        if not cached:
            try:
                cached = self.fetch_contract(address, network_label)
            except Exception:
                cached = None
        if cached:
            add_selector_map(cached.get("abi"), "contract")
            implementation_hint = self._normalize_address_optional(cached.get("implementation"))
            proxy_info = self._proxy_info_from_contract(cached)

        # 1.5) if we know implementation from metadata, prefer its ABI
        if implementation_hint and implementation_hint != address:
            impl_data = load_contract_abi(implementation_hint, "implementation", prefer=True)
            if impl_data:
                loaded_impl_address = implementation_hint

        # 2) proxy-aware: if selector not found yet, try detect proxy and implementation ABI
        need_proxy_lookup = True
        for selector_map, _ in selector_maps:
            if selector in selector_map:
                need_proxy_lookup = False
                break

        if need_proxy_lookup:
            if proxy_info is None:
                proxy_info = self.proxy_cache.get(address, chain_id)
            needs_detect = proxy_info is None or (
                proxy_info.get("is_proxy") and not proxy_info.get("implementation")
            )
            if needs_detect:
                try:
                    proxy_info = self.detect_proxy(address, network_label)
                    self.proxy_cache.set(address, chain_id, proxy_info)
                except Exception:
                    proxy_info = None

            if proxy_info and proxy_info.get("is_proxy") and proxy_info.get("implementation"):
                impl_address = self._normalize_address_optional(proxy_info.get("implementation"))
                if impl_address and impl_address != address and impl_address != loaded_impl_address:
                    impl_data = load_contract_abi(impl_address, "implementation", prefer=True)
                    if impl_data:
                        loaded_impl_address = impl_address

        # Validate against available selector maps (prefer implementation if present by insertion order)
        available_selectors: List[str] = []
        for selector_map, source in selector_maps:
            available_selectors.extend(selector_map.keys())
            if selector not in selector_map:
                continue
            func_entry = selector_map[selector]
            inputs = func_entry.get("inputs", [])
            if not isinstance(inputs, list):
                func_meta["entry"] = func_entry
                func_meta["source"] = source
                func_meta["name"] = func_entry.get("name")
                try:
                    func_meta["signature"] = self._function_signature(func_meta["name"] or "", inputs)
                except Exception:
                    pass
                return normalized, func_meta

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
            func_meta["entry"] = func_entry
            func_meta["source"] = source
            func_meta["name"] = func_entry.get("name")
            try:
                func_meta["signature"] = self._function_signature(func_meta["name"] or "", inputs)
            except Exception:
                pass
            return normalized, func_meta

        # If we have ABI info but selector not found:
        if available_selectors:
            # Soft fail: allow raw call but record warning for decoded/error
            func_meta["warning"] = f"Function selector 0x{selector} not found in cached ABI; returning raw result."

        return normalized, func_meta

    def _decode_call_result(self, result_hex: str, func_meta: Dict[str, Any], decimals_hint: Optional[Any]) -> Dict[str, Any]:
        decoded: Dict[str, Any] = {
            "ok": False,
            "error": None,
            "selector": f"0x{func_meta.get('selector')}" if func_meta.get("selector") else None,
            "function_name": func_meta.get("name"),
            "function_signature": func_meta.get("signature"),
            "source": func_meta.get("source"),
            "outputs": [],
            "warning": func_meta.get("warning"),
        }

        if not isinstance(result_hex, str):
            decoded["error"] = "Unexpected non-hex result."
            return decoded

        raw_hex = result_hex if result_hex.startswith("0x") else f"0x{result_hex}"
        entry = func_meta.get("entry")
        if not isinstance(entry, dict):
            decoded["error"] = decoded["error"] or "ABI not available for decoding."
            return decoded

        outputs = entry.get("outputs", [])
        if not outputs:
            decoded["ok"] = True
            return decoded

        try:
            data_bytes = self._hex_to_bytes(raw_hex)
            values = self._decode_outputs(outputs, data_bytes)
            decimals_cfg = self._parse_decimals_hint(decimals_hint)
            output_items: List[Dict[str, Any]] = []
            for idx, (abi_out, value) in enumerate(zip(outputs, values)):
                name = abi_out.get("name") or f"output{idx}"
                typ = abi_out.get("type") or ""
                item: Dict[str, Any] = {"name": name, "type": typ, "value": value}
                if self._is_numeric_type(typ) and isinstance(value, int):
                    dec = self._select_decimals(decimals_cfg, name, idx)
                    if dec is not None:
                        item["decimals"] = dec
                        item["value_scaled"] = self._format_scaled_int(value, dec)
                output_items.append(item)
            decoded["outputs"] = output_items
            decoded["ok"] = True
        except Exception as exc:
            decoded["error"] = f"Failed to decode result: {exc}"

        return decoded

    def _parse_decimals_hint(self, decimals_hint: Optional[Any]) -> Dict[str, Any]:
        cfg: Dict[str, Any] = {"global": None, "names": {}, "indexes": {}}
        if decimals_hint is None:
            return cfg

        def parse_value(val: Any) -> int:
            if isinstance(val, bool):
                raise ValueError("decimals must be a non-negative integer.")
            if isinstance(val, (int, float)):
                ivalue = int(val)
            elif isinstance(val, str) and val.strip().lstrip("+").isdigit():
                ivalue = int(val.strip())
            else:
                raise ValueError("decimals must be a non-negative integer.")
            if ivalue < 0:
                raise ValueError("decimals must be a non-negative integer.")
            return ivalue

        if isinstance(decimals_hint, (int, float, str)):
            cfg["global"] = parse_value(decimals_hint)
            return cfg

        if isinstance(decimals_hint, dict):
            for key, value in decimals_hint.items():
                dec_value = parse_value(value)
                if isinstance(key, int):
                    cfg["indexes"][key] = dec_value
                elif isinstance(key, str) and key.strip().isdigit():
                    cfg["indexes"][int(key.strip())] = dec_value
                else:
                    cfg["names"][str(key)] = dec_value
            return cfg

        if isinstance(decimals_hint, (list, tuple)):
            for idx, val in enumerate(decimals_hint):
                cfg["indexes"][idx] = parse_value(val)
            return cfg

        raise ValueError("decimals hint must be int, str, list, or dict.")

    def _select_decimals(self, cfg: Dict[str, Any], name: Optional[str], idx: int) -> Optional[int]:
        if name is not None and name in cfg["names"]:
            return cfg["names"][name]
        if idx in cfg["indexes"]:
            return cfg["indexes"][idx]
        return cfg["global"]

    def _format_scaled_int(self, value: int, decimals: int) -> str:
        if decimals <= 0:
            return str(value)
        negative = value < 0
        s = str(abs(value))
        if len(s) <= decimals:
            s = "0." + "0" * (decimals - len(s)) + s
        else:
            s = s[: len(s) - decimals] + "." + s[len(s) - decimals :]
        s = s.rstrip("0").rstrip(".") or "0"
        if negative:
            s = "-" + s
        return s

    def _is_numeric_type(self, typ: str) -> bool:
        return typ.startswith("uint") or typ.startswith("int")

    def _decode_outputs(self, outputs: List[Dict[str, Any]], data_bytes: bytes) -> List[Any]:
        offsets: List[int] = []
        prepared: List[Tuple[str, List[Optional[int]], List[Dict[str, Any]]]] = []
        cursor = 0
        for entry in outputs:
            typ = entry.get("type", "")
            components = entry.get("components") or []
            base_type, dims = self._split_array_dimensions(typ)
            prepared.append((base_type, dims, components))
            if self._is_dynamic_type_full(base_type, dims, components):
                offsets.append(cursor)
                cursor += 32
            else:
                size = self._static_type_size(base_type, dims, components)
                offsets.append(cursor)
                cursor += size

        values: List[Any] = []
        for off, (base_type, dims, components) in zip(offsets, prepared):
            values.append(self._decode_type(base_type, dims, components, data_bytes, off, 0))
        return values

    def _decode_type(
        self,
        base_type: str,
        dimensions: List[Optional[int]],
        components: List[Dict[str, Any]],
        data_bytes: bytes,
        head_offset: int,
        data_base: int,
    ) -> Any:
        if dimensions:
            return self._decode_array(base_type, dimensions, components, data_bytes, head_offset, data_base)

        # static word for inline static types or offset for dynamic
        word = self._read_word(data_bytes, head_offset)
        if base_type == "address":
            return "0x" + word[-20:].hex()

        if base_type.startswith("uint"):
            bits = 256
            suffix = base_type[4:]
            if suffix:
                bits = int(suffix)
            if bits <= 0 or bits > 256 or bits % 8 != 0:
                raise ValueError(f"Unsupported uint size {bits}.")
            return int.from_bytes(word, "big")

        if base_type.startswith("int"):
            bits = 256
            suffix = base_type[3:]
            if suffix:
                bits = int(suffix)
            if bits <= 0 or bits > 256 or bits % 8 != 0:
                raise ValueError(f"Unsupported int size {bits}.")
            unsigned = int.from_bytes(word, "big")
            sign_bit = 1 << (bits - 1)
            mask = 1 << bits
            return unsigned - mask if unsigned & sign_bit else unsigned

        if base_type == "bool":
            return bool(int.from_bytes(word, "big"))

        if base_type == "bytes":
            offset = int.from_bytes(word, "big")
            start = data_base + offset
            length = int.from_bytes(self._read_word(data_bytes, start), "big")
            data_start = start + 32
            data_end = data_start + length
            if data_end > len(data_bytes):
                raise ValueError("bytes out of range.")
            return "0x" + data_bytes[data_start:data_end].hex()

        if base_type == "string":
            offset = int.from_bytes(word, "big")
            start = data_base + offset
            length = int.from_bytes(self._read_word(data_bytes, start), "big")
            data_start = start + 32
            data_end = data_start + length
            if data_end > len(data_bytes):
                raise ValueError("string out of range.")
            try:
                return data_bytes[data_start:data_end].decode("utf-8", errors="replace")
            except Exception as exc:
                raise ValueError("Failed to decode string.") from exc

        if base_type.startswith("bytes"):
            size_part = base_type[5:]
            if not size_part.isdigit():
                raise ValueError(f"Unsupported bytes type {base_type}.")
            size = int(size_part)
            if size <= 0 or size > 32:
                raise ValueError("bytesN size must be between 1 and 32.")
            return "0x" + word[:size].hex()

        if base_type == "tuple":
            is_dynamic_tuple = self._is_dynamic_type_full(base_type, [], components)
            return self._decode_tuple(components, data_bytes, head_offset, data_base, is_dynamic_tuple)

        raise ValueError(f"Unsupported ABI output type '{base_type}'.")

    def _decode_array(
        self,
        base_type: str,
        dimensions: List[Optional[int]],
        components: List[Dict[str, Any]],
        data_bytes: bytes,
        head_offset: int,
        data_base: int,
    ) -> Any:
        dim = dimensions[0]
        remaining_dims = dimensions[1:]
        element_dynamic = self._is_dynamic_type_full(base_type, remaining_dims, components)

        if dim is None or element_dynamic:
            # dynamic array or static array containing dynamic elements -> treated as dynamic
            offset = int.from_bytes(self._read_word(data_bytes, head_offset), "big")
            array_base = data_base + offset
            length = int.from_bytes(self._read_word(data_bytes, array_base), "big")
            values: List[Any] = []
            head_start = array_base + 32
            element_head_size = (
                32 if element_dynamic else self._static_type_size(base_type, remaining_dims, components)
            )
            for idx in range(length):
                elem_head = head_start + element_head_size * idx
                values.append(
                    self._decode_type(base_type, remaining_dims, components, data_bytes, elem_head, array_base)
                )
            return values

        # static array with static elements
        length = dim
        element_size = self._static_type_size(base_type, remaining_dims, components)
        values = []
        for idx in range(length):
            elem_head = head_offset + element_size * idx
            values.append(
                self._decode_type(base_type, remaining_dims, components, data_bytes, elem_head, data_base)
            )
        return values

    def _decode_tuple(
        self,
        components: List[Dict[str, Any]],
        data_bytes: bytes,
        head_offset: int,
        data_base: int,
        is_dynamic: bool,
    ) -> Dict[str, Any]:
        tuple_base = data_base + int.from_bytes(self._read_word(data_bytes, head_offset), "big") if is_dynamic else head_offset
        values = self._decode_components(components, data_bytes, tuple_base)
        obj: Dict[str, Any] = {}
        for idx, (comp, val) in enumerate(zip(components, values)):
            name = comp.get("name") or f"field{idx}"
            obj[name] = val
        return obj

    def _decode_components(self, components: List[Dict[str, Any]], data_bytes: bytes, base_offset: int) -> List[Any]:
        offsets: List[int] = []
        prepared: List[Tuple[str, List[Optional[int]], List[Dict[str, Any]]]] = []
        cursor = 0
        for comp in components:
            typ = comp.get("type", "")
            comp_components = comp.get("components") or []
            base_type, dims = self._split_array_dimensions(typ)
            prepared.append((base_type, dims, comp_components))
            if self._is_dynamic_type_full(base_type, dims, comp_components):
                offsets.append(cursor)
                cursor += 32
            else:
                size = self._static_type_size(base_type, dims, comp_components)
                offsets.append(cursor)
                cursor += size

        values: List[Any] = []
        for off, (base_type, dims, comp_components) in zip(offsets, prepared):
            values.append(self._decode_type(base_type, dims, comp_components, data_bytes, base_offset + off, base_offset))
        return values

    def _is_dynamic_type_full(
        self, base_type: str, dimensions: List[Optional[int]], components: List[Dict[str, Any]]
    ) -> bool:
        if dimensions:
            if dimensions[0] is None:
                return True
            return self._is_dynamic_type_full(base_type, dimensions[1:], components)

        if base_type in {"bytes", "string"}:
            return True
        if base_type == "tuple":
            if not components:
                return True
            return any(
                self._is_dynamic_type_full(
                    *self._split_array_dimensions(comp.get("type", "")), comp.get("components") or []
                )
                for comp in components
            )
        return False

    def _static_type_size(
        self, base_type: str, dimensions: List[Optional[int]], components: List[Dict[str, Any]]
    ) -> int:
        if self._is_dynamic_type_full(base_type, dimensions, components):
            raise ValueError("Type is dynamic; size unknown.")

        if dimensions:
            dim = dimensions[0]
            if dim is None:
                raise ValueError("Dynamic dimensions not supported in static size calculation.")
            return dim * self._static_type_size(base_type, dimensions[1:], components)

        if base_type == "tuple":
            size = 0
            for comp in components:
                comp_base, comp_dims = self._split_array_dimensions(comp.get("type", ""))
                size += self._static_type_size(comp_base, comp_dims, comp.get("components") or [])
            return size

        return 32

    def _read_word(self, data_bytes: bytes, offset: int) -> bytes:
        end = offset + 32
        if end > len(data_bytes):
            raise ValueError("Result shorter than expected for ABI decoding.")
        return data_bytes[offset:end]

    def _hex_to_bytes(self, value: str) -> bytes:
        if not isinstance(value, str):
            raise ValueError("Result must be a hex string.")
        v = value[2:] if value.startswith("0x") else value
        if len(v) % 2 != 0:
            v = "0" + v
        if not re.fullmatch(r"[0-9a-fA-F]*", v):
            raise ValueError("Result must be a hex string.")
        return bytes.fromhex(v)

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

    def _normalize_address_optional(self, address: Any) -> Optional[str]:
        if address is None:
            return None
        try:
            return self._normalize_address(str(address))
        except Exception:
            return None

    def _resolve_network_and_chain(self, network: Optional[str]) -> Tuple[str, str]:
        if network is not None:
            network_value = str(network).strip()
            if not network_value:
                raise ValueError("network must be a non-empty string.")
            try:
                label, cid, _meta = self.chains.resolve(network_value)
                return label, cid
            except Exception as exc:
                try:
                    cid = resolve_chain_id(network_value)
                    return network_value.lower(), cid
                except Exception:
                    raise ValueError(
                        f"Unknown network '{network_value}'. "
                        "Use numeric chainid (e.g. 42161) or call resolve-chain/list-chains."
                    ) from exc

        # network not provided: use defaults
        if self.config.chain_id_override:
            return self.config.network, self.config.chain_id_override

        try:
            label, cid, _meta = self.chains.resolve(self.config.network)
            return label, cid
        except Exception as exc:
            try:
                cid = resolve_chain_id(self.config.network)
                return self.config.network, cid
            except Exception:
                raise ValueError(
                    f"Default NETWORK '{self.config.network}' could not be resolved. "
                    "To avoid accidental mainnet requests, set CHAIN_ID=<numeric chainid> "
                    "or pass --network <chainid> explicitly."
                ) from exc

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
        abi = self._parse_abi(abi_raw, address, network, chain_id)
        source_files = self._parse_source_code(entry.get("SourceCode", ""))
        compiler = entry.get("CompilerVersion") or ""
        proxy_flag = str(entry.get("Proxy", "")).strip().lower()
        is_proxy = proxy_flag in {"1", "true", "yes"}
        implementation = self._normalize_address_optional(entry.get("Implementation"))
        if implementation:
            is_proxy = True

        return {
            "address": address,
            "network": network,
            "chain_id": chain_id,
            "abi": abi,
            "source_files": source_files,
            "compiler": compiler,
            "verified": True,
            "proxy": is_proxy,
            "implementation": implementation,
            "proxy_type": "etherscan" if is_proxy else None,
        }

    def _proxy_info_from_contract(self, contract: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(contract, dict):
            return None
        impl = self._normalize_address_optional(contract.get("implementation"))
        is_proxy = bool(contract.get("proxy")) or bool(impl)
        if not is_proxy:
            return None
        evidence = ["Etherscan getsourcecode Proxy/Implementation fields"]
        if impl:
            evidence.append(f"implementation field -> {impl}")
        return {
            "address": contract.get("address"),
            "network": contract.get("network"),
            "chain_id": contract.get("chain_id"),
            "is_proxy": True,
            "implementation": impl,
            "admin": None,
            "proxy_type": contract.get("proxy_type") or "etherscan",
            "evidence": evidence,
        }

    def _parse_abi(self, abi_raw: Any, address: str, network: str, chain_id: str) -> Any:
        if abi_raw is None:
            abi_raw = "[]"

        if not isinstance(abi_raw, str):
            try:
                abi_raw = str(abi_raw)
            except Exception as exc:
                raise ValueError(
                    f"Invalid ABI returned from Etherscan for {address} "
                    f"(network={network}, chain_id={chain_id}). ABI field could not be stringified."
                ) from exc

        preview = re.sub(r"\s+", " ", abi_raw).strip()
        if len(preview) > 240:
            preview = preview[:240] + "..."

        try:
            return json.loads(abi_raw)
        except (json.JSONDecodeError, TypeError) as exc:
            lowered = abi_raw.strip().lower()
            if "not verified" in lowered or "source code not verified" in lowered:
                raise ValueError(
                    f"Contract {address} is not verified on Etherscan; ABI is unavailable "
                    f"(network={network}, chain_id={chain_id}). ABI field: {preview}"
                ) from exc
            raise ValueError(
                f"Invalid ABI returned from Etherscan for {address} "
                f"(network={network}, chain_id={chain_id}). ABI field: {preview}"
            ) from exc

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

    def _extract_proxy_result(self, payload: Dict[str, Any], allow_none: bool = False) -> Any:
        if not isinstance(payload, dict):
            raise ValueError("Unexpected response from Etherscan.")

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

        # Etherscan "module" style response: status/message/result (including rate-limit NOTOK)
        if "status" in payload or "message" in payload:
            status = str(payload.get("status", "")).strip()
            message = payload.get("message", "")
            result = payload.get("result")
            if status == "1":
                return result
            if allow_none and result is None:
                return None

            detail = result if isinstance(result, str) else ""
            raise ValueError(f"Etherscan error: {detail or message or 'unknown error'}.")

        # JSON-RPC style success response: {jsonrpc,id,result}
        if "result" in payload:
            res = payload.get("result")
            if res is None and allow_none:
                return None
            if isinstance(res, str):
                try:
                    return self._normalize_hex_string(res, "result")
                except ValueError:
                    raise ValueError(f"Etherscan error: {res}.")
            if isinstance(res, (dict, list)):
                return res

        raise ValueError("Unexpected response from Etherscan.")

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

    def _normalize_optional_positive_int(self, value: Optional[int], field: str) -> Optional[int]:
        if value is None:
            return None
        return self._normalize_positive_int(value, 0, field)

    def _normalize_sort(self, sort: Optional[str]) -> str:
        if sort is None:
            return "asc"
        normalized = sort.lower()
        if normalized not in {"asc", "desc"}:
            raise ValueError("sort must be 'asc' or 'desc'.")
        return normalized

    def _normalize_inline_limit(self, inline_limit: Optional[int]) -> int:
        if inline_limit is None:
            return DEFAULT_INLINE_SOURCE_LIMIT
        if isinstance(inline_limit, bool):
            raise ValueError("inline_limit must be a non-negative integer.")
        if isinstance(inline_limit, (int, float)):
            limit = int(inline_limit)
        elif isinstance(inline_limit, str) and inline_limit.strip().isdigit():
            limit = int(inline_limit.strip())
        else:
            raise ValueError("inline_limit must be a non-negative integer.")
        if limit < 0:
            raise ValueError("inline_limit must be a non-negative integer.")
        return limit

    def _get_full_contract(self, address: str, network: str, chain_id: str) -> Dict[str, Any]:
        cached = self.cache.get(address, chain_id)
        if cached:
            return cached

        payload = self.client.get_contract_source(address)
        parsed = self._parse_contract_response(payload, address, network, chain_id)
        self.cache.set(address, chain_id, parsed)
        proxy_info = self._proxy_info_from_contract(parsed)
        if proxy_info:
            self.proxy_cache.set(address, chain_id, proxy_info)
        return parsed

    def _apply_inline_policy(
        self, contract: Dict[str, Any], inline_limit: int, force_inline: bool
    ) -> Dict[str, Any]:
        if not isinstance(contract, dict):
            raise ValueError("Unexpected contract payload.")

        source_files = contract.get("source_files") or []
        total_length = 0
        normalized_files: List[Dict[str, Any]] = []
        for entry in source_files:
            if not isinstance(entry, dict):
                continue
            content = entry.get("content", "")
            if not isinstance(content, str):
                content = str(content)
            total_length += len(content)
            normalized_files.append(
                {
                    "filename": entry.get("filename", "Contract.sol"),
                    "content": content,
                }
            )

        include_content = force_inline or total_length <= inline_limit
        source_omitted = not include_content and bool(normalized_files)
        omitted_reason = None
        response_files: List[Dict[str, Any]] = []

        if source_omitted:
            omitted_reason = (
                f"Total source size {total_length} exceeded inline_limit {inline_limit}; "
                "use get_source_file to fetch content."
            )

        for entry in normalized_files:
            content = entry.get("content", "")
            filename = entry.get("filename", "Contract.sol")
            length = len(content)
            sha256_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if include_content:
                response_files.append(
                    {
                        "filename": filename,
                        "content": content,
                        "length": length,
                        "sha256": sha256_hash,
                        "inline": True,
                    }
                )
            else:
                response_files.append(
                    {
                        "filename": filename,
                        "length": length,
                        "sha256": sha256_hash,
                        "inline": False,
                    }
                )

        response = copy.copy(contract)
        response["source_files"] = response_files
        response["source_omitted"] = source_omitted
        response["source_omitted_reason"] = omitted_reason
        return response

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

    def _normalize_topics_list(
        self, topics: Optional[Sequence[Optional[str]]]
    ) -> Optional[List[Optional[str]]]:
        if not topics:
            return None
        if len(topics) > 4:
            raise ValueError("At most 4 topics are supported.")

        normalized: List[Optional[str]] = []
        for idx, topic in enumerate(topics):
            if topic is None or topic == "":
                normalized.append(None)
                continue
            normalized.append(self._normalize_hex_string(topic, f"topic{idx}"))

        while normalized and normalized[-1] is None:
            normalized.pop()
        return normalized or None

    def _normalize_slot(self, slot: str) -> str:
        return self._normalize_hex_string(slot, "slot", pad_to=64)

    def _normalize_tx_hash(self, tx_hash: str) -> str:
        if not isinstance(tx_hash, str):
            raise ValueError("tx_hash must be a string.")
        candidate = tx_hash.strip().lower()
        if not candidate.startswith("0x"):
            candidate = f"0x{candidate}"
        body = candidate[2:]
        if len(body) != 64 or not re.fullmatch(r"[0-9a-f]{64}", body):
            raise ValueError("tx_hash must be 0x-prefixed 64 hex characters.")
        return candidate

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

    def _hex_to_int(self, value: Optional[str], field: str) -> Optional[int]:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a hex string.")
        candidate = value.strip().lower()
        if not candidate.startswith("0x"):
            raise ValueError(f"{field} must be a 0x-prefixed hex string.")
        try:
            return int(candidate, 16)
        except Exception as exc:
            raise ValueError(f"{field} must be a valid hex string.") from exc

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

    def _map_block(self, block: Dict[str, Any], force_hashes_only: bool = False) -> Dict[str, Any]:
        if not isinstance(block, dict):
            return {}
        mapped = {
            "number": block.get("number"),
            "hash": block.get("hash"),
            "parentHash": block.get("parentHash"),
            "nonce": block.get("nonce"),
            "sha3Uncles": block.get("sha3Uncles"),
            "logsBloom": block.get("logsBloom"),
            "transactionsRoot": block.get("transactionsRoot"),
            "stateRoot": block.get("stateRoot"),
            "receiptsRoot": block.get("receiptsRoot"),
            "miner": block.get("miner"),
            "difficulty": block.get("difficulty"),
            "totalDifficulty": block.get("totalDifficulty"),
            "extraData": block.get("extraData"),
            "size": block.get("size"),
            "gasLimit": block.get("gasLimit"),
            "gasUsed": block.get("gasUsed"),
            "timestamp": block.get("timestamp"),
            "transactions": None,
            "uncles": block.get("uncles"),
            "baseFeePerGas": block.get("baseFeePerGas"),
            "mixHash": block.get("mixHash"),
            "blobGasUsed": block.get("blobGasUsed"),
            "excessBlobGas": block.get("excessBlobGas"),
            "withdrawals": block.get("withdrawals"),
            "withdrawalsRoot": block.get("withdrawalsRoot"),
            "parentBeaconBlockRoot": block.get("parentBeaconBlockRoot"),
            "blobGasPrice": block.get("blobGasPrice"),
        }

        txs = block.get("transactions")
        if force_hashes_only:
            if isinstance(txs, list):
                mapped["transactions"] = [tx.get("hash") if isinstance(tx, dict) else tx for tx in txs]
            else:
                mapped["transactions"] = txs
            return mapped

        if isinstance(txs, list) and all(isinstance(tx, str) for tx in txs):
            mapped["transactions"] = txs
            return mapped

        if isinstance(txs, list):
            mapped_txs = []
            for tx in txs:
                if not isinstance(tx, dict):
                    mapped_txs.append(tx)
                    continue
                mapped_txs.append(
                    {
                        "hash": tx.get("hash"),
                        "from": tx.get("from"),
                        "to": tx.get("to"),
                        "value": tx.get("value"),
                        "nonce": tx.get("nonce"),
                        "gas": tx.get("gas"),
                        "gasPrice": tx.get("gasPrice"),
                        "input": tx.get("input"),
                        "transactionIndex": tx.get("transactionIndex"),
                        "type": tx.get("type"),
                        "maxFeePerGas": tx.get("maxFeePerGas"),
                        "maxPriorityFeePerGas": tx.get("maxPriorityFeePerGas"),
                        "blobVersionedHashes": tx.get("blobVersionedHashes"),
                        "accessList": tx.get("accessList"),
                    }
                )
            mapped["transactions"] = mapped_txs
        else:
            mapped["transactions"] = txs
        return mapped

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
        if "(" not in text:
            fn = text.strip()
            if not fn or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", fn):
                raise ValueError("Invalid function name.")
            return fn, []
        if not text.endswith(")"):
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

    def _read_storage_word(
        self,
        address: str,
        slot: str,
        tag: str,
        *,
        chain_id: str,
        allow_default_rpc: bool,
    ) -> str:
        rpc = self._get_rpc_client(chain_id, allow_default_rpc)
        if rpc:
            result = rpc.call("eth_getStorageAt", [address, slot, tag])
            if not isinstance(result, str):
                raise ValueError("RPC error: eth_getStorageAt returned unexpected result.")
            return self._normalize_hex_string(result, "storage_word", pad_to=64)

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

    def _map_transaction_detail(self, tx: Dict[str, Any]) -> Dict[str, Any]:
        def hx(field: str) -> Optional[int]:
            return self._hex_to_int(tx.get(field), field)

        return {
            "hash": tx.get("hash"),
            "from": tx.get("from"),
            "to": tx.get("to"),
            "nonce": hx("nonce"),
            "value": tx.get("value"),
            "value_int": hx("value"),
            "gas": hx("gas"),
            "gas_price": hx("gasPrice"),
            "max_fee_per_gas": hx("maxFeePerGas"),
            "max_priority_fee_per_gas": hx("maxPriorityFeePerGas"),
            "block_hash": tx.get("blockHash"),
            "block_number": hx("blockNumber"),
            "transaction_index": hx("transactionIndex"),
            "type": hx("type"),
            "input": tx.get("input"),
            "chain_id": hx("chainId"),
            "v": tx.get("v"),
            "r": tx.get("r"),
            "s": tx.get("s"),
        }

    def _map_receipt(self, receipt: Dict[str, Any]) -> Dict[str, Any]:
        def hx(field: str) -> Optional[int]:
            return self._hex_to_int(receipt.get(field), field)

        return {
            "status": hx("status"),
            "contract_address": receipt.get("contractAddress"),
            "cumulative_gas_used": hx("cumulativeGasUsed"),
            "gas_used": hx("gasUsed"),
            "effective_gas_price": hx("effectiveGasPrice"),
            "block_hash": receipt.get("blockHash"),
            "block_number": hx("blockNumber"),
            "transaction_hash": receipt.get("transactionHash"),
            "transaction_index": hx("transactionIndex"),
            "logs": receipt.get("logs"),
        }

    def _hex_to_int(self, value: Any, field: str) -> Optional[int]:
        if value is None:
            return None
        if not isinstance(value, str):
            return None
        try:
            if value.startswith("0x") or value.startswith("0X"):
                return int(value, 16)
            return int(value, 16)
        except Exception:
            raise ValueError(f"{field} is not a valid hex value.")

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
