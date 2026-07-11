-- rollback: product2_repay_33600_asset_code
-- 从 _ops_p2_repay_33600_asset_code_backup 还原 id=33600

BEGIN;

UPDATE trust_repayment_detail_records r
SET asset_code = b.asset_code
FROM _ops_p2_repay_33600_asset_code_backup b
WHERE r.id = 33600
  AND b.id = 33600;

COMMIT;
