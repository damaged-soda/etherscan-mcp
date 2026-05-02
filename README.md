# Etherscan MCP

CLI + stdio MCP server，封装 Etherscan API V2（ABI / 源码 / 索引类查询）+ EVM JSON-RPC（`eth_call` / `eth_getStorageAt` / `eth_getLogs` / 区块 / 交易等只读调用），用于合约研判和链上数据抓取。不签名、不广播链上交易。

## 功能概览

- **合约详情**：ABI、源码、编译器版本、验证状态。
- **创建信息**：创建者、创建交易哈希、块高（Etherscan 优先，失败可回退 RPC 二分定位）。
- **代理检测**：读取 EIP-1967 implementation/admin 槽，输出实现地址与证据。
- **交互数据**：普通交易列表、ERC20/721/1155 代币转移列表、日志按 topic 查询。
- **状态读取**：任意存储槽读取（`eth_getStorageAt`）、只读函数调用（`eth_call`，支持本地 ABI 编码 + 返回值解码）。
- **区块 / 交易**：`eth_getBlockByNumber`、`eth_getTransactionByHash` + receipt。
- **链清单**：基于 Etherscan V2 `/v2/chainlist` 动态拉取，支持别名（`bsc` / `base` / `arb` 等）。
- **缓存**：纯内存（进程级），合约详情与创建信息缓存；动态列表 / 日志 / 存储 / `eth_call` 默认不缓存。

## 环境要求

- Python 3.11（兼容 3.10+）。
- `ETHERSCAN_API_KEY`（必填）。

## 安装

```bash
pip install -r src/etherscan-mcp/requirements.txt
```

## CLI

```bash
ETHERSCAN_API_KEY=<key> python -m app fetch --address <contract> [--network <chain>] [--inline-limit N|--force-inline]
python -m app get-source-file --address <contract> --filename <file> [--offset N --length M]
python -m app get-block --block <latest|dec|0x> [--full-transactions] [--tx-hashes-only]
python -m app get-block-time --block <latest|dec|0x>
python -m app list-chains [--include-degraded]
python -m app resolve-chain --network <name|alias|chainid>
```

源码超内联阈值（默认 20000 字符）且未强制时，`source_files` 仅返回摘要（filename/length/sha256/inline=false）并附 `source_omitted`/`source_omitted_reason`，需要原文用 `get-source-file` 分段拿。

## MCP（Codex 本地注册示例）

```bash
codex mcp add etherscan-mcp \
  --env ETHERSCAN_API_KEY=<your-api-key> \
  --env RPC_URL_56=<your-bsc-rpc-https-endpoint> \
  --env RPC_URL_8453=<your-base-rpc-https-endpoint> \
  -- bash -lc "cd `pwd`/src/etherscan-mcp && python -m app.mcp_server --transport stdio"
```

工具列表变更后需在 Codex / Claude Code 侧重新连接 MCP server。常用主网测试地址：USDT `0xdAC17F958D2ee523a2206206994597C13D831ec7`、USDC `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`。

## 模块结构

入口目录 `src/etherscan-mcp/app/`：

- `config.py` —— 读取环境变量，封装为配置对象；保留少量静态 `NETWORK_CHAIN_ID_MAP`（mainnet/bsc/sepolia 等）作为 chainlist 不可用时的兜底。
- `chains.py` —— 基于 Etherscan V2 `/v2/chainlist` 的链清单模块，进程内 TTL 缓存；提供 `list_chains()` 与 `resolve(network)`（支持数字 chainid、链名模糊、别名 `arb`/`bsc`/`base`）。
- `capabilities.py` —— 手维护的 per-chain caveat 矩阵（`chainid → [{tool, status, reason, workaround}]`），把 README「已知限制」结构化暴露出来。`status` 枚举：`requires_rpc_url` / `paid_tier_only` / `degraded` / `unsupported`；service 层在输出时会附 `status_effective`，`requires_rpc_url` 在配了 `RPC_URL_<chainid>` 时降级为 `ok`。
- `etherscan_client.py` —— requests 封装的 REST client，对源码 / 创建信息 / 交易 / 转移 / 日志 / `module=proxy` 做有限重试与退避，识别限流文案（`rate limit` / `Max calls per sec` / `Too Many Requests`）。
- `rpc_client.py` —— JSON-RPC（HTTP POST）封装；`eth_call` / `eth_getStorageAt` / `eth_getLogs` / `eth_getBlockByNumber` / `eth_getTransactionByHash` / `eth_getTransactionReceipt` / `eth_blockNumber` 等只读调用。
- `cache.py` —— 纯内存缓存（进程级，不落盘），按 address+chainid 键控；contract 详情与 creation 用不同命名空间。
- `service.py` —— 聚合层：地址校验、network/chainid 解析、ABI 解析、读链路由（已配 RPC 走 RPC，未配走 `module=proxy`）、call_function 编码 / 解码、convert helper。
- `cli.py` / `__main__.py` —— CLI 入口。
- `mcp_server.py` —— FastMCP server，注册 tools。

## MCP tools

| 类别 | tools |
|------|-------|
| Contracts | `fetch_contract`、`get_source_file`、`get_contract_creation`、`detect_proxy` |
| Chains | `list_chains`、`resolve_chain` |
| Transactions / Transfers / Logs | `list_transactions`、`list_token_transfers`、`query_logs` |
| State / Calls | `get_storage_at`、`call_function`、`encode_function_data`、`keccak` |
| Blocks / Tx | `get_block_by_number`、`get_block_time_by_number`、`get_transaction`、`get_transaction_summary` |
| Helpers | `convert` |

## 参数与错误约定

容易踩坑的几条：

- **`network` 入参**：支持数字 chainid（`"42161"`，最稳定）、官方链名 / 模糊匹配、轻量别名（`arb`、`arb-sepolia`、`bsc`→`56`、`base`→`8453`）。歧义时强制要求 chainid。
- **默认网络安全**：未显式传 `network` 且默认 `NETWORK` 无法解析、`CHAIN_ID` 也未设置时，service 直接报错，避免误用主网。
- **数组形态参数**：`call_function.args` / `encode_function_data.args` / `query_logs.topics` 必须是数组。MCP 入口层会把标量自动包成单元素数组；字符串 / bytes / 对象会直接报错并提示示例，避免被逐字符拆分。
- **块号输入兼容**：`start_block` / `end_block` / `from_block` / `to_block` 接受整数、十进制字符串、`0x` 十六进制字符串。非法输入报错提示"十进制或 0x 前缀"。
- **未验证合约**：`getsourcecode` 返回典型未验证文案（如 `Contract source code not verified`）时，明确报错"合约未验证导致 ABI 不可用"，附 address/network/chain_id 与截断摘要。
- **`call_function`**：基础校验 0x / 偶数字节 / 至少 4 字节 selector；ABI 命中时按 outputs 解码（含 tuple / 数组），数值类支持 `decimals` hint 计算 `value_scaled`；ABI 加载但 selector 缺失时软失败放行 raw `eth_call`，`decoded.warning` 提示；无参函数可省略括号（`readTokens` 等价 `readTokens()`）。
- **代理感知**：`fetch_contract` 解析 Etherscan Proxy/Implementation 元数据，规范化实现地址写入 proxy cache；`call_function` ABI 选择优先实现合约（来自元数据或 EIP-1967 detect_proxy）；探测异常不缓存"非代理"，避免假阴性；缺实现 ABI 不阻断调用，仅解码受限。
- **`convert`**：`from_unit` / `to_unit` 支持 `hex` / `dec` / `human` / `wei` / `gwei` / `eth`，`decimals` 默认 18；内部用整数 / Decimal 避免浮点丢精度；分数精度超限会报错。
- **`get_transaction`**：优先 RPC 的 `eth_getTransactionByHash` + `eth_getTransactionReceipt`，未配 RPC 回退 Etherscan proxy；`tx_hash` 需 `0x` + 64 hex。
- **`get_transaction_summary`**：一次性给出 tx meta + gas cost + 唯一 log address 列表（带 Etherscan `ContractName` 注解）+ ERC20 `Transfer` 解码（`topic0=0xddf252ad...`，3 topics 严格匹配，自动跳 ERC721 4-topic 变体），并 best-effort 拉每个 token 的 `symbol/decimals/name`（标准 selector + 兼容 `bytes32` symbol/name 的旧式 ERC20 如 MKR）。`decode_transfers` / `annotate_contracts` 默认 `true`，关掉跳过对应 lookup。注解 + token metadata 进进程内缓存，二次同 tx 命中只需重拉 receipt。**协议特异识别（"这是 Pendle market / PT / YT"）刻意不做**，靠 Etherscan ContractName + 调用方在 pendle-mcp 等下游做交叉。
- **`query_logs`（RPC 路径）**：`page/offset` 用"按 block range 分段累积后切片"的 best-effort 实现；RPC log 不含 `timeStamp`，`time_stamp` 字段为 `null`。

错误处理：JSON-RPC error 对象统一抛 `ValueError("RPC error: ...")`；Etherscan proxy 回退路径若返回非 hex `result`（往往是限流文案）会按错误处理而非成功；HTTP 429 / 5xx 走重试与退避。

## 已知限制

> 这些限制结构化进了 `capabilities.py`，跑任务前调一次 `resolve_chain --network <chain>` 就能拿到当前链的 `caveats` + `rpc_configured`；`list_chains` 输出带 `has_caveats` 标记。不必再二手转述这一节。

- **`list_transactions` / `list_token_transfers` 在部分 free tier 链上返回空**：对应 Etherscan 的 `txlist` / `tokentx` indexed 端点，原生 JSON-RPC 没有等价能力（`eth_*` 只能按 hash/block 拿，没法按 address 倒查历史）。Base 等链 free tier 直接返回空，目前没有 fallback。后续如有需要要走 BaseScan native key 或第三方索引服务（Covalent / Alchemy enhanced API），单独立项。`status=paid_tier_only`。
- **`get_contract_creation` 在 BSC 等链可能 NOTOK**：建议配 `RPC_URL_<chainid>` 启用 RPC 二分回退；internal create 场景可能仅返回 `block_number/timestamp`（`complete=false`），且需要 archive / full-history 节点。`status=degraded`。
- **`module=proxy` 在 Base / BSC 等链 free tier 受限**：会报 `Free API access is not supported for this chain`，配 `RPC_URL_<chainid>` 绕开。`status=requires_rpc_url`，配上 RPC 后 `status_effective` 自动降级为 `ok`。
- **新链 / 未列入 caveat 矩阵的链**（HyperEVM、Plasma 等）：默认按"无 caveat"处理。先用 `list_chains` 确认 Etherscan V2 是否覆盖（status=1 为正常），跑任务踩坑后回头补 `capabilities.py`。

## 配置（环境变量）

| 变量 | 默认 | 说明 |
|------|------|------|
| `ETHERSCAN_API_KEY` | — | **必填** |
| `ETHERSCAN_BASE_URL` | `https://api.etherscan.io/v2/api` | API base URL |
| `NETWORK` | `mainnet` | 默认链；可传数字 chainid 或链名 / 别名 |
| `CHAIN_ID` | — | 硬覆盖 network 推导出的 chainid |
| `ETHERSCAN_CHAINLIST_URL` | `https://api.etherscan.io/v2/chainlist` | 链清单端点 |
| `CHAINLIST_TTL_SECONDS` | `3600` | 链清单缓存 TTL |
| `RPC_URL_<chainid>` | — | 指定链的 JSON-RPC HTTP 端点（推荐：`RPC_URL_56` BSC、`RPC_URL_8453` Base） |
| `RPC_<chainid>` | — | `RPC_URL_<chainid>` 的兼容别名 |
| `RPC_URL` | — | 默认链的 JSON-RPC 端点（仅未显式传 `network` 时生效；显式传 `network` 推荐用 `RPC_URL_<chainid>` 避免误绑定） |
| `REQUEST_TIMEOUT` | `10` | 单次请求超时（秒） |
| `REQUEST_RETRIES` | `3` | 重试次数 |
| `REQUEST_BACKOFF_SECONDS` | `0.5` | 退避基数 |

读链类工具（`call_function` / `get_storage_at` / `detect_proxy` / `query_logs` / `get_block_by_number` / `get_block_time_by_number` / `get_transaction`）在配了对应 `RPC_URL_<chainid>` 时优先走 RPC；未配则保持原行为，回退 Etherscan `module=proxy`。

## 命名约定

- MCP tools 对外参数用 `snake_case`。
- 透传给 Etherscan / RPC 的 query 字段保持官方命名（`chainid`、`startblock`、`fromBlock` 等）。
