"""
MCP server exposing contract fetch capability via Etherscan V2.
"""

import argparse
from typing import Optional

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


@server.tool(
    name="fetch_contract",
    title="Fetch Contract Details",
    description="Fetch verified contract ABI and source code from Etherscan.",
)
def fetch_contract(address: str, network: Optional[str] = None) -> dict:
    """
    Fetch contract details for a given address.
    """
    svc = _get_service()
    return svc.fetch_contract(address, network)


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
