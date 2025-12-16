# Etherscan MCP Handler 增加 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：当前仅有 CLI，未提供 Model Context Protocol (MCP) 接口，无法直接被 Codex 通过 MCP 调用。
- 目标：基于 python-mcp 增加 MCP server/handler，复用现有 service 提供合约 ABI/源码查询能力。
- 非目标：不做复杂鉴权、多租户、持久化；不实现 HTTP 网关或前端。

## 1. 影响范围（必须）
- 影响的 repo：etherscan-mcp
- 影响的模块/目录/文件（按 repo 分组）：
  - app/mcp_server.py（或同级命名）：MCP 端点实现
  - app/config.py / app/service.py：必要的小改以便被 MCP 复用
  - requirements.txt：新增 python-mcp 依赖
  - 可选：__main__.py 或入口脚本，便于启动 MCP
- 外部可见变化：新增 MCP 端点（action/command）供 Codex 调用，例如 `fetch_contract`.

## 2. 方案与改动点（必须）
- repo: etherscan-mcp
  - 改动点：引入 python-mcp；实现 MCP server/handler，暴露 `fetch_contract(address, network?)`；启动命令行入口 `python -m app.mcp_server`.
  - 新增/修改的接口或数据结构：MCP 请求/响应 schema（如返回 {address, chain_id, network, abi, source_files, compiler, verified}）；配置加载沿用现有 env。
  - 关键逻辑说明：在 MCP handler 中复用 ContractService；处理错误并返回 MCP 标准错误；可选简单日志。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤：
  - `pip install -r requirements.txt`
  - 启动：`ETHERSCAN_API_KEY=<key> python -m app.mcp_server`
  - 使用 python-mcp 提供的测试/示例客户端或简单脚本调用 `fetch_contract`，验证返回 ABI 与源码。
- 关键用例清单：有效地址成功；无效地址报错；缺少 key 报错；重复调用命中缓存。
- 通过标准：MCP 调用成功返回与 CLI 一致的结构；错误用例返回合理的 MCP 错误；进程可启动/退出正常。

## 4. SOT 更新清单（必须）
- docs/sot/overview.md：补充 MCP 入口与使用方式。
- docs/sot/architecture.md：补充 MCP 模块、入口命令、依赖 python-mcp。
- 其他：无。

## 5. 完成后归档动作（固定）
1) 按第 4 节更新 SOT
2) 将整个目录从 docs/wip/YYYYMMDD-topic/ 移动到 docs/archive/YYYYMMDD-topic/
