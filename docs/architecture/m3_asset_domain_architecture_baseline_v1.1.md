# M3.0《Asset Domain Architecture Baseline》

**Version：** 1.1  
**Status：** Architecture Baseline（**Frozen**）

---

## 一、Document Information

### 1.1 Document Purpose

本文档定义整个资产管理平台（**Asset Domain**）的领域架构。

本文**不是**：

- 页面设计
- 数据库设计
- API 设计
- UI 设计

而是整个 Asset Domain 的**最高层架构**。

以下能力均建立在本文定义之上：

- Workbench
- Timeline
- AI Agent
- Open API
- BI
- Reporting

### 1.2 Scope

**覆盖：**

- Asset Identity
- Asset Alias
- Asset Lineage
- Snapshot
- Timeline
- Aggregate Root
- Workbench
- Canonical API

**不覆盖：**

- DDL
- SQL
- Python 实现
- UI 细节

### 1.3 Relationship

```
M1 Infrastructure Governance
        ↓
M2 Canonical Data Language
        ↓
M3 Asset Domain Architecture   ← 本文
        ↓
M4 Business Applications
        ↓
M5 AI Applications
```

---

## 二、Architecture Vision

**一句话：** 所有资产运营都围绕**发行资产（Issuance Asset）**展开。

发行资产永远代表：

- 某产品
- 某次发行
- 某个托管房源

的**整个生命周期**。

所有运营数据最终都要归属于**同一个 Canonical Asset**。

---

## 三、Business Background

当前平台存在六套数据：发行、监控、还款、风险、逾期、跟进。

它们目前通过 `custody_asset_code` 或 `trust_asset_id` 建立关联。

实际业务中，托管房源编号可能因外部合作机构调整、系统迁移、房源拆分/合并而**发生变化**，导致同一资产生命周期内出现多个托管编号。若继续按运营编号管理，资产历史将断裂。

因此，Workbench 必须围绕**发行资产**建立统一身份。

---

## 四、Core Principles

| # | 原则 |
|---|------|
| **Principle 1** | 发行资产是资产生命周期唯一锚点 |
| **Principle 2** | 运营编号允许变化；Canonical Identity 不允许变化 |
| **Principle 3** | 所有运营数据必须归属发行资产（Monitor / Repayment / Risk / Follow-up / Timeline） |
| **Principle 4** | Alias 负责解析；Workbench 不负责猜测 |
| **Principle 5** | 事实数据永远保留；Projection 可以重建 |
| **Principle 6** | 业务对象优先；数据库不是业务模型 |
| **Principle 7** | Snapshot 与事实分离 |
| **Principle 8** | **Layered Identity**：Business → Operation → Persistence 三层职责不能互换 |
| **Principle 9** | Timeline 永远追加；禁止覆盖历史 |
| **Principle 10** | **Domain First**：API / Workbench / AI 均面向 Domain，禁止直接面向数据库 |
| **Principle 11** | **Aggregate Root**：`AssetIdentity` 是整个 Asset Domain 唯一 Aggregate Root；Alias / Lineage / Snapshot / Timeline 均依附于它 |

---

## 五、Domain Model

```
AssetIdentity
        │
 ├──────────────┐
 │              │
 ▼              ▼
Alias        Lineage
 │              │
 └──────┬───────┘
        ▼
 Snapshot
        │
        ▼
 Timeline
        │
 ┌──────┼──────────┐
 ▼      ▼          ▼
Workbench API     AI
```

---

## 六、Asset Identity

**Canonical Identity：**

```
trust_product_id + issue_date + canonical_custody_asset_code
```

这是整个资产生命周期**唯一业务身份**。

`canonical_custody_asset_code` 即**发行时托管房源编号**。无论运营过程中托管编号如何变化，Canonical 永远不变。

### Identity 与 business_asset_key

| 项 | 说明 |
|----|------|
| `business_asset_key` | `product + issue_date + custody`；用于**发行导入冲突分析** |
| 不是 | 业务主键；不是 Workbench Identity |

---

## 七、Asset Alias

Alias 描述**运营编号 → Canonical Identity** 的映射关系。

- **允许**：一对多历史
- **禁止**：多 Canonical 指向同一 Alias

**解析顺序：**

```
Exact → History Alias → Manual Mapping → Failed
```

解析失败 → `needs_confirm`；**禁止静默挂错**。

---

## 八、Asset Lineage

| 机制 | 解决 |
|------|------|
| **Alias** | 编号变化 |
| **Lineage** | 资产迁移（如美润1号 → 美好生活3号：同一套房、不同发行） |

建立 Canonical → Canonical 血缘。**Lineage ≠ Alias**。

---

## 九、Snapshot Model

Snapshot **不是事实**，**来自事实**。

| Snapshot | 默认语义 |
|----------|----------|
| Monitor | 最新 `data_date` |
| Repayment | 累计 + `repayment_date` 筛选 |
| Issuance | `issue_date` |
| Risk | 最新 |

---

## 十、Timeline Model

Timeline 为统一事件流。事件类型包括：Issuance、Alias Changed、Repayment、Monitor、Risk、Follow-up、Repair 等。

- **允许**重建
- **禁止**直接修改

---

## 十一、Aggregate Root

唯一 Root：**AssetIdentity**。

Alias、Timeline、Snapshot 均不能脱离 Identity。

---

## 十二、Workbench Architecture

Workbench **不是**数据库页面，而是 **Asset Aggregate** 的运营入口。

```
Header (Identity)
    ↓
Snapshot
    ↓
Timeline
    ↓
Operations
    ↓
Attachments
```

所有展示均来自 AssetIdentity。

---

## 十三、API Principles

**输入（统一三元组）：**

```
GET /asset-workbench
  ?trust_product_id=
  &issue_date=
  &canonical_custody_asset_code=
```

未来允许 `identity_id` 作为**内部代理键**；对外长期保持三元组有效。

---

## 十四、Data Import Principles

导入第一步：**Resolve Identity**。

```
Excel → Alias Resolve → Canonical → Import
```

- **禁止**运营编号直接覆盖 Canonical
- **同时保留**：原始编号、`source_asset_code`、Canonical（三层信息）

---

## 十五、Transition Strategy

| 里程碑 | 交付 |
|--------|------|
| **M3.1** | Alias、Resolution、Backfill | [M3.1 Identity & Alias Design V1.1](./m3.1_asset_identity_alias_design.md)（Approved） |
| **M3.2** | Asset Workbench | [M3.2 Workbench Design V1.0](./m3.2_asset_workbench_design.md) |
| **M3.3** | AI |
| **M3.4** | Open API |
| **M3.5** | Domain Service |

现有 Overdue / Risk Workbench 逐步收敛至 Asset Workbench。

---

## 十六、Non-functional Requirements

包括：RBAC、Repair、Audit、Projection、Performance、Pagination、Cache、Open API、Data Repair。

数据修复全部遵循 [M1 Production Data Repair Standard](../engineering/production_data_repair_standard.md)。

---

## 十七、Architecture Governance

### 17.1 Hierarchy

```
Architecture → Domain → Migration → Implementation → UI → AI
```

不得倒置。

### 17.2 SSOT

**唯一架构来源：**

[`docs/architecture/m3_asset_domain_architecture_baseline_v1.1.md`](./m3_asset_domain_architecture_baseline_v1.1.md)

禁止在模块设计中重新定义：Identity、Alias、Timeline、Snapshot、Aggregate Root。

### 17.3 Dependency

更新顺序：

```
Baseline → Canonical → Domain → Migration → Implementation → Tests
```

### 17.4 Evolution

| 允许演进 | 禁止修改（除非升级 Baseline） |
|----------|-------------------------------|
| Alias、Snapshot、Timeline、API、Cache、AI | Canonical Identity、Aggregate Root、Layered Identity、Domain Boundary |

### 17.5 Review Checklist

任何 PR 必须回答：

1. 是否修改 Identity / Alias / Lineage / Timeline / Snapshot？
2. 是否违反 Principle？
3. 是否同步文档？
4. 是否需要升级 Baseline？

### 17.6 Version Policy

| 类型 | 含义 |
|------|------|
| Patch | 文档修正 |
| Minor | 新增章节 |
| Major | 修改 Principle |

---

## Appendix A（Domain Layer）

```
                 Asset Domain
                Aggregate Root
                AssetIdentity
                       │
      ┌────────────────┼────────────────┐
      │                │                │
      ▼                ▼                ▼
 AssetAlias      AssetLineage    AssetSnapshot
      │                                 │
      └────────────────┬────────────────┘
                       ▼
                AssetTimeline
                       │
      ┌────────────────┼─────────────────┐
      ▼                ▼                 ▼
Workbench          Open API         AI Agent
```

---

## Appendix B（Layered Identity）

```
Business Layer    → Canonical Identity
Operation Layer   → source_asset_code
Persistence Layer → trust_asset_id
```

| Layer | Responsibility |
|-------|----------------|
| Canonical | 聚合与业务归属 |
| Operation | 业务事实（分笔、运营编号等） |
| Persistence | 数据库关联与 FK |

**任何一层均不得替代另一层。**

---

## Appendix C（M2 Mapping）

| M2 | M3 |
|----|-----|
| Canonical Field | Identity Attribute |
| Canonical Object | Aggregate |
| Alias Dictionary | Alias Resolution |
| Data Dictionary | Persistence |
| Canonical API | Domain DTO |

**M3 不重新定义 Canonical**，而是在 Canonical 基础上建立 Asset Domain。

---

## 冻结声明（Freeze Statement）

**M3.0《Asset Domain Architecture Baseline》V1.1** 自发布之日起，作为整个资产管理平台 **M3.x 的唯一领域架构基线（Architecture Baseline）**。

后续 **M3.1**（Identity & Alias）、**M3.2**（Asset Workbench）、**M3.3**（Timeline & Snapshot）、**M3.4**（Domain API）、**M3.5**（AI Asset Agent）均必须引用本基线，**不得重新定义**资产身份、聚合根、领域边界或核心原则。

任何涉及 **Canonical Identity、Aggregate Root、Layered Identity、Domain Boundary** 的修改，均视为架构变更，必须先升级本 Baseline 版本（**V1.2 / V2.0**），再开展数据库设计、代码实现和业务开发。

---

## 最终定位

- **Asset Workbench** 不是一个页面，而是 Asset Domain 的**统一运营入口**。
- **Canonical Identity** 不是为了导入，而是为了保证资产在整个生命周期内具有**唯一、稳定、可追溯**的业务身份。
- Alias、Lineage、Snapshot、Timeline、Operations 都围绕 **AssetIdentity** 建立，共同构成 Asset Domain。
- 未来的 Workbench、开放 API、BI、AI Agent 均应基于 **Asset Domain**，而不是直接依赖底层数据库结构。
