# ⚠️ 根目录 SQL 已废弃（3 天过渡期）

**生效：** P0/P1/P2 完成日起 **3 个自然日**内，根目录 `*.sql` 只读保留。  
**P4 目标：** 满 3 天后删除或 stub 化根目录 26 个 SQL 文件。

## 新规范（立即生效）

| 用途 | 新位置 |
|------|--------|
| 新环境初始化 | `./db/apply.sh baseline`（读取 `db/manifest.txt`） |
| 业务模块 schema / seed | `db/modules/<模块>/` |
| 增量迁移 | `db/migrations/` |
| 一次性修复/清理 | `db/ops/`（**不在 manifest 中**） |

详见 [`db/README.md`](db/README.md)。

## 过渡期内禁止

- 在项目根目录**新增**任何 `.sql` 文件
- 在代码、脚本、文档、Cursor Rules 中**新增**对根目录 SQL 的引用
- 新部署继续手工执行根目录 SQL

## P4 待办（3 天后）

1. 全仓搜索确认无根目录 SQL 引用
2. 确认部署流程使用 `./db/apply.sh baseline`
3. 已执行 ops 归档到 `db/ops/archive/`，`status: archived`
4. 删除或 stub 根目录 26 个 `*.sql`
5. 删除或更新本文件
