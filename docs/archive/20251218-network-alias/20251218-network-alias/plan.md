# MCP 网络参数提示与别名支持澄清 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：调用 MCP 时传入 `network="eth"` 会报错 “Unknown network 'eth'. Provide CHAIN_ID explicitly.”，当前错误信息未列出支持的网络名称或别名，易用性差。
- 目标：明确并提示支持的网络名称/别名（如 ethereum/mainnet/holesky/sepolia/chain_id），必要时放宽常见别名（如 eth），让错误提示可直接指导改正。
- 非目标：不新增新的链支持，仅改提示/别名映射。

## 1. 影响范围（必须）
- 影响的 repo（来自 docmap，可多项）：etherscan-mcp
- 影响的模块/目录/文件（按 repo 分组列出即可）：app/service.py（network 解析/错误提示），app/mcp_server.py/文档（如需同步说明）
- 外部可见变化（如适用：API/CLI/配置/数据格式）：MCP 工具 `network` 参数的错误提示更友好，可能新增常见别名（如 `eth`→mainnet）。

## 2. 方案与改动点（必须）
说明：实现将按批次推进；每批次写入前需先列出本批次改动文件/影响并征求确认。

- repo: etherscan-mcp
  - 改动点：梳理现有 network/chainid 解析逻辑，补充错误信息列出允许值；视权衡加入 `eth` 作为 mainnet 别名或在提示中明确推荐值。
  - 新增/修改的接口或数据结构：无新增接口；可能增加 network 别名映射或错误提示结构。
  - 关键逻辑说明：保持现有默认 chainid/mainnet 行为不变，仅增强校验与提示/别名。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤（命令/操作）：运行内置解析/调用代码或 MCP 工具，以 `network="eth"`、错误值、合法值等验证提示/别名行为。
- 关键用例清单：
  - 传入 `network="eth"` 得到更友好的提示（列出允许值）或被识别为 mainnet（视方案）。
  - 传入未知网络值时提示允许值列表。
  - 合法值（如 mainnet/ethereum/holesky/sepolia 或明确 chainid）正常工作。
- 通过标准：提示明确且可操作；合法值不回归；如支持别名则调用正常。

交付摘要口径（固定）：实现完成后，必须输出交付摘要，包含：
- 实际改动清单（按 repo 列出关键文件/模块）
- 自测步骤与结果
- 对照本节“通过标准”的逐条结论
- 已知风险/未决事项（如有必须列出）

约束：用户验收通过前，不更新 SOT，不归档 WIP。

## 4. SOT 更新清单（必须）
用户验收通过后，要把“最终事实”沉淀到 SOT（至少文件级，V1 不要求精确到小节）：

- docs/sot/overview.md：补充 network 参数支持的名称/别名及错误提示。
- docs/sot/architecture.md：描述 network 解析/别名映射与错误提示行为。
- 其他：无

## 5. 完成后归档动作（固定）
实现完成并完成基本自测后：
1) 输出交付摘要并请求用户验收
2) 用户验收通过后，按第 4 节更新 SOT
3) 更新第 6 节检查单（必须全勾）
4) 将整个目录从 docs/wip/YYYYMMDD-topic/ 移动到 docs/archive/YYYYMMDD-topic/

## 6. WIP 检查单（必须全勾才能归档）
- [x] plan.md 已确认（PLAN 闸门已通过）
- [x] 代码改动已完成（IMPLEMENT 完成）
- [x] 基本自测已完成（记录命令/步骤与结果）
- [x] 已输出交付摘要并且用户验收通过（VERIFY 闸门已通过）
- [x] SOT 已更新（按第 4 节执行；列出更新的文件）
- [x] 已归档：wip → archive（目录已移动）
