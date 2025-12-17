# call_function 内置 ABI 解码与可读化返回 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：当前 call_function 只返回原始 hex，需要手工拆解 32 字节并自行按 ABI/decimals 转换，调研成本高，尤其 reward_data 这类多返回值调用。
- 目标：call_function 在有 ABI 时自动解码返回值，直接给出人类可读的结构（多返回值展开、数值十进制/可选 decimals 缩放、地址/bytes 规范化），同时保留原始 hex；保持无 ABI 时仍可调用。
- 非目标：不新增链上写操作、不改 CLI fetch 行为、不引入外部解码依赖。

## 1. 影响范围（必须）
- 影响的 repo（来自 docmap，可多项）：etherscan-mcp
- 影响的模块/目录/文件（按 repo 分组列出即可）：src/etherscan-mcp/app/service.py（call_function 解码/格式化逻辑），src/etherscan-mcp/app/mcp_server.py（工具描述/参数声明）
- 外部可见变化（如适用：API/CLI/配置/数据格式）：MCP 工具 call_function 返回结构新增 decoded（保留 data），支持可选 decimals hint，兼容旧参数。

## 2. 方案与改动点（必须）
说明：实现将按批次推进；每批次写入前先列出改动文件/影响并征求确认。

- repo: etherscan-mcp
  - 改动点：在 service.py 为 call_function 增加 ABI 感知解码与格式化；多返回值按 ABI 名称/索引展开为结构化对象；保留 data。新增可选 decimals hint（全局或按字段/索引）影响数值格式化。无 ABI 或解码失败时返回 data 并在 decoded 标注 error，不阻塞调用。保持 function+args 自动编码与代理 ABI 探测兼容。
  - 新增/修改的接口或数据结构：call_function 响应新增 decoded（含 ok/error、函数名/签名/来源、outputs 列表）；工具参数新增 decimals（选填，字符串/映射）。
  - 关键逻辑说明：复用缓存/即时获取的合约 ABI，若检测到代理则尝试实现 ABI；依据 function/selector 定位 outputs，并支持 tuple/数组/基础类型解码。数值类默认十进制整数，提供 decimals 时附带缩放后的字符串展示。解码失败时捕获并返回 error + raw。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤（命令/操作）：
  - 连接 MCP（重连 Codex 侧以加载新工具），调用 call_function 示例：reward_data(address)（0x50dc9aE51f78C593d4138263da7088a973b8184E, args=[0x808507121b80c02388fad14726482e061b8da827]），验证多返回值展开与数值可读化。
  - 典型单返回值：decimals()、symbol()、balanceOf(address)（含 decimals=6 hint），确认 decoded 数值/字符串正确且 data 保留。
  - 代理合约：任选代理地址，确保实现 ABI 可用时正常解码；实现 ABI 不可用时不报错且返回 data。
  - 异常/降级：无 ABI 或解码失败时，decoded 标注 error，调用不抛异常；function+args 自动编码仍可用。
- 关键用例清单：
  - reward_data(address) 多返回值结构化展开（token/distributor/period_finish/rate/last_update/integral）。
  - uint/uint+decimals hint、string、bool、address、bytes/bytesN、tuple/数组解码。
  - 代理 ABI 探测路径。
  - 无 ABI 或 selector 不匹配时的降级输出。
- 通过标准：
  - 有 ABI 时，call_function decoded 提供正确的多返回值、类型及可选 decimals 格式化；data 原样保留。
  - 无 ABI/解码失败不阻塞，返回 data 且 decoded 标注 error/unknown。
  - 旧参数/行为兼容（可仅传 data 或 function+args，仍可调用）。

交付摘要口径（固定）：实现完成后，必须输出交付摘要，包含：
- 实际改动清单（按 repo 列出关键文件/模块）
- 自测步骤与结果
- 对照本节“通过标准”的逐条结论
- 已知风险/未决事项（如有必须列出）

约束：用户验收通过前，不更新 SOT，不归档 WIP。

## 4. SOT 更新清单（必须）
用户验收通过后，要把“最终事实”沉淀到 SOT（至少文件级，V1 不要求精确到小节）：

- docs/sot/overview.md：补充 call_function 的解码能力、返回字段（decoded/raw）与 decimals hint 行为。
- docs/sot/architecture.md：补充 service.call_function 的解码流程、代理 ABI 复用、降级策略。
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
