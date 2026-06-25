-- type: ops/rollback
-- status: pending
-- executed_at:
-- safe_to_rerun: yes
-- scope: 从 cleanup_demo_assets 备份恢复 FY-* 演示数据
-- ============================================================
-- FY-* 演示数据回滚脚本
-- 从 cleanup_demo_assets.sql 创建的 _demo_fy_backup_* 表恢复
-- 恢复顺序：主表 → 子表（与删除顺序相反）
-- ============================================================

BEGIN;

SELECT '=== 回滚前 FY-* 现存数量 ===' AS section;
SELECT 'trust_assets (FY-*)' AS metric, COUNT(*) AS cnt
FROM trust_assets WHERE asset_code LIKE 'FY-%';

-- 若备份表不存在则中止
DO $$
BEGIN
    IF to_regclass('public._demo_fy_backup_trust_assets') IS NULL THEN
        RAISE EXCEPTION '备份表 _demo_fy_backup_trust_assets 不存在，无法回滚';
    END IF;
END $$;

-- 1. 主表
INSERT INTO trust_assets (
    id, trust_product_id, asset_code, asset_name, initial_transfer_amount,
    created_at, updated_at, custody_asset_code, source_asset_code
)
OVERRIDING SYSTEM VALUE
SELECT
    id, trust_product_id, asset_code, asset_name, initial_transfer_amount,
    created_at, updated_at, custody_asset_code, source_asset_code
FROM _demo_fy_backup_trust_assets
ON CONFLICT (id) DO NOTHING;

-- 2. 监控
INSERT INTO trust_asset_monitor_records (
    id, trust_product_id, trust_asset_id, asset_code, data_date,
    initial_transfer_amount, repaid_amount, remaining_amount,
    overdue_days, last_payment_date, max_payment_date,
    source_file_name, source_sheet_name, synced_at, created_at,
    risk_score, risk_level, custody_asset_code, source_asset_code
)
OVERRIDING SYSTEM VALUE
SELECT
    id, trust_product_id, trust_asset_id, asset_code, data_date,
    initial_transfer_amount, repaid_amount, remaining_amount,
    overdue_days, last_payment_date, max_payment_date,
    source_file_name, source_sheet_name, synced_at, created_at,
    risk_score, risk_level, custody_asset_code, source_asset_code
FROM _demo_fy_backup_trust_asset_monitor_records
ON CONFLICT (id) DO NOTHING;

-- 3. 还款明细
INSERT INTO trust_repayment_detail_records (
    id, trust_product_id, trust_asset_id, asset_code, data_date,
    period_no, actual_repayment_amount, repayment_date,
    source_file_name, source_sheet_name, synced_at, created_at,
    custody_asset_code, source_asset_code
)
OVERRIDING SYSTEM VALUE
SELECT
    id, trust_product_id, trust_asset_id, asset_code, data_date,
    period_no, actual_repayment_amount, repayment_date,
    source_file_name, source_sheet_name, synced_at, created_at,
    custody_asset_code, source_asset_code
FROM _demo_fy_backup_trust_repayment_detail_records
ON CONFLICT (id) DO NOTHING;

-- 4. 跟进台账
INSERT INTO trust_overdue_followups (
    id, trust_product_id, trust_asset_id, data_date, trigger_source,
    overdue_reason, follow_up_plan, status, owner_name, last_follow_up_at,
    trust_feedback, created_at, updated_at,
    risk_score, risk_level, sla_due_date, sla_status, alert_source,
    case_priority, next_action_date
)
OVERRIDING SYSTEM VALUE
SELECT
    id, trust_product_id, trust_asset_id, data_date, trigger_source,
    overdue_reason, follow_up_plan, status, owner_name, last_follow_up_at,
    trust_feedback, created_at, updated_at,
    risk_score, risk_level, sla_due_date, sla_status, alert_source,
    case_priority, next_action_date
FROM _demo_fy_backup_trust_overdue_followups
ON CONFLICT (id) DO NOTHING;

-- 5. 风险预警
INSERT INTO risk_alerts (
    id, trust_product_id, trust_asset_id, data_date, risk_type, risk_level,
    trigger_rule, status, generated_at, resolved_at, created_at, updated_at
)
OVERRIDING SYSTEM VALUE
SELECT
    id, trust_product_id, trust_asset_id, data_date, risk_type, risk_level,
    trigger_rule, status, generated_at, resolved_at, created_at, updated_at
FROM _demo_fy_backup_risk_alerts
ON CONFLICT (id) DO NOTHING;

-- 同步 identity 序列（避免后续 INSERT 冲突）
SELECT setval(
    pg_get_serial_sequence('trust_assets', 'id'),
    COALESCE((SELECT MAX(id) FROM trust_assets), 1)
);
SELECT setval(
    pg_get_serial_sequence('trust_asset_monitor_records', 'id'),
    COALESCE((SELECT MAX(id) FROM trust_asset_monitor_records), 1)
);
SELECT setval(
    pg_get_serial_sequence('trust_repayment_detail_records', 'id'),
    COALESCE((SELECT MAX(id) FROM trust_repayment_detail_records), 1)
);
SELECT setval(
    pg_get_serial_sequence('trust_overdue_followups', 'id'),
    COALESCE((SELECT MAX(id) FROM trust_overdue_followups), 1)
);
SELECT setval(
    pg_get_serial_sequence('risk_alerts', 'id'),
    COALESCE((SELECT MAX(id) FROM risk_alerts), 1)
);

SELECT '=== 回滚后 FY-* 数量 ===' AS section;
SELECT 'trust_assets (FY-*)' AS metric, COUNT(*) AS cnt
FROM trust_assets WHERE asset_code LIKE 'FY-%'
UNION ALL
SELECT 'trust_asset_monitor_records (FY-*)', COUNT(*)
FROM trust_asset_monitor_records m JOIN trust_assets ta ON ta.id = m.trust_asset_id
WHERE ta.asset_code LIKE 'FY-%'
UNION ALL
SELECT 'trust_repayment_detail_records (FY-*)', COUNT(*)
FROM trust_repayment_detail_records r JOIN trust_assets ta ON ta.id = r.trust_asset_id
WHERE ta.asset_code LIKE 'FY-%'
UNION ALL
SELECT 'trust_overdue_followups (FY-*)', COUNT(*)
FROM trust_overdue_followups f JOIN trust_assets ta ON ta.id = f.trust_asset_id
WHERE ta.asset_code LIKE 'FY-%'
UNION ALL
SELECT 'risk_alerts (FY-*)', COUNT(*)
FROM risk_alerts a JOIN trust_assets ta ON ta.id = a.trust_asset_id
WHERE ta.asset_code LIKE 'FY-%';

COMMIT;
