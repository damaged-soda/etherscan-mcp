---
name: etherscan
description: >-
  EVM 链上数据只读查询：验证合约 ABI/源码、交易与回执、token 转移、事件日志、
  storage slot、eth_call(含历史序列)、keccak/单位换算。需要查合约、查交易、
  抓链上数据、做合约研判时使用。
argument-hint: <subcommand>
user-invocable: true
allowed-tools: Bash(etherscan:*)
---

# Etherscan / EVM 链上数据 CLI

使用 `etherscan` CLI(personal 域)查询 Etherscan API V2 与 EVM JSON-RPC 只读
数据。凭据由 wrapper 从 0600 文件注入,不要把 API key 写进命令行、URL 或文件。
只读:不签名、不广播交易。

## CLI 摘要

```bash
etherscan <subcommand> [options]   # 全部输出 JSON;etherscan --help 看环境变量
```

| 子命令 | 用途 |
|---|---|
| `fetch` | 验证合约 ABI + 源码(`--inline-limit`/`--force-inline` 控制内联量) |
| `get-source-file` | 单个源文件,支持 `--offset/--length` 分块读大文件 |
| `get-contract-creation` | 合约创建者、创建 tx、创建区块 |
| `detect-proxy` | EIP-1967 slot 探测 proxy implementation/admin |
| `list-transactions` | 地址的普通交易列表(块区间 + 分页) |
| `list-token-transfers` | ERC20/721/1155 转移列表(`--token-type`) |
| `query-logs` | 按 topics + 块区间查事件日志 |
| `get-storage-at` | eth_getStorageAt 读原始 slot |
| `call-function` | eth_call 只读调用,ABI 可用时自动解码(`--function`+`--args` 或裸 `--data`) |
| `call-function-series` | 同一函数按块区间批量历史采样(需 archive RPC) |
| `encode-function-data` | 函数签名+参数 → selector + calldata |
| `keccak` | keccak-256(`--input-type text|hex|bytes`) |
| `get-transaction` | 单笔交易 + 回执 |
| `get-transaction-summary` | 一次拿 tx 摘要:gas、注解地址、解码 ERC20 流向;`--compact` 出套利向摘要 |
| `get-block` / `get-block-time` | 区块 / 区块时间(latest、十进制、0x hex) |
| `list-chains` / `resolve-chain` | 支持链清单 / 网络名解析 chainid(带 free-tier caveats) |
| `convert` | hex/dec/human/wei/gwei/eth 单位换算(`--decimals`) |

## 常用例子

```bash
# 拿 USDT 的 ABI 与合约元数据(源码超限自动省略)
etherscan fetch --address 0xdAC17F958D2ee523a2206206994597C13D831ec7

# 只读调用:balanceOf,数组参数一律 JSON
etherscan call-function --address 0xdAC17F958D2ee523a2206206994597C13D831ec7 \
  --function 'balanceOf(address)' --args '["0x47ac0Fb4F2D84898e4D9E7b4DaB3C24507a6D503"]' --decimals 6

# ERC20 Transfer 日志(topic0 可先用 keccak 算)
etherscan query-logs --address 0xdAC17F958D2ee523a2206206994597C13D831ec7 \
  --topics '["0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"]' \
  --from-block 20000000 --to-block latest --offset 10

# 交易摘要(研判一笔套利/清算先跑这个)
etherscan get-transaction-summary --tx-hash 0x... --compact

# 其他链:--network 收链名或 chainid;先 resolve-chain 看 free-tier 限制
etherscan resolve-chain --network base
etherscan fetch --address 0x... --network 8453
```

## 注意

- 数组参数(`--args`、`--topics`)必须是 JSON 数组字符串;topic 通配位用 `null`。
- Base/BSC 等链的 `list-transactions`/`list-token-transfers` 在 Etherscan free
  tier 返回空,`resolve-chain` 的 caveats 会提示;改用日志或 RPC 侧能力。
- `call-function-series` 需要该链 `RPC_URL_<chainid>` 指向 archive 节点。
- 内核与参数语义详见 `~/work/personal/etherscan-mcp/README.md`。
