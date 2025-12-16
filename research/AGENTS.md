# 研究工作区指南（etherscan-mcp）

目的
- 本目录用于基于 MCP 的临时链上研究/试验

使用方式
- MCP 已默认可用，直接在研究过程中调用工具：`fetch_contract`、`get_contract_creation`、`detect_proxy`、`list_transactions`、`list_token_transfers`、`query_logs`、`get_storage_at`、`call_function`。topics 请传数组。

现场经验要点
- 事件 topic 以链上为准：先对目标地址在小范围（或指定交易）不带 topic 拉日志，观察实际出现的 topic，再反推签名，再用确认过的 topic 做全量过滤。不要先凭想当然的事件名去 keccak。
- ABI 需核对部署版本：ABI 可能与实际部署不一致。如果按 ABI 计算出的 topic 在链上查不到，就优先相信链上日志；用实际 topic 反推签名，调整解码。
- 函数调用要完整编码参数：只发 selector 不带 32 字节参数，eth_call 会报错。用 ABI 正确编码 selector+参数。
- 先小范围再全量：从已知交易哈希或最近区块拉一段日志，确认事件格式后再跑全历史，避免因为 topic 错误漏查。
- 不确定签名时用 4byte/keccak：有 topic hash 但没签名时，用 4byte 数据库或枚举常见参数 keccak 匹配。
- 事件名≠topic：topic 是完整签名字符串 keccak（如 Event(type1,type2,…)），参数列表有任何差异，topic 就不同。
- 注意单位/小数：解析 data 时确认底层 token 的 decimals，避免误读金额。
- 接口校验细节：MCP 的 topics 要传数组；有些接口不接受 “latest” 字符串作为 to_block，可用数字或直接省略。
- 代理判断：如有代理先探测实现/管理员，再用正确 ABI。
- 日志分页：历史长时用分页/offset，避免截断遗漏。
