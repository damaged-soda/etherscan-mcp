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

    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config()
        service = ContractService(config)

        if args.command == "fetch":
            result = service.fetch_contract(args.address, args.network)
            print(json.dumps(result, indent=2))
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
