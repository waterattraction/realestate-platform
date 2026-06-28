-- ============================================================
-- 最小 bootstrap：默认资产包 + 首个信托产品占位（供导入模块复用 FK）
-- ============================================================

BEGIN;

INSERT INTO asset_pools (code, name, status, appraised_value)
VALUES (
    'AP-DEFAULT-001',
    '默认资产包',
    'active',
    0.00
)
ON CONFLICT (code) DO NOTHING;

INSERT INTO trust_products (
    asset_pool_id, code, name, status, expected_return_rate
)
SELECT
    ap.id,
    'TRU-2026-00001',
    '美好生活1号',
    'raising',
    0.0650
FROM asset_pools ap
WHERE ap.code = 'AP-DEFAULT-001'
  AND NOT EXISTS (SELECT 1 FROM trust_products WHERE code = 'TRU-2026-00001');

COMMIT;
