-- type: ops/cleanup
-- status: executed
-- executed_at: 2026-06-30
-- safe_to_rerun: yes
-- scope: 删除 FY demo 清理遗留的 _demo_fy_backup_* 快照表（正式表 FY 数据已删，无需回滚）
-- ============================================================

BEGIN;

DROP TABLE IF EXISTS _demo_fy_backup_risk_alerts;
DROP TABLE IF EXISTS _demo_fy_backup_trust_overdue_followups;
DROP TABLE IF EXISTS _demo_fy_backup_trust_repayment_detail_records;
DROP TABLE IF EXISTS _demo_fy_backup_trust_asset_monitor_records;
DROP TABLE IF EXISTS _demo_fy_backup_trust_assets;

COMMIT;
