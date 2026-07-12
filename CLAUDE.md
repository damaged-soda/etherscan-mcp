# 子仓面包屑

这个仓属于个人 fleet。**完整上下文先读 `/Users/leavan/work/personal/fleet/AGENTS.md` 与 `/Users/leavan/work/personal/fleet/STATE.md`**；本文件只放 etherscan-mcp 的局部约定。（同目录下也有等价的 `AGENTS.md`。）

## 本仓职责

CLI + MCP server，封装 Etherscan API V2（ABI / 源码 / 索引类查询）+ EVM JSON-RPC（`eth_call` / `eth_getStorageAt` / `eth_getLogs` / 区块 / 交易等只读调用），用于合约研判和链上数据抓取。本机以 `etherscan` CLI 暴露（wrapper 在 `~/ns/personal/bin/etherscan`，凭据从 0600 文件注入；skill 正本在 `~/ns/personal/skills/etherscan/`）；MCP 注册已于 2026-07-07 退役（决策见 `~/work/charter/TOOLING.md`），server 代码保留。

代码、模块结构、tool 清单、参数约定、环境变量见 [README.md](README.md)。

## 工作约定

- **普通 Python 库**，没有专门的 doc-driven workflow —— 直接改代码、跑 CLI 自测、提 PR 就行。
- 任何改动开新分支 + PR 给用户 review，不直接动 `main`。
- 文档语言中文；JSON key、代码标识符、API 字段名按官方英文。
- API / RPC 对齐变化（新链支持、参数语义改动、tool 增删）直接改代码 + 更新 README 的 tools 表 / 参数约定 / 环境变量章节，不再生成 plan / SOT / archive 三件套。
