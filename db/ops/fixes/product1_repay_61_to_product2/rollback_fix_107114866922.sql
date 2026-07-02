-- 回滚 fix_107114866922.sql：恢复 id=32903 在美好生活2号 / asset_code=107114866922 的状态

BEGIN;

INSERT INTO trust_assets (
    trust_product_id, asset_code, custody_asset_code, source_asset_code, initial_transfer_amount
)
SELECT 2, '107114866922', '107114866922', '107114866922', 0
WHERE NOT EXISTS (
    SELECT 1 FROM trust_assets ta
    WHERE ta.trust_product_id = 2 AND ta.asset_code = '107114866922'
);

UPDATE trust_repayment_detail_records r
SET
    trust_product_id = 2,
    trust_asset_id = ta.id,
    asset_code = '107114866922',
    custody_asset_code = '107114866922',
    source_asset_code = '107114866922'
FROM trust_assets ta
WHERE r.id = 32903
  AND ta.trust_product_id = 2
  AND ta.asset_code = '107114866922';

COMMIT;
