# 项目概览（SOT）

Last Updated: 2026-01-05

## 项目是什么
Etherscan MCP：单仓 Python 项目。用户提供 `ETHERSCAN_API_KEY`，通过 CLI/MCP 拉取并缓存已验证合约的 ABI、源码和基本元数据（Etherscan API V2），辅助离线分析，不涉及部署或链上写操作。读链能力（`eth_call`/`eth_getStorageAt`/`eth_getLogs`/区块/交易等）在配置 `RPC_URL_<chainid>` 时走真实 EVM JSON-RPC；未配置时保持原行为，继续通过 Etherscan `module=proxy`。

## Repo 列表与职责（与 docmap 对齐）
- etherscan-mcp：入口目录 `src/etherscan-mcp/`。模块包括 config（读取 env）、etherscan client（requests 封装）、rpc client（JSON-RPC POST 封装）、cache（纯内存，进程级）、service（聚合合约详情）、CLI 入口、MCP 入口。

## 本地开发最小路径（只到开发自测）
- 环境：Python 3.11（或兼容 3.10+）。
- 安装：（可选）创建虚拟环境 → `pip install -r src/etherscan-mcp/requirements.txt`。
- CLI：  
  - 合约：`ETHERSCAN_API_KEY=<key> [NETWORK=<network>|CHAIN_ID=<id>] [ETHERSCAN_BASE_URL=<url>] python -m app fetch --address <contract> [--inline-limit N|--force-inline]`。源码超内联阈值（默认 20000 字符）且未强制时返回摘要（filename/length/sha256/inline=false）并附 `source_omitted`/`source_omitted_reason`。  
  - 单文件源码：`python -m app get-source-file --address <contract> --filename <file> [--offset N --length M]`。  
  - 区块：`python -m app get-block --block <latest|dec|0x> [--full-transactions] [--tx-hashes-only]`；`tx_hashes_only` 强制仅哈希。  
  - 区块时间：`python -m app get-block-time --block <latest|dec|0x>`，返回块号与时间戳（十进制/0x/ISO）。  
  - 链清单：`python -m app list-chains [--include-degraded]`。  
  - 解析链：`python -m app resolve-chain --network <name|alias|chainid>`（如 `arb` / `Arbitrum One Mainnet` / `42161`）。
- MCP（Codex 本地注册示例）：  
  1) 在项目根执行：  
     ```bash
     codex mcp add etherscan-mcp \
       --env ETHERSCAN_API_KEY=<your-api-key> \
       --env RPC_URL_56=<your-bsc-rpc-https-endpoint> \
       -- bash -lc "cd `pwd`/src/etherscan-mcp && python -m app.mcp_server --transport stdio"
     ```  
  2) 工具：  
     - `fetch_contract(address, network?, inline_limit?, force_inline?)`：ABI/源码/编译器信息，超限时仅摘要并给出 `source_omitted`；未验证合约会明确报错提示 ABI 不可用。  
     - `get_contract_creation(address, network?)`：创建者、创建交易哈希、块高。  
     - `detect_proxy(address, network?)`：EIP-1967 implementation/admin 槽探测。  
     - `list_chains(include_degraded?)`：列出 Etherscan V2 `/v2/chainlist` 返回的链清单。  
     - `resolve_chain(network)`：解析 network 字符串/别名为 `chain_id`（建议优先传数字 chainid 以避免歧义）。  
     - `list_transactions(address, network?, start_block?, end_block?, page?, offset?, sort?)`  
     - `list_token_transfers(address, network?, token_type?, start_block?, end_block?, page?, offset?, sort?)`  
     - `query_logs(address, network?, topics?, from_block?, to_block?, page?, offset?)`  
     - `get_storage_at(address, slot, network?, block_tag?)`  
     - `get_transaction(tx_hash, network?)`  
     - `call_function(address, data?, function?, args?, network?, block_tag?, decimals?)`（含 encode/convert/keccak 辅助工具）  
     - `get_source_file(address, filename, network?, offset?, length?)`  
     - `get_block_by_number(block, network?, full_transactions?, tx_hashes_only?)`  
     - `get_block_time_by_number(block, network?)`  
    参数形态提示：`call_function.args`、`encode_function_data.args`、`query_logs.topics` 必须为数组，字符串/对象会报错，标量自动包成单元素数组。  
    代理感知：call_function 优先实现 ABI；探测异常不缓存“非代理”。  
    无需常驻进程，Codex 按需启动。  
- MCP 自测/重载提示：工具列表变更后需在 Codex 侧重新连接/重新添加 MCP；可用主网示例地址 USDT `0xdAC17F958D2ee523a2206206994597C13D831ec7`、USDC `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`。

## 网络参数支持
- network 入参支持（任意需要 network 的 CLI/MCP 参数一致）：
  - 数字 chainid（十进制字符串）：如 `"42161"`（最稳定，始终可用）
  - 链名/近似链名：基于 Etherscan V2 `GET /v2/chainlist` 动态解析
  - 常用简称：通过轻量别名层映射到动态清单（如 `arb`、`arb-sepolia`、`bsc`→`56`）
- 配置：
  - `CHAIN_ID`：硬覆盖默认链（用于 network 未显式传入的场景）
  - `ETHERSCAN_CHAINLIST_URL`：链清单端点（默认 `https://api.etherscan.io/v2/chainlist`）
  - `CHAINLIST_TTL_SECONDS`：链清单缓存 TTL（默认 3600 秒）
  - `RPC_URL_<chainid>` / `RPC_<chainid>`：为指定链配置 JSON-RPC HTTP 端点（例如 `RPC_URL_56`），配置后读链类工具优先走 RPC（BSC 等链推荐配置以避免 Etherscan proxy 链覆盖限制）
  - `RPC_URL`：默认链的 JSON-RPC 端点（仅当调用未显式传 `network` 时生效）
- 安全策略：默认 `NETWORK` 无法解析且未设置 `CHAIN_ID` 时会明确报错，避免误用主网；可用 `list-chains/resolve-chain`（或 MCP 的 `list_chains/resolve_chain`）先查后用。
