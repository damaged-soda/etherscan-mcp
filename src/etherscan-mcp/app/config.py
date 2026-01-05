import os
import re
from dataclasses import dataclass, field
from typing import Dict, Optional

DEFAULT_BASE_URL = "https://api.etherscan.io/v2/api"
DEFAULT_CHAINLIST_URL = "https://api.etherscan.io/v2/chainlist"

# Keep a small fallback mapping so core networks still work if chainlist fetch fails.
NETWORK_CHAIN_ID_MAP = {
    "mainnet": "1",
    "ethereum": "1",
    "eth": "1",
    "bsc": "56",
    "sepolia": "11155111",
    "holesky": "17000",
}

_RPC_URL_ENV_RE = re.compile(r"^(RPC_URL|RPC)_(\d+)$")


@dataclass
class Config:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    chainlist_url: str = DEFAULT_CHAINLIST_URL
    network: str = "mainnet"
    chain_id: str = "1"
    chain_id_override: Optional[str] = None
    request_timeout: int = 10
    max_retries: int = 3
    backoff_seconds: float = 0.5
    chainlist_ttl_seconds: int = 3600
    rpc_urls: Dict[str, str] = field(default_factory=dict)
    rpc_url_default: Optional[str] = None


def resolve_chain_id(network: str, override_chain_id: Optional[str] = None) -> str:
    """Resolve chain ID from override or static network mapping."""
    if override_chain_id:
        return override_chain_id

    normalized = (network or "").strip().lower()
    if normalized.isdigit():
        return normalized

    if normalized in NETWORK_CHAIN_ID_MAP:
        return NETWORK_CHAIN_ID_MAP[normalized]

    allowed = ", ".join(sorted(NETWORK_CHAIN_ID_MAP.keys()) + ["<chain_id>"])
    raise ValueError(
        f"Unknown network '{network}' in static map. Supported: {allowed}. "
        "Provide numeric chainid, set CHAIN_ID explicitly, or rely on /v2/chainlist dynamic resolution."
    )


def _load_rpc_urls_from_env() -> Dict[str, str]:
    """Load chainid -> RPC URL mapping from environment variables."""
    rpc_urls: Dict[str, str] = {}
    for key, value in os.environ.items():
        match = _RPC_URL_ENV_RE.match(key)
        if not match:
            continue
        chain_id = match.group(2)
        url = (value or "").strip()
        if url:
            rpc_urls[chain_id] = url
    return rpc_urls


def load_config() -> Config:
    """Load configuration from environment variables."""
    api_key = os.getenv("ETHERSCAN_API_KEY")
    if not api_key:
        raise ValueError("ETHERSCAN_API_KEY is required but not set.")

    base_url = os.getenv("ETHERSCAN_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    chainlist_url = os.getenv("ETHERSCAN_CHAINLIST_URL", DEFAULT_CHAINLIST_URL).rstrip("/")
    network = os.getenv("NETWORK", "mainnet").strip().lower()
    chain_id_env = os.getenv("CHAIN_ID")
    timeout = int(os.getenv("REQUEST_TIMEOUT", "10"))
    max_retries = int(os.getenv("REQUEST_RETRIES", "3"))
    backoff = float(os.getenv("REQUEST_BACKOFF_SECONDS", "0.5"))
    ttl = int(os.getenv("CHAINLIST_TTL_SECONDS", "3600"))
    rpc_urls = _load_rpc_urls_from_env()
    rpc_url_default = os.getenv("RPC_URL")
    rpc_url_default = rpc_url_default.strip() if rpc_url_default else None

    chain_id_override = chain_id_env.strip() if chain_id_env else None

    # If NETWORK is unknown here, defer resolution to ChainRegistry at runtime.
    if chain_id_override:
        chain_id = chain_id_override
    else:
        try:
            chain_id = resolve_chain_id(network)
        except Exception:
            chain_id = NETWORK_CHAIN_ID_MAP["mainnet"]

    return Config(
        api_key=api_key,
        base_url=base_url,
        chainlist_url=chainlist_url,
        network=network,
        chain_id=chain_id,
        chain_id_override=chain_id_override,
        request_timeout=timeout,
        max_retries=max_retries,
        backoff_seconds=backoff,
        chainlist_ttl_seconds=ttl,
        rpc_urls=rpc_urls,
        rpc_url_default=rpc_url_default,
    )
