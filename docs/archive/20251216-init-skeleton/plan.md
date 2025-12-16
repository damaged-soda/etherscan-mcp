# 项目骨架初始化 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：仓库暂无代码实现，需要最小可运行骨架来调用 Etherscan API。
- 目标：搭建 Python 项目基本结构（配置/客户端/缓存/服务/CLI），支持 `python -m app.cli fetch --address <contract>` 从 Etherscan 获取合约 ABI 与源码并输出。
- 非目标：复杂限流/重试策略、全面文件缓存策略、多网络深度适配、部署/CI 相关工作。

## 1. 影响范围（必须）
- 影响的 repo：etherscan-mcp
- 影响的模块/目录/文件（按 repo 分组）：
  - 新增 app 包：config.py、etherscan_client.py、cache.py、service.py、cli.py、__init__.py、__main__.py
  - 根目录：requirements.txt（requests 等依赖）
- 外部可见变化：新增 CLI 命令 `python -m app.cli fetch --address ... [--network ...]`；需要 `ETHERSCAN_API_KEY`，可选 `ETHERSCAN_BASE_URL`、`NETWORK`、`CACHE_DIR`。

## 2. 方案与改动点（必须）
- repo: etherscan-mcp
  - 改动点：建立项目结构；配置模块加载/校验环境变量；Etherscan 客户端封装 `contract.getsourcecode`（基础错误检查与简单限速/重试）；内存缓存（按 address+network，可选写入 CACHE_DIR）；服务层组合返回 `{address, network, abi, source_files, compiler, verified}`；CLI 解析参数并输出 JSON。
  - 新增/修改的接口或数据结构：配置对象；客户端方法 `fetch_contract_details(address)`；服务返回结构；CLI 子命令 `fetch`。
  - 关键逻辑说明：缓存命中直接返回；未命中调用 Etherscan，检查 status/message；将 SourceCode 作为单文件内容返回（若包含多文件标记则按简单拆分处理）；错误抛出可读提示。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤：
  - `pip install -r requirements.txt`
  - 设置 `ETHERSCAN_API_KEY=<key>`
  - `python -m app.cli fetch --address 0xdAC17F958D2ee523a2206206994597C13D831ec7`，期望输出含 abi 的 JSON。
  - 未设置 `ETHERSCAN_API_KEY` 运行命令，期望得到缺少配置的明确错误。
- 关键用例清单：有效地址成功；无效/格式错误地址给出友好错误；重复调用同地址命中缓存（可通过提示或日志表明）。
- 通过标准：成功用例退出码 0，输出含 `abi`（非空）与 `source_files`；错误用例返回非 0 并给出清晰提示。

## 4. SOT 更新清单（必须）
- docs/sot/overview.md：补充最小运行路径、依赖与 CLI 用法。
- docs/sot/architecture.md：补充配置/客户端/缓存/服务/CLI 的实际实现状态与数据流。
- 其他：无。

## 5. 完成后归档动作（固定）
实现完成并完成自测后：
1) 按第 4 节更新 SOT
2) 将整个目录从 docs/wip/YYYYMMDD-topic/ 移动到 docs/archive/YYYYMMDD-topic/
