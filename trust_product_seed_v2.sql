-- ============================================================
-- trust_product_seed_v2.sql
-- 信托产品初始化 — 导入 V2 上线前
-- 依赖：asset_pools.id = 1 已存在（seed.sql 默认创建）
-- 幂等：按 code / name 检查，可重复执行
-- 执行顺序：… → ingestion_upload_v2_schema.sql → 本文件
-- ============================================================

BEGIN;

-- A. id=1 对齐为「美好生活1号」（保留历史 FK 与导入数据）
UPDATE trust_products
SET
    name = '美好生活1号',
    updated_at = NOW()
WHERE id = 1
  AND name IN ('滨江公寓信托一期', '美好生活1号');

-- B. 新增其余 3 个产品（按 code 防重复）
INSERT INTO trust_products (
    asset_pool_id, code, name, status,
    target_amount, raised_amount, expected_return_rate,
    open_date, close_date
)
VALUES
    (1, 'TRU-2026-00002', '美好生活2号', 'raising', 5000000.00, 0.00, 0.0650, '2026-01-01', '2026-12-31'),
    (1, 'TRU-2026-00003', '美好生活3号', 'raising', 5000000.00, 0.00, 0.0650, '2026-01-01', '2026-12-31'),
    (1, 'TRU-2026-00004', '美润1号',     'raising', 5000000.00, 0.00, 0.0650, '2026-01-01', '2026-12-31')
ON CONFLICT (code) DO UPDATE SET
    name       = EXCLUDED.name,
    status     = EXCLUDED.status,
    updated_at = NOW();

-- C. 按 name 二次兜底（防止同名多条脏数据）
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

-- 执行后校验：
-- SELECT id, code, name, asset_pool_id, status FROM trust_products ORDER BY id;
