# 编码与标识符规范

Canonical 名称以本文件为准；中文仅作 Excel 展示别名。详见 [`glossary.md`](../glossary.md)。

## 标识符总表

| 标识符 | 中文 | 生成方 | 唯一性 | 可变性 | 可空 | 使用模块 | 禁止误用 |
|--------|------|--------|--------|--------|:----:|----------|----------|
| `custody_asset_code` | 托管房源主体号 | Excel/推导 | 产品内业务唯一（意图） | 否 | 发行否 | 全模块 | 当作 `asset_code` 写入新逻辑 |
| `source_asset_code` | 资产分笔号（死列） | 历史 Excel | 分笔级 | 否 | 是 | 监控/还款（只读历史） | **停导入、停展示**；勿与 custody 混用 |
| `asset_code` | 资产主编号 | Excel 房源列左 12 / 历史 | `(product, asset_code)` DB 唯一 | **否**（已有非空不改） | 否 | trust_assets、监控、还款 | 已有值禁止 UPDATE 覆盖 |
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
| 生成方 | Excel「托管房源编码」；无托管列时 = 房源列左 12（与 `asset_code` 相同） |
| 格式 | 通常 12 位数字；允许带后缀的变体（TODO：完整格式规范） |
| 使用模块 | 发行、监控、还款、逾期、风险、标记表 |
| 禁止误用 | 不要用 `asset_code` 或「房源编号」作为新字段名；Excel 别名应映射到本字段 |
| 预检 | 监控/还款：房源列原文 ≠ 托管列 → ERROR（`needs_confirm`） |

---

## source_asset_code

| 项 | 说明 |
|----|------|
| 中文含义 | **资产分笔号**（历史）；列保留、**停导入停展示** |
| 生成方 | ~~Excel「资产编号(房源)」~~ → 已改写为 `asset_code` 左 12；新导入第三返回值恒为 `None` |
| 示例（历史） | `101127075900-001` |
| 使用模块 | 仅读历史数据；新写入禁止 |
| 禁止误用 | 不等于 `custody_asset_code`；不要单独用分笔号做发行 business key |

---

## asset_code

| 项 | 说明 |
|----|------|
| 中文含义 | **资产主编号**（监控/还款导入口径：Excel「资产编号(房源)」**左 12 位**） |
| 生成方 | 导入解析 `_primary_asset_code_from_trust_no`；无主编号时回填 |
| 可变性 | **否** — 已有非空值永不 UPDATE |
| DB 约束 | `UNIQUE (trust_product_id, asset_code)` 仍存在 |
| 禁止误用 | 不要把带后缀的完整房源号整值写入本字段 |

### 监控 / 还款编码口径（2026-07-21）

| 规则 | 说明 |
|------|------|
| 房源列 → `asset_code` | 仅左 12 |
| `source_asset_code` | 停导入、停展示 |
| 无托管列 | `custody_asset_code` = 左 12 |
| 例外 | 美好生活3号 Sheet「0612已还款」托管曾错，**不参与主编号推导**（与 [`product3_repay_0612_custody`](../../db/ops/fixes/product3_repay_0612_custody/) 一致） |

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
| 2026-07-21 | 监控/还款：房源列→asset_code 左 12；source 停导入展示；0612 排除 |
