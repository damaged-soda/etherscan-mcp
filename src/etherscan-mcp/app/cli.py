import argparse
import json
import sys
from typing import Optional

from .config import load_config
from .service import ContractService


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch verified contract ABI and source from Etherscan.",
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="Fetch contract details")
    fetch_parser.add_argument(
        "--address",
        required=True,
        help="Contract address (0x-prefixed).",
    )
    fetch_parser.add_argument(
        "--network",
        required=False,
        help="Optional network override. Defaults to NETWORK env or mainnet.",
    )
    fetch_parser.add_argument(
        "--inline-limit",
        required=False,
        type=int,
        help="Max total source chars to inline (service default 20000). Use 0 to omit, or --force-inline to bypass.",
    )
    fetch_parser.add_argument(
        "--force-inline",
        action="store_true",
        help="Force inlining source regardless of size (may be large).",
    )

    get_file_parser = subparsers.add_parser("get-source-file", help="Fetch a single source file")
    get_file_parser.add_argument(
        "--address",
        required=True,
        help="Contract address (0x-prefixed).",
    )
    get_file_parser.add_argument(
        "--filename",
        required=True,
        help="Exact filename as reported by Etherscan.",
    )
    get_file_parser.add_argument(
        "--network",
        required=False,
        help="Optional network override. Defaults to NETWORK env or mainnet.",
    )
    get_file_parser.add_argument(
        "--offset",
        required=False,
        type=int,
        help="Optional offset (chars) to start from. Defaults to 0.",
    )
    get_file_parser.add_argument(
        "--length",
        required=False,
        type=int,
        help="Optional length (chars) to return from offset.",
    )

    block_parser = subparsers.add_parser("get-block", help="Fetch a block by number or latest")
    block_parser.add_argument(
        "--block",
        required=True,
        help="Block identifier: latest, decimal number, or 0x-prefixed hex.",
    )
    block_parser.add_argument(
        "--network",
        required=False,
        help="Optional network override. Defaults to NETWORK env or mainnet.",
    )
    block_parser.add_argument(
        "--full-transactions",
        action="store_true",
        help="Return full transaction objects (may be large).",
    )
    block_parser.add_argument(
        "--tx-hashes-only",
        action="store_true",
        help="Force transactions to be returned as hashes list (overrides --full-transactions).",
    )

    block_time_parser = subparsers.add_parser("get-block-time", help="Fetch block time by number or latest")
    block_time_parser.add_argument(
        "--block",
        required=True,
        help="Block identifier: latest, decimal number, or 0x-prefixed hex.",
    )
    block_time_parser.add_argument(
        "--network",
        required=False,
        help="Optional network override. Defaults to NETWORK env or mainnet.",
    )

    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config()
        service = ContractService(config)

        if args.command == "fetch":
            result = service.fetch_contract(
                args.address,
                args.network,
                inline_limit=args.inline_limit,
                force_inline=args.force_inline,
            )
            print(json.dumps(result, indent=2))
        elif args.command == "get-source-file":
            result = service.get_source_file(
                args.address,
                args.filename,
                args.network,
                offset=args.offset,
                length=args.length,
            )
            print(json.dumps(result, indent=2))
        elif args.command == "get-block":
            result = service.get_block_by_number(
                args.block,
                args.network,
                full_transactions=args.full_transactions,
                tx_hashes_only=args.tx_hashes_only,
            )
            print(json.dumps(result, indent=2))
        elif args.command == "get-block-time":
            result = service.get_block_time_by_number(
                args.block,
                args.network,
            )
            print(json.dumps(result, indent=2))
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
