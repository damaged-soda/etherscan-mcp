# call_function 参数前置校验 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：当前 `call_function` 仅校验地址和 data 的基本十六进制格式，未对 data 长度/ABI 编码有效性做进一步检查，容易在调用时触发链上 revert，而错误信息较难定位。多数场景调用前已执行过 `fetch_contract`，ABI 已在本地缓存。
- 目标：在调用前增加合理的参数校验，若已缓存 ABI 则校验 selector 与参数长度；缓存缺失时仅做基础校验并放行；明显错误提前返回可读提示，减少无意义的链上调用。
- 非目标：不主动拉取/推断/解码 ABI，不改其它工具，不引入新依赖。

## 1. 影响范围（必须）
- 影响的 repo（来自 docmap，可多项）：etherscan-mcp
- 影响的模块/目录/文件（按 repo 分组列出即可）：app/service.py（call_function 参数校验、使用缓存 ABI）；如需微调缓存读取，可触及 app/cache.py。
- 外部可见变化（如适用：API/CLI/配置/数据格式）：`call_function` 在明显非法的 data 时直接抛出更具体的校验错误（含 selector/长度提示）；若缓存有 ABI，会校验 selector/参数长度；无缓存时保持基础校验后直接调用。

## 2. 方案与改动点（必须）
说明：实现将按批次推进；每批次写入前需先列出本批次改动文件/影响并征求确认。

- repo: etherscan-mcp
  - 改动点：
    - 基础校验：data 必须 0x 开头、偶数字节、长度至少 4 字节 selector，否则报错。
    - 利用缓存 ABI 校验（仅在已有缓存命中，不额外请求）：提取 selector，与 ABI 函数匹配；若无匹配，报错并列出已知函数/selector；若匹配且全部参数为静态类型，校验 data 长度应为 4 + 32*n；若包含动态参数，至少校验 head 长度（4 + 32*n）。
  - 新增/修改的接口或数据结构：无新接口；仅校验文案更具体。
  - 关键逻辑说明：不主动 fetch ABI；仅使用已有 ContractCache（fetch_contract 后存入的）做校验；无缓存时仅做基础校验后照常调用。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤（命令/操作）：
  1) 明显非法 data（无 0x、奇数字节、少于 4 字节 selector）调用 `call_function`，应抛出明确校验错误。
  2) 先 `fetch_contract` 某合约使 ABI 入缓存，再用错误 selector 调用 `call_function`，应提示 selector 不匹配并列出已知函数。
  3) 对全静态参数函数，构造长度不足的 data，应提示长度不足；长度正确可进入远端调用。
  4) 对含动态参数的函数，校验至少 head 长度；远端返回 JSON-RPC error 时仍透出。
- 关键用例清单：
  - data 少于 4 字节 selector，报“data too short/invalid”。
  - data 非 hex 或奇数字节，报“must be hex/length even”。
  - 缓存 ABI 时 selector 不匹配，报“selector not found”并列出已知函数/selector。
  - 静态参数函数长度不足报错，长度正确通过。
  - 动态参数函数至少 head 校验通过，远端错误可见。
- 通过标准：
  - 以上用例得到预期错误/成功路径，不出现“unknown error”类模糊提示；校验仅使用缓存，不额外请求 Etherscan。

交付摘要口径（固定）：实现完成后，必须输出交付摘要，包含：
- 实际改动清单（按 repo 列出关键文件/模块）
- 自测步骤与结果
- 对照本节“通过标准”的逐条结论
- 已知风险/未决事项（如有必须列出）

约束：用户验收通过前，不更新 SOT，不归档 WIP。

## 4. SOT 更新清单（必须）
用户验收通过后，要把“最终事实”沉淀到 SOT（至少文件级，V1 不要求精确到小节）：

- docs/sot/overview.md：如需补充 `call_function` 参数校验行为则更新，否则无。
- docs/sot/architecture.md：补充 `call_function` 基础校验与缓存 ABI 校验逻辑。
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
