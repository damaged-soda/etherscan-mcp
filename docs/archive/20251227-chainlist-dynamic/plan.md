# 动态链清单（chainlist）解析与链发现 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：当前仅支持少量静态 `NETWORK_CHAIN_ID_MAP`（mainnet/sepolia/holesky…），对 `arb`/`arbitrum` 这类常用链需要用户手动填 `CHAIN_ID`，且未知 `NETWORK` 会在启动阶段直接报错，不利于“先查后用”（CLI/MCP）。
- 目标：
  - 主路径统一走 Etherscan V2 `GET /v2/chainlist` 动态链清单来解析 `network -> chainid`（数字 chainid 永远可用）。
  - 保留轻量别名层（包含 `arb` 等常用简称）提升人/模型输入体验。
  - 新增 CLI：`list-chains`、`resolve-chain`；新增 MCP 工具：`list_chains`、`resolve_chain`。
  - 避免“未知 NETWORK 时默默回主网”的错配风险：当默认 `NETWORK` 无法解析且未提供 `CHAIN_ID` 覆盖时，应给出明确错误与自救路径。
- 非目标：
  - 不引入磁盘持久化缓存（仍为进程内 TTL）。
  - 不引入复杂的搜索/打分依赖（仅轻量规范化 + 简单模糊匹配）。
  - 不新增第三方依赖（继续使用 requests / mcp）。

## 1. 影响范围（必须）
- 影响的 repo（来自 docmap，可多项）：`etherscan-mcp`（`./src/etherscan-mcp`）
- 影响的模块/目录/文件（按 repo 分组列出即可）：
  - repo: `etherscan-mcp`
    - 新增：`src/etherscan-mcp/app/chains.py`
    - 修改：`src/etherscan-mcp/app/config.py`
    - 修改：`src/etherscan-mcp/app/etherscan_client.py`
    - 修改：`src/etherscan-mcp/app/service.py`
    - 修改：`src/etherscan-mcp/app/cli.py`
    - 修改：`src/etherscan-mcp/app/mcp_server.py`
    - 可选修改：`src/etherscan-mcp/app/__init__.py`
- 外部可见变化（如适用：API/CLI/配置/数据格式）：
  - 配置新增：`ETHERSCAN_CHAINLIST_URL`、`CHAINLIST_TTL_SECONDS`。
  - `NETWORK` 入参能力增强：支持数字 chainid、链名/近似链名、以及别名（如 `arb`）。
  - CLI 新增子命令：`python -m app list-chains`、`python -m app resolve-chain --network arb`（本项目入口为 `app`）。
  - MCP 新增工具：`list_chains`、`resolve_chain`。
  - `network` 返回字段可能从“用户输入”变为“规范标签”（例如 `arbitrum-one-mainnet`）；同时返回 `meta.chainname/matched_by` 以便理解与溯源。

## 2. 方案与改动点（必须）
说明：实现将按批次推进；每批次写入前需先列出本批次改动文件/影响并征求确认。

- repo: etherscan-mcp
  - 改动点：
    - 新增 `ChainRegistry`：基于 `/v2/chainlist` 拉取链清单，进程内缓存 + TTL，支持 `list_chains()` 与 `resolve(network)`。
    - config：
      - 新增 `chainlist_url`、`chainlist_ttl_seconds`；保留少量静态 `NETWORK_CHAIN_ID_MAP` 仅作兜底（chainlist 不可用时保证 mainnet/sepolia/holesky 仍可用）。
      - `load_config()` 不因未知 `NETWORK` 直接失败；但默认链若无法解析且未提供 `CHAIN_ID`，应在 service 初始化/首次解析时抛出明确错误，避免“默默回主网”。
    - etherscan_client：
      - 增加“请求任意 URL”的内部入口（复用 retry/限流检测逻辑），用于 chainlist 拉取（保持心智复杂度低：仍沿用现有 session/header；是否附带 apikey 参数保持简单一致）。
    - service：
      - 初始化 `ChainRegistry`，并在无 `CHAIN_ID` 覆盖时尝试将默认 `NETWORK` 动态解析为 chainid（支持 `NETWORK=arb` 直接开箱可用）。
      - 重写 `_resolve_network_and_chain()`：显式传 `network` 时按动态解析；`network=None` 时按默认（若有 `CHAIN_ID` 覆盖则优先使用覆盖）。
    - cli：
      - 新增 `list-chains`、`resolve-chain` 子命令，输出 JSON。
    - mcp_server：
      - 新增 `list_chains`、`resolve_chain` 工具，返回结构与 CLI 对齐。
    - 可选：`__init__.py` 增加 `chains` 导出。
  - 新增/修改的接口或数据结构：
    - 新增：`ChainInfo`、`ChainRegistry`。
    - 新增 CLI 子命令：`list-chains`、`resolve-chain`。
    - 新增 MCP 工具：`list_chains(include_degraded?)`、`resolve_chain(network)`.
  - 关键逻辑说明：
    - 解析优先级：数字 chainid > 精确命中（规范化后的 key）> 轻量模糊（startswith/contains）；歧义时抛错并给出候选，要求用户提供数字 chainid。
    - 轻量别名层：如 `arb`/`arb-sepolia` 映射到更可匹配的查询串（最终仍以 chainlist 返回为准）。
    - 安全兜底：当默认 `NETWORK` 无法解析且 `CHAIN_ID` 未提供时，必须报错提示“使用 list-chains/resolve-chain 或直接传 numeric chainid/设置 CHAIN_ID”，避免隐式落到 chainid=1。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤（命令/操作）：
  - `ETHERSCAN_API_KEY=... python -m app list-chains`
  - `ETHERSCAN_API_KEY=... python -m app resolve-chain --network arb`
  - `ETHERSCAN_API_KEY=... python -m app resolve-chain --network \"Arbitrum One Mainnet\"`
  - `ETHERSCAN_API_KEY=... python -m app resolve-chain --network 42161`
  - 任选一个 Arbitrum 合约地址：
    - `ETHERSCAN_API_KEY=... python -m app fetch --address 0x... --network arb`
    - `ETHERSCAN_API_KEY=... python -m app fetch --address 0x... --network 42161`
- 关键用例清单：
  - `network` 为数字 chainid：可直接解析并请求成功。
  - `NETWORK=arb` 且无 `CHAIN_ID`：启动/首次请求时可自动解析出 42161 并成功请求。
  - `NETWORK=<未知>` 且 chainlist 拉取失败/不可用、且无 `CHAIN_ID`：必须明确报错，不允许静默回主网。
  - MCP 工具 `list_chains/resolve_chain` 与 CLI 输出字段一致且可用。
- 通过标准：
  - 新增 CLI/MCP 工具可用，且 `arb` 能稳定解析到 Arbitrum One 的 chainid（以 chainlist 为准）。
  - 原有功能（fetch/get-source-file/get-block/get-block-time 等）在 mainnet/sepolia/holesky 不回归。
  - 对“未知 NETWORK 且无 CHAIN_ID”场景不再出现“实际请求主网但用户以为是其它链”的情况（有明确错误提示）。

交付摘要口径（固定）：实现完成后，必须输出交付摘要，包含：
- 实际改动清单（按 repo 列出关键文件/模块）
- 自测步骤与结果
- 对照本节“通过标准”的逐条结论
- 已知风险/未决事项（如有必须列出）

约束：用户验收通过前，不更新 SOT，不归档 WIP。

## 4. SOT 更新清单（必须）
用户验收通过后，要把“最终事实”沉淀到 SOT（至少文件级，V1 不要求精确到小节）：

- `docs/sot/overview.md`：更新“网络参数支持”与新增 CLI/MCP 工具列表；补充 chainlist 动态解析与新增 env。
- `docs/sot/architecture.md`：更新 config/service 的网络解析不变量与兜底策略（静态 map 降级为兜底；动态 chainlist 为主路径），以及新增 `chains` 模块边界。

## 5. 完成后归档动作（固定）
实现完成并完成基本自测后：
1) 输出交付摘要并请求用户验收
2) 用户验收通过后，按第 4 节更新 SOT
3) 更新第 6 节检查单（必须全勾）
4) 将整个目录从 `docs/wip/20251227-chainlist-dynamic/` 移动到 `docs/archive/20251227-chainlist-dynamic/`

## 6. WIP 检查单（必须全勾才能归档）
- [x] plan.md 已确认（PLAN 闸门已通过）
- [x] 代码改动已完成（IMPLEMENT 完成）
- [x] 基本自测已完成（记录命令/步骤与结果）
- [x] 已输出交付摘要并且用户验收通过（VERIFY 闸门已通过）
- [x] SOT 已更新（按第 4 节执行；列出更新的文件）
- [x] 已归档：wip → archive（目录已移动）
