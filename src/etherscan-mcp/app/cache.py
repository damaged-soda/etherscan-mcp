import json
from pathlib import Path
from typing import Any, Dict, Optional


class ContractCache:
    """In-memory cache with optional file persistence."""

    def __init__(self, cache_dir: Optional[str] = None, namespace: Optional[str] = None) -> None:
        self._memory: Dict[str, Any] = {}
        self.namespace = namespace
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            root = self.cache_dir / namespace if namespace else self.cache_dir
            root.mkdir(parents=True, exist_ok=True)

    def _key(self, address: str, network: str) -> str:
        prefix = f"{self.namespace}:" if self.namespace else ""
        return f"{prefix}{network}:{address.lower()}"

    def _file_path(self, address: str, network: str) -> Optional[Path]:
        if not self.cache_dir:
            return None
        base = self.cache_dir / self.namespace if self.namespace else self.cache_dir
        return base / network / f"{address.lower()}.json"

    def get(self, address: str, network: str) -> Optional[Dict[str, Any]]:
        key = self._key(address, network)
        if key in self._memory:
            return self._memory[key]

        path = self._file_path(address, network)
        if path and path.exists():
            try:
                data = json.loads(path.read_text())
                self._memory[key] = data
                return data
            except (OSError, json.JSONDecodeError):
                return None

        return None

    def set(self, address: str, network: str, data: Dict[str, Any]) -> None:
        key = self._key(address, network)
        self._memory[key] = data

        path = self._file_path(address, network)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
