from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

_WORD_RE = re.compile(r"[a-z0-9]+")
_SPACE_RE = re.compile(r"[\s_\-]+")


def _norm(text: str) -> str:
    candidate = (text or "").strip().lower()
    candidate = _SPACE_RE.sub(" ", candidate)
    candidate = " ".join(_WORD_RE.findall(candidate))
    return candidate


def _slug(text: str) -> str:
    return _norm(text).replace(" ", "-")


def _drop_env_words(tokens: List[str]) -> List[str]:
    drop = {"mainnet", "testnet", "network", "chain"}
    return [token for token in tokens if token not in drop]


@dataclass(frozen=True)
class ChainInfo:
    chainname: str
    chainid: str
    blockexplorer: str
    apiurl: str
    status: int
    comment: str

    @property
    def canonical_label(self) -> str:
        return _slug(self.chainname)


class ChainRegistry:
    """
    Dynamic chain registry backed by Etherscan V2 /v2/chainlist.
    - Caches list in-memory with TTL.
    - Resolves network input by chainid or (fuzzy) chainname/slug/aliases.
    """

    def __init__(
        self,
        client: Any,
        chainlist_url: str,
        ttl_seconds: int = 3600,
    ) -> None:
        self._client = client
        self._chainlist_url = (chainlist_url or "").rstrip("/")
        self._ttl = max(30, int(ttl_seconds))
        self._loaded_at: float = 0.0
        self._chains: Dict[str, ChainInfo] = {}
        self._index: Dict[str, List[str]] = {}  # key -> [chainid,...]

        self._alias: Dict[str, str] = {
            "eth": "ethereum mainnet",
            "ethereum": "ethereum mainnet",
            "mainnet": "ethereum mainnet",
            "arb": "arbitrum one",
            "arbitrum": "arbitrum one",
            "arb1": "arbitrum one",
            "arbitrum one": "arbitrum one",
            "arbitrum nova": "arbitrum nova",
            "nova": "arbitrum nova",
            "arb sepolia": "arbitrum sepolia",
            "arb-sepolia": "arbitrum sepolia",
            "arbitrum sepolia": "arbitrum sepolia",
        }

    def _expired(self) -> bool:
        return (time.time() - self._loaded_at) > self._ttl or not self._chains

    def refresh(self, force: bool = False) -> None:
        if not force and not self._expired():
            return

        if not self._chainlist_url:
            raise ValueError("chainlist_url is empty.")

        payload = self._client.get_chainlist(self._chainlist_url)
        if not isinstance(payload, dict):
            raise ValueError("Unexpected chainlist response (non-object).")

        result = payload.get("result")
        if not isinstance(result, list):
            raise ValueError("Unexpected chainlist response (missing result list).")

        chains: Dict[str, ChainInfo] = {}
        for item in result:
            if not isinstance(item, dict):
                continue
            chainid = str(item.get("chainid", "")).strip()
            chainname = str(item.get("chainname", "")).strip()
            if not chainid.isdigit() or not chainname:
                continue
            info = ChainInfo(
                chainname=chainname,
                chainid=chainid,
                blockexplorer=str(item.get("blockexplorer", "")).strip(),
                apiurl=str(item.get("apiurl", "")).strip(),
                status=int(item.get("status", 0) or 0),
                comment=str(item.get("comment", "") or "").strip(),
            )
            chains[chainid] = info

        if not chains:
            raise ValueError("chainlist returned empty or unparseable chain set.")

        self._chains = chains
        self._rebuild_index()
        self._loaded_at = time.time()

    def _rebuild_index(self) -> None:
        idx: Dict[str, List[str]] = {}

        def add(key: str, chainid: str) -> None:
            normalized = _norm(key)
            if not normalized:
                return
            idx.setdefault(normalized, [])
            if chainid not in idx[normalized]:
                idx[normalized].append(chainid)

        for cid, info in self._chains.items():
            add(cid, cid)
            add(info.chainname, cid)
            add(_slug(info.chainname), cid)

            tokens = _norm(info.chainname).split()
            tokens2 = _drop_env_words(tokens)
            if tokens2:
                add(" ".join(tokens2), cid)
                add("-".join(tokens2), cid)

        self._index = idx

    def list_chains(self, include_degraded: bool = True) -> List[Dict[str, Any]]:
        self.refresh()

        out: List[Dict[str, Any]] = []
        for cid, info in sorted(self._chains.items(), key=lambda x: int(x[0])):
            if not include_degraded and info.status != 1:
                continue
            out.append(
                {
                    "chainid": info.chainid,
                    "chainname": info.chainname,
                    "label": info.canonical_label,
                    "blockexplorer": info.blockexplorer,
                    "apiurl": info.apiurl,
                    "status": info.status,
                    "comment": info.comment,
                }
            )
        return out

    def resolve(self, network: Optional[str]) -> Tuple[str, str, Dict[str, Any]]:
        """
        Returns:
          (network_label, chain_id, meta)
        meta includes chainname/blockexplorer/apiurl/status/comment and a 'matched_by' field.
        """
        if network is None:
            raise ValueError("network is required for resolution (should not be None here).")

        raw = str(network).strip()
        if not raw:
            raise ValueError("network must be a non-empty string.")

        # Numeric chainid: always accepted (even if chainlist is unavailable).
        if raw.isdigit():
            info = self._chains.get(raw) if self._chains else None
            if info:
                return info.canonical_label, info.chainid, self._meta(info, matched_by="chainid")
            return raw, raw, self._meta(None, matched_by="chainid")

        self.refresh()

        q = _norm(raw)
        q = _norm(self._alias.get(q, q))

        exact = self._index.get(q)
        if exact:
            return self._pick_or_raise(q, exact, matched_by="exact")

        candidates: List[Tuple[int, str]] = []
        for key, ids in self._index.items():
            if key.startswith(q):
                for cid in ids:
                    candidates.append((80, cid))
                continue
            if q in key:
                for cid in ids:
                    candidates.append((50, cid))

        if not candidates:
            raise ValueError(
                f"Unknown network '{raw}'. Try numeric chainid (e.g. 42161) or call list-chains/list_chains."
            )

        best: Dict[str, int] = {}
        for score, cid in candidates:
            best[cid] = max(best.get(cid, 0), score)

        ranked = sorted(best.items(), key=lambda x: (-x[1], int(x[0])))
        top_score = ranked[0][1]
        top = [cid for cid, score in ranked if score == top_score]
        return self._pick_or_raise(q, top, matched_by="fuzzy")

    def _pick_or_raise(
        self, q: str, chainids: List[str], matched_by: str
    ) -> Tuple[str, str, Dict[str, Any]]:
        if len(chainids) == 1:
            info = self._chains[chainids[0]]
            return info.canonical_label, info.chainid, self._meta(info, matched_by=matched_by)

        previews = []
        for cid in sorted(chainids, key=lambda x: int(x))[:10]:
            info = self._chains.get(cid)
            if info:
                previews.append(f"{info.chainname} (chainid={info.chainid})")

        raise ValueError(
            f"Ambiguous network query '{q}'. Candidates: "
            + "; ".join(previews)
            + ". Please pass a numeric chainid."
        )

    def _meta(self, info: Optional[ChainInfo], matched_by: str) -> Dict[str, Any]:
        if info is None:
            return {
                "chainname": None,
                "blockexplorer": None,
                "apiurl": None,
                "status": None,
                "comment": None,
                "matched_by": matched_by,
            }

        return {
            "chainname": info.chainname,
            "blockexplorer": info.blockexplorer,
            "apiurl": info.apiurl,
            "status": info.status,
            "comment": info.comment,
            "matched_by": matched_by,
        }
