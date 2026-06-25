-- type: ops/fix
-- repair_name: {{REPAIR_NAME}}
-- status: pending
-- safe_to_rerun: no
-- orchestrator: db/ops/fixes/{{REPAIR_NAME}}/repair.py
-- ============================================================
-- {{REPAIR_TITLE}}
--
-- 推荐：使用 Python RepairJob（含 dry-run / 行数断言 / verify / rollback）
--   python3 db/ops/fixes/{{REPAIR_NAME}}/repair.py check
--   python3 db/ops/fixes/{{REPAIR_NAME}}/repair.py dry-run
--   python3 db/ops/fixes/{{REPAIR_NAME}}/repair.py apply
-- ============================================================

\echo '=== PRE: 只读检查（见 check.sql）==='

BEGIN;

-- 1. 创建备份（命名规范：_ops_backup_{{REPAIR_NAME}}）
DROP TABLE IF EXISTS _ops_backup_{{REPAIR_NAME}};

CREATE TABLE _ops_backup_{{REPAIR_NAME}} AS
SELECT t.*, NOW() AS backed_up_at
FROM {{TARGET_TABLE}} t
WHERE {{SCOPE_WHERE}};

-- 2. 断言备份行数
DO $$
DECLARE v_cnt INT;
BEGIN
    SELECT COUNT(*) INTO v_cnt FROM _ops_backup_{{REPAIR_NAME}};
    IF v_cnt <> {{EXPECTED_ROWS}} THEN
        RAISE EXCEPTION 'backup count % <> expected {{EXPECTED_ROWS}}', v_cnt;
    END IF;
END $$;

-- 3. UPDATE（示例 — 按实际 Repair 替换）
-- UPDATE {{TARGET_TABLE}} t
-- SET ...
-- FROM ...
-- WHERE {{SCOPE_WHERE}};

-- 4. 断言 rowcount（在应用层或 GET DIAGNOSTICS）

-- 默认不提交 — 审阅后改为 COMMIT
ROLLBACK;
