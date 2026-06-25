# 编码与标识符规范

Canonical 名称以本文件为准；中文仅作 Excel 展示别名。详见 [`glossary.md`](../glossary.md)。

## 标识符总表

| 标识符 | 中文 | 生成方 | 唯一性 | 可变性 | 可空 | 使用模块 | 禁止误用 |
|--------|------|--------|--------|--------|:----:|----------|----------|
| `custody_asset_code` | 托管房源主体号 | Excel/推导 | 产品内业务唯一（意图） | 否 | 发行否 | 全模块 | 当作 `asset_code` 写入新逻辑 |
| `source_asset_code` | 资产分笔号 | Excel | 分笔级 | 否 | 是 | 监控/还款 | 与 custody 混用 |
| `asset_code` | 资产编号（历史） | 导入历史 | `(product, asset_code)` DB 唯一 | 否 | 否 | trust_assets、监控、还款 | **新功能禁止扩散** |
| `business_asset_key` | 发行资产标识 | 计算 | **不唯一** | 随发行日变 | 否 | 发行 | 作主键/UNIQUE |
| `trust_product_id` | 信托产品 ID | 系统 | 全局唯一 | 否 | 否 | 全模块 | — |
| `trust_asset_id` | 底层资产 ID | 系统 upsert | 全局唯一 | 否 | 发行可空 | 监控/还款/逾期/风险 | — |
| `issue_date` | 发行日 | 用户导入参数 | — | — | 否 | **仅发行** | 在发行中用 `data_date` |
| `data_date` | 快照日期 | Excel/系统 | — | — | 否 | 监控/还款/逾期/风险 | 在发行中使用；还款核对勿依赖 |
| `repayment_date` | 还款业务日 | Excel | — | — | 是 | 还款 | 与 `data_date` 混为核对维度 |
| `migration_type` | 迁移类型 | Excel/推断 | — | 是 | 是 | 发行 | — |

---

## custody_asset_code

| 项 | 说明 |
|----|------|
| 中文含义 | **托管房源主体号**，跨模块识别同一套房源 |
| 生成方 | Excel（房源编码/托管房源号等别名）；或由 `source_asset_code` 推导 |
| 格式 | 通常 12 位数字；允许带后缀的变体（TODO：完整格式规范） |
| 使用模块 | 发行、监控、还款、逾期、风险、标记表 |
| 禁止误用 | 不要用 `asset_code` 或「房源编号」作为新字段名；Excel 别名应映射到本字段 |

---

## source_asset_code

| 项 | 说明 |
|----|------|
| 中文含义 | **资产分笔号**，同一托管房源下的分笔 |
| 生成方 | Excel「资产编号(房源)」 |
| 示例 | `101127075900-001` |
| 使用模块 | 监控、还款（发行表无此列） |
| 禁止误用 | 不等于 `custody_asset_code`；不要单独用分笔号做发行 business key |

---

## asset_code

| 项 | 说明 |
|----|------|
| 中文含义 | **历史兼容字段**，早期唯一标识底层资产 |
| 生成方 | 历史导入写入 `trust_assets.asset_code` |
| DB 约束 | `UNIQUE (trust_product_id, asset_code)` 仍存在 |
| 禁止误用 | **新逻辑不要扩散**；新代码应使用 `custody_asset_code` + `source_asset_code` |

---

## business_asset_key

| 项 | 说明 |
|----|------|
| 中文含义 | 发行资产冲突分析键 |
| 公式 | `{trust_product_id}:{issue_date}:{custody_asset_code}`（日期 ISO） |
| 唯一性 | **不唯一**；无 UNIQUE 索引 |
| 用途 | 发行 precheck 跨文件/同 Sheet 冲突分析 |
| 禁止误用 | 不得作主键；不得假设一行一 key |

---

## trust_product_id / trust_asset_id

| 项 | 说明 |
|----|------|
| `trust_product_id` | 系统主键，外键维度 |
| `trust_asset_id` | `trust_assets.id`；监控/还款/逾期/风险必填 FK；发行可选 |

---

## issue_date

| 项 | 说明 |
|----|------|
| 中文含义 | **发行业务日** |
| 使用模块 | **仅** `trust_product_issuance_asset_records` |
| 禁止误用 | 发行模块**无 `data_date`**；不得引入快照日期 |

---

## data_date

| 项 | 说明 |
|----|------|
| 中文含义 | **监控/业务快照日期**（Excel「统计日期」） |
| 使用模块 | 监控、逾期、风险；还款表有遗留列 |
| 禁止误用 | 不在发行使用；还款金额核对**不应**以 `data_date` 为主维度 |

---

## repayment_date

| 项 | 说明 |
|----|------|
| 中文含义 | **单笔还款实际发生日** |
| 使用模块 | `trust_repayment_detail_records` |
| 与 data_date | 导入时可能相同；新业务以本字段为准 |

---

## migration_type

| 项 | 说明 |
|----|------|
| 枚举 | `new_issuance`, `transfer`, `rollover`, `repackage`, `replenishment`（预留） |
| 默认 | 无转出产品 → `new_issuance`；有转出 → `transfer` |
| 使用模块 | 发行 |

---

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06 | M2 初稿 |
