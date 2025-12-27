# 架构说明（SOT）

Last Updated: 2025-12-27

## 模块边界（按 repo 或关键模块描述）
- config：从环境读取配置（必需 `ETHERSCAN_API_KEY`；可选 `ETHERSCAN_BASE_URL`、`NETWORK`、`CHAIN_ID`、`ETHERSCAN_CHAINLIST_URL`、`CHAINLIST_TTL_SECONDS`、`REQUEST_TIMEOUT`、`REQUEST_RETRIES`、`REQUEST_BACKOFF_SECONDS`），封装为配置对象。默认基址 `https://api.etherscan.io/v2/api`，默认 network=mainnet、chainid=1；`CHAIN_ID` 可硬覆盖默认链。
  - 静态兜底：保留少量静态 `NETWORK_CHAIN_ID_MAP`（mainnet/ethereum/eth/sepolia/holesky）用于 chainlist 不可用时仍能工作。
  - 动态主路径：未知 `NETWORK` 不在 config 阶段报错，交由 `chains` 基于 `/v2/chainlist` 动态解析；若默认 `NETWORK` 无法解析且未提供 `CHAIN_ID`，service 会明确报错避免误用主网。
- chains：链清单模块，基于 Etherscan V2 `GET /v2/chainlist` 动态拉取链清单，进程内 TTL 缓存；提供 `list_chains()` 与 `resolve(network)`（支持数字 chainid、链名模糊、以及轻量别名如 `arb`），歧义时要求显式提供 chainid。
- etherscan client：基于 requests 的 REST 封装（默认 V2 基址），对合约源码、创建信息、交易、代币转移、日志，以及 `proxy.eth_getStorageAt`/`proxy.eth_call` 等接口做有限重试与简单退避；除 HTTP/网络异常外，也会对 payload 中可识别的限流信息（例如 `rate limit`/`Max calls per sec`/`Too Many Requests`）进行退避重试。使用 `X-API-Key` 头并附带 `chainid` 参数；额外提供请求任意 URL 的入口用于 chainlist 拉取（复用相同重试/限流逻辑）。
- cache：纯内存缓存（进程级，不落盘）；按地址+chainid 键控；合约详情与创建信息使用不同命名空间，动态列表类接口默认不缓存。
- service：聚合合约详情与调研能力，统一地址格式校验和 network/chainid 解析；解析 Etherscan 响应（包含多文件 SourceCode JSON）；新增能力：创建信息（可缓存）、代理检测（EIP-1967 implementation/admin 槽）、交易列表、代币转移列表（ERC20/721/1155）、日志查询、存储槽读取、eth_call 只读调用；动态接口对空结果返回空列表，对错误返回可读 ValueError；fetch_contract 支持 inline_limit/force_inline 内联策略，超限时仅返回摘要并指示 source_omitted/source_omitted_reason；get_source_file 支持按文件名分段获取源码（offset/length），返回 content/sha256/total_length/truncated；get_block_by_number 提供区块详情（支持 latest/十进制/0x，full_transactions 展开交易对象，tx_hashes_only 强制仅哈希）；get_block_time_by_number 基于区块 timestamp 返回块号/时间戳/ISO。
  - network/chainid 解析：显式传入 `network` 时优先走 `chains.resolve()`（支持 `arb` 等别名）；`network=None` 时使用默认（若设置 `CHAIN_ID` 则优先覆盖）；默认网络无法解析时抛错避免误用主网。
  - 块号输入兼容：块范围相关字段（start_block/end_block/from_block/to_block）接受整数、十进制字符串或 `0x` 十六进制字符串，统一解析为整数；非法输入报错提示“十进制或 0x 前缀”。
  - proxy/eth_call/eth_getStorageAt 错误处理：若 Etherscan 返回 JSON-RPC error 对象，透出其中的 code/message/data；若返回 module 风格的 `status/message`（例如限流 `NOTOK`），则按错误处理并抛出可读 ValueError；对 proxy 成功响应中的字符串 `result` 会校验为 hex（非 hex 视为错误信息，避免把限流文案当作成功结果）。
  - call_function 输入校验与编码：基础检查 0x/偶数字节/至少 4 字节 selector；若 ContractCache/即时获取到 ABI，则校验 selector 并按静态参数校验最小长度；未命中自动 detect_proxy，识别 EIP-1967 代理后尝试实现 ABI，缺失实现 ABI 时不阻塞；支持 function+args 本地 ABI 编码（内置 Keccak-256/4byte）。无参函数可省略括号（`readTokens` 等价 `readTokens()`）。
  - call_function 返回解码：有 ABI 时按 outputs 解码（含 tuple/数组），多返回值展开并返回 decoded（ok/error、函数信息、输出列表）；数值类支持可选 decimals hint 计算 value_scaled；原始返回 hex 保留在 data；无 ABI 或解码失败时 decoded 标注 error 但调用不抛异常；若 ABI 已加载但缺 selector，则软失败放行 raw eth_call，decoded.warning 提示 selector 未命中。
  - get_transaction：基于 proxy.eth_getTransactionByHash / eth_getTransactionReceipt 获取单笔交易与回执；返回字段保留 hex 及整数解析（value_int 等），包含 gas/price/nonce/blockNumber 等交易字段及 receipt 的 status/gasUsed/logs/contractAddress；tx_hash 需 0x+64 hex 校验。
  - convert：from/to 支持 hex/dec/human/wei/gwei/eth，decimals 默认 18；hex/dec 互转自动去 0x；human 与整数按 decimals 放缩，提供 plain/thousands/scientific；wei/gwei/eth 按 1e0/1e9/1e18 缩放；非法 hex、分数精度超限等给出可读错误；内部使用整数/Decimal 避免浮点精度丢失。
- entry：CLI 入口 `python -m app fetch --address ... [--network ...] [--inline-limit N|--force-inline]`，输出 JSON；当源码总长度超过内联阈值（默认 20000）且未强制时，`source_files` 只返回摘要（filename/length/sha256/inline=false）并附带 `source_omitted`/`source_omitted_reason` 提示使用单文件获取；CLI 子命令 `get-source-file --address ... --filename <file> [--offset N --length M]` 支持分段获取；区块相关命令：`get-block --block <latest|dec|0x> [--full-transactions] [--tx-hashes-only]`、`get-block-time --block <latest|dec|0x>`；链解析命令：`list-chains`、`resolve-chain`；MCP 入口 `python -m app.mcp_server --transport stdio|sse|streamable-http`，提供工具 `fetch_contract`（支持 inline_limit/force_inline）、`get_source_file`、`get_contract_creation`、`detect_proxy`、`list_chains`、`resolve_chain`、`list_transactions`、`list_token_transfers`、`query_logs`、`get_storage_at`、`get_transaction`、`call_function`、`keccak`、`convert`、`get_block_by_number`、`get_block_time_by_number`。
- mcp_server 参数形态约束：对需要数组的参数（`call_function.args`、`encode_function_data.args`、`query_logs.topics`）在入口层做形态规范：list/tuple 保持，标量自动包成单元素数组，字符串/bytes 或对象直接报错并提示示例，避免被逐字符拆分。
- tests/fixtures：暂未实现。
- 代理感知与缓存：fetch_contract 解析 Etherscan Proxy/Implementation 元数据，规范化实现地址并写入 proxy cache；call_function 的 ABI 选择优先使用实现合约（来自 getsourcecode 元数据或 EIP-1967 detect_proxy），探测异常不缓存“非代理”，避免假阴性；缺失实现 ABI 时调用不阻断，仅解码受限。

## 关键约束 / 不变量
- 单进程、单仓（src/etherscan-mcp），无跨进程依赖。
- 运行环境：Python 3.11（兼容 3.10+），仅使用官方 Etherscan API，暂不涉及链上写操作。
- 必需环境变量：`ETHERSCAN_API_KEY`；默认 network=mainnet、chainid=1，可通过 `NETWORK`/`CHAIN_ID` 覆盖；未知 NETWORK 通过 `/v2/chainlist` 动态解析（数字 chainid 始终可用），链清单可用 `ETHERSCAN_CHAINLIST_URL`/`CHAINLIST_TTL_SECONDS` 配置。
- 基础重试与简单退避，降低短时配额/限流抖动导致的失败；缓存命中时不重复请求（动态列表/日志/存储/eth_call 默认不缓存）。
- 无外部持久化，缓存仅驻内存，进程重启即清空；日志简洁、可读性优先。

## 跨 repo 交互（如适用）
- 无跨 repo 交互（单仓）。
