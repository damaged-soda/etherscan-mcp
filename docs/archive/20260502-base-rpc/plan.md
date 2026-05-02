# Base 链 RPC fallback 对齐 BSC 方案 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：用户在 Base（chainid 8453）做链上调研时遇到 Etherscan V2 free tier 限权：`resolve_chain("base")` 能解析到 8453，但 `get_transaction` 报 `Free API access is not supported for this chain`；`list_transactions` 对部分 Base 地址直接返回空。最后用户只能跳出 MCP，用 Base 公共 RPC 自己拿 receipt。`RPC_URL_<chainid>` fallback 当前在 BSC 上已经跑通（见 `docs/archive/20260105-rpc-readchain/`），但 Base 没有 alias、文档示例也没提，用户体感是「同一类问题但 Base 没解」。
- 目标：把 Base 的体感对齐 BSC，**不改机制、不写新代码路径**，只补 alias + 文档：
  - `chains.py` alias 表加 `"base": "8453"`，让 CLI/MCP 可以直接传 `network="base"`。
  - README + SOT 显式列出「Base 推荐配置 `RPC_URL_8453`」，跟 BSC 一并示例。
  - 用户在 MCP 服务端配上 `RPC_URL_8453=<base RPC>` 后，B 类读链工具（`get_transaction` / `query_logs` / `get_block_by_number` / `call_function` / `get_storage_at` / `detect_proxy`）就会自动走 RPC，绕开 Etherscan free tier 限权 —— 这部分零代码改动，复用现有路由。
- 非目标：
  - 不引入 BaseScan native API key 方案。
  - 不内置默认公共 RPC（保持「RPC 选择权完全在用户手里」的现状，避免隐性依赖和不稳节点把锅扣给 MCP）。
  - 不解决 `list_transactions` / `list_token_transfers` 在 Base 上返回空 —— 这俩对应 Etherscan 的 `txlist`/`tokentx` indexed 端点，原生 RPC 没等价能力，BSC 方案当时就明确剥出去了；后续如有需要再单独立项（可能走 BaseScan key 或第三方索引）。本次只在 STATUS 挂 deferred。
  - 不改 MCP / CLI 的对外接口签名。

## 1. 影响范围（必须）
- 影响的 repo（来自 docmap）：etherscan-mcp（`./src/etherscan-mcp`）
- 影响的模块/目录/文件：
  - repo: etherscan-mcp
    - `src/etherscan-mcp/app/chains.py`：alias 表新增 `"base": "8453"`
    - `README.md`：环境变量章节补充 `RPC_URL_8453` 示例，注明 Base 与 BSC 同一限权情况
    - `docs/sot/overview.md`：环境变量小节补充 Base 推荐配置；提示部分能力在 free tier 受限
    - `docs/sot/architecture.md`：不动（机制无变化）
- 外部可见变化：
  - `network="base"` 现在可解析到 chainid 8453（之前只能传数字 8453）
  - 文档显式建议 Base 用户配 `RPC_URL_8453`；不配时行为不变（继续走 Etherscan proxy，可能受 free tier 限）

## 2. 方案与改动点（必须）
说明：实现按一批写入；写入前列出变更清单征求确认。

- repo: etherscan-mcp
  - 改动点：
    1) `src/etherscan-mcp/app/chains.py` 的 `_alias` dict 加一行：`"base": "8453"`。位置紧挨 `"bsc": "56"`，保持「常用主网别名」分组。
    2) `README.md` 第 28-44 行附近的环境变量与示例：
       - 把现有 `--env RPC_URL_56=...`（BSC 示例）扩展为同时展示 `RPC_URL_56` 和 `RPC_URL_8453`，或者在示例下加一行说明「Base/Arbitrum 等同样受 free tier 限的链可如此配置」。
       - 在第 44 行那段「读链能力…未配置时保持原行为…在 BSC 等链的 Free tier 下可能受限」里把「BSC 等链」更明确为「BSC、Base 等链」。
    3) `docs/sot/overview.md`：
       - 第 26 行示例补 `RPC_URL_8453=<base-rpc>`（或在示例下说明 Base 可同样配置）。
       - 第 58 行环境变量描述把 BSC 例子扩成「BSC、Base 等链推荐配置以避免 Etherscan free tier 链覆盖限制」。
    4) `docs/sot/architecture.md`：不改（chains/rpc/service 三层职责无变化，仅 alias 多一条不构成架构变更）。
  - 新增/修改的接口或数据结构：无。alias 只是查表数据。
  - 关键逻辑说明：
    - alias 走 `ChainRegistry.resolve()` 现有路径，对静态 alias 命中直接拿 chainid，跟 `bsc → 56` 完全同构。
    - 读链路由 `_get_rpc_client(chain_id, allow_default_rpc)` 现有逻辑：configured `RPC_URL_8453` 后自动生效，不需要任何代码 patch。
    - `get_contract_creation` 在 Etherscan 返回 `NOTOK` 时也会自动走 RPC fallback（已有逻辑），同样 free。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤：
  1) alias 解析（无需配 RPC）：
     ```
     cd ~/work/etherscan-mcp/src/etherscan-mcp
     python -c "
     from app.config import load_config
     from app.service import ContractService
     s = ContractService(load_config())
     label, cid, meta = s.chains.resolve('base')
     print(label, cid, meta['matched_by'])
     "
     ```
     期望：`base 8453 exact`（或 `... matched_by` 为 exact / fuzzy 任一，关键 chainid=8453）。
  2) 配上 `RPC_URL_8453=https://mainnet.base.org`（或用户自有节点），跑 `get_transaction`：
     ```
     RPC_URL_8453=https://mainnet.base.org python -c "
     from app.config import load_config
     from app.service import ContractService
     s = ContractService(load_config())
     # 任意一笔近期 Base 交易 hash
     r = s.get_transaction('<base_tx_hash>', network='base')
     print(r['transaction']['from'], r['receipt']['status'])
     "
     ```
     期望：返回 from / status，**不再出现** `Free API access is not supported for this chain`。
  3) 配上 RPC 后跑 `get_block_by_number`：
     ```
     RPC_URL_8453=... python -c "
     from app.config import load_config
     from app.service import ContractService
     s = ContractService(load_config())
     print(s.get_block_time_by_number('latest', network='base'))
     "
     ```
     期望：返回 block 高度 + timestamp。
  4) 不配 RPC 时 `fetch_contract`（A 类，走 Etherscan）仍可用：
     ```
     python -c "
     from app.config import load_config
     from app.service import ContractService
     s = ContractService(load_config())
     # 任一 Base 已验证合约
     print(s.fetch_contract('<base_verified_addr>', network='base')['contract_name'])
     "
     ```
     期望：正常返回 ABI/源码（Etherscan V2 的 ABI/源码端点对 Base 不受 free tier 限）。
- 关键用例清单：
  - alias：`network='base'` 可解析到 8453
  - 读链：配 `RPC_URL_8453` 后 `get_transaction` / `get_block_by_number` 走 RPC，不再撞 free tier 报错
  - ABI/源码：Base 上 `fetch_contract` 仍走 Etherscan V2 正常返回
  - 回归：不配 `RPC_URL_8453` 时行为不变（继续走 Etherscan proxy，可能报 free tier，跟改前一致）
- 通过标准：
  - alias `base` 解析到 chainid `8453`
  - 配 `RPC_URL_8453` 后 B 类工具不再依赖 Etherscan proxy
  - A 类工具行为不回退
  - 文档（README + SOT）显式列出 Base 推荐配置，不再让用户摸索

交付摘要口径（固定）：实现完成后，必须输出交付摘要，包含：
- 实际改动清单（按 repo 列出关键文件/模块）
- 自测步骤与结果
- 对照本节"通过标准"的逐条结论
- 已知风险/未决事项（如有必须列出）

约束：用户验收通过前，不更新 SOT，不归档 WIP。

## 4. SOT 更新清单（必须）
用户验收通过后，把最终事实沉淀到 SOT：

- `docs/sot/overview.md`：环境变量与示例小节加 `RPC_URL_8453` 推荐配置；把 BSC 例子扩为「BSC、Base 等」
- `docs/sot/architecture.md`：不更新（机制无变化）
- 其他：home-ops 仓 `STATUS.md` 挂个 deferred 项 —— 「Base 上 list_transactions/list_token_transfers 因 Etherscan free tier 索引限制返回空，RPC 无等价能力，待后续单独立项」。这一项不属于 etherscan-mcp 的 SOT，但属于跨工具的接力棒事实，需要在 home-ops 中控仓登记。

## 5. 完成后归档动作（固定）
实现完成并完成基本自测后：
1) 输出交付摘要并请求用户验收
2) 用户验收通过后，按第 4 节更新 SOT
3) 更新第 6 节检查单（必须全勾）
4) 将整个目录从 `docs/wip/20260502-base-rpc/` 移动到 `docs/archive/20260502-base-rpc/`

## 6. WIP 检查单（必须全勾才能归档）
- [x] plan.md 已确认（PLAN 闸门已通过）
- [x] 代码改动已完成（IMPLEMENT 完成）
- [x] 基本自测已完成（记录命令/步骤与结果）
- [x] 已输出交付摘要并且用户验收通过（VERIFY 闸门已通过）
- [x] SOT 已更新（按第 4 节执行；列出更新的文件）
- [x] 已归档：wip → archive（目录已移动）
