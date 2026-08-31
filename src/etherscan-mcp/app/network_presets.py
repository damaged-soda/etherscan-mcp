"""Built-in metadata for EVM networks not present in Etherscan chainlist."""

from __future__ import annotations

from typing import Any, Dict


# Etherscan V2's chainlist is still the primary registry. These presets cover
# chains whose official explorer/indexer is Etherscan-compatible but hosted by
# another provider. Environment variables may override both endpoint maps.
NETWORK_PRESETS: Dict[str, Dict[str, Any]] = {
    "4663": {
        "chainname": "Robinhood Chain",
        "aliases": ("robinhood", "robinhood-mainnet", "rh", "rh-mainnet"),
        "blockexplorer": "https://robinhoodchain.blockscout.com",
        "apiurl": "https://robinhoodchain.blockscout.com/api",
        "rpc_url": "https://rpc.mainnet.chain.robinhood.com",
        "alchemy_rpc_url": "https://robinhood-mainnet.g.alchemy.com/v2/{api_key}",
        "status": 1,
        "comment": "Built-in Blockscout/public-RPC preset; public endpoints are rate-limited.",
    },
    "46630": {
        "chainname": "Robinhood Chain Testnet",
        "aliases": ("robinhood-testnet", "rh-testnet"),
        "blockexplorer": "https://explorer.testnet.chain.robinhood.com",
        "apiurl": "https://explorer.testnet.chain.robinhood.com/api",
        "rpc_url": "https://rpc.testnet.chain.robinhood.com",
        "alchemy_rpc_url": "https://robinhood-testnet.g.alchemy.com/v2/{api_key}",
        "status": 1,
        "comment": "Built-in Blockscout/public-RPC preset; testnet assets have no value.",
    },
}


def default_rpc_urls() -> Dict[str, str]:
    return {
        chain_id: str(preset["rpc_url"])
        for chain_id, preset in NETWORK_PRESETS.items()
        if preset.get("rpc_url")
    }


def default_rpc_url_sources() -> Dict[str, str]:
    return {chain_id: "builtin" for chain_id in default_rpc_urls()}


def alchemy_rpc_urls(api_key: str) -> Dict[str, str]:
    return {
        chain_id: str(preset["alchemy_rpc_url"]).format(api_key=api_key)
        for chain_id, preset in NETWORK_PRESETS.items()
        if preset.get("alchemy_rpc_url")
    }


def default_explorer_api_urls() -> Dict[str, str]:
    return {
        chain_id: str(preset["apiurl"])
        for chain_id, preset in NETWORK_PRESETS.items()
        if preset.get("apiurl")
    }


def preset_aliases() -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    for chain_id, preset in NETWORK_PRESETS.items():
        for alias in preset.get("aliases", ()):
            aliases[str(alias).strip().lower()] = chain_id
    return aliases
