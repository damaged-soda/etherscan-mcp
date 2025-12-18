# fetch_contract 缺少 json import 修复 技术变更计划（Plan）

## 0. 背景与目标（简短即可）
- 背景：调用 `fetch_contract` 报错 `name 'json' is not defined`，原因是 service.py 缺少 json 导入。
- 目标：恢复 json 导入，确保 fetch_contract 正常工作。
- 非目标：不改动其他逻辑。

## 1. 影响范围（必须）
- 影响的 repo：etherscan-mcp
- 影响的模块/目录/文件：app/service.py
- 外部可见变化：fetch_contract 不再报 json 未定义。

## 2. 方案与改动点（必须）
- repo: etherscan-mcp
  - 改动点：在 service.py 重新导入 json。
  - 新增/修改的接口或数据结构：无
  - 关键逻辑说明：仅修复缺失导入。

## 3. 自测与验收口径（必须，可执行）
- 自测：运行 fetch_contract 示例地址，确认不再抛 json 未定义。
- 通过标准：无报错，返回合同数据。

## 4. SOT 更新清单（必须）
- 无（行为恢复，无需 SOT 变更）

## 5. 完成后归档动作（固定）
1) 输出交付摘要并请求验收
2) 验收通过后，若无 SOT 变更，直接归档

## 6. WIP 检查单（必须全勾才能归档）
- [x] plan.md 已确认（PLAN 闸门已通过）
- [x] 代码改动已完成（IMPLEMENT 完成）
- [x] 基本自测已完成（记录命令/步骤与结果）
- [x] 已输出交付摘要并且用户验收通过（VERIFY 闸门已通过）
- [ ] 已归档：wip → archive（目录已移动）
