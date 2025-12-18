# get-block-by-number 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：用户通过 Etherscan proxy `eth_getBlockByNumber` 查询最新块，返回巨量区块数据（含 tx 对象）会在对话里被截断；目前 MCP 未提供获取区块详情或当前区块时间的工具。
- 目标：在 MCP/CLI 中提供 `eth_getBlockByNumber` 能力（可控 tx 展开/裁剪）并新增“当前区块时间”便捷接口，支持 latest/数值/0x，尽量避免响应在对话中被截断。
- 非目标：不实现区块流式订阅、不处理交易追踪；不修改现有其他接口行为。

## 1. 影响范围（必须）
- 影响的 repo：etherscan-mcp
- 影响的模块/目录/文件：app/service.py（新增 block 查询逻辑与参数规范、当前区块时间封装）、app/etherscan_client.py（新增 proxy 调用）、app/mcp_server.py（新工具）、app/cli.py（新增子命令/参数）
- 外部可见变化：新增 MCP 工具 `get_block_by_number` 与 `get_block_time_by_number`（支持 `latest` 参数）；新增 CLI 子命令支持同功能；响应结构包含区块字段，可选 `full_transactions` 控制是否展开 tx 对象，可选裁剪（仅交易哈希）；时间接口返回指定或最新块号与时间戳（可含 ISO 文本）。

## 2. 方案与改动点（必须）
说明：实现将按批次推进；每批次写入前先列出改动文件征求确认。

- repo: etherscan-mcp
  - 改动点：在 etherscan_client 增加 proxy/eth_getBlockByNumber 封装；service 新增 get_block_by_number，支持块号输入（latest/hex/dec）、full_txs 开关，可选 `tx_hashes_only` 减少响应；新增 get_block_time_by_number（支持 latest）返回块号和时间戳；MCP/CLI 新增对应工具/命令。
  - 新增/修改接口/数据结构：`get_block_by_number(block, network?, full_transactions?, tx_hashes_only?)`；`get_block_time_by_number(block, network?)` 返回 {block_number, timestamp, timestamp_iso}；必要时保持 tx_hashes_only 优先级高于 full_transactions。
  - 关键逻辑：复用 _normalize_block_tag；full_transactions=false 默认返回哈希列表；full_transactions=true 返回交易对象；tx_hashes_only=true 强制仅哈希以防对话截断；块时间接口通过传入块号（含 latest）获取 timestamp 并转换为 ISO 字符串。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤：使用有效 API Key 运行 CLI `get-block --block latest`（默认哈希列表）；`get-block --block latest --full-transactions`；`get-block --block latest --tx-hashes-only`；`get-block --block 0xABC`；`get-block-time --block latest`；MCP 工具调用同样参数。
- 关键用例：1) 默认返回区块+tx 哈希列表；2) full_transactions=true 返回 tx 对象；3) tx_hashes_only=true 强制仅哈希；4) 非法块号报错（需 0x/十进制/“latest”）；5) 区块时间接口在 latest/指定块返回块号与时间戳（含 ISO 文本）；6) 支持 chainid/network 解析。
- 通过标准：上述用例无异常；响应字段完整且形态一致；错误提示可读。

交付摘要口径（固定）：实现完成后输出交付摘要（改动清单、自测结果、通过标准结论、风险）。

约束：用户验收通过前，不更新 SOT，不归档 WIP。

## 4. SOT 更新清单（必须）
- docs/sot/overview.md：新增 block 查询工具/CLI 命令说明、参数。
- docs/sot/architecture.md：记录 service/client 新增 proxy 调用、参数规范、tx 哈希列表行为。
- 其他：无。

## 5. 完成后归档动作（固定）
1) 输出交付摘要并请求用户验收
2) 用户验收通过后更新 SOT（按第 4 节）
3) 更新第 6 节检查单（全勾）
4) 将目录 docs/wip/20251219-get-block-by-number/ 移动到 docs/archive/20251219-get-block-by-number/

## 6. WIP 检查单（必须全勾才能归档）
- [x] plan.md 已确认（PLAN 闸门已通过）
- [x] 代码改动已完成（IMPLEMENT 完成）
- [x] 基本自测已完成（记录命令/步骤与结果）
- [ ] 已输出交付摘要并且用户验收通过（VERIFY 闸门已通过）
- [ ] SOT 已更新（按第 4 节执行；列出更新的文件）
- [ ] 已归档：wip → archive（目录已移动）
