# call_function 在缺 selector 时放行 raw 调用 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：当前 `call_function` 若缓存/探测到的 ABI 中不存在请求的 selector，会直接拦截报错，哪怕用户已手写 calldata。遇到非标准代理或不完整 ABI 时（如只有 constructor/fallback），无法执行 raw eth_call。
- 目标：当 selector 不在 ABI 时，放行 raw eth_call（不解码或标注解码受限），并返回警告信息，而非直接拒绝。保持已有解码与校验逻辑在 ABI 命中时不变。
- 非目标：不实现高级代理检测/反编译；不改变已存在的成功解码路径；不修改 encode_function_data 行为。

## 1. 影响范围（必须）
- 影响的 repo：etherscan-mcp
- 影响的模块/目录/文件：app/service.py（call_function selector 校验逻辑）、app/mcp_server.py（如需描述提示）、docs/sot（工具行为说明）
- 外部可见变化：call_function 在 ABI 缺失 selector 时不再报错，返回原始 data，并附带警告/解码状态。

## 2. 方案与改动点（必须）
说明：实现将按批次推进；每批次写入前先列出改动文件/影响征求确认。

- repo: etherscan-mcp
  - 改动点：调整 service.call_function 中 selector 校验逻辑：当 ABI 已知但 selector 未命中时，允许继续 eth_call，返回原始 hex，decoded 标注 error/warning（如 “selector not found in ABI; returned raw”）；explain/warning 字段明确放行原因。
  - 新增/修改的接口或数据结构：call_function 响应中可能增加 warning/notes 字段（或在 decoded.error 中体现）；不改参数。
  - 关键逻辑说明：保持现有长度校验；仅将“selector 不在 ABI”从 hard fail 改为 soft warning + raw 调用；解码失败时 decoded.error 说明原因。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤：调用 call_function 传入 data 对应 ABI 缺失的 selector，验证不报错、返回 raw data 且 decoded.error 有提示；对已有 ABI selector 继续正常解码。
- 关键用例清单：
  - 无 ABI 情况：依旧放行 raw 调用。
  - 有 ABI 但 selector 缺失：执行 eth_call，返回 data，decoded.error/warning 提示 selector 未命中。
  - 正常有 ABI 且 selector 存在：仍能解码成功。
- 通过标准：上述用例均符合预期，错误/警告信息明确，不影响已有正常路径。

交付摘要口径（固定）：实现完成后，必须输出交付摘要，包含：
- 实际改动清单（按 repo 列出关键文件/模块）
- 自测步骤与结果
- 对照本节“通过标准”的逐条结论
- 已知风险/未决事项（如有必须列出）

约束：用户验收通过前，不更新 SOT，不归档 WIP。

## 4. SOT 更新清单（必须）
- docs/sot/overview.md：补充 call_function 在 ABI 缺 selector 时放行 raw eth_call、返回原始 hex + 警告/decoded.error 的行为。
- docs/sot/architecture.md：补充 selector 校验改为 soft fail，解码失败时的返回形态。
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
- [ ] SOT 已更新（按第 4 节执行；列出更新的文件）
- [ ] 已归档：wip → archive（目录已移动）
