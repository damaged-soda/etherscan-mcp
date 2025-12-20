# call_function 无参签名宽容支持 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：当前 `call_function`/`encode_function_data` 需要完整签名 `name(type1,...)`，无参函数漏写 `()` 会直接报错。
- 目标：当 `function` 仅提供函数名且无参数时，自动按 `name()` 处理，避免误报错。
- 非目标：不推断有参函数的参数类型；不接受有参函数缺失 `()` 的写法。

## 1. 影响范围（必须）
- 影响的 repo（来自 docmap，可多项）：etherscan-mcp
- 影响的模块/目录/文件（按 repo 分组列出即可）：
  - src/etherscan-mcp/app/service.py
- 外部可见变化（如适用：API/CLI/配置/数据格式）：`call_function`/`encode_function_data` 的 `function` 参数允许无参函数省略 `()`（`readTokens` 等价 `readTokens()`）。

## 2. 方案与改动点（必须）
说明：实现将按批次推进；每批次写入前需先列出本批次改动文件/影响并征求确认。

按 repo 分组写清楚“要改什么”，不写部署流程：

- repo: etherscan-mcp
  - 改动点：放宽 `_parse_function_signature`，当签名不含括号时按“零参数函数名”解析；保留对非法名称、空类型等校验。
  - 新增/修改的接口或数据结构：无
  - 关键逻辑说明：仅当未出现 `(` 时才走零参分支；原有 `name(...)` 解析逻辑保持不变；有参但缺 `()` 的情况仍通过参数个数不匹配报错。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤（命令/操作）：
  - 运行最小 Python 片段验证 `_parse_function_signature` 行为（示例：`readTokens`→零参；`readTokens()`→零参；`readTokens(address)` 正常解析；`readTokens(` 报错）。
- 关键用例清单：
  - `function: "readTokens"` + `args: []` 不报错，selector 与 `readTokens()` 一致。
  - `function: "balanceOf"` + `args: ["0x..."]` 仍报参数数量不匹配（提示需完整签名）。
- 通过标准：
  - 无参函数漏写 `()` 时不再报 “function must be in the form ...”。
  - 其他非法签名行为不被放宽（仍报错）。

交付摘要口径（固定）：实现完成后，必须输出交付摘要，包含：
- 实际改动清单（按 repo 列出关键文件/模块）
- 自测步骤与结果
- 对照本节“通过标准”的逐条结论
- 已知风险/未决事项（如有必须列出）

约束：用户验收通过前，不更新 SOT，不归档 WIP。

## 4. SOT 更新清单（必须）
用户验收通过后，要把“最终事实”沉淀到 SOT（至少文件级，V1 不要求精确到小节）：

- docs/sot/architecture.md：补充 `call_function` 对无参函数签名的容错说明。
- docs/sot/overview.md：无

## 5. 完成后归档动作（固定）
实现完成并完成基本自测后：
1) 输出交付摘要并请求用户验收
2) 用户验收通过后，按第 4 节更新 SOT
3) 更新第 6 节检查单（必须全勾）
4) 将整个目录从 docs/wip/20251220-call-function-autoparens/ 移动到 docs/archive/20251220-call-function-autoparens/

## 6. WIP 检查单（必须全勾才能归档）
- [x] plan.md 已确认（PLAN 闸门已通过）
- [x] 代码改动已完成（IMPLEMENT 完成）
- [x] 基本自测已完成（记录命令/步骤与结果）
- [x] 已输出交付摘要并且用户验收通过（VERIFY 闸门已通过）
- [x] SOT 已更新（按第 4 节执行；列出更新的文件）
- [x] 已归档：wip → archive（目录已移动）
