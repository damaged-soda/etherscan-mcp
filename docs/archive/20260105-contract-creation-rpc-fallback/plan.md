# get_contract_creation Etherscan 优先 + RPC 兜底 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：Etherscan V2 `module=contract&action=getcontractcreation` 在部分链（例如 BSC，chainid=56）返回 `NOTOK`，导致 MCP 工具 `get_contract_creation` 无法使用。
- 目标：`get_contract_creation` 默认优先走 Etherscan `getcontractcreation`（快且信息更全）；当 Etherscan 返回错误（例如 `NOTOK`）且配置了 `RPC_URL_<chainid>`（或在未显式传 `network` 时配置 `RPC_URL`）时，再回退走 JSON-RPC best-effort 推导创建信息；RPC 无法完整定位时返回可用的部分字段并明确标记完整性。
- 非目标：不引入 trace/indexer；不保证能解析“合约内部 CREATE/CREATE2（非顶层创建交易）”的 creator/tx_hash；不新增 BscScan 等“独立 key+base url”的配置体系。

## 1. 影响范围（必须）
- 影响的 repo（来自 docmap，可多项）：`etherscan-mcp`（`./src/etherscan-mcp`）
- 影响的模块/目录/文件（按 repo 分组列出即可）：
  - repo: etherscan-mcp
    - `src/etherscan-mcp/app/service.py`
- 外部可见变化（如适用：API/CLI/配置/数据格式）：
  - `get_contract_creation(address, network?)`：默认优先走 Etherscan；当 Etherscan 失败且该 `chainid` 配置了 RPC 时，回退走 RPC 推导。
  - 返回 JSON 将新增可选字段：`source`（`rpc|etherscan`）、`complete`（`true|false`，表示是否成功定位到 `tx_hash/creator`）。

## 2. 方案与改动点（必须）
说明：实现将按批次推进；每批次写入前需先列出本批次改动文件/影响并征求确认。

- repo: etherscan-mcp
  - 改动点：
    - `ContractService.get_contract_creation()`：增加“Etherscan 优先，失败再 RPC”的回退路径；两者都失败时抛出可读错误。
      - Etherscan 路径：现有 `getcontractcreation`（预期更快、信息更完整）
      - RPC 回退路径：仅在 Etherscan 报错且存在 RPC client 时尝试（best-effort）
    - RPC 推导逻辑（best-effort，标准 JSON-RPC，无 trace）：
      1) `eth_getCode(address, latest)`：确认当前为合约地址
      2) 二分：用 `eth_getCode(address, block)` 找到“首次出现非空 code”的区块号（部署区块）
      3) `eth_getBlockByNumber(block, true)` 拉取该块交易列表；仅对 `to == null`（合约创建交易）的 tx 拉 `eth_getTransactionReceipt`，以 `receipt.contractAddress` 匹配目标地址，得到 `tx_hash` 与 `creator=tx.from`
      4) `timestamp` 取该块的 `timestamp`
    - 对 internal create 场景：若无法定位 `tx_hash/creator`，仍返回 `block_number/timestamp` 并设置 `complete=false`（`creator/tx_hash` 为空字符串）。
    - 错误提示增强：当 Etherscan 返回 `NOTOK` 时：
      - 若存在 RPC：提示“已回退 RPC 推导”（若仍失败则提示检查 `RPC_URL_<chainid>`）
      - 若不存在 RPC：提示“该链可能不支持 getcontractcreation；可配置 RPC_URL_<chainid> 走 RPC 推导”
  - 新增/修改的接口或数据结构：
    - 仅在 `get_contract_creation` 返回中新增可选字段（不删除/重命名现有字段）。
  - 关键逻辑说明：
    - 复用现有 RPC 路由策略：优先 `RPC_URL_<chainid>`，仅在 `network=None` 时允许用默认 `RPC_URL`。
    - `complete=false` 并不表示失败，仅表示无法在无 trace 条件下定位创建交易与创建者。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤（命令/操作）：
  - 进入 repo：`cd src/etherscan-mcp`
  - mainnet（不配 RPC，走 Etherscan）：`ETHERSCAN_API_KEY=<key> python -c "from app.config import load_config; from app.service import ContractService; s=ContractService(load_config()); print(s.get_contract_creation('0xdAC17F958D2ee523a2206206994597C13D831ec7','mainnet'))"`
  - BSC（配 RPC，先 Etherscan，失败回退 RPC）：`ETHERSCAN_API_KEY=<key> RPC_URL_56=<bsc-rpc> python -c "from app.config import load_config; from app.service import ContractService; s=ContractService(load_config()); print(s.get_contract_creation('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c','56'))"`
- 关键用例清单：
  - BSC：原本 `NOTOK` 的地址（如 WBNB）在配置 `RPC_URL_56` 后可返回 `block_number` 且 `complete=true`（若为顶层创建）
  - mainnet：不配置 RPC 时行为不变
  - internal create：可返回 `block_number/timestamp`，并明确 `complete=false`
- 通过标准：
  - Etherscan 可用时：`get_contract_creation` 仍走 Etherscan（`source=etherscan`）
  - Etherscan 不可用且配置 RPC 时：`get_contract_creation` 回退 RPC 仍可返回结果（`source=rpc`）
  - 不配置 RPC 时，主网用例保持可用且输出字段不回归

交付摘要口径（固定）：实现完成后，必须输出交付摘要，包含：
- 实际改动清单（按 repo 列出关键文件/模块）
- 自测步骤与结果
- 对照本节“通过标准”的逐条结论
- 已知风险/未决事项（如有必须列出）

约束：用户验收通过前，不更新 SOT，不归档 WIP。

## 4. SOT 更新清单（必须）
用户验收通过后，要把“最终事实”沉淀到 SOT（至少文件级，V1 不要求精确到小节）：

- `docs/sot/overview.md`：补充 `get_contract_creation` 的 Etherscan 优先 + RPC fallback 策略与 `RPC_URL_<chainid>` 配置建议（尤其是 BSC）。
- `docs/sot/architecture.md`：补充 `get_contract_creation` 的 RPC 推导流程与 internal create 的限制（`complete=false` 语义）。

## 5. 完成后归档动作（固定）
实现完成并完成基本自测后：
1) 输出交付摘要并请求用户验收
2) 用户验收通过后，按第 4 节更新 SOT
3) 更新第 6 节检查单（必须全勾）
4) 将整个目录从 `docs/wip/YYYYMMDD-topic/` 移动到 `docs/archive/YYYYMMDD-topic/`

## 6. WIP 检查单（必须全勾才能归档）
- [x] plan.md 已确认（PLAN 闸门已通过）
- [x] 代码改动已完成（IMPLEMENT 完成）
- [x] 基本自测已完成（记录命令/步骤与结果）
- [x] 已输出交付摘要并且用户验收通过（VERIFY 闸门已通过）
- [x] SOT 已更新（按第 4 节执行；列出更新的文件：docs/sot/overview.md、docs/sot/architecture.md）
- [x] 已归档：wip → archive（目录已移动）
