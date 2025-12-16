# call_function 错误透出修复 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：MCP 工具 `call_function` 调用 Etherscan `eth_call` 时，如果链上返回 JSON-RPC 错误（如 execution reverted），当前解析逻辑忽略了 `error` 字段，最后抛出 “Etherscan error: unknown error.”，导致真实原因被吃掉。
- 目标：正确解析并透出 Etherscan JSON-RPC 返回的 `error.message`（及可用的 data 详情），让调用方能看到具体报错。
- 非目标：不改动其它工具的业务逻辑或新增缓存/重试策略，不引入新依赖。

## 1. 影响范围（必须）
- 影响的 repo（来自 docmap，可多项）：etherscan-mcp
- 影响的模块/目录/文件（按 repo 分组列出即可）：app/service.py（错误解析）、必要时 app/etherscan_client.py（若需补充错误信息传递）
- 外部可见变化（如适用：API/CLI/配置/数据格式）：MCP 工具 `call_function`（及复用相同解析的 get_storage_at）在错误时的返回信息将包含更具体的 Etherscan JSON-RPC 错误文本。

## 2. 方案与改动点（必须）
说明：实现将按批次推进；每批次写入前需先列出本批次改动文件/影响并征求确认。

- repo: etherscan-mcp
  - 改动点：完善 `_extract_proxy_result` 的错误解析逻辑，检测并优先使用 payload 中的 `error.message` / `error.data` 信息；在缺省字段时保留现有兜底。
  - 新增/修改的接口或数据结构：无新增接口；`call_function`/`get_storage_at` 的错误文本更具体。
  - 关键逻辑说明：在处理 `proxy` 类接口返回时，若存在 JSON-RPC `error` 对象（含 message/data），将其拼装进 ValueError 文案，避免返回 “unknown error”。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤（命令/操作）：
  1) 设置有效 `ETHERSCAN_API_KEY`，运行 MCP 服务器或直接运行 Python 片段调用 `ContractService.call_function`，对一个会 revert 的输入（或非法 data）触发 Etherscan 返回 JSON-RPC error。
  2) 观察抛出的异常消息，确认包含 Etherscan 的 `error.message`（例如 `execution reverted`），而非 “unknown error”。
- 关键用例清单：
  - `call_function` 调用返回 JSON-RPC error 时，错误信息包含远端 `error.message`；无 `error` 时仍按原逻辑处理。
  - `get_storage_at` 同路径返回 JSON-RPC error 时也能透出具体信息。
- 通过标准：
  - 以上自测用例均符合预期，未出现 “unknown error” 且未引入新的异常类型。

交付摘要口径（固定）：实现完成后，必须输出交付摘要，包含：
- 实际改动清单（按 repo 列出关键文件/模块）
- 自测步骤与结果
- 对照本节“通过标准”的逐条结论
- 已知风险/未决事项（如有必须列出）

约束：用户验收通过前，不更新 SOT，不归档 WIP。

## 4. SOT 更新清单（必须）
用户验收通过后，要把“最终事实”沉淀到 SOT（至少文件级，V1 不要求精确到小节）：

- docs/sot/overview.md：无更新（功能范围未变）。
- docs/sot/architecture.md：已补充 proxy/eth_call/eth_getStorageAt 错误透出行为。
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
