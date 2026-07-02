-- 还款 id=32903：误为 product2 / asset_code=107114866922
-- 更正为 product1 / asset_code=107112757529，关联 trust_assets.id=377

BEGIN;

UPDATE trust_repayment_detail_records
SET
    trust_product_id = 1,
    trust_asset_id = 377,
    asset_code = '107112757529',
    custody_asset_code = '107112757529',
    source_asset_code = '107112757529-001'
WHERE id = 32903;

DELETE FROM trust_assets ta
WHERE ta.trust_product_id = 2
  AND ta.asset_code = '107114866922'
  AND NOT EXISTS (SELECT 1 FROM trust_repayment_detail_records r WHERE r.trust_asset_id = ta.id)
  AND NOT EXISTS (SELECT 1 FROM trust_asset_monitor_records m WHERE m.trust_asset_id = ta.id);

COMMIT;
