# RPC Provider 读链能力切换（BSC 支持）技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：Etherscan API V2 在 2025 年底调整了 Free tier 的“链覆盖/限权”策略，导致部分链（如 BNB Chain 56/97）上的 `module=proxy`（JSON-RPC 代理）相关能力（`eth_call`/`eth_getStorageAt`/`eth_getLogs`/`eth_getBlockByNumber` 等）直接返回 `Free API access is not supported for this chain`；但合约 ABI/源码类端点仍可用。
- 目标：保留 “Etherscan V2 拉已验证合约 ABI/源码” 的定位，同时把“读链（JSON-RPC）能力”统一切到真实 JSON-RPC Provider，以避免被 Etherscan Free tier 链覆盖限制卡死，并使 BSC 的 `call_function` 等工具可用。
- 非目标：
  - 不引入 BscScan 的 API KEY 方案（本需求不走 scan 的 proxy）。
  - 不尝试用 RPC 复刻 `txlist/tokentx` 这类索引分页接口（继续保留为 Etherscan HTTP 能力或后续另立需求）。
  - 不改变 MCP/CLI 的对外接口签名（仅内部路由与配置变化；必要时只新增环境变量）。

## 1. 影响范围（必须）
- 影响的 repo（来自 docmap，可多项）：etherscan-mcp（`./src/etherscan-mcp`）
- 影响的模块/目录/文件（按 repo 分组列出即可）：
  - repo: etherscan-mcp
    - `src/etherscan-mcp/app/config.py`：新增 RPC 配置读取（按 chainid 映射）
    - `src/etherscan-mcp/app/service.py`：将读链相关方法改为走 JSON-RPC（provider）
    - `src/etherscan-mcp/app/rpc_client.py`（新）：requests 封装 JSON-RPC POST + 重试/超时
    - （可选）`src/etherscan-mcp/app/cli.py`：仅在需要增加本地自测入口时才改（默认不改）
- 外部可见变化（如适用：API/CLI/配置/数据格式）：
  - 新增环境变量：按链配置 RPC URL（见第 2 节）
  - 行为变化：`call_function/get_storage_at/query_logs/get_transaction/get_block_by_number/get_block_time_by_number/detect_proxy` 在“该 chainid 配置了 RPC URL”时走 RPC；未配置时保持原行为（继续走 Etherscan `module=proxy`）。

## 2. 方案与改动点（必须）
说明：实现将按批次推进；每批次写入前需先列出本批次改动文件/影响并征求确认。

按 repo 分组写清楚“要改什么”，不写部署流程：

- repo: etherscan-mcp
  - 改动点：
    1) 引入 `RpcClient`：对 JSON-RPC 进行 `POST` 调用（`jsonrpc=2.0`），复用现有超时/重试/退避参数，并统一错误格式（HTTP 错误、JSON-RPC error、空 result）。
    2) 配置：在 `Config` 中加入 `rpc_urls: dict[str,str]`（key 为 chainid），支持以下 env 形式：
       - `RPC_URL_<chainid>=https://...`（推荐，例如 `RPC_URL_56`）
       - `RPC_<chainid>=https://...`（兼容别名）
       - `RPC_URL=https://...`（可选）：仅作为“默认链”的 RPC（当调用未显式传 `network` 时使用）；显式传 `network` 的场景仍建议用 `RPC_URL_<chainid>` 以避免误绑定
    2.5) network 体验优化：
       - 注册常用别名：`bsc` → `56`（让用户可以在 CLI/MCP 里传 `network="bsc"`）
    3) service 内部路由（不改对外接口）：
       - A 类能力继续走 Etherscan V2（ABI/源码）：
         - `fetch_contract`
         - `get_source_file`
       - B 类能力切 RPC Provider（读链）：
         - `call_function` → `eth_call`
         - `get_storage_at`/`detect_proxy` → `eth_getStorageAt`
         - `query_logs` → `eth_getLogs`（分页差异见下）
         - `get_transaction` → `eth_getTransactionByHash` + `eth_getTransactionReceipt`
         - `get_block_by_number`/`get_block_time_by_number` → `eth_getBlockByNumber`
    4) `query_logs` 的分页兼容策略（保持入参 page/offset 不变）：
       - RPC 原生无分页，采用“按 block range 分段查询 + 累积到足够条数后切片”的 best-effort：
         - 对 `from_block..to_block` 按固定步长切片（可配置常量，例如每段 2k/5k blocks）
         - 累积日志直到达到 `page*offset` 条，停止继续请求
         - 返回 `logs` 只包含对应页的切片结果
       - 输出字段差异：RPC log 不含 `timeStamp`，返回中 `time_stamp` 将为 `null`（或保持缺省），其余字段按 JSON-RPC 返回映射。
    5) 回退策略（已确定：增量接入，默认不破坏现有行为）：
       - 若 `chainid` 配置了 `RPC_URL_<chainid>`（或 `RPC_<chainid>`），则 B 类能力走真实 JSON-RPC Provider
       - 若未配置，则完全保持原行为：继续走 Etherscan `module=proxy`（因此 BSC 等链在 Free tier 下仍可能报 `Free API access is not supported for this chain`，错误信息中提示改配 RPC）
  - 新增/修改的接口或数据结构：
    - 新增：`Config.rpc_urls`
    - 新增：`RpcClient`
    - 无：MCP tools/CLI 参数不变
  - 关键逻辑说明：
    - 所有 network 输入仍通过现有 `ChainRegistry.resolve()` 统一解析为 `chain_id`，再用 `chain_id` 选择 RPC URL（避免 alias/chainname 歧义）
    - 当链配置了 RPC URL 时，读链相关调用不再依赖 Etherscan 的 proxy（避免链覆盖/限权带来的不可控风险）；未配置时保持旧路径

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤（命令/操作）：
  1) 准备环境变量：
     - `ETHERSCAN_API_KEY=...`（用于 ABI/源码）
     - `RPC_URL_56=...`（BSC 主网 JSON-RPC）
     - （可选）`RPC_URL_1=...`（Ethereum JSON-RPC，用于对比/回归）
  1.5) 验证 network 别名解析：
     - `python -c "from app.config import resolve_chain_id; print(resolve_chain_id('bsc'))"`（期望输出 `56`）
  2) 验证 ABI/源码仍可用（Etherscan V2）：
     - `python -m app fetch --address <bsc_verified_contract> --network 56`
  3) 验证 BSC 读链能力不再触发 Etherscan Free tier 报错（走 RPC）：
     - `python -c "from app.config import load_config; from app.service import ContractService; s=ContractService(load_config()); print(s.call_function('<addr>', network='56', function='paused()', args=[]))"`
     - `python -c "from app.config import load_config; from app.service import ContractService; s=ContractService(load_config()); print(s.get_storage_at('<addr>', '0x0', network='56'))"`
  4) 验证区块/交易/日志（走 RPC）：
     - `python -c "from app.config import load_config; from app.service import ContractService; s=ContractService(load_config()); print(s.get_block_time_by_number('latest', network='56'))"`
     - `python -c "from app.config import load_config; from app.service import ContractService; s=ContractService(load_config()); print(s.query_logs('<token>', network='56', topics=[<topic0>], from_block=<n>, to_block=<m>, page=1, offset=10))"`
- 关键用例清单：
  - BSC：`call_function` 能返回 decoded（不再出现 `Free API access is not supported for this chain`）
  - BSC：`get_storage_at`/`detect_proxy` 正常工作
  - BSC：`get_block_by_number`、`get_transaction` 正常工作
  - ABI/源码：`fetch_contract/get_source_file` 在 BSC 仍可工作（仍走 Etherscan V2）
- 通过标准：
  - 对 chainid=56：上述 B 类能力均不依赖 Etherscan proxy，并能在配置 RPC URL 后成功返回
  - 对所有链：A 类能力行为不回退、不改变（仍从 Etherscan V2 获取 ABI/源码）

交付摘要口径（固定）：实现完成后，必须输出交付摘要，包含：
- 实际改动清单（按 repo 列出关键文件/模块）
- 自测步骤与结果
- 对照本节“通过标准”的逐条结论
- 已知风险/未决事项（如有必须列出）

约束：用户验收通过前，不更新 SOT，不归档 WIP。

## 4. SOT 更新清单（必须）
用户验收通过后，要把“最终事实”沉淀到 SOT（至少文件级，V1 不要求精确到小节）：

- `docs/sot/overview.md`：更新“能力边界/配置”，新增 RPC 配置方式与“读链走 RPC、ABI/源码走 Etherscan V2”的事实
- `docs/sot/architecture.md`：更新模块边界（新增 rpc_client、service 路由策略、query_logs 分页策略差异）
- 其他：无

## 5. 完成后归档动作（固定）
实现完成并完成基本自测后：
1) 输出交付摘要并请求用户验收
2) 用户验收通过后，按第 4 节更新 SOT
3) 更新第 6 节检查单（必须全勾）
4) 将整个目录从 `docs/wip/20260105-rpc-readchain/` 移动到 `docs/archive/20260105-rpc-readchain/`

## 6. WIP 检查单（必须全勾才能归档）
- [x] plan.md 已确认（PLAN 闸门已通过）
- [x] 代码改动已完成（IMPLEMENT 完成）
- [x] 基本自测已完成（记录命令/步骤与结果）
- [x] 已输出交付摘要并且用户验收通过（VERIFY 闸门已通过）
- [x] SOT 已更新（按第 4 节执行：`docs/sot/overview.md`、`docs/sot/architecture.md`）
- [x] 已归档：wip → archive（目录已移动）
