-- rollback: product1_repay_33841_asset_code
-- 从 _ops_backup_product1_repay_33841_asset_code 还原 asset_code

BEGIN;

UPDATE trust_repayment_detail_records r
SET asset_code = b.asset_code
FROM _ops_backup_product1_repay_33841_asset_code b
WHERE r.id = 33841
  AND b.id = 33841;

COMMIT;
