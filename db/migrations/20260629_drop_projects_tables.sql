-- ============================================================
-- 移除已废弃的 projects / project_asset_pools（demo 概念，表已空）
-- ============================================================

BEGIN;

DROP TRIGGER IF EXISTS trg_project_asset_pools_updated_at ON project_asset_pools;
DROP TRIGGER IF EXISTS trg_projects_updated_at ON projects;

DROP TABLE IF EXISTS project_asset_pools;
DROP TABLE IF EXISTS projects;

COMMIT;
