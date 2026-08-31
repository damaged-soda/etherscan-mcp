import os
import unittest
from unittest.mock import Mock, patch

import requests

from app.chains import ChainRegistry
from app.config import Config, load_config, resolve_chain_id
from app.etherscan_client import EtherscanClient
from app.service import ContractService


class _OfflineChainlistClient:
    def get_chainlist(self, _url):
        raise AssertionError("Robinhood presets should resolve without Etherscan chainlist")


class _CountingChainlistClient:
    def __init__(self):
        self.calls = 0

    def get_chainlist(self, _url):
        self.calls += 1
        return {
            "result": [
                {
                    "chainname": "Base Mainnet",
                    "chainid": "8453",
                    "blockexplorer": "https://basescan.org",
                    "apiurl": "https://api.etherscan.io/v2/api",
                    "status": 1,
                    "comment": "",
                }
            ]
        }


class RobinhoodConfigTest(unittest.TestCase):
    def test_static_aliases_resolve(self) -> None:
        self.assertEqual(resolve_chain_id("robinhood"), "4663")
        self.assertEqual(resolve_chain_id("rh-mainnet"), "4663")
        self.assertEqual(resolve_chain_id("robinhood-testnet"), "46630")

    def test_load_config_includes_public_endpoints(self) -> None:
        with patch.dict(os.environ, {"ETHERSCAN_API_KEY": "test-key"}, clear=True):
            config = load_config()

        self.assertEqual(
            config.rpc_urls["4663"],
            "https://rpc.mainnet.chain.robinhood.com",
        )
        self.assertEqual(
            config.explorer_api_urls["46630"],
            "https://explorer.testnet.chain.robinhood.com/api",
        )

    def test_environment_overrides_builtin_endpoints(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ETHERSCAN_API_KEY": "test-key",
                "RPC_URL_4663": "https://rpc.example/robinhood",
                "EXPLORER_API_URL_4663": "https://explorer.example/api/",
            },
            clear=True,
        ):
            config = load_config()

        self.assertEqual(config.rpc_urls["4663"], "https://rpc.example/robinhood")
        self.assertEqual(config.rpc_url_sources["4663"], "env")
        self.assertEqual(
            config.explorer_api_urls["4663"],
            "https://explorer.example/api",
        )

    def test_empty_environment_values_disable_builtin_endpoints(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ETHERSCAN_API_KEY": "test-key",
                "RPC_URL_4663": "",
                "EXPLORER_API_URL_4663": "",
            },
            clear=True,
        ):
            config = load_config()

        self.assertNotIn("4663", config.rpc_urls)
        self.assertNotIn("4663", config.rpc_url_sources)
        self.assertNotIn("4663", config.explorer_api_urls)


class RobinhoodRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ChainRegistry(
            client=_OfflineChainlistClient(),
            chainlist_url="https://example.invalid/v2/chainlist",
        )

    def test_mainnet_resolves_offline(self) -> None:
        label, chain_id, meta = self.registry.resolve("robinhood")

        self.assertEqual(label, "robinhood-chain")
        self.assertEqual(chain_id, "4663")
        self.assertEqual(meta["apiurl"], "https://robinhoodchain.blockscout.com/api")
        self.assertEqual(meta["matched_by"], "exact")

    def test_testnet_resolves_offline(self) -> None:
        label, chain_id, meta = self.registry.resolve("rh-testnet")

        self.assertEqual(label, "robinhood-chain-testnet")
        self.assertEqual(chain_id, "46630")
        self.assertEqual(
            meta["blockexplorer"],
            "https://explorer.testnet.chain.robinhood.com",
        )

    def test_remote_exact_match_refreshes_after_ttl_expiry(self) -> None:
        client = _CountingChainlistClient()
        registry = ChainRegistry(
            client=client,
            chainlist_url="https://example.invalid/v2/chainlist",
        )

        registry.resolve("base")
        registry._loaded_at = 0
        registry.resolve("base")

        self.assertEqual(client.calls, 2)


class RobinhoodExplorerRoutingTest(unittest.TestCase):
    def test_client_routes_robinhood_to_blockscout(self) -> None:
        client = EtherscanClient(
            api_key="test-key",
            base_url="https://api.etherscan.io/v2/api",
            chain_id="46630",
            chain_api_urls={
                "46630": "https://explorer.testnet.chain.robinhood.com/api"
            },
            max_retries=1,
        )
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"status": "1", "message": "OK", "result": []}
        response.raise_for_status.return_value = None
        client.session.get = Mock(return_value=response)

        client.get_contract_source("0x" + "1" * 40)

        url = client.session.get.call_args.args[0]
        params = client.session.get.call_args.kwargs["params"]
        headers = client.session.get.call_args.kwargs["headers"]
        self.assertEqual(url, "https://explorer.testnet.chain.robinhood.com/api")
        self.assertEqual(params["chainid"], "46630")
        self.assertNotIn("apikey", params)
        self.assertNotIn("X-API-Key", headers)
        self.assertNotIn("X-API-Key", client.session.headers)
        self.assertEqual(client.indexer_name(), "blockscout")

    def test_client_scopes_api_key_to_etherscan_origin(self) -> None:
        client = EtherscanClient(
            api_key="test-key",
            base_url="https://api.etherscan.io/v2/api",
            chain_id="1",
            max_retries=1,
        )
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"status": "1", "message": "OK", "result": []}
        response.raise_for_status.return_value = None
        client.session.get = Mock(return_value=response)

        client.get_contract_source("0x" + "1" * 40)

        params = client.session.get.call_args.kwargs["params"]
        headers = client.session.get.call_args.kwargs["headers"]
        self.assertEqual(params["apikey"], "test-key")
        self.assertEqual(headers["X-API-Key"], "test-key")

    def test_http_error_does_not_echo_api_key_or_query(self) -> None:
        client = EtherscanClient(
            api_key="SUPER-SECRET-KEY",
            base_url="https://api.etherscan.io/v2/api",
            chain_id="46630",
            chain_api_urls={
                "46630": "https://explorer.testnet.chain.robinhood.com/api"
            },
            max_retries=1,
        )
        client.session.get = Mock(
            side_effect=requests.HTTPError(
                "403 for https://explorer.testnet.chain.robinhood.com/api?apikey=SUPER-SECRET-KEY"
            )
        )

        with self.assertRaises(ValueError) as caught:
            client.get_contract_source("0x" + "1" * 40)

        message = str(caught.exception)
        self.assertNotIn("SUPER-SECRET-KEY", message)
        self.assertNotIn("apikey", message)
        self.assertEqual(
            message,
            "Explorer API request failed for https://explorer.testnet.chain.robinhood.com/***.",
        )

    def test_blockscout_html_response_uses_correct_indexer_label(self) -> None:
        client = EtherscanClient(
            api_key="test-key",
            base_url="https://api.etherscan.io/v2/api",
            chain_id="46630",
            chain_api_urls={
                "46630": "https://explorer.testnet.chain.robinhood.com/api"
            },
            max_retries=1,
        )
        response = Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.side_effect = ValueError("not JSON")
        client.session.get = Mock(return_value=response)

        with self.assertRaisesRegex(ValueError, "Failed to parse response from Blockscout"):
            client.get_contract_source("0x" + "1" * 40)

    def test_service_reports_builtin_rpc_as_configured(self) -> None:
        service = ContractService(Config(api_key="test-key"))

        result = service.resolve_chain("robinhood")

        self.assertEqual(result["chain_id"], "4663")
        self.assertFalse(result["rpc_configured"])
        self.assertTrue(result["rpc_available"])
        self.assertEqual(result["rpc_source"], "builtin")
        self.assertTrue(
            any(
                caveat["tool"] == "fetch_contract"
                and caveat["status_effective"] == "degraded"
                for caveat in result["caveats"]
            )
        )
        self.assertTrue(
            any(
                caveat["tool"] == "call_function_series"
                and caveat["status_effective"] == "requires_rpc_url"
                for caveat in result["caveats"]
            )
        )
        self.assertEqual(
            service._rpc_url_for("4663", allow_default=False),
            "https://rpc.mainnet.chain.robinhood.com",
        )

    def test_contract_creation_identifies_blockscout_source(self) -> None:
        service = ContractService(Config(api_key="test-key"))
        service.client.get_contract_creation = Mock(
            return_value={
                "status": "1",
                "message": "OK",
                "result": [
                    {
                        "contractCreator": "0x" + "2" * 40,
                        "txHash": "0x" + "3" * 64,
                        "blockNumber": "20",
                        "timestamp": "1770408381",
                    }
                ],
            }
        )

        result = service.get_contract_creation("0x" + "1" * 40, "robinhood-testnet")

        self.assertEqual(result["source"], "blockscout")
        self.assertTrue(result["complete"])

    def test_explicit_rpc_override_mitigates_rpc_caveats(self) -> None:
        service = ContractService(
            Config(
                api_key="test-key",
                rpc_urls={"4663": "https://provider.example/rpc"},
                rpc_url_sources={"4663": "env"},
            )
        )

        result = service.resolve_chain("robinhood")

        self.assertTrue(result["rpc_available"])
        self.assertTrue(result["rpc_configured"])
        self.assertEqual(result["rpc_source"], "env")
        self.assertTrue(
            all(
                caveat["status_effective"] == "ok"
                for caveat in result["caveats"]
                if caveat["tool"] in {"call_function", "call_function_series", "get_storage_at"}
            )
        )


if __name__ == "__main__":
    unittest.main()
