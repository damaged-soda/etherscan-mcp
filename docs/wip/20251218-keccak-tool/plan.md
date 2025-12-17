# MCP keccak 工具暴露 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：当前 MCP 仅在内部用于 selector 编码时计算 keccak，未对外提供通用的 keccak-256 工具。用户希望直接通过 MCP 暴露 `keccak(text|string|bytes) -> hex` 以便快速计算 selector/哈希。
- 目标：在 MCP 侧新增一个 `keccak` 实用工具，支持输入字符串或字节（文本默认按 UTF-8 编码），输出十六进制哈希；保持现有功能不受影响。
- 非目标：不更换哈希实现、不改动现有 call_function/encode_function_data 行为。

## 1. 影响范围（必须）
- 影响的 repo（来自 docmap，可多项）：etherscan-mcp
- 影响的模块/目录/文件（按 repo 分组列出即可）：app/mcp_server.py（新增工具注册）、app/service.py（如复用内部 keccak 实现或暴露包装函数）、文档（SOT 说明）
- 外部可见变化（如适用：API/CLI/配置/数据格式）：新增 MCP 工具 `keccak(input, input_type?)`（命名待定，默认 UTF-8 编码字符串）。

## 2. 方案与改动点（必须）
说明：实现将按批次推进；每批次写入前需先列出本批次改动文件/影响并征求确认。

- repo: etherscan-mcp
  - 改动点：在 service 中暴露/包装 keccak-256 计算（复用现有 `_keccak256`）；在 mcp_server 注册新工具 `keccak`，描述清晰参数；必要时添加输入类型选择（默认 text→UTF-8，若传十六进制/bytes 则直接哈希原始字节）。
  - 新增/修改的接口或数据结构：新增 MCP 工具 `keccak`.
  - 关键逻辑说明：输入规范化支持 text (str) / hex bytes / raw bytes-like；输出统一 `0x` 前缀 hex。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤（命令/操作）：使用 MCP 工具调用 keccak，覆盖字符串、hex 字符串、空字符串等输入，核对与本地参考实现一致。
- 关键用例清单：
  - 纯文本（如 "transfer(address,uint256)"）返回与已知 selector 4byte 前 8 hex 匹配。
  - hex 字符串输入（带 0x）按原始 bytes 处理。
  - 空字符串处理正确（keccak256 of empty string）。
  - 错误输入类型给出可读提示。
- 通过标准：上述用例哈希结果正确且格式统一 `0x...`，错误提示明确。

交付摘要口径（固定）：实现完成后，必须输出交付摘要，包含：
- 实际改动清单（按 repo 列出关键文件/模块）
- 自测步骤与结果
- 对照本节“通过标准”的逐条结论
- 已知风险/未决事项（如有必须列出）

约束：用户验收通过前，不更新 SOT，不归档 WIP。

## 4. SOT 更新清单（必须）
用户验收通过后，要把“最终事实”沉淀到 SOT（至少文件级，V1 不要求精确到小节）：

- docs/sot/overview.md：补充新增 MCP 工具 `keccak` 的用途与参数。
- docs/sot/architecture.md：补充 keccak 工具的输入规范化与实现来源（复用现有 keccak256）。
- 其他：无

## 5. 完成后归档动作（固定）
实现完成并完成基本自测后：
1) 输出交付摘要并请求用户验收
2) 用户验收通过后，按第 4 节更新 SOT
3) 更新第 6 节检查单（必须全勾）
4) 将整个目录从 docs/wip/YYYYMMDD-topic/ 移动到 docs/archive/YYYYMMDD-topic/

## 6. WIP 检查单（必须全勾才能归档）
- [ ] plan.md 已确认（PLAN 闸门已通过）
- [ ] 代码改动已完成（IMPLEMENT 完成）
- [ ] 基本自测已完成（记录命令/步骤与结果）
- [ ] 已输出交付摘要并且用户验收通过（VERIFY 闸门已通过）
- [ ] SOT 已更新（按第 4 节执行；列出更新的文件）
- [ ] 已归档：wip → archive（目录已移动）
