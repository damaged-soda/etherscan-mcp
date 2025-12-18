# fetch-contract-truncation 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：`fetch_contract` 目前始终内联全部源码文件，超大合约在 MCP 调用时会被对话上下文自动截断（出现 “...tokens truncated...”），完整源码无法查看。
- 目标：为大体积合约提供不被截断的交付方式，仍能按需获取完整源码（可分段），并保持 CLI/MCP 调用的可控体验。
- 非目标：不修改 Etherscan 拉取逻辑、重试/缓存策略；不处理其他工具的非相关行为。

## 1. 影响范围（必须）
- 影响的 repo（来自 docmap，可多项）：etherscan-mcp
- 影响的模块/目录/文件（按 repo 分组列出即可）：app/service.py（fetch_contract 响应整形、单文件获取能力），app/mcp_server.py（工具参数与新增工具），app/cli.py（新增参数/子命令暴露源码获取能力，视实现需要）
- 外部可见变化（如适用：API/CLI/配置/数据格式）：fetch_contract 增加内联保护开关/阈值与提示字段，新增获取单个源码文件的 MCP 工具（含可选偏移/长度），CLI 增加对应参数/命令（如需）。

## 2. 方案与改动点（必须）
说明：实现将按批次推进；每批次写入前需先列出本批次改动文件/影响并征求确认。

按 repo 分组写清楚“要改什么”，不写部署流程：

- repo: etherscan-mcp
  - 改动点：为 fetch_contract 增加内联长度上限（可配置/可强制内联）；超过阈值时返回文件摘要（文件名、长度、sha256、inline 标志）与提示字段，不直接附带大源码；新增按文件名获取源码内容的 service 方法和 MCP 工具，支持偏移/长度分段并复用缓存；（可选）CLI 暴露 inline-limit/force-inline 控制及单文件获取命令/flag。
  - 新增/修改的接口或数据结构：fetch_contract 响应新增 source_omitted/source_omitted_reason 与文件摘要字段；fetch_contract 工具新增 inline_limit/force_inline 参数；新增 get_source_file 工具（address, filename, network?, offset?, length?）；（可选）CLI 参数/子命令对应。
  - 关键逻辑说明：以总源码字符数与阈值比较决定是否内联；内部缓存保留完整内容，响应时构造浅拷贝并按需移除 content；get_source_file 在缓存缺失时先 fetch，返回指定文件内容/哈希/长度并可分段。

## 3. 自测与验收口径（必须，可执行）
- 本地自测步骤（命令/操作）：无 API Key 环境下运行 `python -m app.cli --help`、`python -m app.cli fetch --help`、`python -m app.cli get-source-file --help`（若新增）；如有有效 key，可用主网示例地址调用 fetch_contract 和 get_source_file，观察 source_omitted 标志与分段返回。
- 关键用例清单：1) 小合约总长低于阈值时保持全部内联且 source_omitted=false；2) 大合约超阈值时返回摘要并提示使用 get_source_file；3) get_source_file 返回文件内容、长度与 sha256；4) offset/length 分段返回生效，越界或文件不存在给出可读错误；5) force_inline 时强制内联。
- 通过标准：上述用例表现符合预期；无回溯/格式错误；工具描述与参数与实现一致。

交付摘要口径（固定）：实现完成后，必须输出交付摘要，包含：
- 实际改动清单（按 repo 列出关键文件/模块）
- 自测步骤与结果
- 对照本节“通过标准”的逐条结论
- 已知风险/未决事项（如有必须列出）

约束：用户验收通过前，不更新 SOT，不归档 WIP。

## 4. SOT 更新清单（必须）
用户验收通过后，要把“最终事实”沉淀到 SOT（至少文件级，V1 不要求精确到小节）：

- docs/sot/overview.md：补充 fetch_contract 的内联保护、相关参数/新工具、CLI 新增参数/命令（如实现）。
- docs/sot/architecture.md：记录响应新增字段、内联阈值逻辑、get_source_file 服务/工具及分段能力。
- 其他：无。

## 5. 完成后归档动作（固定）
实现完成并完成基本自测后：
1) 输出交付摘要并请求用户验收
2) 用户验收通过后，按第 4 节更新 SOT
3) 更新第 6 节检查单（必须全勾）
4) 将整个目录从 docs/wip/YYYYMMDD-topic/ 移动到 docs/archive/YYYYMMDD-topic/

## 6. WIP 检查单（必须全勾才能归档）
- [x] plan.md 已确认（PLAN 闸门已通过）
- [x] 代码改动已完成（IMPLEMENT 完成）
- [x] 基本自测已完成（记录命令/步骤与结果）
- [x] 已输出交付摘要并且用户验收通过（VERIFY 闸门已通过）
- [x] SOT 已更新（按第 4 节执行；列出更新的文件）
- [ ] 已归档：wip → archive（目录已移动）
