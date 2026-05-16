"""
Per-chain tool capability matrix.

Etherscan V2 plan limits and chain-specific quirks are not visible from chainlist
itself — they only surface as runtime errors (typically `Free API access is not
supported for this chain` or `txlist`/`tokentx` returning an empty result on free
tier). This module hand-curates the known caveats so callers can see them up
front via `resolve_chain` / `list_chains` / `chain_capabilities` instead of
discovering them mid-run.

Structure:
- CHAIN_CAVEATS: chainid (str) -> list of caveat dicts. Chain-specific quirks
  (Etherscan free-tier limits on BSC/Base, etc.).
- GLOBAL_CAVEATS: list of caveat dicts that apply to every chain (chain-agnostic
  Etherscan API behaviors that don't change per chain). Merged into every
  `caveats_for(...)` response.
- A caveat targets either a specific tool name, or the wildcard `*module_proxy`
  which expands to every tool that falls back to Etherscan `module=proxy` when no
  `RPC_URL_<chainid>` is configured.

Status values:
- requires_rpc_url   Etherscan path blocked; setting `RPC_URL_<chainid>` makes
                     the affected tool route via JSON-RPC and unblocks it.
- paid_tier_only     Needs an Etherscan paid plan (or a third-party indexer);
                     no RPC fallback exists for this surface.
- degraded           Works but unreliably / partially.
- unsupported        Not available on this chain at all.
"""

from __future__ import annotations

from typing import Any, Dict, List

STATUS_REQUIRES_RPC = "requires_rpc_url"
STATUS_PAID_TIER_ONLY = "paid_tier_only"
STATUS_DEGRADED = "degraded"
STATUS_UNSUPPORTED = "unsupported"
STATUS_OK = "ok"

# Tools that route via Etherscan `module=proxy` when no RPC_URL_<chainid> is
# configured. Setting RPC_URL_<chainid> makes them go via JSON-RPC and bypass
# Etherscan plan limits.
MODULE_PROXY_TOOLS = (
    "call_function",
    "get_storage_at",
    "detect_proxy",
    "query_logs",
    "get_block_by_number",
    "get_block_time_by_number",
    "get_transaction",
)

_WILDCARD_MODULE_PROXY = "*module_proxy"

# Hand-curated caveat matrix, sourced from README "已知限制" + observed runtime
# failures. Keep entries minimal; only known-bad surfaces. Empty list / missing
# chainid means "no known caveats — expected to work".
# Chain-agnostic caveats. Apply to every chain regardless of CHAIN_CAVEATS entry.
# Use for Etherscan API behaviors that don't change per chain (e.g. `module=proxy`
# silently ignoring non-latest block tags is true on every chain Etherscan covers).
GLOBAL_CAVEATS: List[Dict[str, str]] = [
    {
        "tool": "call_function",
        "status": STATUS_REQUIRES_RPC,
        "reason": "Etherscan `module=proxy` (eth_call) 静默忽略非 latest/earliest/pending 的 block_tag，对历史区块号永远返回 latest state。",
        "workaround": "配 archive 节点的 `RPC_URL_<chainid>`（Alchemy / Quicknode / drpc / Ankr / 自建 erigon）；普通 full node 也不行，要 archive。",
    },
    {
        "tool": "call_function_series",
        "status": STATUS_REQUIRES_RPC,
        "reason": "历史区块序列 eth_call 只走 JSON-RPC batch；Etherscan `module=proxy` 不能可靠读取历史 state。",
        "workaround": "配 archive 节点的 `RPC_URL_<chainid>`（Alchemy / Quicknode / drpc / Ankr / 自建 erigon）；普通 full node 也不行，要 archive。",
    },
    {
        "tool": "get_storage_at",
        "status": STATUS_REQUIRES_RPC,
        "reason": "Etherscan `module=proxy` (eth_getStorageAt) 同样不支持历史 block_tag；某些链节点会返回 `historical state ... not available`，但路径本身需要 archive。",
        "workaround": "配 archive 节点的 `RPC_URL_<chainid>`（Alchemy / Quicknode / drpc / Ankr / 自建 erigon）；普通 full node 也不行。",
    },
]


CHAIN_CAVEATS: Dict[str, List[Dict[str, str]]] = {
    # BSC
    "56": [
        {
            "tool": "get_contract_creation",
            "status": STATUS_DEGRADED,
            "reason": "Etherscan getcontractcreation 在 BSC 上对部分地址（尤其是 internal CREATE）返回 NOTOK。",
            "workaround": "配 RPC_URL_56 启用二分回退（需要 archive / full-history 节点）。",
        },
        {
            "tool": _WILDCARD_MODULE_PROXY,
            "status": STATUS_REQUIRES_RPC,
            "reason": "Etherscan free tier 的 `module=proxy` 在 BSC 报 'Free API access is not supported for this chain'。",
            "workaround": "配 RPC_URL_56；受影响的 tool 会自动改走 JSON-RPC。",
        },
    ],
    # Base
    "8453": [
        {
            "tool": "list_transactions",
            "status": STATUS_PAID_TIER_ONLY,
            "reason": "Etherscan txlist 在 Base free tier 返回空；JSON-RPC 没有等价的按地址倒查能力。",
            "workaround": "Etherscan 付费计划，或用第三方索引服务（Covalent / Alchemy enhanced API）。",
        },
        {
            "tool": "list_token_transfers",
            "status": STATUS_PAID_TIER_ONLY,
            "reason": "Etherscan tokentx 在 Base free tier 返回空，同样无 RPC 等价。",
            "workaround": "Etherscan 付费计划，或用第三方索引服务。",
        },
        {
            "tool": _WILDCARD_MODULE_PROXY,
            "status": STATUS_REQUIRES_RPC,
            "reason": "Etherscan free tier 的 `module=proxy` 在 Base 被挡。",
            "workaround": "配 RPC_URL_8453；受影响的 tool 会自动改走 JSON-RPC。",
        },
    ],
}


# Heuristic rules for `get_transaction_summary` compact mode `route_hints`.
# These are best-effort substring / prefix matches against verified contract
# names and ERC20 symbols; callers must treat them as hints, not assertions.
# Keep the rule set conservative — false positives here pollute every compact
# response.
ROUTE_HINT_RULES: List[Dict[str, Any]] = [
    {
        "label": "Pendle router call",
        "any_contract_name_substr": ["PendleRouter"],
    },
    {
        "label": "Touches Pendle market",
        "any_contract_name_substr": ["PendleMarket"],
    },
    {
        "label": "Kyber aggregation used",
        "any_contract_name_substr": ["MetaAggregationRouter", "Kyber"],
    },
    {
        "label": "1inch aggregation used",
        "any_contract_name_substr": ["AggregationRouterV"],
        # Kyber 的 MetaAggregationRouterV2 子串包含 AggregationRouterV，不能算 1inch。
        "not_contract_name_substr": ["Meta"],
    },
    {
        "label": "Touches Uniswap V3 / CL pool",
        "any_contract_name_substr": ["UniswapV3", "CLPool"],
    },
    {
        "label": "Touches PT/YT/SY",
        "any_token_symbol_prefix": ["PT-", "YT-", "SY-"],
    },
]


def build_route_hints(
    contract_names: List[str], token_symbols: List[str]
) -> List[str]:
    """Best-effort labels — see ROUTE_HINT_RULES for caveats."""
    out: List[str] = []
    names = [(n or "") for n in contract_names]
    symbols_upper = [(s or "").upper() for s in token_symbols]
    for rule in ROUTE_HINT_RULES:
        excludes = rule.get("not_contract_name_substr", []) or []

        def _name_matches(substr: str) -> bool:
            return any(
                substr in n and not any(ex in n for ex in excludes)
                for n in names
            )

        matched = False
        for substr in rule.get("any_contract_name_substr", []) or []:
            if _name_matches(substr):
                matched = True
                break
        if not matched:
            for prefix in rule.get("any_token_symbol_prefix", []) or []:
                pu = prefix.upper()
                if any(s.startswith(pu) for s in symbols_upper):
                    matched = True
                    break
        if matched:
            out.append(rule["label"])
    return out


def has_caveats(chain_id: str) -> bool:
    """Cheap check used by `list_chains` to flag rows with known issues.

    Only counts chain-specific caveats. `GLOBAL_CAVEATS` apply to every chain
    by definition, so flagging them here would mark every row — defeating the
    point of `has_caveats` (which is to highlight rows that need extra
    attention vs the default). Use `caveats_for(...)` to see the full
    chain + global merged view."""
    return bool(CHAIN_CAVEATS.get(str(chain_id)))


def _expand(caveats: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Expand `*module_proxy` wildcard into per-tool entries."""
    out: List[Dict[str, str]] = []
    for c in caveats:
        if c.get("tool") == _WILDCARD_MODULE_PROXY:
            for tool_name in MODULE_PROXY_TOOLS:
                expanded = dict(c)
                expanded["tool"] = tool_name
                out.append(expanded)
        else:
            out.append(dict(c))
    return out


def caveats_for(chain_id: str, rpc_configured: bool) -> List[Dict[str, Any]]:
    """
    Return caveats for a chain, with `status_effective` reflecting whether
    a configured RPC_URL_<chainid> mitigates each entry.

    Chain-specific entries from CHAIN_CAVEATS are merged with chain-agnostic
    entries from GLOBAL_CAVEATS. `requires_rpc_url` flips to `ok` when
    rpc_configured=True; everything else stays as-is (paid_tier_only /
    degraded / unsupported are not RPC-fixable).

    Note: `GLOBAL_CAVEATS` for `call_function` / `call_function_series` /
    `get_storage_at` flagging historical-block-tag support flips to `ok`
    when ANY RPC_URL is configured,
    but the workaround text reminds callers that the configured node must be
    an archive node (we can't introspect URL to verify that).
    """
    raw = list(CHAIN_CAVEATS.get(str(chain_id), [])) + list(GLOBAL_CAVEATS)
    expanded = _expand(raw)
    for c in expanded:
        status = c.get("status")
        if rpc_configured and status == STATUS_REQUIRES_RPC:
            c["status_effective"] = STATUS_OK
        else:
            c["status_effective"] = status
    return expanded
