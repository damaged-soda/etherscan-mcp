import argparse
import json
import re
import sys
from typing import Any, List, Optional

from .config import load_config
from .service import ContractService

# RPC_URL_<chainid> 常内嵌 api-key(Alchemy / drpc 等)。错误信息原样打印完整
# URL 会把 key 带进 stderr / 日志 / transcript,截到 scheme://host、其余换 /***。
_URL_RE = re.compile(r"(https?://)(?:[^@/\s?#]+@)?([^/\s?#]+)[^\s]*")


def _redact_secrets(text: str) -> str:
    return _URL_RE.sub(r"\1\2/***", text)

_ENV_EPILOG = """\
environment:
  ETHERSCAN_API_KEY        required. Etherscan V2 API key.
  NETWORK                  default network name/alias or numeric chainid (default mainnet).
  CHAIN_ID                 explicit chainid override (beats NETWORK).
  RPC_URL                  default JSON-RPC endpoint for eth_call / storage / logs.
  RPC_URL_<chainid>        per-chain JSON-RPC endpoint, e.g. RPC_URL_1, RPC_URL_56.
  ETHERSCAN_MCP_CACHE_DIR  token/contract metadata cache dir (default ~/.cache/etherscan-mcp).

Full variable list and parameter semantics: README.md in the repo root.
All commands print JSON to stdout; errors go to stderr with exit code 1.
"""


def _json_value(raw: str, name: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"{name} must be valid JSON: {exc}") from exc


def _json_array(raw: str, name: str) -> List[Any]:
    value = _json_value(raw, name)
    if not isinstance(value, list):
        raise argparse.ArgumentTypeError(f"{name} must be a JSON array, e.g. '[\"0x...\", 123]'")
    return value


def _block_value(raw: str) -> Any:
    """Pass decimal blocks as int, keep 'latest' / 0x-hex as strings."""
    stripped = raw.strip()
    if stripped.isdigit():
        return int(stripped)
    return stripped


def _add_network(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--network",
        required=False,
        help="Optional network override (name/alias or numeric chainid). Defaults to NETWORK env or mainnet.",
    )


def _add_paging(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start-block", type=int, help="Inclusive start block.")
    parser.add_argument("--end-block", type=int, help="Inclusive end block.")
    parser.add_argument("--page", type=int, help="Page number (1-based).")
    parser.add_argument("--offset", type=int, help="Rows per page.")
    parser.add_argument("--sort", choices=["asc", "desc"], help="Sort order by block number.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="etherscan",
        description=(
            "Etherscan API V2 + EVM JSON-RPC read-only CLI: verified contract ABI/source, "
            "transactions, token transfers, logs, storage, eth_call, and chain utilities. "
            "Never signs or broadcasts transactions."
        ),
        epilog=_ENV_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser(
        "fetch",
        help="Fetch verified contract ABI and source code",
        description="Fetch verified contract ABI and source code from Etherscan. Use --inline-limit/--force-inline to control inlined source size.",
    )
    fetch_parser.add_argument("--address", required=True, help="Contract address (0x-prefixed).")
    _add_network(fetch_parser)
    fetch_parser.add_argument(
        "--inline-limit",
        type=int,
        help="Max total source chars to inline (service default 20000). Use 0 to omit source, or --force-inline to bypass.",
    )
    fetch_parser.add_argument(
        "--force-inline",
        action="store_true",
        help="Force inlining source regardless of size (may be large).",
    )
    fetch_parser.set_defaults(
        run=lambda svc, a: svc.fetch_contract(
            a.address, a.network, inline_limit=a.inline_limit, force_inline=a.force_inline
        )
    )

    get_file_parser = subparsers.add_parser(
        "get-source-file",
        help="Fetch a single source file of a verified contract",
        description="Fetch one source file by exact filename as reported by Etherscan. Supports --offset/--length for chunked reads of large files.",
    )
    get_file_parser.add_argument("--address", required=True, help="Contract address (0x-prefixed).")
    get_file_parser.add_argument("--filename", required=True, help="Exact filename as reported by Etherscan.")
    _add_network(get_file_parser)
    get_file_parser.add_argument("--offset", type=int, help="Offset (chars) to start from. Defaults to 0.")
    get_file_parser.add_argument("--length", type=int, help="Length (chars) to return from offset.")
    get_file_parser.set_defaults(
        run=lambda svc, a: svc.get_source_file(
            a.address, a.filename, a.network, offset=a.offset, length=a.length
        )
    )

    creation_parser = subparsers.add_parser(
        "get-contract-creation",
        help="Fetch contract creator, creation tx hash, and block number",
        description="Fetch contract creator address, creation tx hash, and creation block number.",
    )
    creation_parser.add_argument("--address", required=True, help="Contract address (0x-prefixed).")
    _add_network(creation_parser)
    creation_parser.set_defaults(run=lambda svc, a: svc.get_contract_creation(a.address, a.network))

    proxy_parser = subparsers.add_parser(
        "detect-proxy",
        help="Detect proxy implementation/admin via EIP-1967 slots",
        description="Detect proxy implementation/admin by reading EIP-1967 storage slots.",
    )
    proxy_parser.add_argument("--address", required=True, help="Contract address (0x-prefixed).")
    _add_network(proxy_parser)
    proxy_parser.set_defaults(run=lambda svc, a: svc.detect_proxy(a.address, a.network))

    txs_parser = subparsers.add_parser(
        "list-transactions",
        help="List normal transactions for an address",
        description="List normal transactions for an address with optional block range and pagination.",
    )
    txs_parser.add_argument("--address", required=True, help="Account or contract address (0x-prefixed).")
    _add_network(txs_parser)
    _add_paging(txs_parser)
    txs_parser.set_defaults(
        run=lambda svc, a: svc.list_transactions(
            a.address, a.network, a.start_block, a.end_block, a.page, a.offset, a.sort
        )
    )

    transfers_parser = subparsers.add_parser(
        "list-token-transfers",
        help="List token transfers (ERC20/721/1155) for an address",
        description="List token transfers for an address with optional block range and pagination.",
    )
    transfers_parser.add_argument("--address", required=True, help="Account or contract address (0x-prefixed).")
    _add_network(transfers_parser)
    transfers_parser.add_argument(
        "--token-type",
        default="erc20",
        choices=["erc20", "erc721", "erc1155"],
        help="Token standard to list. Defaults to erc20.",
    )
    _add_paging(transfers_parser)
    transfers_parser.set_defaults(
        run=lambda svc, a: svc.list_token_transfers(
            a.address, a.network, a.token_type, a.start_block, a.end_block, a.page, a.offset, a.sort
        )
    )

    logs_parser = subparsers.add_parser(
        "query-logs",
        help="Query contract logs by topics and block range",
        description=(
            "Query contract logs by topics and block range.\n"
            "Example: query-logs --address 0xdAC1... "
            "--topics '[\"0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef\"]' "
            "--from-block 20000000 --to-block latest"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    logs_parser.add_argument("--address", required=True, help="Contract address (0x-prefixed).")
    _add_network(logs_parser)
    logs_parser.add_argument(
        "--topics",
        type=lambda raw: _json_array(raw, "--topics"),
        help="JSON array of topic filters; use null for wildcard slots, e.g. '[\"0xddf2...\", null, \"0x...\"]'.",
    )
    logs_parser.add_argument("--from-block", type=_block_value, help="Start block: decimal, 0x hex, or latest.")
    logs_parser.add_argument("--to-block", type=_block_value, help="End block: decimal, 0x hex, or latest.")
    logs_parser.add_argument("--page", type=int, help="Page number (1-based).")
    logs_parser.add_argument("--offset", type=int, help="Rows per page.")
    logs_parser.set_defaults(
        run=lambda svc, a: svc.query_logs(
            a.address, a.network, a.topics, a.from_block, a.to_block, a.page, a.offset
        )
    )

    storage_parser = subparsers.add_parser(
        "get-storage-at",
        help="Read a storage slot via eth_getStorageAt",
        description="Read a raw storage slot via eth_getStorageAt. Requires RPC_URL / RPC_URL_<chainid>.",
    )
    storage_parser.add_argument("--address", required=True, help="Contract address (0x-prefixed).")
    storage_parser.add_argument("--slot", required=True, help="Storage slot (decimal or 0x hex).")
    _add_network(storage_parser)
    storage_parser.add_argument("--block-tag", help="Block tag: latest, decimal, or 0x hex. Defaults to latest.")
    storage_parser.set_defaults(
        run=lambda svc, a: svc.get_storage_at(a.address, a.slot, a.network, a.block_tag)
    )

    call_parser = subparsers.add_parser(
        "call-function",
        help="Call a read-only contract function via eth_call",
        description=(
            "Call a read-only contract function via eth_call, with ABI-aware decode when the ABI is available.\n"
            "Provide either raw --data, or --function plus optional --args.\n"
            "Examples:\n"
            "  call-function --address 0xdAC1... --function 'balanceOf(address)' \\\n"
            "      --args '[\"0x47ac0Fb4F2D84898e4D9E7b4DaB3C24507a6D503\"]' --decimals 6\n"
            "  call-function --address 0xdAC1... --data 0x18160ddd"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    call_parser.add_argument("--address", required=True, help="Contract address (0x-prefixed).")
    call_parser.add_argument("--data", help="Raw 0x call data (alternative to --function/--args).")
    _add_network(call_parser)
    call_parser.add_argument("--block-tag", help="Block tag: latest, decimal, or 0x hex. Defaults to latest.")
    call_parser.add_argument(
        "--function",
        help="Function name or signature, e.g. balanceOf(address). Selector is resolved via the verified ABI when needed.",
    )
    call_parser.add_argument(
        "--args",
        type=lambda raw: _json_array(raw, "--args"),
        help="JSON array of function arguments, e.g. '[\"0x...\", 123]'.",
    )
    call_parser.add_argument(
        "--decimals",
        type=lambda raw: _json_value(raw, "--decimals"),
        help="Decimals hint for numeric outputs: int, JSON array, or JSON object keyed by output name/index.",
    )
    call_parser.set_defaults(
        run=lambda svc, a: svc.call_function(
            a.address, a.data, a.network, a.block_tag, a.function, a.args, a.decimals
        )
    )

    series_parser = subparsers.add_parser(
        "call-function-series",
        help="Call the same read-only function across a historical block range",
        description=(
            "Call the same read-only function across a historical block range via JSON-RPC batch eth_call.\n"
            "Requires RPC_URL_<chainid> backed by an archive node.\n"
            "Example:\n"
            "  call-function-series --address 0xdAC1... --function 'totalSupply()' \\\n"
            "      --from-block 20000000 --to-block 20001000 --stride 100 --decimals 6"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    series_parser.add_argument("--address", required=True, help="Contract address (0x-prefixed).")
    series_parser.add_argument("--from-block", required=True, type=_block_value, help="Start block: decimal, 0x hex, or latest.")
    series_parser.add_argument("--to-block", required=True, type=_block_value, help="End block: decimal, 0x hex, or latest.")
    series_parser.add_argument("--stride", type=int, default=1, help="Sample every N blocks. Defaults to 1.")
    series_parser.add_argument("--data", help="Raw 0x call data (alternative to --function/--args).")
    _add_network(series_parser)
    series_parser.add_argument("--function", help="Function name or signature, e.g. totalSupply().")
    series_parser.add_argument(
        "--args",
        type=lambda raw: _json_array(raw, "--args"),
        help="JSON array of function arguments.",
    )
    series_parser.add_argument(
        "--decimals",
        type=lambda raw: _json_value(raw, "--decimals"),
        help="Decimals hint for numeric outputs: int, JSON array, or JSON object.",
    )
    series_parser.add_argument("--batch-size", type=int, help="JSON-RPC batch size per request.")
    series_parser.set_defaults(
        run=lambda svc, a: svc.call_function_series(
            a.address,
            a.from_block,
            a.to_block,
            a.stride,
            a.data,
            a.network,
            a.function,
            a.args,
            a.decimals,
            a.batch_size,
        )
    )

    encode_parser = subparsers.add_parser(
        "encode-function-data",
        help="Compute selector and ABI-encoded call data",
        description=(
            "Compute the 4-byte selector and ABI-encoded call data from a function signature and arguments.\n"
            "Example: encode-function-data --function 'transfer(address,uint256)' "
            "--args '[\"0x...\", 1000]'"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    encode_parser.add_argument("--function", required=True, help="Function signature, e.g. transfer(address,uint256).")
    encode_parser.add_argument(
        "--args",
        type=lambda raw: _json_array(raw, "--args"),
        help="JSON array of function arguments.",
    )
    encode_parser.set_defaults(run=lambda svc, a: svc.encode_function_data(a.function, a.args))

    keccak_parser = subparsers.add_parser(
        "keccak",
        help="Compute keccak-256 hash",
        description=(
            "Compute keccak-256. --input-type text|hex|bytes (default text, UTF-8).\n"
            "Repeat --value to concatenate elements before hashing.\n"
            "Example: keccak --value 'Transfer(address,address,uint256)'"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    keccak_parser.add_argument(
        "--value",
        required=True,
        action="append",
        help="Value to hash. Repeatable; multiple values are concatenated.",
    )
    keccak_parser.add_argument("--input-type", choices=["text", "hex", "bytes"], help="How to interpret values. Defaults to text.")
    keccak_parser.set_defaults(
        run=lambda svc, a: svc.keccak(a.value[0] if len(a.value) == 1 else a.value, a.input_type)
    )

    tx_parser = subparsers.add_parser(
        "get-transaction",
        help="Fetch a single transaction (and receipt) by tx hash",
        description="Fetch a single transaction and its receipt by tx hash.",
    )
    tx_parser.add_argument("--tx-hash", required=True, help="Transaction hash (0x-prefixed).")
    _add_network(tx_parser)
    tx_parser.set_defaults(run=lambda svc, a: svc.get_transaction(a.tx_hash, a.network))

    summary_parser = subparsers.add_parser(
        "get-transaction-summary",
        help="Per-tx digest: meta, gas, annotated log addresses, decoded ERC20 flow",
        description=(
            "Lightweight per-tx digest in one call: tx meta + gas cost + unique log addresses annotated "
            "with verified ContractName, plus decoded ERC20 Transfer flow with token symbol/decimals "
            "(best-effort). Use --compact for an arbitrage-oriented digest (gas split, net_token_flow_by_address, "
            "route_hints); --flow-scope controls which net-flow rows are kept in compact mode."
        ),
    )
    summary_parser.add_argument("--tx-hash", required=True, help="Transaction hash (0x-prefixed).")
    _add_network(summary_parser)
    summary_parser.add_argument(
        "--no-decode-transfers",
        action="store_true",
        help="Skip ERC20 Transfer decoding and token metadata lookups.",
    )
    summary_parser.add_argument(
        "--no-annotate-contracts",
        action="store_true",
        help="Skip ContractName annotation lookups.",
    )
    summary_parser.add_argument("--compact", action="store_true", help="Arbitrage-oriented compact digest.")
    summary_parser.add_argument(
        "--flow-scope",
        default="user",
        choices=["user", "user_router", "all"],
        help="Compact mode only: user keeps tx.from rows, user_router adds tx.to, all keeps every row.",
    )
    summary_parser.set_defaults(
        run=lambda svc, a: svc.get_transaction_summary(
            a.tx_hash,
            a.network,
            not a.no_decode_transfers,
            not a.no_annotate_contracts,
            a.compact,
            a.flow_scope,
        )
    )

    block_parser = subparsers.add_parser(
        "get-block",
        help="Fetch a block by number or latest",
        description="Fetch a block by number. Use --full-transactions to expand tx objects or --tx-hashes-only to force hashes list.",
    )
    block_parser.add_argument("--block", required=True, help="Block identifier: latest, decimal number, or 0x-prefixed hex.")
    _add_network(block_parser)
    block_parser.add_argument("--full-transactions", action="store_true", help="Return full transaction objects (may be large).")
    block_parser.add_argument(
        "--tx-hashes-only",
        action="store_true",
        help="Force transactions to be returned as hashes list (overrides --full-transactions).",
    )
    block_parser.set_defaults(
        run=lambda svc, a: svc.get_block_by_number(
            a.block, a.network, full_transactions=a.full_transactions, tx_hashes_only=a.tx_hashes_only
        )
    )

    block_time_parser = subparsers.add_parser(
        "get-block-time",
        help="Fetch block timestamp by number or latest",
        description="Fetch block timestamp (and block number) by number or latest.",
    )
    block_time_parser.add_argument("--block", required=True, help="Block identifier: latest, decimal number, or 0x-prefixed hex.")
    _add_network(block_time_parser)
    block_time_parser.set_defaults(run=lambda svc, a: svc.get_block_time_by_number(a.block, a.network))

    chains_parser = subparsers.add_parser(
        "list-chains",
        help="List supported chains from Etherscan chainlist",
        description="List chains supported by Etherscan V2 via /v2/chainlist. Rows carry has_caveats flagging known plan/RPC limits.",
    )
    chains_parser.add_argument("--include-degraded", action="store_true", help="Include offline/degraded chains.")
    chains_parser.set_defaults(
        run=lambda svc, a: svc.list_chains_with_caveats(include_degraded=bool(a.include_degraded))
    )

    resolve_parser = subparsers.add_parser(
        "resolve-chain",
        help="Resolve a network string to chainid via chainlist",
        description="Resolve a network name/alias to chainid via chainlist. Returns rpc_configured plus per-tool caveats.",
    )
    resolve_parser.add_argument("--network", required=True, help="Network name/alias or numeric chainid.")
    resolve_parser.set_defaults(run=lambda svc, a: svc.resolve_chain(a.network))

    convert_parser = subparsers.add_parser(
        "convert",
        help="Convert hex/dec/human/wei/gwei/eth values",
        description=(
            "Convert between hex/dec/human/wei/gwei/eth with decimals (default 18).\n"
            "Examples:\n"
            "  convert --value 0x1bc16d674ec80000 --from hex --to eth\n"
            "  convert --value 2500000 --from dec --to human --decimals 6"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    convert_parser.add_argument("--value", required=True, help="Value to convert (string, hex, or decimal).")
    convert_parser.add_argument("--from", required=True, dest="from_unit", help="Source unit: hex|dec|human|wei|gwei|eth.")
    convert_parser.add_argument("--to", required=True, dest="to_unit", help="Target unit: hex|dec|human|wei|gwei|eth.")
    convert_parser.add_argument("--decimals", type=lambda raw: _json_value(raw, "--decimals"), help="Token decimals. Defaults to 18.")
    convert_parser.set_defaults(
        run=lambda svc, a: svc.convert(a.value, a.from_unit, a.to_unit, a.decimals)
    )

    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config()
        service = ContractService(config)
        result = args.run(service, args)
        print(json.dumps(result, indent=2))
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Error: {_redact_secrets(str(exc))}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
