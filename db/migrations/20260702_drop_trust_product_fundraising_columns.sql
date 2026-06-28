-- ============================================================
-- 移除 trust_products 募集占位列（target_amount / raised_amount）
-- ============================================================

BEGIN;

ALTER TABLE trust_products DROP CONSTRAINT IF EXISTS chk_trust_products_target;
ALTER TABLE trust_products DROP CONSTRAINT IF EXISTS chk_trust_products_raised;
ALTER TABLE trust_products DROP COLUMN IF EXISTS target_amount;
ALTER TABLE trust_products DROP COLUMN IF EXISTS raised_amount;

COMMIT;
