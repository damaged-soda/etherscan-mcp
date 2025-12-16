# Codex MCP 文档同步 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：当前 Codex MCP 使用说明不足，用户在执行 `codex mcp add` 遇到参数错误；需对齐官方文档并更新 SOT。
- 目标：阅读 https://developers.openai.com/codex/mcp/ ，整理正确的 MCP CLI 添加方式（尤其 `codex mcp add <NAME> -- <COMMAND>` 语法），补充到 SOT。
- 非目标：不改代码、不改 MCP 实现，仅更新文档。

## 1. 影响范围（必须）
- 影响的 repo：无代码改动，仅文档（docs）
- 影响的模块/目录/文件：docs/sot/overview.md（或相关 SOT 文档，补充 MCP 使用说明）
- 外部可见变化：SOT 增补 Codex MCP 正确用法示例。

## 2. 方案与改动点（必须）
- repo: docs
  - 改动点：阅读官方页面，提取正确的 `codex mcp add` CLI 语法和示例；在 SOT 中添加 MCP 配置与调用指引。
  - 新增/修改的数据结构：无。
  - 关键逻辑说明：明确 `codex mcp add <NAME> -- <COMMAND...>` 的用法，含环境变量示例。

## 3. 自测与验收口径（必须，可执行）
- 检查：SOT 文档中包含可直接复制的 `codex mcp add` 示例，参数顺序正确。
- 通过标准：示例符合官方语法（NAME 位置、`--` 分隔、env/cwd/args 写法清晰），无歧义。

## 4. SOT 更新清单（必须）
- docs/sot/overview.md：补充 Codex MCP 添加和使用说明（含命令示例）。
- 其他：无。

## 5. 完成后归档动作（固定）
1) 按第 4 节更新 SOT
2) 将整个目录从 docs/wip/YYYYMMDD-topic/ 移动到 docs/archive/YYYYMMDD-topic/
