# 架构说明（SOT）

Last Updated: 2025-12-16

## 模块边界（按 repo 或关键模块描述）
- config：从环境读取配置（必需 `ETHERSCAN_API_KEY`；可选 `ETHERSCAN_BASE_URL`、`NETWORK`、`CHAIN_ID`、`CACHE_DIR`、`REQUEST_TIMEOUT`、`REQUEST_RETRIES`、`REQUEST_BACKOFF_SECONDS`），封装为配置对象。默认基址 `https://api.etherscan.io/v2/api`，默认 chainid=1（mainnet），NETWORK 可映射为 chainid（mainnet/ethereum/holesky/sepolia），或直接用 `CHAIN_ID` 覆盖。
- etherscan client：基于 requests 的 REST 封装（默认 V2 基址），对 `contract.getsourcecode` 进行有限重试与简单退避，使用 `X-API-Key` 头并附带 `chainid` 参数。
- cache：内存缓存，选配文件缓存目录（例如 `./.cache/etherscan`）；按地址+chainid 键控，序列化 JSON 落盘。
- service：聚合合约详情 `{ address, network, chain_id, abi, source_files, compiler, verified }`，处理地址格式校验、网络/chainid 解析、缓存命中、Etherscan 响应解析（包含多文件 SourceCode JSON 支持），异常抛出可读错误。
- entry：CLI 入口 `python -m app.cli fetch --address ... [--network ...]`，输出 JSON；MCP 入口 `python -m app.mcp_server --transport stdio|sse|streamable-http`，提供工具 `fetch_contract(address, network?)`。
- tests/fixtures：暂未实现。

## 关键约束 / 不变量
- 单进程、单仓（src/etherscan-mcp），无跨进程依赖。
- 运行环境：Python 3.11（兼容 3.10+），仅使用官方 Etherscan API，暂不涉及链上写操作。
- 必需环境变量：`ETHERSCAN_API_KEY`；默认 network=mainnet、chainid=1，可通过 `NETWORK` 或 `CHAIN_ID` 覆盖，基址默认为 V2。
- 基础重试与简单退避，避免接口配额超限；缓存命中时不重复请求。
- 无外部持久化，仅可选本地文件缓存；日志简洁、可读性优先。

## 跨 repo 交互（如适用）
- 无跨 repo 交互（单仓）。
