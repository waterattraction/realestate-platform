# 逾期跟进工作台 V2.2 — 具体实现方案（影响评估）

| 项 | 值 |
|----|-----|
| 状态 | 实施前方案；**不含代码变更** |
| 依据 | [`overdue_followup_workbench.md`](./overdue_followup_workbench.md) V2.2 |
| 目的 | 对照当前库表 / 代码 / 页面，列出分期改动、影响面与风险 |

---

## 1. 现状 vs 目标（差距总览）

### 1.1 数据库

| 能力 | 现状 | V2.2 目标 | 差距 |
|------|------|-----------|------|
| 跟进主体 | `trust_overdue_followups` 绑 **分笔** `trust_asset_id` | `followup_cases` 绑 **托管** `custody_asset_code` | Phase 2 新表 |
| 跟进语义 | 一行台账 **UPDATE 覆盖** | `entries` **只追加** | Phase 2 行为变更 |
| 活跃案件 | 每分笔最多 1 条 open/in_progress（应用层） | 每托管最多 1 条活跃 case | 主体从分笔→托管 |
| 附件 | 无 | `followup_attachments` | Phase 3 |
| 信托标注 | `trust_asset_trust_marks` 已有 | 工作台展示 + 现有 PATCH | Phase 1 只读接入 |
| 发行/还款/监控 | 事实表齐全 | Repo 按托管读取 | Phase 1 扩展 Repo |
| 风险扩展列 | `trust_overdue_followups` 有 `sla_*`、`risk_*` | 新模型 **不迁** SLA 列到 case（Ops 投影承担） | 需明确 risk_hub 边界 |

### 1.2 代码

| 模块 | 现状 | V2.2 目标 |
|------|------|-----------|
| 工作台读 | `main.py` → `fetch_overdue_workbench()` **大 SQL + JOIN** | `OverdueWorkbenchService.get_detail()` 唯一读路径 |
| 工作台写 | 3 条 POST：`/followups`、`/update`、`/resolve` | 单条 `POST .../followups/entries` |
| 检查逻辑 | `main.py` `_recon_checks_for_asset()` | `checks_service.py` |
| Ops | `OverdueOpsService` + `/overdue/ops/{identity_id}` **独立** | `ops_service.suggest()` 嵌入 `get_detail()` |
| Repo | `issuance/monitor/repayment/followup` 多按 **trust_asset_id** | 增加 **custody + product** 维度查询 |
| HTML | `render_overdue_workbench_html()` 在 `main.py` ~400 行内联 | `html/render.py` 纯 DTO 渲染 |
| M3 Workbench | `/asset-workbench/{id}` 独立 | **不合并读路径**；可互跳 `identity_id` |

### 1.3 页面（运营可见）

| 区块 | 现状工作台 | V2.2 目标 |
|------|------------|-----------|
| 顶栏 KPI | 有（分笔维度） | 有（托管汇总 + 数据日期） |
| ① 发行信息 | **无** | 有（多行 issuance） |
| ② 还款明细 | 仅 `detail_total_repaid` 用于核对 | 汇总 + 期次表 |
| ③ 监控分笔 | 左侧队列按分笔 | 托管汇总 + 分笔列表 |
| ④ 金额检查 | 有（2 项） | 有（迁入 checks_service） |
| ⑤ 信托标注 | **无**（仅在 `/overdue` 列表） | 有（展示 + 下拉 PATCH） |
| ⑥ Ops 建议 | **无** | 有（只读） |
| ⑦ 时间线 | 简单 history 表（旧 followups） | repayment + followup entries 合并 |
| 底栏录入 | 创建 / 更新 / 解决 **三分支** | **单一**「保存本次跟进」 |
| 左侧队列 | 同托管下 **分笔切换** | Phase 1 可保留；Phase 3 可加产品待办队列 |

---

## 2. 数据库变更方案

### 2.1 Phase 1 — 无 migration

只读聚合，**不改表**。依赖现有表：

- `trust_product_issuance_asset_records`
- `trust_asset_monitor_records`
- `trust_repayment_detail_records`
- `trust_asset_trust_marks`
- `trust_overdue_followups`（历史只读）
- `trust_assets`（分笔解析）

**Repo 扩展（非 DDL）**：为 custody 维度增加查询方法（见 §3.2）。

### 2.2 Phase 2 — 跟进写模型

**新 migration 文件（建议名）**：`db/migrations/20260xxx_overdue_followup_cases_entries.sql`

#### 表 A：`trust_overdue_followup_cases`

```sql
-- 示意，评审后定稿
CREATE TABLE trust_overdue_followup_cases (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trust_product_id    BIGINT NOT NULL REFERENCES trust_products (id),
    custody_asset_code  VARCHAR(128) NOT NULL,
    data_date           DATE NOT NULL,
    status              VARCHAR(32) NOT NULL DEFAULT 'open',
    owner_name          VARCHAR(100),
    opened_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at           TIMESTAMPTZ,
    last_follow_up_at   TIMESTAMPTZ,
    created_by          VARCHAR(64),
    updated_by          VARCHAR(64),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 每托管仅一条活跃案件（PostgreSQL 部分唯一索引）
CREATE UNIQUE INDEX uq_followup_cases_active_custody
    ON trust_overdue_followup_cases (trust_product_id, custody_asset_code)
    WHERE status IN ('open', 'in_progress');

CREATE INDEX idx_followup_cases_product_custody
    ON trust_overdue_followup_cases (trust_product_id, custody_asset_code);
```

#### 表 B：`trust_overdue_followup_entries`

```sql
CREATE TABLE trust_overdue_followup_entries (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    case_id             BIGINT NOT NULL REFERENCES trust_overdue_followup_cases (id),
    entry_type          VARCHAR(32) NOT NULL DEFAULT 'manual',
    status_snapshot     VARCHAR(32),
    overdue_reason      TEXT,
    follow_up_plan      TEXT,
    trust_feedback      TEXT,
    note                TEXT,
    owner_name          VARCHAR(100),
    created_by          VARCHAR(64),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_followup_entries_case_created
    ON trust_overdue_followup_entries (case_id, created_at DESC);
```

#### 旧表策略

| 对象 | Phase 2 | Phase 3 |
|------|---------|---------|
| `trust_overdue_followups` | **保留**；只读进 timeline | 迁移脚本 → cases/entries；停止写入 |
| `risk_v2` 扩展列（`sla_*` 等） | **不动**；`risk_hub` 仍写旧表直至单独排期 | 评估是否迁到 Ops 或废弃 |

#### 文档同步（Phase 2 前）

- `docs/data_dictionary/` 新增 cases / entries
- `docs/canonical/status_dictionary.md` 补充 case / entry_type
- `docs/data_dictionary/overdue.md` 标注旧表 deprecated

### 2.3 Phase 3 — 附件

```sql
CREATE TABLE trust_overdue_followup_attachments (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entry_id            BIGINT NOT NULL REFERENCES trust_overdue_followup_entries (id),
    file_name           VARCHAR(500) NOT NULL,
    stored_path         VARCHAR(1000) NOT NULL,
    content_type        VARCHAR(128),
    file_size           BIGINT,
    attachment_type     VARCHAR(16) NOT NULL,  -- image | file
    uploaded_by         VARCHAR(64),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_followup_attachments_entry
    ON trust_overdue_followup_attachments (entry_id);
```

文件落盘：`{ASSET_UPLOAD_DIR}/followups/{case_id}/{entry_id}/`（对齐 `assetinfo_upload.save_batch_files` 模式）。

### 2.4 列表 SQL 影响（`/overdue` overview）

**现状**（`main.py`）：

```text
_custody_followup_count_sql() → COUNT(DISTINCT f.id) FROM trust_overdue_followups
_custody_has_follow_up_sql()  → EXISTS open/in_progress ON trust_asset_id
```

**Phase 2 后改为**：

```text
followup_count → COUNT(entries) JOIN cases ON custody
has_follow_up  → EXISTS active case OR count > 0（产品确认：建议「有活跃 case」）
```

**影响**：列表「跟进次数」数字可能变化（从台账行数 → 跟进次数）；需运营沟通。

---

## 3. 代码变更方案

### 3.1 目标目录（V2.2）

```
backend/app/
  service/
    overdue_workbench.py      # NEW — get_detail(), resolve_scope()
    checks_service.py         # NEW — 从 main.py 抽出
    ops_service.py            # NEW 薄封装 — suggest(facts) 调现有 engines
  repo/
    issuance_repo.py          # EXTEND — fetch_by_custody()
    monitor_repo.py           # EXTEND — fetch_splits_by_custody(), fetch_custody_aggregate()
    repayment_repo.py         # EXTEND — fetch_by_custody()
    followup_repo.py          # EXTEND — cases/entries CRUD（Phase 2）
  api/
    overdue_workbench.py      # NEW — GET detail
    followups.py              # NEW — POST entries（Phase 2）
  html/
    render.py                 # NEW — 从 main.py 迁出
    overdue_workbench.html    # 可选：模板字符串外置
  main.py                     # SHRINK — 路由委托 + 逐步删旧函数
```

**不新建**：独立 ScopeResolver 包、Projection Builder 家族、Timeline Builder 包。

### 3.2 Phase 1 — 读通（详细任务）

| # | 任务 | 说明 | 影响文件 |
|---|------|------|----------|
| 1.1 | 定义 `OverdueWorkbenchDetailDTO` | Typed dict 或 Pydantic model | `service/overdue_workbench.py` 或 `dto/` |
| 1.2 | `resolve_scope(product, custody, data_date?)` | 返回 `trust_asset_ids[]`、`identity_id`（首条 issuance.id）、`resolved_data_date` | `overdue_workbench.py` |
| 1.3 | 扩展 `IssuanceRepo.fetch_by_product_custody()` | `ORDER BY issue_date DESC` | `issuance_repo.py` |
| 1.4 | 扩展 `MonitorRepo` 托管聚合 + 分笔列表 | 逻辑对齐 `main._monitor_custody_ctes` 但 **分多次查询** 或单表聚合 | `monitor_repo.py` |
| 1.5 | 扩展 `RepaymentRepo.fetch_by_product_custody()` | 汇总 + items | `repayment_repo.py` |
| 1.6 | 抽出 `checks_service.run(monitor, repayment)` | 迁 `_recon_checks_for_asset` | `checks_service.py` |
| 1.7 | `ops_service.suggest(facts)` | 包装 `OverdueOpsService.get_ops(identity_id)` 或直调 engines，输出简化 DTO | `ops_service.py` |
| 1.8 | `get_detail()` 组装 | repo → checks → ops → timeline merge | `overdue_workbench.py` |
| 1.9 | 读 marks | `SELECT` from `trust_asset_trust_marks`（可 inline repo 或小函数） | `overdue_workbench.py` |
| 1.10 | 读旧 followup 历史 | `FollowupRepo` 按 custody 下所有 `trust_asset_id` | `followup_repo.py` |
| 1.11 | `GET /overdue/workbench/detail` | 新 API | `api/overdue_workbench.py` |
| 1.12 | 改 HTML 路由 | `get_detail()` → `render.py` | `main.py`, `html/render.py` |
| 1.13 | `/overdue/workbench/data` | **改为** 调 `get_detail()` 或 301 到 `/detail` | `main.py` |
| 1.14 | 注册路由 | `app.include_router` | `main.py` |

**`get_detail()` 伪流程**：

```text
1. resolve_scope → product, custody, data_date, trust_asset_ids[], identity_id
2. parallel/sequential repo reads（无 JOIN）
3. checks_service.run(...)
4. if identity_id: ops_service.suggest(...)
5. timeline = merge(repayment_events, legacy_followups + placeholder for entries)
6. assemble DTO
```

**保留不动（Phase 1）**：

- `POST /overdue/workbench/followups*` 三条写路由（旧 CRUD）
- `fetch_overdue_workbench()` 可暂留，标记 deprecated，HTML 切走后 Phase 3 删除

**与 M3 关系**：

- **不修改** `AssetApplicationService` / `timeline_builder.py` 读路径
- `event_repo.fetch_followup_events` 仍读旧表；Phase 2 后扩展读 entries

### 3.3 Phase 2 — 写通

| # | 任务 | 说明 |
|---|------|------|
| 2.1 | 执行 migration cases + entries | §2.2 |
| 2.2 | `FollowupRepo.upsert_case_and_insert_entry()` | 事务：UPSERT case + INSERT entry |
| 2.3 | `POST /overdue/workbench/followups/entries` | multipart 预留字段，Phase 3 接 files |
| 2.4 | 废弃旧 POST 三条 | 返回 410 或内部转发到新 API（过渡期） |
| 2.5 | 改 `_custody_followup_count_sql` | `main.py` overview |
| 2.6 | `timeline` 读新 entries | `get_detail()` 内 merge |
| 2.7 | escalate → system entry | `ops_service` 或 entries handler 内可选分支 |

**`main.py` 删除/替换函数**：

| 函数 | 处置 |
|------|------|
| `create_overdue_followup_record` | Phase 2 废弃 → 调 `followup_repo` |
| `update_overdue_followup_record` | 废弃（违背 entry-only 原则） |
| `fetch_overdue_followups` | 保留供列表/迁移；工作台改读 repo |

### 3.4 Phase 3 — 增强

| # | 任务 |
|---|------|
| 3.1 | attachments migration + `FollowupRepo.insert_attachments` |
| 3.2 | `GET/DELETE .../attachments/{id}` 鉴权下载 |
| 3.3 | `GET /overdue/ops/queue?trust_product_id=` 组合队列（扩展 `queue_engine` 入参） |
| 3.4 | 左侧栏改「产品待办」可选 |
| 3.5 | 旧表数据迁移脚本 `db/ops/migrations/...` |
| 3.6 | 删除 `fetch_overdue_workbench`、`render` 内联旧版 |

### 3.5 横切：需评估但不在本方案内的代码

| 模块 | 现状 | 风险 |
|------|------|------|
| `risk_hub.py` | 自动 CREATE/UPDATE `trust_overdue_followups` | **双写源**；Phase 2 后需冻结或改读 cases |
| `event_repo.fetch_followup_events` | 读旧表 | Phase 2 需同步 entries |
| `projection/operations_builder` | 读旧 followup | 可选延后对齐 M3 |
| `OverdueOpsService.get_queue(identity_id)` | 单 identity | Phase 3 扩展 portfolio queue |

---

## 4. 页面变更方案

### 4.1 布局重构（Phase 1）

**现状结构**：

```text
[ 左侧：同托管分笔队列 ] | [ 右侧：KPI + 核对 + 跟进表单 + 历史表 ]
```

**目标结构**：

```text
TOP: 托管号 · 产品 · M级 · 数据日期

[ 左：分笔队列 Phase1 / 产品队列 Phase3 ] | [ 右：7 个只读 Panel ]

BOTTOM: 单一跟进表单（Phase 1 仍可走旧 POST；Phase 2 改 entries）
```

### 4.2 Panel 级改动清单

| Panel | Phase 1 UI | 数据来源字段 |
|-------|------------|--------------|
| 发行 | 新增折叠区，多卡片 | `dto.issuance_records[]` |
| 还款 | 新增表格 | `dto.repayment.items[]` |
| 监控 | 增强：托管汇总行 + 分笔表 | `dto.monitor.custody`, `.splits[]` |
| 检查 | 迁移现有表格 | `dto.checks.*`（含 `passed` 供 render 用 class） |
| 标注 | 新增；复用列表页下拉 JS 模式 | `dto.trust_mark` + PATCH API |
| Ops | 新增只读卡片 | `dto.ops.recommended_actions`, `.sla` |
| 时间线 | 替换 history 表为统一时间线 | `dto.timeline[]` |

### 4.3 底栏表单（Phase 2）

| 现状 | 目标 |
|------|------|
| 「创建跟进」/「更新」/「标记已解决」三个 form | **一个** form → `POST .../entries` |
| `trust_asset_id` hidden | 改为 `trust_product_id` + `custody_asset_code` hidden |
| 无 status 下拉（创建时固定 open） | 显式 status：open / in_progress / resolved / closed |
| 无附件 | Phase 3：`enctype=multipart/form-data` |

### 4.4 `render.py` 约束（Phase 1 验收）

- 函数签名：`render_overdue_workbench_html(dto: dict, page_user: str) -> str`
- **禁止**：`engine.connect()`、`if overdue_days > 30`（应用层判断改在 service，DTO 带 `is_overdue_highlight`）
- 允许：`|safe` 等价转义、`dto.checks.balance_equation.passed` 选 CSS class

### 4.5 路由与链接影响

| URL | 变更 |
|-----|------|
| `/overdue/workbench?...` | 保留；内部实现换 `get_detail()` |
| `/overdue/workbench/data` | 对齐新 DTO 或重定向 `/detail` |
| `/overdue/workbench/detail` | **新增** JSON |
| `/overdue` 列表 → 工作台深链 | **不变** |
| `/overdue/custody-marks` PATCH | **不变** |

---

## 5. 分期交付与工作量粗估

| Phase | DB | 后端 | 前端 HTML | 可并行 |
|-------|:--:|:----:|:---------:|--------|
| **1 读通** | 0 | 中（~8–12 文件） | 大（Panel 全增） | Repo 扩展 ∥ checks 抽出 |
| **2 写通** | 小（2 表） | 中 | 中（表单合一） | migration ∥ API |
| **3 增强** | 小（1 表） | 中 | 小 | 迁移脚本可晚于附件 |

**建议人日（1 人，含自测）**：

- Phase 1：5–8 天（Repo + service + 页面 Panel 为主）
- Phase 2：3–5 天（migration + 写路径 + overview 计数）
- Phase 3：3–4 天（附件 + 队列 + 清理）

---

## 6. 风险登记与缓解

| ID | 风险 | 等级 | 说明 | 缓解 |
|----|------|:----:|------|------|
| **R1** | `risk_hub` 与 cases 双写 | **高** | 风险中台仍 INSERT/UPDATE 旧 `trust_overdue_followups` | Phase 2 前冻结 risk_hub 自动建案，或限定只写旧表、工作台只读新表并标注来源 |
| **R2** | 托管 vs 分笔主体切换 | **高** | 现台账按分笔；新 case 按托管 | 迁移时按 custody 合并；UI 时间线展示关联分笔 |
| **R3** | `followup_count` 口径变化 | **中** | 列表数字变含义 | 上线说明；可选短期双列展示 |
| **R4** | Phase 1 新旧读路径并存 | **中** | `/data` 与 `/detail` 结构不一致 | Phase 1 末统一；旧 `fetch_overdue_workbench` 删前只保留一处 |
| **R5** | Repo 多次查询性能 | **中** | 替代一条大 SQL | 单托管分笔数通常 <10；`data_date` 走索引；必要时 service 内短缓存 |
| **R6** | Ops identity 依赖 issuance | **中** | 无发行行则 ops 空 | 空态 Panel；不阻塞跟进 |
| **R7** | HTML 迁移遗漏业务 if | **中** | render 内藏逻辑 | Code review + 「render 禁止 connect」lint 约定 |
| **R8** | 旧 POST 书签/脚本 | **低** | 运营习惯 | Phase 2 过渡期 307 转发到新 API |
| **R9** | 附件安全 | **中** | 路径遍历、未授权下载 | 鉴权路由；stored_path 不暴露；复用 ingestion 校验 |
| **R10** | M3 文档与实现漂移 | **低** | m3.2 写 followup 事实表名仍为旧表 | Phase 2 后补文档；本方案明确工作台不走路径 asset-workbench 读 |
| **R11** | 活跃 case 唯一约束 | **中** | 并发双开案 | DB 部分唯一索引 + 应用层捕获冲突提示 |
| **R12** | escalate 写 system entry | **低** | 与「Ops 不写」例外混淆 | UI 明确「系统记录」；entry_type=system 不可当人工跟进 |

---

## 7. 回归测试清单（按 Phase）

### Phase 1

- [ ] `/overdue` 点托管号进入，发行/还款/监控/检查/标注/Ops/时间线有数据或空态
- [ ] 无发行记录：发行空态，其余正常
- [ ] 检查异常行高亮与 `/overdue/reconciliation` 单户结论一致
- [ ] `GET /detail` 与 HTML 展示一致
- [ ] 旧跟进创建/更新仍可用
- [ ] PATCH custody-marks 在工作台可用

### Phase 2

- [ ] 连续保存 3 次 → 3 条 entry、case 状态更新
- [ ] 关闭案件后再逾期可新开
- [ ] 列表 `followup_count` 与 entry 数一致
- [ ] 旧 followups 在时间线标「历史台账」
- [ ] 同一托管两分笔不再有两个活跃「案件」

### Phase 3

- [ ] 上传图片/文件后时间线可下载
- [ ] 未登录下载 401
- [ ] 产品队列左侧栏排序与 `/overdue` 筛选一致
- [ ] 旧表迁移后无孤儿 entry

---

## 8. 实施顺序建议

```text
Week 1–2  Phase 1
  ├── Repo 扩展（issuance/monitor/repayment/followup custody）
  ├── checks_service + ops_service.suggest
  ├── overdue_workbench.get_detail + GET /detail
  └── html/render.py 新 Panel + 旧写表单暂留

Week 3    Phase 2
  ├── migration + followup_repo 写
  ├── POST entries + 废弃旧 POST
  ├── overview followup_count SQL
  └── 与 risk_hub 边界会议（R1）

Week 4    Phase 3
  ├── attachments
  ├── ops queue + 左侧栏
  ├── 数据迁移 + 删 main.py 旧 SQL
  └── 回归 + 运营 brief
```

---

## 9. 明确不改动的范围

- 监控 / 还款 / 发行 **导入链路**
- `trust_asset_trust_marks` 表结构
- `/overdue` 列表 M 级分桶逻辑（仅 followup_count SQL 变）
- `/asset-workbench` MVP（独立演进）
- M3.1 identity migration（不阻塞 Phase 1–2）

---

## 10. 相关文档

| 文档 | 用途 |
|------|------|
| [`overdue_followup_workbench.md`](./overdue_followup_workbench.md) | V2.2 业务与架构铁律 |
| [`docs/data_dictionary/overdue.md`](../data_dictionary/overdue.md) | 旧表字段 |
| [`docs/data_dictionary/trust_asset_trust_marks.md`](../data_dictionary/trust_asset_trust_marks.md) | 标注 |

---

*本文档为实施前影响评估；评审通过后再按 Phase 1 开工。*
