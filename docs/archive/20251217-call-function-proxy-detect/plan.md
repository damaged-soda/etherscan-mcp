# call_function 代理实现校验与缓存增强 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：call_function 的输入校验依赖缓存的 ABI。对 EIP-1967/透明代理地址，如果未缓存实现合约 ABI，就会因 selector 不匹配而本地报错，阻止可用的调用。
- 目标：在 call_function 过程中自动探测代理并缓存实现 ABI：首次遇到地址时调用 detect_proxy 缓存结果；若是代理则拉取实现 ABI 并用于 selector/长度校验；若已确认非代理或仍无 ABI 则退回现有逻辑。
- 非目标：不改其它工具行为，不引入新的持久化格式，不变更外部接口签名。

## 1. 影响范围（必须）
- 影响的 repo（来自 docmap，可多项）：etherscan-mcp
- 影响的模块/目录/文件（按 repo 分组列出即可）：app/service.py（call_function 校验流程、代理探测与缓存）、app/cache.py（如需存储 detect_proxy/实现 ABI 结果）
- 外部可见变化（如适用：API/CLI/配置/数据格式）：call_function 在代理合约上可自动探测实现并使用其 ABI 做校验；若 selector 缺失时不再盲目报错（在实现 ABI 可用的前提下）。

## 2. 方案与改动点（必须）
说明：实现将按批次推进；每批次写入前需先列出本批次改动文件/影响并征求确认。

- repo: etherscan-mcp
  - 改动点：
    - call_function 流程：如果缓存无 ABI 或 selector 不匹配，且未有 proxy 判定缓存，则调用 detect_proxy（一次）并缓存结果。
    - 若 detect_proxy 显示是代理且有 implementation 地址：尝试 fetch_contract(implementation)，缓存实现 ABI；再用实现 ABI 做 selector/长度校验。
    - 若 detect_proxy 显示非代理或实现 ABI 仍不可用：回退到当前逻辑（基础校验 + 可用的 ABI 校验），避免无限请求。
  - 新增/修改的接口或数据结构：可能在 ContractCache 中增加用于存储 detect_proxy/implementation ABI 的命名空间或复用现有缓存键。
  - 关键逻辑说明：保证 detect_proxy 只对同一地址做一次（缓存结果）；实现 ABI 获取失败时不阻塞调用，只回退；仍保持不主动联网超出必要范围。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤（命令/操作）：
  1) 针对真实 EIP-1967 代理地址，先调用 call_function（无预热）；期望：自动 detect_proxy，拉实现 ABI 后校验 selector/长度（可用缺参/错 selector 验证）。
  2) 非代理地址：call_function 不应重复 detect_proxy（缓存命中后不再调用），行为与现有校验一致。
  3) 当实现 ABI 获取失败时，call_function 应回退，不因 selector 不匹配而硬错误（除非已有 ABI 明确不匹配）。
- 关键用例清单：
  - 代理地址 + 错 selector：报“selector not found”基于实现 ABI。
  - 代理地址 + 缺参：报“data too short …”基于实现 ABI。
  - 非代理地址：与现有行为一致，无额外 detect_proxy 调用。
  - detect_proxy/实现 ABI 拉取失败：不阻塞调用，回退。
- 通过标准：
  - 以上用例结果与预期一致；detect_proxy 对同一地址仅调用一次（后续走缓存）；无新增“unknown error”类模糊提示。

交付摘要口径（固定）：实现完成后，必须输出交付摘要，包含：
- 实际改动清单（按 repo 列出关键文件/模块）
- 自测步骤与结果
- 对照本节“通过标准”的逐条结论
- 已知风险/未决事项（如有必须列出）

约束：用户验收通过前，不更新 SOT，不归档 WIP。

## 4. SOT 更新清单（必须）
用户验收通过后，要把“最终事实”沉淀到 SOT（至少文件级，V1 不要求精确到小节）：

- docs/sot/overview.md：如需补充 call_function 在代理场景的自动探测与实现 ABI 校验行为。
- docs/sot/architecture.md：补充 call_function 的 proxy 探测与实现 ABI 校验/回退逻辑。
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
