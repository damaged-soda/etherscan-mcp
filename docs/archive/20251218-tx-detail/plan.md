# 单笔交易详情获取工具 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：现有 MCP 提供交易列表，但缺少按 tx hash 获取单笔交易详情的工具，用户需要重复遍历列表或外部查询。
- 目标：新增 MCP 工具获取单个交易详情（通过 tx hash），返回标准字段（from/to/value/gas/nonce/status 等），支持可选 network；错误时给出可读提示。
- 非目标：不实现内置交易回执解析为事件（保持原生 receipt 数据结构）；不做链上重放/模拟。

## 1. 影响范围（必须）
- 影响的 repo：etherscan-mcp
- 影响的模块/目录/文件：app/etherscan_client.py（新增接口）、app/service.py（业务封装）、app/mcp_server.py（工具注册）、docs/sot（工具说明）
- 外部可见变化：新增 MCP 工具（名称暂定 `get_transaction` 或类似），输入 tx hash、network；返回交易 detail JSON。

## 2. 方案与改动点（必须）
说明：实现将按批次推进；每批次写入前先列出改动文件/影响征求确认。

- repo: etherscan-mcp
  - 改动点：EtherscanClient 增加获取单笔交易细节（tx hash）；service 包装并规范字段（含 receipt/status）；mcp_server 注册新工具。
  - 新增/修改的接口或数据结构：新增 MCP 工具 `get_transaction(tx_hash, network?)`（命名待确认）；返回 JSON 包含交易字段和回执关键字段。
  - 关键逻辑说明：输入 tx hash 0x 校验；调用 Etherscan 对应模块/动作获取交易和回执（若可），合并输出；错误时 ValueError 友好提示。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤：调用新工具获取一笔主网已知 tx，核对字段；测试错误输入（非法 hash）。
- 关键用例清单：
  - 有效 tx hash 返回 from/to/value/nonce/gas/gasPrice/input/blockNumber/status 等字段。
  - 非法 tx hash 报错提示“需 0x + 64 hex”。
  - 指定 network（如 sepolia）正常工作或给出缺失提示。
- 通过标准：上述用例结果正确；错误信息明确；返回字段齐全且 JSON 结构稳定。

交付摘要口径（固定）：实现完成后，必须输出交付摘要，包含：
- 实际改动清单（按 repo 列出关键文件/模块）
- 自测步骤与结果
- 对照本节“通过标准”的逐条结论
- 已知风险/未决事项（如有必须列出）

约束：用户验收通过前，不更新 SOT，不归档 WIP。

## 4. SOT 更新清单（必须）
- docs/sot/overview.md：新增工具说明（名称、参数、返回内容）。
- docs/sot/architecture.md：补充调用链（client/service/mcp_server）、字段规范、错误处理。
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
