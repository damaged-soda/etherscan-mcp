# call_function 编码工具内置（keccak/4byte/参数编码） 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：当前 call_function 依赖外部工具/库来生成 4byte selector 和编码参数，用户需要自行编码 data。希望在 MCP 内置轻量编码能力，减少本地额外依赖。
- 目标：提供内置 keccak/4byte 查询与函数选择器+参数 ABI 编码能力，尽量零新依赖（纯 Python 实现），让调用方可直接传递函数签名和参数列表生成 data。
- 非目标：不实现完整 ABI 解码器、不覆盖所有复杂类型（如 nested tuples 深层解码），不改现有工具签名行为（除新增可选参数）。

## 1. 影响范围（必须）
- 影响的 repo（来自 docmap，可多项）：etherscan-mcp
- 影响的模块/目录/文件（按 repo 分组列出即可）：app/service.py（编码逻辑/扩展）、app/mcp_server.py（工具参数定义，如需新增可选参数）、可能新增 utils 模块存放编码函数。
- 外部可见变化（如适用：API/CLI/配置/数据格式）：call_function 可选新增参数（如 function_signature / args）用于自动编码；提供 keccak/4byte 查询辅助（可作为单独工具或在 call_function 内部使用）。

## 2. 方案与改动点（必须）
说明：实现将按批次推进；每批次写入前需先列出本批次改动文件/影响并征求确认。

- repo: etherscan-mcp
  - 改动点：
    - 内置 keccak-256（复用现有纯 Python实现）+ 4byte selector 计算接口。
    - 扩展 call_function：允许传入 `function`（签名字符串，如 `transfer(address,uint256)`）和 `args`（列表），自动编码 data；若同时提供 data 和 function/args，优先使用编码结果或明确冲突报错。
    - ABI 编码支持：基础静态类型（uint256/int256/bool/address/bytes32/fixed-size bytes/静态数组）、动态类型（string/bytes/dynamic array）按 ABI 规范编码；报错信息可读。
    - 可选新增 MCP 工具：`encode_function_data(function, args, abi?)` 与 `keccak(text)`/`selector(function)`（若简单，可作为 call_function 的子能力无需额外工具，视实现权衡）。
  - 新增/修改的接口或数据结构：为 call_function 增加可选参数（function/args）；若新增工具，需在 mcp_server.py 注册。
  - 关键逻辑说明：编码纯 Python，无新依赖；参数类型来源于提供的函数签名或 ABI（如提供），不自动拉取链上 ABI；错误即时抛出 ValueError。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤（命令/操作）：
  1) keccak/selector：`selector("transfer(address,uint256)")` 返回 `a9059cbb`；其他已知函数校验。
  2) 编码静态参数：`function=transfer(address,uint256), args=[0x..., 1]` 生成 data 与已知值一致。
  3) 编码动态参数：`function=foo(bytes,string)`/`function=bar(uint256[])` 生成长度和 offset 合规（对比参考编码）。
  4) call_function 使用 function+args（无需 data）能成功调用公共合约只读函数（例如 `name()`）。
  5) 错误路径：类型不匹配/参数数量错误/不支持类型时返回明确错误。
- 关键用例清单：
  - selector 计算正确；
  - 静态参数编码正确；
  - 动态参数编码正确（offset + length）；
  - call_function 可用 function+args 成功调用；
  - 错误提示清晰。
- 通过标准：
  - 上述用例通过，输出与参考值匹配；未引入新依赖；错误文案可读。

交付摘要口径（固定）：实现完成后，必须输出交付摘要，包含：
- 实际改动清单（按 repo 列出关键文件/模块）
- 自测步骤与结果
- 对照本节“通过标准”的逐条结论
- 已知风险/未决事项（如有必须列出）

约束：用户验收通过前，不更新 SOT，不归档 WIP。

## 4. SOT 更新清单（必须）
用户验收通过后，要把“最终事实”沉淀到 SOT（至少文件级，V1 不要求精确到小节）：

- docs/sot/overview.md：补充 call_function 支持 function+args 编码/内置 keccak/selector 工具的说明（如新增工具）。
- docs/sot/architecture.md：补充编码逻辑、支持类型范围、错误行为。
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
