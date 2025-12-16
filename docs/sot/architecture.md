# 架构说明（SOT）

Last Updated: 2025-12-16

## 模块边界（按 repo 或关键模块描述）
- config：读取环境变量（必需 `ETHERSCAN_API_KEY`，可选 `ETHERSCAN_BASE_URL`、`NETWORK`、`CACHE_DIR`），输出配置对象。
- etherscan client：基于 requests 的 REST 封装（默认主网 baseUrl），带基础重试/简单节流，提供获取合约 ABI、源码、验证状态等方法。
- cache：内存缓存，选配文件缓存目录 `./.cache/etherscan`，按地址+网络键控，缓存 ABI/源码。
- service：聚合合约详情 `{ address, network, abi, source_files, compiler, verified }`，协调 client 与 cache，处理缺少 key、无效地址等错误。
- entry：MCP handler、CLI 或简易 HTTP，消费 service，将合约信息提供给 Codex，本地运行即可。
- tests/fixtures：client 与 service 层的单元测试及示例响应数据。

## 关键约束 / 不变量
- 单进程、单仓（src/etherscan-mcp），无跨进程依赖。
- 运行环境：conda 创建的 Python 3.11（可兼容 3.10+），仅使用官方 Etherscan API，暂不涉及链上写操作。
- 必需环境变量：`ETHERSCAN_API_KEY`；默认网络 mainnet，可通过配置覆盖 baseUrl/network。
- 需有基础速率保护与有限重试，避免接口配额超限；缓存命中时不重复请求。
- 无外部持久化，仅可选本地文件缓存；日志简洁、可读性优先。

## 跨 repo 交互（如适用）
- 无跨 repo 交互（单仓）。
