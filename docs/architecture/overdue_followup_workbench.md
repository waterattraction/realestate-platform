# 逾期跟进工作台补全方案（V2.2 · 收敛版）

| 项 | 值 |
|----|-----|
| 状态 | 方案文档，待评审；**不包含代码实现** |
| 适用范围 | 房地产资产证券化平台 — 逾期管理模块 |
| 版本 | V2.2（在 V2.1 评审基础上工程收敛） |
| 一句话 | **1 个读服务 + 1 个写入口 + 1 个 Ops 计算器** |

---

## 0. 四条铁律

| # | 铁律 | 说明 |
|---|------|------|
| **1** | **读：一条主查询路径** | 所有页面数据 **必须** 来自 `OverdueWorkbenchService.get_detail()`；禁止多 Service 拼 SQL、HTML 自己查、Ops 路由单独查 |
| **2** | **写：只有一个入口** | `POST /overdue/workbench/followups/entries`；只写 entry，case 仅为副作用更新；**禁止** 以 `PATCH case` 为主逻辑入口 |
| **3** | **Ops：只读 + 建议** | Ops 不写库、不改 case/followup；可输出 bucket / risk / recommended action / SLA；**唯一例外**：`escalate` 可写 `entry_type=system` |
| **4** | **HTML = dumb render** | 只吃 DTO；不写 SQL；不做业务判断 |

> Fact / Decision / View 可作为**概念**理解读写分工，**不落目录、不单独命名模块**。

---

## 1. 背景与目标

### 1.1 业务目标

| 目标 | 说明 |
|------|------|
| G1 | 跟进时看清：发行、还款、监控、检查、Ops 建议、标注、时间线 |
| G2 | 页底集中录入本次跟进 |
| G3 | 图片/文件附件（Phase 3） |

### 1.2 工程约束

- 单体 FastAPI + PostgreSQL + `sqlalchemy.text()`（Repo 层）  
- 不引入 Redis / Kafka / 微服务  
- 发行用 `issue_date`，监控/逾期用 `data_date`  
- 新表走 `db/migrations/` + data_dictionary，评审后实施  

---

## 2. 最简工程结构

```
service/
  overdue_workbench.py      # 唯一读入口：get_detail()
  checks_service.py         # 检查逻辑（余额等式、跨表已还）
  ops_service.py            # Ops 计算（只输出建议，不落库）

repo/
  issuance_repo.py
  repayment_repo.py
  monitor_repo.py
  followup_repo.py

api/
  overdue_workbench.py      # thin：调 get_detail()
  followups.py              # thin：POST entries

html/
  overdue_workbench.html
  render.py                 # render_overdue_workbench_html(dto)，纯模板
```

### 2.1 砍掉或弱化的概念

| 不再单独设立 | 并入 |
|--------------|------|
| Scope Resolver | `overdue_workbench.py` 内 `resolve_scope()` |
| Projection Builder 家族 | `get_detail()` 内一次组装 DTO |
| Timeline Builder 模块 | `get_detail()` 内 `timeline = repayment_events + followup_entries` |
| `AssetApplicationService` 并行第三读路径 | 工作台读路径 **不经过** asset-workbench；后者保持独立 MVP |
| Fact/Decision/View 目录分层 | 仅文档概念，代码按上表扁平组织 |

---

## 3. 数据流

### 3.1 读取路径（唯一）

```
API  GET /overdue/workbench/detail
  → OverdueWorkbenchService.get_detail(trust_product_id, custody_asset_code, data_date?)
       → repo 查询（issuance / repayment / monitor / followup / marks）
       → checks_service.run(facts)
       → ops_service.suggest(facts)     # 只算建议，不写库
       → timeline merge（repayment_events + followup_entries）
  → return OverdueWorkbenchDetailDTO

HTML  GET /overdue/workbench
  → get_detail()   # 同上
  → render.py(dto) # 纯渲染
```

**禁止**：`render.py` 内 SQL；`ops_service` 单独暴露给前端的第二套 detail API；`main.py` 遗留 workbench 聚合 SQL（Phase 3 删除）。

### 3.2 写入路径（唯一）

```
POST /overdue/workbench/followups/entries  (multipart)
  → INSERT followup_entry
  → UPDATE followup_case（status / owner / last_follow_up_at / closed_at）— 副作用
  → optional: ops escalate → INSERT entry_type=system 的 entry（唯一 Ops 写例外）
  → return 201 + entry_id
```

**禁止**：`PATCH /cases/{id}` 作为运营改状态主入口。

---

## 4. 主体锚点与 Identity（简化）

### 4.1 双字段并存（当前最稳）

| 字段 | 用途 |
|------|------|
| `custody_asset_code` + `trust_product_id` | 运营深链、案件主体、列表一致 |
| `identity_id` | 当前 **= `trust_product_issuance_asset_records.id`**（Phase 0 surrogate，暂作唯一真相） |

运营 URL：

```
/overdue/workbench?trust_product_id={pid}&custody_asset_code={code}
```

JSON API（可选带 `identity_id` 便于与 `/asset-workbench` 互跳）。

### 4.2 本方案明确不做（Phase 1–2）

- 不引入 `asset_identity_map`  
- 不把 M3.1 migration 作为 Phase 1 前置依赖  
- 不做 canonical 重构  

Identity 长期演进归 M3.1 独立排期，**不阻塞**本方案 Phase 1 开发。

`get_detail()` 内 `resolve_scope(product, custody)` 仅：查 issuance 行 + trust_assets 分笔 + 默认 `data_date`，逻辑内联在 `overdue_workbench.py`。

---

## 5. Ops（工程现实版）

### 5.1 输入 / 输出

```
input:  facts（monitor / repayment / issuance 摘要）
output:
  - bucket（M 级）
  - risk_level
  - recommended_actions[]   # 文案 + 类型：recommend / suggest / escalate
  - sla                     # 截止时间、是否超期
```

### 5.2 允许 vs 禁止

| 允许 | 禁止 |
|------|------|
| 计算风险、给建议、输出 SLA | 写 followup、改 case 状态 |
| **escalate 触发 system entry**（写路径唯一例外） | Ops Case 落库、PATCH 任何运营状态 |

Panel ⑥ 只读展示；与底栏录入区视觉隔离。

---

## 6. Followup 数据模型

### 6.1 两张核心表（Phase 2）

**`trust_overdue_followup_cases`** — 状态缓存

| 字段 | 说明 |
|------|------|
| trust_product_id + custody_asset_code | 托管主体；唯一活跃 open/in_progress |
| status | open / in_progress / resolved / closed |
| owner_name, data_date, opened_at, closed_at | |

**`trust_overdue_followup_entries`** — 事实

| 字段 | 说明 |
|------|------|
| case_id | FK |
| entry_type | manual / system / trust_request |
| status_snapshot, overdue_reason, follow_up_plan, trust_feedback, note | |
| owner_name, created_by, created_at | |

**规则**：entry 永远追加；case 仅缓存「当前状态」，由最新 entry 驱动更新。

### 6.2 附件（Phase 3）

`trust_overdue_followup_attachments` → `entry_id`；目录 `{ASSET_UPLOAD_DIR}/followups/{case_id}/{entry_id}/`；单文件 10MB，单次最多 10 个；鉴权下载。

### 6.3 旧表 `trust_overdue_followups`

Phase 2 起新表并行；旧记录只读进 timeline（标「历史台账」）；Phase 3 迁移后废弃写入。

**followup_count**：`COUNT(entries)` per `(trust_product_id, custody_asset_code)`。

### 6.4 三态不合并

| 维度 | 存储 | 写入 |
|------|------|------|
| 信托标记 / 内部状态 | `trust_asset_trust_marks` | PATCH `/overdue/custody-marks` |
| 案件状态 | `followup_cases` | **仅** POST entries 副作用 |

---

## 7. Timeline（收敛）

```python
timeline = merge_sorted(
    repayment_events,      # 来自 repayment_repo
    followup_entries,      # 来自 followup_repo（含旧表只读）
    key=event_time,
    order=desc,
)
```

不设立 Timeline Builder 包；合并逻辑在 `get_detail()` 内 ≤ 1 个函数。

Ops 建议 **不进入** timeline（非事实事件）。

---

## 8. 页面结构

```
TOP:   托管号 · 产品 · M 级 · 数据日期 · 返回 /overdue

LEFT:  待跟进队列（Phase 3，调 ops queue）

RIGHT: ① issuance  ② repayment  ③ monitor
       ④ checks    ⑤ trust marks  ⑥ ops（只读）
       ⑦ timeline

BOTTOM: followup form（唯一写入区）
        [保存本次跟进]  [关闭案件 → status=closed 写入 entry]
```

各 Panel 字段与 V1 设计稿一致（发行分组、还款期次表、监控托管+分笔、检查异常高亮等）；数据一律来自 `get_detail()` 返回的 DTO 子对象。

---

## 9. API

### 9.1 读

```
GET /overdue/workbench/detail
  ?trust_product_id={pid}&custody_asset_code={code}&data_date={optional}
```

响应：`OverdueWorkbenchDetailDTO`（示意）

```json
{
  "custody_asset_code": "...",
  "trust_product_id": 4,
  "identity_id": 2134,
  "data_date": "2026-06-19",
  "issuance_records": [],
  "repayment": { "total_repaid": 0, "items": [] },
  "monitor": { "custody": {}, "splits": [] },
  "checks": { "balance_equation": {}, "cross_sheet_repayment": {} },
  "trust_mark": {},
  "ops": { "bucket": "M2", "risk_level": "...", "recommended_actions": [], "sla": {} },
  "followup_case": {},
  "timeline": []
}
```

### 9.2 写

| 方法 | 路径 |
|------|------|
| POST | `/overdue/workbench/followups/entries` |
| PATCH | `/overdue/custody-marks`（标注，独立事实） |
| GET | `/overdue/workbench/attachments/{id}`（Phase 3） |

### 9.3 队列（Phase 3）

```
GET /overdue/ops/queue?trust_product_id={pid}&...
```

---

## 10. 实施分期

### 基线（已完成）

`/overdue` 列表、托管深链、旧 followup CRUD、`/asset-workbench` MVP、`/overdue/ops/{id}` 初版。

### Phase 1 — 读通

| 交付物 |
|--------|
| `OverdueWorkbenchService.get_detail()` |
| 一个 DTO |
| `GET /overdue/workbench/detail` |
| `html/render.py` 纯渲染 |
| 从 `main.py` 迁出检查逻辑 → `checks_service.py` |
| Ops 建议嵌入 `ops_service.py`，经 `get_detail()` 输出 |

**验收**：从 `/overdue` 点进托管号，全 Panel 有数据；全站工作台读只有一条链路；HTML 无 SQL/无 if 业务分支。

### Phase 2 — 写通

| 交付物 |
|--------|
| migration：`followup_cases` + `followup_entries` |
| `POST .../entries` + case 副作用更新 |
| timeline 含新 entries；旧表只读兼容 |
| `followup_count` 改 entry 计数 |
| escalate → system entry（可选开关） |

**验收**：同一托管多次跟进；状态仅经 entry 变更；无 PATCH case 主入口。

### Phase 3 — 增强

| 交付物 |
|--------|
| attachments 上传/下载 |
| `GET /overdue/ops/queue` + 左侧栏 |
| 旧 `trust_overdue_followups` 迁移与废弃 |
| 删除 `main.py` 遗留 workbench SQL |

---

## 11. 验收标准

1. 所有工作台数据来自 `get_detail()`  
2. 写入仅 `POST entries`（+ 标注 PATCH）  
3. Ops 不落库；escalate system entry 为唯一写例外  
4. HTML dumb render  
5. 发行/还款/监控/检查/标注/Ops/时间线单页可见  
6. Phase 3：附件与队列  
7. 不破坏导入与既有核对链路  

---

## 12. 不涉及范围

- 不改造发行/监控/还款导入  
- 无工作流、消息通知、信托 API  
- 无 OCR / AI  
- 本方案不前置 M3.1 identity migration  

---

## 13. 版本演进摘要

| 版本 | 要点 |
|------|------|
| V1 | CRUD 工作台 + 三表模型草案 |
| V2 | M3 对齐、双轨锚点、Projection 收敛 |
| V2.1 | Fact/Decision/View、硬化 Ops 边界、压缩 Phase |
| **V2.2** | **单读服务 `get_detail()`、单写入口、扁平目录、identity 暂不复杂化、escalate 写 system entry 例外** |

---

*评审通过前不实施代码与 migration。*
