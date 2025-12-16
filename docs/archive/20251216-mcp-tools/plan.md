# MCP 工具扩充 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：当前 MCP 仅提供 `fetch_contract`（ABI/源码/元数据）；代理识别、创建信息、交易/日志明细、存储槽读取等调研能力缺失，限制 agent 自动研判合约。
- 目标：补齐常用调研工具集（创建信息、代理检测、交易/代币转移、日志查询、存储槽读取、只读合约调用），保持网络/chainId 解析一致，返回结构清晰可读，并对输入做基础校验与错误提示。
- 非目标：不改部署/CI，不扩展 CLI 子命令，不做前端或 agent 编排逻辑，仅在 MCP 层新增工具和必要的服务/客户端支持。

## 1. 影响范围（必须）
- 影响的 repo（来自 docmap，可多项）：etherscan-mcp
- 影响的模块/目录/文件（按 repo 分组列出即可）：
  - app/etherscan_client.py（新增 Etherscan API 包装方法）
  - app/service.py（新增业务方法、参数校验、解析逻辑；选择性缓存策略）
  - app/mcp_server.py（注册新增 MCP 工具）
  - 可能新增测试/fixtures 目录（如补自测用例）
- 外部可见变化（如适用：API/CLI/配置/数据格式）：
  - MCP 新增工具：见第 2 节“新增接口”列表；输入参数与输出字段将作为对外契约。
  - 配置项沿用现有 env（网络/chainId/超时/重试等），无新增 env。

## 2. 方案与改动点（必须）
按 repo 分组写清楚“要改什么”，不写部署流程：

- repo: etherscan-mcp
  - 改动点：
    - 在 EtherscanClient 中封装所需接口：`contract.getcontractcreation`、`account.txlist`、`account.tokentx`/`tokennfttx`/`token1155tx`（通过参数选择）、`logs.getLogs`、`proxy.eth_getStorageAt`、`proxy.eth_call`，并复用现有超时/重试/退避。
    - 在 ContractService 增加对应业务方法，统一地址/网络解析，合理的分页/块高默认值与边界检查，对动态数据（交易/日志）默认不落盘缓存，静态数据（创建信息）可按地址+chainId 缓存。
    - 代理检测逻辑：读取常见槽位（EIP-1967 implementation/admin、EIP-1822）、可选从 ABI/源码字段辅助判断，返回实现地址/管理员/证据说明。
    - MCP 层注册新工具，保持命名清晰，与服务方法一一对应，并在工具描述中注明参数含义。
  - 新增/修改的接口或数据结构：
    - MCP 工具（均支持可选 `network` 覆盖全局 chainId）：
      1) `get_contract_creation(address, network?)` → `{creator, tx_hash, block_number, timestamp?}`
      2) `detect_proxy(address, network?)` → `{is_proxy, implementation?, admin?, proxy_type?, evidence}`（evidence 为槽位读数/解析说明）
      3) `list_transactions(address, start_block?, end_block?, page?, offset?, sort?)` → `[{hash, from, to, value, gas, gas_price, block_number, time, input}]`
      4) `list_token_transfers(address, token_type?, start_block?, end_block?, page?, offset?, sort?)` → `[{token_address, token_symbol, token_type, from, to, value|token_id, id? , block_number, tx_hash}]`
      5) `query_logs(address, topics?, from_block?, to_block?, page?, offset?)` → `[{address, topics, data, block_number, tx_hash, index}]`
      6) `get_storage_at(address, slot, block_tag?)` → `{slot, data}`
      7) `call_function(address, data, block_tag?)` → `{data}`（返回 raw hex）
      8) 保留已有 `fetch_contract`。
    - 视实现需要新增内部辅助结构（如分页参数 dataclass），不对外暴露。
  - 关键逻辑说明：
    - 地址校验复用现有规范（0x-prefixed 40 hex），network/chainId 解析复用 resolve_chain_id。
    - 对 `topics`/`slot`/`block_tag` 等输入做格式校验（hex 长度、0x 前缀），避免接口直通返回混乱错误。
    - 缓存策略：保留 fetch_contract 缓存；`get_contract_creation` 可缓存；交易/日志/存储/eth_call 默认不缓存以避免过期。
    - 错误提示保持可读性，Etherscan 返回非 1 状态或空结果时抛出带上下文的 ValueError。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤（命令/操作）：
  1) `cd src/etherscan-mcp && pip install -r requirements.txt`（如未装依赖）
  2) `ETHERSCAN_API_KEY=<key> python - <<'PY' ...` 调用 ContractService 各方法；或 `python -m app.mcp_server --transport stdio` 并用 FastMCP 客户端逐一调用工具。
- 关键用例清单：
  - fetch_contract：主网已验证合约（例：USDT 0xdAC17F958D2ee523a2206206994597C13D831ec7）。
  - get_contract_creation：返回 creator/tx_hash/块高。
  - detect_proxy：对已知代理（如 USDC 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48）识别实现地址/管理员。
  - list_transactions：指定地址分页返回，sort asc/desc 正常。
  - list_token_transfers：token_type=erc20/erc721/erc1155 覆盖。
  - query_logs：提供 topics[0] 过滤，块高范围生效。
  - get_storage_at：读取 EIP-1967 implementation 槽返回非零实现地址。
  - call_function：对 view 方法（如 name()）返回正确 ABI 编码结果。
  - 异常场景：无效地址、未知网络、空结果、Etherscan 返回错误码时有可读报错。
- 通过标准：上述用例均返回预期字段与合理数据，异常场景抛出明确错误，无未处理异常；mcp_server 可启动且注册到 FastMCP 后工具可调用。

## 4. SOT 更新清单（必须）
- docs/sot/overview.md：补充 MCP 工具列表与能力描述，增加新工具的简要说明。
- docs/sot/architecture.md：更新客户端/服务模块职责（新增接口、代理检测、存储/eth_call 支持、缓存策略差异）。
- 其他：无。

## 5. 完成后归档动作（固定）
实现完成并完成自测后：
1) 按第 4 节更新 SOT
2) 将整个目录从 docs/wip/20251216-mcp-tools/ 移动到 docs/archive/20251216-mcp-tools/
