# Etherscan MCP

基于 Etherscan API 的调研工具集，提供 CLI 和 MCP（Model Context Protocol）接口，用于拉取已验证合约的 ABI/源码、创建信息、代理检测、交易/转账/日志查询，以及只读存储与 `eth_call`。适合合约研判、数据抓取和离线分析。

## 功能概览
- 合约详情：ABI、源码、编译器版本、验证状态。
- 创建信息：创建者、创建交易哈希、块高。
- 代理检测：读取 EIP-1967 implementation/admin 槽，输出实现地址与证据。
- 交互数据：普通交易列表、ERC20/721/1155 代币转移列表、日志按 topic 查询。
- 状态读取：任意存储槽读取（`eth_getStorageAt`）、只读函数调用（`eth_call`，需 ABI 编码输入）。
- 缓存：内存 + 可选文件缓存（合约详情与创建信息可缓存；动态列表/日志/存储/eth_call 默认不缓存）。

## 环境要求
- Python 3.11（兼容 3.10+）。
- Etherscan API Key：`ETHERSCAN_API_KEY`（必填）。

## 安装
```bash
pip install -r src/etherscan-mcp/requirements.txt
```

## 配置
环境变量（必需及可选）：
- `ETHERSCAN_API_KEY`（必需）：你的 Etherscan API Key。
- `NETWORK`（可选，默认 `mainnet`）：可传数字 chainId，或链名/常用别名（例如 `bsc`），会基于 chainlist 动态解析。
- `CHAIN_ID`（可选）：覆盖 network 推导的 chainId。
- `ETHERSCAN_BASE_URL`（可选，默认 `https://api.etherscan.io/v2/api`）。
- `RPC_URL_<chainid>`（可选，推荐）：指定某条链的 JSON-RPC HTTP 端点（例如 `RPC_URL_56` 用于 BSC 读链）。
- `RPC_<chainid>`（可选）：`RPC_URL_<chainid>` 的兼容别名。
- `RPC_URL`（可选）：默认链的 JSON-RPC 端点（仅当调用未显式传 `network` 时生效）；显式传 `network` 的场景建议用 `RPC_URL_<chainid>` 避免误绑定。
- `REQUEST_TIMEOUT`（秒，默认 10）、`REQUEST_RETRIES`（默认 3）、`REQUEST_BACKOFF_SECONDS`（默认 0.5）。

## MCP 使用
示例添加命令（在项目根执行，替换你的 Python 解释器与 Key）：
```bash
codex mcp add etherscan-mcp \
  --env ETHERSCAN_API_KEY=<your-api-key> \
  --env RPC_URL_56=<your-bsc-rpc-https-endpoint> \
  -- bash -lc "cd `pwd`/src/etherscan-mcp && python -m app.mcp_server --transport stdio"
```

说明：
- ABI/源码能力（如 `fetch_contract/get_source_file`）仍使用 Etherscan V2 API。
- 读链能力（如 `call_function/get_storage_at/query_logs/get_block_by_number/get_transaction`）在配置了对应 `RPC_URL_<chainid>` 时会走真实 JSON-RPC；未配置时保持原行为（继续走 Etherscan `module=proxy`），在 BSC 等链的 Free tier 下可能受限。
