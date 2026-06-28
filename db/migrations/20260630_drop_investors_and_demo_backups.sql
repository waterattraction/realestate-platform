-- ============================================================
-- 移除 demo 备份表 + investors / investments（认购 demo，已废弃）
-- ============================================================

BEGIN;

DROP TABLE IF EXISTS _demo_baseline_backup_project_asset_pools;
DROP TABLE IF EXISTS _demo_baseline_backup_projects;
DROP TABLE IF EXISTS _demo_baseline_backup_investments;
DROP TABLE IF EXISTS _demo_baseline_backup_investors;

DROP TRIGGER IF EXISTS trg_investments_updated_at ON investments;
DROP TRIGGER IF EXISTS trg_investors_updated_at ON investors;

DROP TABLE IF EXISTS investments;
DROP TABLE IF EXISTS investors;

COMMIT;
