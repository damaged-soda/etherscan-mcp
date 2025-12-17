# 代理合约 ABI 缓存修复 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：当前 ABI 缓存按合约地址存储，遇到代理（如 USDC 0xa0b8...eB48 指向实现 0x4350...02dd）时，call_function 在缺省模式下只用代理自身 ABI，导致 balanceOf 等实现函数无法调用。
- 目标：让 call_function 在代理场景能命中实现 ABI，支持 balanceOf 等函数调用，同时缓存策略与 proxy-aware 流程正确工作，避免重复请求。
- 非目标：不改现有接口签名，不涉及链上写操作，不改 Etherscan 调用方式。

## 1. 影响范围（必须）
- 影响的 repo（来自 docmap，可多项）：etherscan-mcp
- 影响的模块/目录/文件（按 repo 分组列出即可）：app/service.py（proxy-aware ABI 获取与缓存）、app/cache.py（可能的键/命名空间调整）、app/mcp_server.py（如需入口声明变化）、文档 SOT。
- 外部可见变化（如适用：API/CLI/配置/数据格式）：call_function 对代理地址可自动使用实现 ABI 进行 selector 校验与解码，缓存命中逻辑对代理实现生效。

## 2. 方案与改动点（必须）
说明：实现将按批次推进；每批次写入前需先列出本批次改动文件/影响并征求确认。

- repo: etherscan-mcp
  - 改动点：加强 proxy-aware ABI 读取与缓存链路；区分代理 ABI 与实现 ABI 缓存键；在 call_function 路径上优先尝试实现 ABI 解析和解码；避免重复探测代理实现；必要时调整 proxy_cache 结构（存储 implementation +版本）；补充对实现 ABI 的缓存/回填。
  - 新增/修改的接口或数据结构：可能扩展 proxy_cache 数据结构（含 implementation、fetched_at 等）、cache 键（namespace 或地址 label）；无需新增对外 API。
  - 关键逻辑说明：调用时先查代理 ABI；若检测到代理且有 implementation，则尝试直接使用实现地址的 ABI（缓存优先、未命中则抓取并缓存）；call_function 在 selector 校验/解码时优先使用实现 ABI，若缺失则不阻塞调用但提示；在代理检测结果上添加缓存避免重复探测。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤（命令/操作）：通过 MCP `call_function` 对 USDC 代理地址调用 `balanceOf(0xe3d4...)`；调用实现地址同样请求；重复调用验证缓存命中（日志或行为）；异常路径验证（不存在实现 ABI 时不报 selector 缺失）。
- 关键用例清单：
  - 代理地址 + 有实现 ABI：call_function 能校验 selector、成功 eth_call 并解码返回（balanceOf）。
  - 实现地址直接调用：行为不回退。
  - 代理实现 ABI 未验证或获取失败：call_function 不阻断调用（至少能透传 data），报错信息清晰。
  - 缓存：同一实现地址重复调用不重复请求 Etherscan。
- 通过标准：上述用例全部满足；错误路径提示清晰；无非代理回退行为变化。

交付摘要口径（固定）：实现完成后，必须输出交付摘要，包含：
- 实际改动清单（按 repo 列出关键文件/模块）
- 自测步骤与结果
- 对照本节“通过标准”的逐条结论
- 已知风险/未决事项（如有必须列出）

约束：用户验收通过前，不更新 SOT，不归档 WIP。

## 4. SOT 更新清单（必须）
用户验收通过后，要把“最终事实”沉淀到 SOT（至少文件级，V1 不要求精确到小节）：

- docs/sot/overview.md：补充 call_function 代理场景使用实现 ABI 的行为。
- docs/sot/architecture.md：补充 proxy-aware ABI 缓存策略（代理地址与实现地址区分）与 selector 校验/解码顺序。
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
