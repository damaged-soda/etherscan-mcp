# 项目概览（SOT）

Last Updated: 2025-12-16

## 项目是什么
Etherscan MCP：单仓 Python 项目。用户提供 `ETHERSCAN_API_KEY`，通过 CLI 拉取并缓存 Etherscan 上已验证合约的 ABI、源码和基本元数据，辅助离线分析，不涉及部署或链上写操作。已落地最小可运行骨架（配置、客户端、缓存、服务、CLI），默认使用 Etherscan API V2。

## Repo 列表与职责（与 docmap 对齐）
- etherscan-mcp：入口目录 `src/etherscan-mcp/`。模块包括 config（读取 env）、etherscan client（requests 封装）、cache（内存+可选文件）、service（聚合合约详情）、CLI 入口、MCP 入口。

## 本地开发最小路径（只到开发自测）
- 环境：Python 3.11（或兼容 3.10+）。
- 安装：`cd src/etherscan-mcp` → （可选）创建虚拟环境 → `pip install -r requirements.txt`。
- CLI：`ETHERSCAN_API_KEY=<key> [NETWORK=<network>|CHAIN_ID=<id>] [ETHERSCAN_BASE_URL=<url>] [CACHE_DIR=./.cache/etherscan] python -m app.cli fetch --address <contract>`，默认基址 `https://api.etherscan.io/v2/api`、默认 chainid=1（mainnet）；成功时输出含 `abi` 与 `source_files` 的 JSON；缺失/无效 key 时返回清晰错误。
- MCP（Codex 本地注册示例，需 codex CLI 开启 rmcp_client）：  
  1) 启用实验特性：`codex --enable rmcp_client`  
  2) 添加服务器（使用 conda 环境 python，按需替换 KEY）：  
     ```bash
     codex mcp add etherscan-mcp \\
       --env ETHERSCAN_API_KEY=<your-api-key> \\
       --env CACHE_DIR=./.cache/etherscan \\
       --cwd /Users/liyifan/Work/etherscan-mcp/src/etherscan-mcp \\
       -- /opt/homebrew/Caskroom/miniconda/base/envs/etherscan-mcp/bin/python -m app.mcp_server --transport stdio
     ```  
  3) 工具：`fetch_contract(address, network?)` 返回与 CLI 一致的结构。无需手动常驻进程，Codex 按需启动。
