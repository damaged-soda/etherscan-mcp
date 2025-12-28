# 更明确的 ABI 错误提示 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：对未在 Etherscan 验证的合约调用 `fetch_contract` 时，Etherscan 的 `getsourcecode` 往往返回非 JSON 的 `ABI` 字符串（如 “Contract source code not verified”），当前实现会统一报 `Invalid ABI returned from Etherscan.`，信息不够明确，容易误判为工具解析问题。
- 目标：当 Etherscan 返回“未验证/无 ABI”类信息时，给出明确、可行动的错误提示（包含 address/network/chainid 与 Etherscan 返回的 ABI 字段摘要）。
- 非目标：不改变 `fetch_contract` 的返回结构；不引入持久化缓存；不新增/维护 CI/CD 文档；不进行任何 git 操作。

## 1. 影响范围（必须）
- 影响的 repo（来自 docmap，可多项）：etherscan-mcp（`./src/etherscan-mcp`）
- 影响的模块/目录/文件（按 repo 分组列出即可）：
  - repo: etherscan-mcp
    - `src/etherscan-mcp/app/service.py`：ABI 解析与 getsourcecode 响应解析
    - （如需）`src/etherscan-mcp/app/cli.py` / `src/etherscan-mcp/app/mcp_server.py`：仅在需要补充上下文/透传信息时调整
- 外部可见变化（如适用：API/CLI/配置/数据格式）：对未验证合约的报错文案更明确（CLI/MCP 均受影响）；不改变成功返回字段。

## 2. 方案与改动点（必须）
说明：实现将按批次推进；每批次写入前需先列出本批次改动文件/影响并征求确认。

- repo: etherscan-mcp
  - 改动点：
    - 增强 ABI 解析：当 `ABI` 字段为非 JSON 且匹配“未验证/不可用 ABI”的典型 Etherscan 文案时，抛出更明确的 `ValueError`（例如包含 “not verified”/“ABI unavailable”）。
    - 增强错误上下文：错误信息包含 `address`、`network`、`chain_id`，并附带 ABI 原始字段的截断摘要，便于用户定位是“未验证”还是其它异常返回。
  - 新增/修改的接口或数据结构：无（仅调整错误文案与分支判断）。
  - 关键逻辑说明：
    - 仍以 `json.loads(abi_raw)` 为主路径；仅在 JSON 解析失败时做分支识别。
    - 对识别为“未验证”的场景输出明确指引：合约需在 Etherscan 验证后才可获取 ABI/源码；若只做只读调用可改用 `call_function(data=...)` 或提供 `function+args`（若 ABI 可用才可自动解码）。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤（命令/操作）：
  - 需要可用的 `ETHERSCAN_API_KEY`：
    - 已验证合约：`python -m app fetch --address 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2 --network mainnet`
    - 未验证合约：`python -m app fetch --address 0x8d5b01e6f01ad17dc5fc1ee8ff8fdd2da8546037 --network mainnet`
  - MCP 自测（可选）：通过 Codex 调用 `etherscan-mcp.fetch_contract(...)` 复现同样行为。
- 关键用例清单：
  1) 已验证合约：`fetch_contract` 正常返回 `abi`（列表）且不影响现有字段。
  2) 未验证合约：`fetch_contract` 抛错信息明确指出“合约未验证/ABI 不可用”，而非笼统的 “Invalid ABI…”，并包含 address/network/chain_id。
- 通过标准：
  - 用例 1) 返回成功且结构不变。
  - 用例 2) 错误信息可读、可行动（明确“未验证”）且包含必要上下文。

交付摘要口径（固定）：实现完成后，必须输出交付摘要，包含：
- 实际改动清单（按 repo 列出关键文件/模块）
- 自测步骤与结果
- 对照本节“通过标准”的逐条结论
- 已知风险/未决事项（如有必须列出）

约束：用户验收通过前，不更新 SOT，不归档 WIP。

## 4. SOT 更新清单（必须）
用户验收通过后，要把“最终事实”沉淀到 SOT（至少文件级，V1 不要求精确到小节）：

- `docs/sot/overview.md`：补充 `fetch_contract` 在未验证合约上的错误行为说明（更明确的报错/提示）。
- `docs/sot/architecture.md`：补充 service 对 Etherscan `ABI` 非 JSON 返回（未验证场景）的识别与错误处理策略。

## 5. 完成后归档动作（固定）
实现完成并完成基本自测后：
1) 输出交付摘要并请求用户验收
2) 用户验收通过后，按第 4 节更新 SOT
3) 更新第 6 节检查单（必须全勾）
4) 将整个目录从 `docs/wip/20251228-abi-error-message/` 移动到 `docs/archive/20251228-abi-error-message/`

## 6. WIP 检查单（必须全勾才能归档）
- [x] plan.md 已确认（PLAN 闸门已通过）
- [x] 代码改动已完成（IMPLEMENT 完成）
- [x] 基本自测已完成（`python -m compileall -q src/etherscan-mcp/app`；MCP `fetch_contract` 未验证示例地址返回明确报错）
- [x] 已输出交付摘要并且用户验收通过（VERIFY 闸门已通过）
- [x] SOT 已更新（`docs/sot/overview.md`、`docs/sot/architecture.md`）
- [x] 已归档：wip → archive（目录已移动）
