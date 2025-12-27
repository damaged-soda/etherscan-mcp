import os
from dataclasses import dataclass
from typing import Optional

DEFAULT_BASE_URL = "https://api.etherscan.io/v2/api"
DEFAULT_CHAINLIST_URL = "https://api.etherscan.io/v2/chainlist"

# Keep a small fallback mapping so core networks still work if chainlist fetch fails.
NETWORK_CHAIN_ID_MAP = {
    "mainnet": "1",
    "ethereum": "1",
    "eth": "1",
    "sepolia": "11155111",
    "holesky": "17000",
}


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
    )
