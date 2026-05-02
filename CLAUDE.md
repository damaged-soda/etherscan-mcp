# 子仓面包屑

这个仓是 home-ops 系统的一片碎片。**完整上下文请先读 `~/work/home-ops/CLAUDE.md`** —— 那里有架构图、决策日志、运维手册和当前状态。（同目录下也有等价的 `AGENTS.md`，Claude Code / Codex / 其他 agent 都能找到入口。）

## 本仓职责

CLI + stdio MCP server，封装 Etherscan API V2（ABI / 源码 / 索引类查询）+ EVM JSON-RPC（`eth_call` / `eth_getStorageAt` / `eth_getLogs` / 区块 / 交易等只读调用），用于合约研判和链上数据抓取。当前已注册为本机 Claude Code + Codex 的 MCP server。

代码、模块结构、tool 清单、参数约定、环境变量见 [README.md](README.md)。

## 工作约定

- **普通 Python 库**，没有专门的 doc-driven workflow —— 直接改代码、跑 CLI 自测、提 PR 就行。
- 任何改动开新分支 + PR 给用户 review，不直接动 `main`。
- 文档语言中文；JSON key、代码标识符、API 字段名按官方英文。
- API / RPC 对齐变化（新链支持、参数语义改动、tool 增删）直接改代码 + 更新 README 的 tools 表 / 参数约定 / 环境变量章节，不再生成 plan / SOT / archive 三件套。
