"""
MCP server exposing contract fetch capability via Etherscan V2.
"""

import argparse
from collections.abc import Mapping
from typing import Any, Optional, Union

from mcp.server.fastmcp import FastMCP

from .config import load_config
from .service import ContractService

server = FastMCP(
    name="etherscan-mcp",
    instructions="Fetch verified contract ABI and source code via Etherscan API V2.",
)

_service: Optional[ContractService] = None


def _get_service() -> ContractService:
    global _service
    if _service is None:
        cfg = load_config()
        _service = ContractService(cfg)
    return _service


def _normalize_array_param(value: Optional[Any], name: str) -> Optional[list]:
    """
    Ensure a parameter intended as an array is actually treated as one:
    - str/bytes: likely misuse, raise with guidance
    - list/tuple: keep as list
    - Mapping: reject (not an array)
    - other scalars: auto-wrap into single-element list
    """
    if value is None:
        return None
    if isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{name} must be an array (e.g. ['0x...', 123]); got a string/bytes.")
    if isinstance(value, Mapping):
        raise ValueError(f"{name} must be an array, not an object/map.")
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


@server.tool(
    name="fetch_contract",
    title="Fetch Contract Details",
    description="Fetch verified contract ABI and source code from Etherscan. Use inline_limit/force_inline to control inlined source size.",
)
def fetch_contract(
    address: str,
    network: Optional[str] = None,
    inline_limit: Optional[int] = None,
    force_inline: bool = False,
) -> dict:
    """
    Fetch contract details for a given address.
    """
    svc = _get_service()
    return svc.fetch_contract(address, network, inline_limit, force_inline)


@server.tool(
    name="get_contract_creation",
    title="Get Contract Creation Info",
    description="Fetch contract creator, creation tx hash, and block number.",
)
def get_contract_creation(address: str, network: Optional[str] = None) -> dict:
    svc = _get_service()
    return svc.get_contract_creation(address, network)


@server.tool(
    name="detect_proxy",
    title="Detect Proxy Implementation/Admin",
    description="Detect proxy implementation/admin via EIP-1967 storage slots.",
)
def detect_proxy(address: str, network: Optional[str] = None) -> dict:
    svc = _get_service()
    return svc.detect_proxy(address, network)


@server.tool(
    name="list_transactions",
    title="List Transactions",
    description="List normal transactions for an address with optional block range and pagination.",
)
def list_transactions(
    address: str,
    network: Optional[str] = None,
    start_block: Optional[int] = None,
    end_block: Optional[int] = None,
    page: Optional[int] = None,
    offset: Optional[int] = None,
    sort: Optional[str] = None,
) -> dict:
    svc = _get_service()
    return svc.list_transactions(address, network, start_block, end_block, page, offset, sort)


@server.tool(
    name="list_token_transfers",
    title="List Token Transfers",
    description="List token transfers (ERC20/721/1155) for an address with optional block range and pagination.",
)
def list_token_transfers(
    address: str,
    network: Optional[str] = None,
    token_type: str = "erc20",
    start_block: Optional[int] = None,
    end_block: Optional[int] = None,
    page: Optional[int] = None,
    offset: Optional[int] = None,
    sort: Optional[str] = None,
) -> dict:
    svc = _get_service()
    return svc.list_token_transfers(
        address, network, token_type, start_block, end_block, page, offset, sort
    )


@server.tool(
    name="query_logs",
    title="Query Logs",
    description="Query contract logs by topics and block range. `topics` must be an array of topic filters (use None for empty).",
)
def query_logs(
    address: str,
    network: Optional[str] = None,
    topics: Optional[Any] = None,
    from_block: Optional[Union[int, str]] = None,
    to_block: Optional[Union[int, str]] = None,
    page: Optional[int] = None,
    offset: Optional[int] = None,
) -> dict:
    svc = _get_service()
    normalized_topics = _normalize_array_param(topics, "topics")
    return svc.query_logs(address, network, normalized_topics, from_block, to_block, page, offset)


@server.tool(
    name="get_storage_at",
    title="Get Storage Slot",
    description="Read a storage slot via eth_getStorageAt.",
)
def get_storage_at(
    address: str,
    slot: str,
    network: Optional[str] = None,
    block_tag: Optional[str] = None,
) -> dict:
    svc = _get_service()
    return svc.get_storage_at(address, slot, network, block_tag)


@server.tool(
    name="call_function",
    title="Call Read-Only Function",
    description="Call a contract read-only function via eth_call (ABI-aware decode when ABI is available). `args` must be an array (e.g. ['0x...', 123]).",
)
def call_function(
    address: str,
    data: Optional[str] = None,
    network: Optional[str] = None,
    block_tag: Optional[str] = None,
    function: Optional[str] = None,
    args: Optional[Any] = None,
    decimals: Optional[Any] = None,
) -> dict:
    svc = _get_service()
    normalized_args = _normalize_array_param(args, "args")
    return svc.call_function(address, data, network, block_tag, function, normalized_args, decimals)


@server.tool(
    name="encode_function_data",
    title="Encode Function Call",
    description="Compute selector and ABI-encoded call data from function signature and arguments. `args` must be an array.",
)
def encode_function_data(function: str, args: Optional[Any] = None) -> dict:
    svc = _get_service()
    normalized_args = _normalize_array_param(args, "args")
    return svc.encode_function_data(function, normalized_args)


@server.tool(
    name="get_source_file",
    title="Get Single Source File",
    description="Fetch a specific source file for a verified contract. Supports optional offset/length for chunked reads.",
)
def get_source_file(
    address: str,
    filename: str,
    network: Optional[str] = None,
    offset: Optional[int] = None,
    length: Optional[int] = None,
) -> dict:
    svc = _get_service()
    return svc.get_source_file(address, filename, network, offset, length)


@server.tool(
    name="keccak",
    title="Keccak-256 Hash",
    description="Compute keccak-256 hash. input_type: text|hex|bytes (default text, UTF-8). Supports single value or list/tuple (elements concatenated). Returns 0x-prefixed hex.",
)
def keccak(value: Any, input_type: Optional[str] = None) -> dict:
    svc = _get_service()
    return svc.keccak(value, input_type)


@server.tool(
    name="get_transaction",
    title="Get Transaction Detail",
    description="Fetch a single transaction (and receipt) by tx hash.",
)
def get_transaction(tx_hash: str, network: Optional[str] = None) -> dict:
    svc = _get_service()
    return svc.get_transaction(tx_hash, network)


@server.tool(
    name="convert",
    title="Chain Number Convert",
    description="Convert hex/dec/human/wei/gwei/eth with decimals (default 18). Use convert(value, from, to, decimals?). Returns JSON with original, converted, explain.",
)
def convert(value: Any, from_unit: str, to_unit: str, decimals: Optional[Any] = None) -> dict:
    svc = _get_service()
    return svc.convert(value, from_unit, to_unit, decimals)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Etherscan MCP server.")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport protocol for MCP.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for SSE/HTTP transports.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for SSE/HTTP transports.",
    )
    parser.add_argument(
        "--mount-path",
        default="/",
        help="Mount path for SSE transport (only when transport=sse).",
    )
    args = parser.parse_args()

    # FastMCP uses host/port only for SSE/HTTP transports; stdio ignores them.
    server.settings.host = args.host
    server.settings.port = args.port

    if args.transport == "sse":
        server.run(transport="sse", mount_path=args.mount_path)
    else:
        server.run(transport=args.transport)


if __name__ == "__main__":
    main()
