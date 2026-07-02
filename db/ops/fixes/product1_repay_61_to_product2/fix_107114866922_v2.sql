-- 还款 id=32903：误挂 product2，资产主编号误为 107114866922
-- 更正为 product1 / asset_code=107112757529；其余字段（含 custody/source）保持不变

BEGIN;

UPDATE trust_repayment_detail_records
SET
    trust_product_id = 1,
    trust_asset_id = 377,
    asset_code = '107112757529'
WHERE id = 32903;

DELETE FROM trust_assets ta
WHERE ta.id = 2610
  AND ta.trust_product_id = 2
  AND ta.asset_code = '107114866922'
  AND NOT EXISTS (SELECT 1 FROM trust_repayment_detail_records r WHERE r.trust_asset_id = ta.id)
  AND NOT EXISTS (SELECT 1 FROM trust_asset_monitor_records m WHERE m.trust_asset_id = ta.id);

COMMIT;
