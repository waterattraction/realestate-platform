-- ============================================================
-- 移除 trust_products.open_date / close_date（demo 占位，无业务使用）
-- ============================================================

BEGIN;

ALTER TABLE trust_products DROP COLUMN IF EXISTS open_date;
ALTER TABLE trust_products DROP COLUMN IF EXISTS close_date;

COMMIT;
