# 项目概览（SOT）

Last Updated: 2025-12-18

## 项目是什么
Etherscan MCP：单仓 Python 项目。用户提供 `ETHERSCAN_API_KEY`，通过 CLI 拉取并缓存 Etherscan 上已验证合约的 ABI、源码和基本元数据，辅助离线分析，不涉及部署或链上写操作。已落地最小可运行骨架（配置、客户端、缓存、服务、CLI），默认使用 Etherscan API V2。

## Repo 列表与职责（与 docmap 对齐）
- etherscan-mcp：入口目录 `src/etherscan-mcp/`。模块包括 config（读取 env）、etherscan client（requests 封装）、cache（内存+可选文件）、service（聚合合约详情）、CLI 入口、MCP 入口。

## 本地开发最小路径（只到开发自测）
- 环境：Python 3.11（或兼容 3.10+）。
- 安装：（可选）创建虚拟环境 → `pip install -r src/etherscan-mcp/requirements.txt`。
- CLI：`ETHERSCAN_API_KEY=<key> [NETWORK=<network>|CHAIN_ID=<id>] [ETHERSCAN_BASE_URL=<url>] [CACHE_DIR=./.cache/etherscan] python -m app.cli fetch --address <contract>`，默认基址 `https://api.etherscan.io/v2/api`、默认 chainid=1（mainnet）；成功时输出含 `abi` 与 `source_files` 的 JSON；缺失/无效 key 时返回清晰错误。
- MCP（Codex 本地注册示例）：  
  1) 在项目根执行，添加服务器（替换你的 Python 解释器与 KEY）：  
     ```bash
     codex mcp add etherscan-mcp \\
       --env ETHERSCAN_API_KEY=<your-api-key> \\
       --env CACHE_DIR=./.cache/etherscan \\
       -- bash -lc "cd `pwd`/src/etherscan-mcp && python -m app.mcp_server --transport stdio"
     ```  
  2) 工具：  
     - `fetch_contract(address, network?)`：ABI/源码/编译器信息。  
     - `get_contract_creation(address, network?)`：创建者、创建交易哈希、块高（静态可缓存）。  
     - `detect_proxy(address, network?)`：读取 EIP-1967 implementation/admin 槽，返回实现/管理员与证据。  
     - `list_transactions(address, network?, start_block?, end_block?, page?, offset?, sort?)`：普通交易分页。  
     - `list_token_transfers(address, network?, token_type?, start_block?, end_block?, page?, offset?, sort?)`：ERC20/721/1155 转移分页。  
     - `query_logs(address, network?, topics?, from_block?, to_block?, page?, offset?)`：按 topics 过滤日志，`topics` 必须为数组（可用 `None` 占位跳过某 topic），`from_block`/`to_block` 支持十进制或 `0x` 十六进制块号输入。  
     - `get_storage_at(address, slot, network?, block_tag?)`：只读存储槽。  
- `call_function(address, data?, function?, args?, network?, block_tag?, decimals?)`：eth_call 只读函数；支持直接传 ABI 编码的 `data`，也支持提供 `function`+`args` 自动编码；有 ABI 时自动解码返回并提供 decoded（含函数信息、outputs，多返回值展开，数值支持可选 decimals 缩放的 value_scaled），原始返回保留在 data；无 ABI/解码失败时 decoded 标注 error 但调用不抛异常。  
     - `encode_function_data(function, args?)`：纯本地计算 4byte selector 与 ABI 编码 data，便于构造调用；`args` 必须为数组。  
     - 参数形态提醒：`call_function.args`、`encode_function_data.args`、`query_logs.topics` 必须是数组；传入字符串/对象会报错，标量会自动包成单元素数组。  
     无需手动常驻进程，Codex 按需启动。  
- MCP 自测/重载提示：代码或工具列表变更后需在 Codex 侧重新连接/重新添加 MCP才能加载最新工具；可用主网示例地址用于快速验证（如 USDT `0xdAC17F958D2ee523a2206206994597C13D831ec7`、USDC `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`）。

## 网络参数支持
- NETWORK 支持：`mainnet`/`ethereum`/`eth`（均指主网）、`sepolia`、`holesky`，或直接使用十进制 chain_id（字符串）/设置 `CHAIN_ID`。
- 当 network 未被识别时，错误提示会列出支持值，并建议直接提供 `CHAIN_ID`。
