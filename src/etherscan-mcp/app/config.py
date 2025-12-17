import os
from dataclasses import dataclass
from typing import Optional

DEFAULT_BASE_URL = "https://api.etherscan.io/v2/api"
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
    network: str = "mainnet"
    chain_id: str = "1"
    request_timeout: int = 10
    max_retries: int = 3
    backoff_seconds: float = 0.5


def resolve_chain_id(network: str, override_chain_id: Optional[str] = None) -> str:
    """Resolve chain ID from override or known network mapping."""
    if override_chain_id:
        return override_chain_id

    normalized = (network or "").lower()
    if normalized.isdigit():
        return normalized

    if normalized in NETWORK_CHAIN_ID_MAP:
        return NETWORK_CHAIN_ID_MAP[normalized]

    allowed = ", ".join(sorted(NETWORK_CHAIN_ID_MAP.keys()) + ["<chain_id>"])
    raise ValueError(f"Unknown network '{network}'. Supported: {allowed}. Or provide CHAIN_ID explicitly.")


def load_config() -> Config:
    """Load configuration from environment variables."""
    api_key = os.getenv("ETHERSCAN_API_KEY")
    if not api_key:
        raise ValueError("ETHERSCAN_API_KEY is required but not set.")

    base_url = os.getenv("ETHERSCAN_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    network = os.getenv("NETWORK", "mainnet").lower()
    chain_id_env = os.getenv("CHAIN_ID")
    timeout = int(os.getenv("REQUEST_TIMEOUT", "10"))
    max_retries = int(os.getenv("REQUEST_RETRIES", "3"))
    backoff = float(os.getenv("REQUEST_BACKOFF_SECONDS", "0.5"))

    chain_id = resolve_chain_id(network, chain_id_env)

    return Config(
        api_key=api_key,
        base_url=base_url,
        network=network,
        chain_id=chain_id,
        request_timeout=timeout,
        max_retries=max_retries,
        backoff_seconds=backoff,
    )
