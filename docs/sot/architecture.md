# 架构说明（SOT）

Last Updated: 2025-12-18

## 模块边界（按 repo 或关键模块描述）
- config：从环境读取配置（必需 `ETHERSCAN_API_KEY`；可选 `ETHERSCAN_BASE_URL`、`NETWORK`、`CHAIN_ID`、`REQUEST_TIMEOUT`、`REQUEST_RETRIES`、`REQUEST_BACKOFF_SECONDS`），封装为配置对象。默认基址 `https://api.etherscan.io/v2/api`，默认 chainid=1（mainnet），NETWORK 可映射为 chainid（mainnet/ethereum/holesky/sepolia），或直接用 `CHAIN_ID` 覆盖。
  - network 解析与别名：`mainnet`/`ethereum`/`eth`→1，`sepolia`→11155111，`holesky`→17000；数字字符串直接视为 chain_id；未知值会报错并列出允许值或建议用 `CHAIN_ID`。
- etherscan client：基于 requests 的 REST 封装（默认 V2 基址），对合约源码、创建信息、交易、代币转移、日志，以及 `proxy.eth_getStorageAt`/`proxy.eth_call` 等接口做有限重试与简单退避，使用 `X-API-Key` 头并附带 `chainid` 参数。
- cache：纯内存缓存（进程级，不落盘）；按地址+chainid 键控；合约详情与创建信息使用不同命名空间，动态列表类接口默认不缓存。
- service：聚合合约详情与调研能力，统一地址格式校验和 network/chainid 解析；解析 Etherscan 响应（包含多文件 SourceCode JSON）；新增能力：创建信息（可缓存）、代理检测（EIP-1967 implementation/admin 槽）、交易列表、代币转移列表（ERC20/721/1155）、日志查询、存储槽读取、eth_call 只读调用；动态接口对空结果返回空列表，对错误返回可读 ValueError。
  - 块号输入兼容：块范围相关字段（start_block/end_block/from_block/to_block）接受整数、十进制字符串或 `0x` 十六进制字符串，统一解析为整数；非法输入报错提示“十进制或 0x 前缀”。
  - proxy/eth_call/eth_getStorageAt 错误处理：若 Etherscan 返回 JSON-RPC error 对象，透出其中的 code/message/data，避免“unknown error”。
  - call_function 输入校验与编码：基础检查 0x/偶数字节/至少 4 字节 selector；若 ContractCache/即时获取到 ABI，则校验 selector 并按静态参数校验最小长度；未命中自动 detect_proxy，识别 EIP-1967 代理后尝试实现 ABI，缺失实现 ABI 时不阻塞；支持 function+args 本地 ABI 编码（内置 Keccak-256/4byte）。
  - call_function 返回解码：有 ABI 时按 outputs 解码（含 tuple/数组），多返回值展开并返回 decoded（ok/error、函数信息、输出列表）；数值类支持可选 decimals hint 计算 value_scaled；原始返回 hex 保留在 data；无 ABI 或解码失败时 decoded 标注 error 但调用不抛异常；若 ABI 已加载但缺 selector，则软失败放行 raw eth_call，decoded.warning 提示 selector 未命中。
  - get_transaction：基于 proxy.eth_getTransactionByHash / eth_getTransactionReceipt 获取单笔交易与回执；返回字段保留 hex 及整数解析（value_int 等），包含 gas/price/nonce/blockNumber 等交易字段及 receipt 的 status/gasUsed/logs/contractAddress；tx_hash 需 0x+64 hex 校验。
  - convert：from/to 支持 hex/dec/human/wei/gwei/eth，decimals 默认 18；hex/dec 互转自动去 0x；human 与整数按 decimals 放缩，提供 plain/thousands/scientific；wei/gwei/eth 按 1e0/1e9/1e18 缩放；非法 hex、分数精度超限等给出可读错误；内部使用整数/Decimal 避免浮点精度丢失。
- entry：CLI 入口 `python -m app.cli fetch --address ... [--network ...]`，输出 JSON；MCP 入口 `python -m app.mcp_server --transport stdio|sse|streamable-http`，提供工具 `fetch_contract`、`get_contract_creation`、`detect_proxy`、`list_transactions`、`list_token_transfers`、`query_logs`、`get_storage_at`、`get_transaction`、`call_function`、`keccak`（keccak-256，支持 text|hex|bytes 的单值或 list/tuple，列表按顺序拼接为 bytes，文本 UTF-8）、`convert`（hex/dec/human/wei/gwei/eth 互转，decimals 默认 18，返回 original/converted/decimals/explain，human 输出含千分位和科学计数字段）。
- mcp_server 参数形态约束：对需要数组的参数（`call_function.args`、`encode_function_data.args`、`query_logs.topics`）在入口层做形态规范：list/tuple 保持，标量自动包成单元素数组，字符串/bytes 或对象直接报错并提示示例，避免被逐字符拆分。
- tests/fixtures：暂未实现。
- 代理感知与缓存：fetch_contract 解析 Etherscan Proxy/Implementation 元数据，规范化实现地址并写入 proxy cache；call_function 的 ABI 选择优先使用实现合约（来自 getsourcecode 元数据或 EIP-1967 detect_proxy），探测异常不缓存“非代理”，避免假阴性；缺失实现 ABI 时调用不阻断，仅解码受限。

## 关键约束 / 不变量
- 单进程、单仓（src/etherscan-mcp），无跨进程依赖。
- 运行环境：Python 3.11（兼容 3.10+），仅使用官方 Etherscan API，暂不涉及链上写操作。
- 必需环境变量：`ETHERSCAN_API_KEY`；默认 network=mainnet、chainid=1，可通过 `NETWORK` 或 `CHAIN_ID` 覆盖，基址默认为 V2。
- 基础重试与简单退避，避免接口配额超限；缓存命中时不重复请求（动态列表/日志/存储/eth_call 默认不缓存）。
- 无外部持久化，缓存仅驻内存，进程重启即清空；日志简洁、可读性优先。

## 跨 repo 交互（如适用）
- 无跨 repo 交互（单仓）。
