from typing import Any, Dict, Optional


class ContractCache:
    """Simple in-memory cache keyed by address+network."""

    def __init__(self) -> None:
        self._memory: Dict[str, Any] = {}

    def _key(self, address: str, network: str) -> str:
        return f"{network}:{address.lower()}"

    def get(self, address: str, network: str) -> Optional[Dict[str, Any]]:
        key = self._key(address, network)
        return self._memory.get(key)

    def set(self, address: str, network: str, data: Dict[str, Any]) -> None:
        key = self._key(address, network)
        self._memory[key] = data
