# 数据披露快照

披露页将模版列结果冻结为不可变副本，与导入事实表分离。

## 表

| 表 | 用途 |
|----|------|
| `disclosure_snapshots` | 快照头：`repayment` / `monitor`、`as_of_date`、还款可选 `as_of_start_date`、`frozen_at`、`product_ids[]`、行数、备注 |
| `disclosure_repayment_rows` | 还款明细模版列物化（`overdue_days` 列保留兼容，披露模版已不再展示） |
| `disclosure_repayment_plan_rows` | 回款计划模版列物化 |
| `disclosure_monitor_rows` | 资产监控披露列物化（含 `overdue_days`；`asset_status` 含业务态/M 级覆写） |

Migration：`db/migrations/20260720_disclosure_snapshots.sql`、`db/migrations/20260721_disclosure_monitor_overdue_days.sql`、`db/migrations/20260721_disclosure_as_of_start.sql`

## 业务规则

| 项 | 规则 |
|----|------|
| 还款时点 UI | **披露开始日** + **截止日**（默认含首尾共 7 天：开始日=截止日−6） |
| 还款裁切 | 明细 `repayment_date = 截止日` 且 `actual_repayment_amount > 0`；计划按产品取 `data_date ≤ 截止日` 最新批次 |
| 手工结算（还款活数据） | 当期实际还款：叠加 `[开始日,截止日]` 内结算；累计已还/剩余应还、回款计划已还/剩余：叠加**全部**未作废结算；区间内有结算但无截止日事实行时追加虚拟行。虚拟行：当前还款方=`repayer`；当期计划还款金额=当期实际还款金额；初始受让装修金额取自该资产回款计划 `initial_transfer_amount` |
| 还款明细列 | 不含「当期逾期天数」 |
| 归属 | 置换转入 / 回购 / 发行按业务日最新定产品（**仅相对截止日**，不受开始日影响）；同日多事件报错不取数；无事件保留原产品（`disclosure_attribution`） |
| 三列 | 置换→转入快照；回购→回购资产；发行→监控表；映射 `initial_transfer/repaid/remaining` → 装修/累计/剩余 |
| 已回购 | 截止日前已回购：明细与计划排除；监控状态「已回购」 |
| 已置换转出 | 转出方产品监控披露状态「已置换转出」 |
| 监控时点 UI | **统计日期** = `trust_asset_monitor_records.data_date`（单日，不变） |
| 监控手工结算 | 已还款金额 / 剩余还款金额叠加该资产**全部**未作废手工结算（不改统计日） |
| 监控资产状态 | 优先级：①已回购 / 已置换转出（高于 M 级）；②活跃「重度逾期」跟进→重度；③M 级（ES→提前结清，M0→正常，M0.5/M1/M1+→轻度，SD→重度）；④导入原值。转入方不标「已置换转出」，按 M 级 |
| 监控逾期天数 | 披露列在「资产状态」之后。仅状态为「轻度」「重度」时展示；「已回购」「已置换转出」「正常」等置空（不影响监控事实表与逾期计算） |
| 产品 | 可多选；冻结须至少选一个 |
| 多次冻结 | 同产品同时点允许；以 `frozen_at` 区分 |
| 删除 | 物理删除 + 确认；`frozen_at` 满 30 天不可删 |
| 还款快照导出 | 按产品拆多份 xlsx 打 ZIP；ZIP=`还款明细披露信息-{YYYYMMDDHHMM}.zip`（冻结时刻·北京时间）；内含 `{产品名}-还款明细披露信息-{YYYYMMDD}.xlsx`；Sheet `{YYYYMMDD}已还款` / `回款计划` |
| 监控导出 | 活数据 / 快照均按产品拆多份 xlsx 打 ZIP；ZIP=`资产监控表-{YYYYMMDDHHMM}.zip`；内含 `{产品名}-资产监控表-{YYYYMMDD}.xlsx`；Sheet `资产监控表` |

## 页面入口

- `/disclosure/repayment` — 还款明细披露
- `/disclosure/monitor` — 资产监控披露
- 主页 §5「数据披露」

列契约 SSOT：`backend/app/assetinfo_templates.py`（监控披露用 `DISCLOSURE_MONITOR_TEMPLATE_COLUMNS`）
