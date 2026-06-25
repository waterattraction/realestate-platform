# 数据质量规范

与 [`identifiers.md`](identifiers.md)、[`glossary.md`](../glossary.md) 配套使用。

## 金额字段

| 规则 | 说明 |
|------|------|
| 存储类型 | `NUMERIC(18, 2)` |
| 默认 | 非负（表级 CHECK 或业务校验） |
| 比较容差 | `0.01`（`ingestion_cleanse.RECONCILIATION_TOLERANCE`） |
| API 展示 | `float` |

## 比例字段

| 规则 | 说明 |
|------|------|
| 存储 | 小数 `0~1`（如 `0.83`） |
| Excel | `0.83` 保持；`83` 除以 100（`to_rate_value`） |
| 展示 | 页面可格式化为百分比 |

## 日期字段

| 规则 | 说明 |
|------|------|
| 存储 | `DATE` |
| 展示 | `YYYY-MM-DD` |
| 发行 | 仅用 `issue_date` |
| 监控/逾期/风险 | `data_date` 为快照日 |
| 还款 | `repayment_date` 为业务日 |

## 时间字段

| 规则 | 说明 |
|------|------|
| 存储 | `TIMESTAMPTZ` |
| 展示 | 到分钟（TODO：统一时区 UTC+8 说明） |

## 字符串字段

| 规则 | 说明 |
|------|------|
| 导入 | `trim`；全角空格清理 |
| 空字符串 | 视为 NULL（业务字段） |
| 托管号 | `clean_custody_code`：去 tab、整数化浮点 |

## Excel 错误值

匹配模式：`#NAME?` `#REF!` `#VALUE!` `#N/A` `#DIV/0!` `#NULL!` `#NUM!`

| 场景 | 处理 |
|------|------|
| 必填字段 | 行 failed |
| 可选字段 | 置 NULL + warning |

## 导入 Action 状态机

| action | 含义 | 可导入 | 用户操作 |
|--------|------|:------:|----------|
| `import` | 新数据，无 scope 冲突 | 是 | 直接导入 |
| `overwrite` | 同 scope 已有数据，将 DELETE 后 INSERT | 是 | 确认覆盖 |
| `skip` | 与库内完全一致（还款） | 否 | 跳过 |
| `needs_confirm` | 跨文件重复/冲突/需人工确认 | 是* | 勾选 confirm |
| `failed` / `reject` | 解析失败或未确认 | 否 | 修正 Excel |

\* 发行/还款需在请求中传 `confirm_sheet_keys`。

### warning vs needs_confirm vs failed

| 级别 | 含义 | 示例 |
|------|------|------|
| **warning** | 可导入，数据质量提醒 | 城市为空、转出产品未匹配、折扣率为空 |
| **needs_confirm** | 可导入但存在业务风险 | 跨文件同 business_asset_key 金额冲突 |
| **failed** | 不可导入 | 缺核心列、解析错误、未 confirm |

## 空值处理

| 模块 | 规则 |
|------|------|
| 发行必填 | 缺 custody/金额 → 行 failed |
| 发行可选 | 空 → NULL；统计 `*_blank_count` |
| 还款 | 缺 repayment_date → 行 failed |
| 监控 | 缺 data_date → failed |

## 重复处理

| 模块 | 规则 |
|------|------|
| 发行 | 同 Sheet 同 `business_asset_key` → warning；跨文件同 key → needs_confirm |
| 还款 | 五字段指纹；跨文件 overlap → needs_confirm |
| 监控 | 同批次重复 → precheck 处理；历史重复见 ops 清理 |

## 模块特例

- **发行无 `data_date`**（见 `issuance_assets` 字典）
- **还款 `data_date` 遗留**：不与 `repayment_date` 混用于新核对逻辑
- **覆盖导入**：scope = `trust_product_id + issue_date + source_file + source_sheet`（发行）

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06 | M2 初稿 |
