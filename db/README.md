# 数据库 SQL 文件管理

本目录统一管理 PostgreSQL 的 schema、种子数据、增量迁移和一次性运维脚本。

不引入 Flyway / Liquibase，保持「文件 + manifest + 简单 shell」方式。

**治理状态：** P0/P1/P2 已完成（2026-06）。根目录 26 个旧 SQL 处于 **3 天过渡期**，之后执行 P4 清理。

---

## 目录结构

| 目录 | 用途 | 新环境自动执行 |
|------|------|:-------------:|
| `baseline/` | 平台基础表结构与基础种子 | ✅ |
| `modules/` | 各业务模块长期有效的 schema / seed | ✅ |
| `migrations/` | 增量 ALTER、索引、小迁移 | ✅（全量初始化时） |
| `ops/` | 一次性修复、清理、回滚 | ❌ 人工按需 |

```
db/
├── README.md           # 本文件
├── manifest.txt        # 新环境全量初始化顺序（唯一清单）
├── apply.sh            # 执行脚本
├── baseline/
├── modules/
│   ├── overdue/
│   ├── risk/
│   ├── ingestion/
│   ├── issuance/
│   ├── users/
│   └── trust/
├── migrations/
└── ops/
    ├── fixes/
    ├── cleanups/
    ├── rollbacks/
    └── archive/        # 已执行完毕、status=archived 的 ops 脚本
```

---

## 强制规则

1. **禁止**在项目根目录新增任何 `.sql` 文件。
2. **禁止**将 `ops/` 脚本加入 `manifest.txt`。
3. **禁止**继续手工执行根目录 SQL（过渡期兼容只读，不用于新部署）。
4. 新增 migration **必须**同步更新 `manifest.txt`。
5. 所有数据库结构变更遵循：**设计 → 评审 → Migration → 实施 → 验收**。

---

## 新环境初始化

```bash
chmod +x db/apply.sh
./db/apply.sh baseline
```

> 容器内需能访问 `db/`（compose 将项目根挂载为 `/data/repo`）。

## 已有环境

仅执行尚未应用的 migration：

```bash
./db/apply.sh migration 20260624_trust_product_aliases.sql
```

建议维护 `db/migrations/APPLIED.log` 记录已执行项。

## Ops（人工执行）

```bash
./db/apply.sh ops fixes/20260624_issuance_product1_issue_date_city.sql
```

- 不在 manifest 中
- `apply.sh baseline` 不会执行 ops
- 执行后将 `status` 改为 `executed`，最终移入 `ops/archive/` 并改为 `archived`

---

## 新增 SQL 放哪里

| 场景 | 放置位置 | 更新 manifest |
|------|---------|:-------------:|
| 新平台核心表 | `db/baseline/`（极少） | ✅ |
| 新模块 schema | `db/modules/<module>/schema.sql` | ✅ |
| 新模块 seed | `db/modules/<module>/seed*.sql` | ✅ |
| ALTER / 索引 / 小迁移 | `db/migrations/YYYYMMDD_描述.sql` | ✅ |
| 数据修复 / 清理 / 回滚 | `db/ops/fixes\|cleanups\|rollbacks/` | ❌ |

---

## Migration 规范

### 命名

```
YYYYMMDD_<short_description>.sql
```

示例：`20260625_add_issuance_indexes.sql`

### 文件头元数据（必须）

```sql
-- type: migration
-- created_at: 2026-06-25
-- author: Cursor
-- purpose: 增加发行资产查询索引
-- dependencies:
--   - db/modules/issuance/schema.sql
-- idempotent: yes
```

| 字段 | 说明 |
|------|------|
| `purpose` | 本次变更目的 |
| `dependencies` | 依赖的 schema 或 migration |
| `idempotent` | 是否允许重复执行（`yes` / `no`） |

### 提交 checklist

- [ ] 文件在 `db/migrations/`
- [ ] 命名符合 `YYYYMMDD_` 前缀
- [ ] 文件头元数据完整
- [ ] 已追加到 `manifest.txt` 末尾（顺序正确）
- [ ] 本 README 依赖说明已更新（如有新依赖链）

---

## Ops 规范

### 文件头元数据（必须）

```sql
-- type: ops/fix | ops/cleanup | ops/rollback
-- status: pending | executed | archived
-- executed_at: YYYY-MM-DD
-- safe_to_rerun: yes | no
-- scope: 简述影响表/产品/行数
```

### 生命周期

1. 创建 → `status: pending`
2. 人工审阅并执行 → `status: executed`，填写 `executed_at`
3. 确认无需再执行 → 移入 `ops/archive/`，`status: archived`

---

## Manifest 管理

`db/manifest.txt` 是**数据库初始化唯一执行清单**。

- 所有 baseline、modules、migrations 必须出现在 manifest 中
- ops **永远不能**加入 manifest
- 修改执行顺序时同步更新本 README 中的依赖说明

当前依赖链：

```text
baseline → overdue → risk → ingestion → users → upload_v2
  → trust seed → mapping seed → issuance → trust marks
  → migrations（audit → semantics → overdue_recalc → indexes → issuance_type → aliases）
```

---

## SQL 评审（编码前必做）

每一个数据库相关需求，**开始编码前**必须先回答：

1. **类型**：新 Schema / 新 Module / Migration / Ops 修复？
2. **重复性**：是否已有相同表或字段？能否复用？
3. **索引**：是否需要新索引？查询场景是什么？
4. **模块影响**：是否影响导入、逾期、风险、发行等模块？
5. **文档**：是否需要更新 `manifest.txt`、`db/README.md`、`.cursor/rules/project.mdc`？
6. **回滚**：预计影响范围与回滚方案是什么？

确认后再进入 Migration 编写与实施。

---

## 根目录旧 SQL（3 天过渡期）

根目录 26 个 `*.sql` 仅作历史兼容，参见 [`SQL_DEPRECATED.md`](../SQL_DEPRECATED.md)。

| 时间 | 要求 |
|------|------|
| 过渡期内（3 天） | 根目录 SQL 只读保留；**禁止**新增任何引用根目录 SQL 的代码、脚本或文档 |
| P4（满 3 天后） | 全仓确认无引用 → 删除或 stub 根目录 SQL → 更新/删除 `SQL_DEPRECATED.md` |

### P4 清理 checklist

- [ ] `rg` 全仓无根目录 `*.sql` 引用
- [ ] 部署流程已切换为 `./db/apply.sh baseline`
- [ ] 已执行 ops 移入 `db/ops/archive/`，`status: archived`
- [ ] 删除根目录 26 个 SQL（或改为 `\i db/...` stub）
- [ ] 更新或删除 `SQL_DEPRECATED.md`
