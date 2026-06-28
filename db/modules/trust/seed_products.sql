-- ============================================================
-- trust_product_seed_v2.sql
-- 信托产品初始化 — 导入 V2 上线前
-- 依赖：asset_pools.id = 1 已存在（seed.sql 默认创建）
-- 幂等：按 code / name 检查，可重复执行
-- ============================================================

BEGIN;

UPDATE trust_products
SET
    name = '美好生活1号',
    updated_at = NOW()
WHERE id = 1
  AND name <> '美好生活1号';

INSERT INTO trust_products (
    asset_pool_id, code, name, status, expected_return_rate
)
VALUES
    (1, 'TRU-2026-00002', '美好生活2号', 'raising', 0.0650),
    (1, 'TRU-2026-00003', '美好生活3号', 'raising', 0.0650),
    (1, 'TRU-2026-00004', '美润1号',     'raising', 0.0650)
ON CONFLICT (code) DO UPDATE SET
    name       = EXCLUDED.name,
    status     = EXCLUDED.status,
    updated_at = NOW();

DO $$
DECLARE
    target_names TEXT[] := ARRAY['美好生活2号', '美好生活3号', '美润1号'];
    n TEXT;
BEGIN
    FOREACH n IN ARRAY target_names LOOP
        IF (SELECT COUNT(*) FROM trust_products WHERE name = n) > 1 THEN
            RAISE NOTICE '警告: 产品名 "%" 存在多条记录，请人工合并', n;
        END IF;
    END LOOP;
END $$;

COMMIT;
