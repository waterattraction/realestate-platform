-- ============================================================
-- 默认资产包命名对齐（去除 demo「滨江公寓」命名）
-- ============================================================

BEGIN;

UPDATE asset_pools
SET
    code = 'AP-DEFAULT-001',
    name = '默认资产包',
    updated_at = NOW()
WHERE id = 1
  AND (code = 'AP-2026-00001' OR name LIKE '%滨江%');

COMMIT;
