-- ============================================================
-- 信托资产风险中台 V2 — 演示数据补丁
-- 执行顺序：… → risk_v2_schema.sql → 本文件
-- 依赖 overdue_seed 已加载
-- ============================================================

BEGIN;

-- 风险评分（与引擎规则一致）
-- FY-B-301: 50+30+20=100/A | FY-B-302: 20+30+20=70/B | FY-A-201: 35+20=55/C
UPDATE trust_asset_monitor_records SET risk_score = 5,  risk_level = 'D' WHERE asset_code = 'FY-A-101';
UPDATE trust_asset_monitor_records SET risk_score = 40, risk_level = 'C' WHERE asset_code = 'FY-A-102';
UPDATE trust_asset_monitor_records SET risk_score = 55, risk_level = 'C' WHERE asset_code = 'FY-A-201';
UPDATE trust_asset_monitor_records SET risk_score = 100, risk_level = 'A' WHERE asset_code = 'FY-B-301';
UPDATE trust_asset_monitor_records SET risk_score = 70, risk_level = 'B' WHERE asset_code = 'FY-B-302';
UPDATE trust_asset_monitor_records SET risk_score = 5,  risk_level = 'D' WHERE asset_code = 'FY-C-101';
UPDATE trust_asset_monitor_records SET risk_score = 5,  risk_level = 'D' WHERE asset_code = 'FY-C-102';

-- 案件升级（原 followups）
UPDATE trust_overdue_followups SET
    risk_score = 100,
    risk_level = 'A',
    case_priority = 'P0',
    alert_source = 'system',
    sla_due_date = '2026-06-17 09:00:00+08',
    sla_status = 'breached',
    next_action_date = '2026-06-23'
WHERE trust_asset_id = 4;

UPDATE trust_overdue_followups SET
    risk_score = 70,
    risk_level = 'B',
    case_priority = 'P1',
    alert_source = 'manual',
    sla_due_date = '2026-06-20 10:00:00+08',
    sla_status = 'overdue',
    next_action_date = '2026-06-22'
WHERE trust_asset_id = 5;

-- 风险预警
INSERT INTO risk_alerts (
    trust_product_id, trust_asset_id, data_date,
    risk_type, risk_level, trigger_rule, status, generated_at
)
VALUES
    (1, 4, '2026-06-15', 'delinquency_m3_plus', 'A',
     '逾期天数 ≥92（M3+）', 'open', '2026-06-16 09:10:00+08'),
    (1, 4, '2026-06-15', 'reconciliation_failure', 'A',
     '金额核对失败（余额等式）', 'acknowledged', '2026-06-16 09:10:00+08'),
    (1, 4, '2026-06-15', 'high_risk_score', 'A',
     'risk_score >= 80', 'open', '2026-06-16 09:10:00+08'),
    (1, 5, '2026-06-15', 'reconciliation_failure', 'B',
     '金额核对失败（跨表已还）', 'open', '2026-06-16 09:10:00+08'),
    (1, 3, '2026-06-15', 'delinquency_m3', 'C',
     '逾期天数 64-91（M3）', 'open', '2026-06-16 09:10:00+08');

COMMIT;
