# 链上数字小助手转换工具 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：目前 MCP 提供链上查询/编码工具，但缺乏轻量的数字转换助手。用户希望在 MCP 内一站式完成 hex/dec 转换、金额换算（按 decimals）、常用单位速查（wei/gwei/eth），并返回可直接消费的 JSON 结果。
- 目标：新增单函数接口 `convert(value, from, to, decimals?)`，覆盖 hex↔dec、人类可读金额↔整数、ETH/wei/gwei 与常见 ERC20 decimals（6/8/18）快捷转换；返回包含原值、目标值、解释字符串的 JSON。
- 非目标：不引入外部汇率/法币转换；不实现复杂格式化/本地化；不改动现有链上查询工具行为。

## 1. 影响范围（必须）
- 影响的 repo：etherscan-mcp
- 影响的模块/目录/文件：app/mcp_server.py（注册新工具）、app/service.py（转换实现/格式化）、可能的辅助模块（若拆分）、docs/sot（工具说明）
- 外部可见变化：新增 MCP 工具 `convert(value, from, to, decimals?)`；支持 from/to: hex/dec/human/wei/gwei/eth，decimals 默认 18，可指定。

## 2. 方案与改动点（必须）
说明：实现将按批次推进，写入前先列出文件与影响征求确认。

- repo: etherscan-mcp
  - 改动点：在 service 中实现转换逻辑（十六进制<->十进制，金额整数<->人类可读，单位 wei/gwei/eth 换算，常见 decimals 快捷）；在 mcp_server 注册工具 `convert`，描述参数/默认 decimals=18/支持的 from,to；返回 JSON 包含原值、目标值、解释。
  - 新增/修改的接口或数据结构：新增 MCP 工具 `convert`。
  - 关键逻辑说明：
    - 输入规范化：from/to 枚举 hex/dec/human/wei/gwei/eth；value 支持字符串/数值（hex 自动去 0x）。
    - 数制转换：hex↔dec（无 0x），错误提示非法字符。
    - 金额换算：整数 + decimals -> 人类可读字符串（包含千分位和科学计数显示字段），反向人类可读字符串 -> 整数（支持小数点，按 decimals 放大，校验精度不丢失）。
    - 单位速查：wei/gwei/eth 互转；常见 ERC20 decimals（6/8/18）按 decimals 处理。
    - 输出：`{"original": ..., "converted": ..., "from": ..., "to": ..., "decimals": ..., "explain": <字符串>}`。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤：调用 MCP convert 覆盖 hex→dec、dec→hex、整数->human、human->整数、wei/gwei/eth 互转、decimals 6/8/18 场景，检查输出与解释字符串。
- 关键用例清单：
  - hex "0x2a" -> dec "42"；dec "42" -> hex "2a"。
  - 金额：整数 123456789，decimals 6 -> human "123.456789"（含千分位字段），科学计数字段存在；反向 "123.456789" -> 整数 123456789。
  - wei↔gwei↔eth：1 eth -> 1e18 wei；1 gwei -> 1e9 wei；反向转换准确。
  - 错误：非法 hex 字符报错；human 小数精度超过 decimals 报错。
- 通过标准：上述用例转换正确；错误提示明确；返回 JSON 包含原值、目标值、解释，字段完整。

交付摘要口径（固定）：实现完成后，必须输出交付摘要，包含：
- 实际改动清单（按 repo 列出关键文件/模块）
- 自测步骤与结果
- 对照本节“通过标准”的逐条结论
- 已知风险/未决事项（如有必须列出）

约束：用户验收通过前，不更新 SOT，不归档 WIP。

## 4. SOT 更新清单（必须）
- docs/sot/overview.md：补充 convert 工具用途、参数（from/to/decimals）、支持的模式（hex/dec/human/wei/gwei/eth）。
- docs/sot/architecture.md：补充转换逻辑要点（数制转换、金额缩放、人类格式与科学计数、单位换算、错误提示）。
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
