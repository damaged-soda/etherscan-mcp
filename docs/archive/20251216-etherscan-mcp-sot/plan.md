# Etherscan MCP SOT 初始化 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：项目刚初始化，SOT 文档为空，docmap 仍指向 repo-a/repo-b 且 .gitignore 屏蔽了 src；需要定义单仓库、最小心智负担的 Etherscan MCP（用户提供 ETHERSCAN_API_KEY，可供 Codex 在本地获取合约信息），技术栈确定为 Python（conda 环境）。
- 目标：确定单仓库 `etherscan-mcp` 的 Python 架构与模块边界，更新 docmap 与 SOT（overview/architecture），放开 .gitignore 对 src 的屏蔽，为后续实现打好文档基线。
- 非目标：暂不编写或发布代码；不设计多仓/多环境部署、CI/CD、打包分发；不扩展到多链/复杂缓存策略。

## 1. 影响范围（必须）
- 影响的 repo（来自 docmap，可多项）：当前 docmap 占位 repo 将被替换为单仓库 `etherscan-mcp`（路径 `./src/etherscan-mcp`）。
- 影响的模块/目录/文件（按 repo 分组列出即可）：docmap.yaml；docs/sot/overview.md；docs/sot/architecture.md；.gitignore；（创建占位目录）src/etherscan-mcp/。
- 外部可见变化（如适用：API/CLI/配置/数据格式）：唯一必需配置 `ETHERSCAN_API_KEY`（环境变量）；规划的输出结构包含合约地址、网络、ABI、源码、编译信息；repo 列表改为单仓库；本地运行方式基于 conda + Python。

## 2. 方案与改动点（必须）
按 repo 分组写清楚“要改什么”，不写部署流程：

- repo: docs（docmap + SOT）
  - 改动点：将 docmap 更新为单仓库 `etherscan-mcp`（src/etherscan-mcp）；补全 SOT（overview/architecture）描述项目目标、Python 模块、配置与自测入口；说明最小可行架构（conda 环境）。
  - 新增/修改的接口或数据结构：docmap repo 配置；配置项 `ETHERSCAN_API_KEY`（必需，主网默认），可选缓存目录约定（如 `./.cache/etherscan`）、`ETHERSCAN_BASE_URL`、`NETWORK`，以及调用返回的合约信息结构（地址、网络、ABI、源码文件、编译器/验证状态）。
  - 关键逻辑说明：单进程 Python 架构：配置加载（env/默认值），Etherscan client（requests 封装 + 基础重试/节流），缓存层（内存 + 可选本地文件），服务层（聚合合约详情），入口层（CLI/MCP/简易 HTTP）供 Codex 调用。
- repo: etherscan-mcp（规划中的单仓）
  - 改动点：创建 src/etherscan-mcp/ 作为项目根；规划后续代码结构（config、client、cache、service、entry/cli/http、tests），后续实现时按 SOT 落地。
  - 新增/修改的接口或数据结构：规划合约信息返回结构 `{ address, network, abi, source_files, compiler, verified }` 与配置结构 `{ api_key, base_url?, cache_dir?, network }`。
  - 关键逻辑说明：启动时加载配置 → 初始化 Etherscan client（带简单重试与节流）→ 获取合约元信息/ABI/源码 → 写入缓存 → 入口层将数据提供给 Codex（MCP handler 或 CLI/HTTP）。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤（命令/操作）：文档完成后自查 docmap 与目录一致性；确认 SOT 填充完整；未来实现阶段的最小路径（预告）为 `conda create -n etherscan-mcp python=3.11` → `conda activate etherscan-mcp` → `pip install -r requirements.txt` → `ETHERSCAN_API_KEY=... python -m app.cli fetch --address <addr>` 验证能返回 ABI+源码。
- 关键用例清单：有有效 API Key 时能获取已验证合约的 ABI 与源码；无/错 API Key 时给出清晰错误；缓存命中减少重复请求；无效地址返回可读错误。
- 通过标准：docmap 指向单仓库且目录存在；SOT 反映项目目标/架构/配置；.gitignore 不再屏蔽 src；自测步骤可按文档执行（conda + CLI 流程）。

## 4. SOT 更新清单（必须）
实现完成后要把“最终事实”沉淀到 SOT（至少文件级，V1 不要求精确到小节）：

- docs/sot/overview.md：更新项目描述、单仓库列表、最小本地开发/自测路径、必需配置。
- docs/sot/architecture.md：更新模块边界（config/client/cache/service/entry）、关键约束（单进程、API Key 必需、基础重试/速率限制、简单缓存策略）、跨模块交互。
- docmap.yaml：更新为单仓库 `etherscan-mcp`（src/etherscan-mcp）。
- 其他：如无。

## 5. 完成后归档动作（固定）
实现完成并完成自测后：
1) 按第 4 节更新 SOT
2) 将整个目录从 docs/wip/YYYYMMDD-topic/ 移动到 docs/archive/YYYYMMDD-topic/
