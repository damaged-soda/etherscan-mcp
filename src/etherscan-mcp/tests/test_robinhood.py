import os
import unittest
from unittest.mock import Mock, patch

from app.chains import ChainRegistry
from app.config import Config, load_config, resolve_chain_id
from app.etherscan_client import EtherscanClient
from app.service import ContractService


class _OfflineChainlistClient:
    def get_chainlist(self, _url):
        raise AssertionError("Robinhood presets should resolve without Etherscan chainlist")


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
        self.assertEqual(
            config.explorer_api_urls["4663"],
            "https://explorer.example/api",
        )


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
        self.assertEqual(url, "https://explorer.testnet.chain.robinhood.com/api")
        self.assertEqual(params["chainid"], "46630")
        self.assertEqual(client.indexer_name(), "blockscout")

    def test_service_reports_builtin_rpc_as_configured(self) -> None:
        service = ContractService(Config(api_key="test-key"))

        result = service.resolve_chain("robinhood")

        self.assertEqual(result["chain_id"], "4663")
        self.assertTrue(result["rpc_configured"])
        self.assertTrue(
            any(
                caveat["tool"] == "fetch_contract"
                and caveat["status_effective"] == "degraded"
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


if __name__ == "__main__":
    unittest.main()
