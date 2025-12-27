# Rate Limit（Etherscan API）修复 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：
  - Etherscan V2 在各类接口（含 `proxy` 模块）会返回限流响应（常见为 `status=0,message=NOTOK,result="Max calls per sec rate limit reached (3/sec)"`）。
  - 当前实现中，`ContractService._extract_proxy_result()` 对包含 `result` 的 payload 会提前返回，未优先检查 `status/message`，导致 `proxy.*` 类接口在限流时把错误文案当成“成功结果”透出（例如 `call_function` 的 `data` 变成限流字符串，继而出现误导性的 “ABI not available…”）。
  - 同时，`EtherscanClient._request()` 只对网络/HTTP 异常做重试，对 HTTP 200 但 payload 表示限流（NOTOK）未做自动退避重试，导致所有 Etherscan API 在高频调用下更容易直接失败。
- 目标：
  - 限流/NOTOK 时返回清晰错误（明确是 rate limit / NOTOK），避免把错误文案当作 `eth_call` 的 hex result。
  - 客户端遇到限流时自动退避重试，至少重试 3 次（沿用现有 `REQUEST_RETRIES` 默认值 3），覆盖所有 Etherscan API 调用路径。
- 非目标：
  - 不引入跨进程/分布式限流器（仅进程内重试退避）。
  - 不新增持久化缓存或队列。
  - 不改变非限流情况下的返回结构与解码逻辑。

## 1. 影响范围（必须）
- 影响的 repo（来自 docmap，可多项）：etherscan-mcp
- 影响的模块/目录/文件（按 repo 分组列出即可）：
  - repo: etherscan-mcp
    - `src/etherscan-mcp/app/service.py`：修正 proxy 返回提取逻辑，避免错误分支被当成成功结果。
    - `src/etherscan-mcp/app/etherscan_client.py`：在 `_request` 中识别限流响应并按退避策略重试。
- 外部可见变化（如适用：API/CLI/配置/数据格式）：
  - MCP/CLI 所有经由 Etherscan 的能力在限流时将更“抗抖”（自动退避重试），最终失败时错误更清晰。
  - 对 `proxy.*` 接口：不再出现“data=限流字符串”这种伪成功结果（影响 `call_function` / `get_storage_at` / `get_transaction` / `get_block_by_number` / `get_block_time_by_number` 等）。
  - 重试/退避通过既有环境变量控制：`REQUEST_RETRIES`（默认 3）、`REQUEST_BACKOFF_SECONDS`（默认 0.5）。

## 2. 方案与改动点（必须）
说明：实现将按批次推进；每批次写入前需先列出本批次改动文件/影响并征求确认。

- repo: etherscan-mcp
  - 改动点：
    1) `ContractService._extract_proxy_result()`：调整判断顺序与错误分支处理。
       - 优先处理 `error` 对象与 `status/message`（当 `status != "1"` 时即视为错误并抛出 ValueError）。
       - 仅在 `status == "1"`（或 payload 无 status 且为 JSON-RPC proxy 成功形态）时返回 `result`。
    2) `EtherscanClient._request()`：增加对限流响应的识别与重试。
       - 当返回 JSON 命中 “rate limit”/“Max calls per sec” 等特征且 `attempt < max_retries` 时，按 `backoff_seconds * attempt` sleep 并重试。
       - 超出重试次数后返回最后一次 payload，由 service 层给出清晰错误。
  - 新增/修改的接口或数据结构：无（仅内部逻辑与错误信息改进）
  - 关键逻辑说明：
    - 限流重试发生在 client 层，避免业务层重复处理；service 层负责把错误统一转成可读 ValueError（含 detail/message）。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤（命令/操作）：
  1) 纯本地（无需网络）验证：用 Python 构造典型限流 payload，确认 `_extract_proxy_result()` 会抛出包含 rate limit 关键信息的 ValueError。
  2) 可选（需要真实 `ETHERSCAN_API_KEY` 且可能受配额影响）：通过 MCP/CLI 连续调用 `call_function(symbol())` 触发限流，确认最终报错清晰且期间有退避重试（可通过日志/耗时观察）。
- 关键用例清单：
  - 用例 A：proxy 返回 `status=0,message=NOTOK,result=Max calls...` → `call_function` 失败且错误原因明确为限流/NOTOK。
  - 用例 B：同一类限流 payload → `get_storage_at` / `get_block_by_number` / `get_transaction` 等不返回伪成功结果（统一抛可读错误）。
  - 用例 C：proxy 返回 JSON-RPC `error` 对象 → 继续按既有逻辑透出 code/message/data。
  - 用例 D：正常 proxy 返回 `0x...` / dict / list → 行为不变。
  - 用例 E：非 proxy 模块接口（如 `getsourcecode`）在限流时自动退避重试，超出重试后仍能给出清晰的 NOTOK/rate limit 错误（本次不改非 proxy 的 `_extract_result_list` 语义）。
- 通过标准：
  - `proxy.*` 路径在限流时不再返回 `data="Max calls per sec..."` 这种伪成功结构（至少覆盖当前 repo 内所有使用 `_extract_proxy_result()` 的能力）。
  - 错误信息包含可检索关键字（例如 `rate limit` 或 `Max calls per sec` 或 `NOTOK`）。
  - 限流时 client 至少重试 3 次（默认 `REQUEST_RETRIES=3`），并按 `REQUEST_BACKOFF_SECONDS` 进行退避（1x/2x/3x...）。

自测记录（本次实现实际执行）：
- 编译检查：`python -m compileall -q src/etherscan-mcp`（通过）
- 纯本地：构造 `{"status":"0","message":"NOTOK","result":"Max calls per sec..."}` 调用 `_extract_proxy_result()`（按预期抛出 `ValueError`，信息包含限流文案）
- 实网回归（需自备 `ETHERSCAN_API_KEY`）：
  - `REQUEST_RETRIES=3`：高频 `eth_call` 多次调用，出现重试但最终成功返回 `0x...`
  - `REQUEST_RETRIES=1`：可触发限流，错误为 `Etherscan error: Max calls per sec rate limit reached (3/sec).`，且 `call_function` 不再伪成功返回限流字符串

交付摘要口径（固定）：实现完成后，必须输出交付摘要，包含：
- 实际改动清单（按 repo 列出关键文件/模块）
- 自测步骤与结果
- 对照本节“通过标准”的逐条结论
- 已知风险/未决事项（如有必须列出）

约束：用户验收通过前，不更新 SOT，不归档 WIP。

## 4. SOT 更新清单（必须）
用户验收通过后，要把“最终事实”沉淀到 SOT（至少文件级，V1 不要求精确到小节）：

- `docs/sot/architecture.md`：补充/更新 client 对 rate limit 的退避重试行为，以及 proxy 结果提取的错误处理要点。
- `docs/sot/overview.md`：补充“遇到限流会自动退避重试；最终错误更清晰”的外部行为说明（含对 `proxy.*` 不再伪成功）。

## 5. 完成后归档动作（固定）
实现完成并完成基本自测后：
1) 输出交付摘要并请求用户验收
2) 用户验收通过后，按第 4 节更新 SOT
3) 更新第 6 节检查单（必须全勾）
4) 将整个目录从 `docs/wip/20251227-rate-limit-proxy-result/` 移动到 `docs/archive/20251227-rate-limit-proxy-result/`

## 6. WIP 检查单（必须全勾才能归档）
- [x] plan.md 已确认（PLAN 闸门已通过）
- [x] 代码改动已完成（IMPLEMENT 完成）
- [x] 基本自测已完成（记录命令/步骤与结果）
- [x] 已输出交付摘要并且用户验收通过（VERIFY 闸门已通过）
- [x] SOT 已更新（按第 4 节执行；列出更新的文件）
- [x] 已归档：wip → archive（目录已移动）
