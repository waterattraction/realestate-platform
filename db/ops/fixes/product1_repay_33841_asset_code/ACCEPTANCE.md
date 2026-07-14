# Acceptance — product1_repay_33841_asset_code

| 项 | 值 |
|----|-----|
| 决策 | `source_asset_code` 不改；导入逻辑不改 |
| 范围 | 还款 `id=33841`，仅 `asset_code` |
| 风险 | P3 |
| Apply 时间 | 2026-07-14 |
| 备份表 | `_ops_backup_product1_repay_33841_asset_code`（保留） |

## 验收检查

- [x] `id=33841.asset_code = 101130798182`
- [x] `source_asset_code` 仍为 `101135047520`
- [x] `custody_asset_code` 仍为 `101135047520`
- [x] 全库 `r.asset_code IS DISTINCT FROM ta.asset_code` = 0
- [x] 备份表 `_ops_backup_product1_repay_33841_asset_code` 1 行
