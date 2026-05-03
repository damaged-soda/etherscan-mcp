import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Optional


class ContractCache:
    """In-memory cache keyed by address+network, with optional JSON disk
    persistence so per-(chain, address) lookups (token symbol/decimals/name,
    contract names) survive process restarts.

    Persistence is best-effort: load failures (corrupt JSON, missing dir)
    silently fall back to an empty cache; write failures are silently swallowed
    so a flaky disk never breaks the request path. Writes are atomic via
    tempfile + rename so a crash mid-write can't leave a half-written file.

    Threading: the in-memory dict and the disk-write lock are both protected by
    a single RLock — multiple threads (e.g. the parallel token-metadata
    workers in `get_transaction_summary`) can safely share an instance.
    """

    def __init__(self, disk_path: Optional[Path] = None) -> None:
        self._memory: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._disk_path = Path(disk_path) if disk_path else None
        self._load_from_disk()

    def _key(self, address: str, network: str) -> str:
        return f"{network}:{address.lower()}"

    def get(self, address: str, network: str) -> Optional[Dict[str, Any]]:
        key = self._key(address, network)
        with self._lock:
            return self._memory.get(key)

    def set(self, address: str, network: str, data: Dict[str, Any]) -> None:
        key = self._key(address, network)
        with self._lock:
            self._memory[key] = data
            self._flush_to_disk()

    def _load_from_disk(self) -> None:
        if not self._disk_path:
            return
        try:
            with open(self._disk_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                # Best-effort: only accept dict values; drop anything weird
                # rather than fail the whole load.
                with self._lock:
                    for k, v in loaded.items():
                        if isinstance(k, str) and isinstance(v, dict):
                            self._memory[k] = v
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return

    def _flush_to_disk(self) -> None:
        # Caller already holds self._lock.
        if not self._disk_path:
            return
        try:
            self._disk_path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write: write to a sibling tempfile then os.replace, so a
            # crash can't leave a half-written file at the canonical path.
            tmp_fd, tmp_path = tempfile.mkstemp(
                prefix=self._disk_path.name + ".",
                suffix=".tmp",
                dir=str(self._disk_path.parent),
            )
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(self._memory, f, separators=(",", ":"))
                os.replace(tmp_path, self._disk_path)
            except Exception:
                # Cleanup the tempfile if rename failed.
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except (OSError, TypeError):
            # Disk full / permission denied / non-JSON-serializable value.
            # Fall back to memory-only for this entry; don't break the request.
            return
