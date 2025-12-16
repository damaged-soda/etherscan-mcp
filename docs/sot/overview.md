# 项目概览（SOT）

Last Updated: 2025-12-16

## 项目是什么
Etherscan MCP：单仓 Python 项目，用户提供 `ETHERSCAN_API_KEY`，本地通过 Codex 获取并缓存 Etherscan 上已验证合约的 ABI、源码和基本元数据，辅助离线分析，不涉及部署或链上写操作。

## Repo 列表与职责（与 docmap 对齐）
- etherscan-mcp：单仓实现，入口：src/etherscan-mcp/。模块包括 config（读取 env）、etherscan client（requests 封装）、cache（内存+可选文件）、service（聚合合约详情）、entry（MCP/CLI/简易 HTTP 入口）、tests/fixtures。

## 本地开发最小路径（只到开发自测）
- 当前代码未实现，需按架构落地模块。
- 预期最小路径（实现后）：`conda create -n etherscan-mcp python=3.11` → `conda activate etherscan-mcp` → `pip install -r requirements.txt` → `ETHERSCAN_API_KEY=<key> python -m app.cli fetch --address <contract>`，应返回 ABI 与源码；缺失/无效 key 时给出清晰错误。
