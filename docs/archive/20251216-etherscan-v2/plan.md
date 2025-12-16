# Etherscan V2 迁移 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：当前使用 Etherscan V1 `contract.getsourcecode`，CLI 返回 “You are using a deprecated V1 endpoint...”，无法获取合约信息。
- 目标：切换到 Etherscan API V2，CLI `python -m app.cli fetch --address ...` 能正常返回 ABI 和源码。
- 非目标：不做复杂多网络适配、超出基础的限流/重试、CI/部署。

## 1. 影响范围（必须）
- 影响的 repo：etherscan-mcp
- 影响的模块/目录/文件：
  - app/config.py：默认基址/版本/chainid 配置
  - app/etherscan_client.py：V2 请求路径、参数与认证方式（X-API-Key/Query）
  - app/service.py：V2 响应解析、错误提示
  - app/cli.py：沿用 CLI，必要时补充提示
  - docs/sot/*：更新现状与使用方法
- 外部可见变化：默认改用 V2 端点 `https://api.etherscan.io/v2/api`，需要 `chainid` 参数；优先使用 `X-API-Key` 头，可兼容 query `apikey`。

## 2. 方案与改动点（必须）
- repo: etherscan-mcp
  - 改动点：配置新增/调整默认 V2 基址与 chainid；将客户端请求切到 V2（带 `chainid`，使用 `X-API-Key` header，必要时兼容 `apikey` query）；若收到 V1 弃用提示自动改用 V2；服务层适配 V2 响应字段（ABI/SourceCode/Compiler 等）。
  - 新增/修改的接口或数据结构：配置增加 chainid（可从 NETWORK 映射或显式覆盖）；客户端支持 V2 请求方法；服务解析 V2 `getsourcecode` 结果。
  - 关键逻辑说明：地址校验保持；请求时附带 chainid 和 API Key；解析 V2 结果结构，提取 abi/source/编译器信息；错误时给出可读提示。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤：
  - `pip install -r requirements.txt`
  - `ETHERSCAN_API_KEY=<key> [NETWORK=<network>|CHAIN_ID=<id>] python -m app.cli fetch --address 0xdAC17F958D2ee523a2206206994597C13D831ec7`
  - 断网或无 key 场景校验错误提示。
- 关键用例清单：成功获取 ABI+源码；收到 V1 弃用提示时改用 V2 仍成功；无效地址报可读错误；缓存命中不重复请求。
- 通过标准：成功用例退出码 0 且输出含非空 abi/source_files；错误用例返回非 0 且提示明确。

## 4. SOT 更新清单（必须）
- docs/sot/overview.md：更新默认 API 版本/基地址与运行方式。
- docs/sot/architecture.md：更新客户端/配置使用 V2、认证方式、chainid 逻辑。
- 其他：无。

## 5. 完成后归档动作（固定）
实现完成并完成自测后：
1) 按第 4 节更新 SOT
2) 将整个目录从 docs/wip/YYYYMMDD-topic/ 移动到 docs/archive/YYYYMMDD-topic/
