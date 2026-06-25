-- rollback for product3_repay_0612_custody
-- 从 _ops_p3_repay_0612_custody_fix_backup 恢复（历史备份表名）
-- 推荐：python3 db/ops/fixes/product3_repay_0612_custody/repair.py rollback

BEGIN;

UPDATE trust_repayment_detail_records r
SET trust_asset_id = b.trust_asset_id,
    asset_code = b.asset_code,
    custody_asset_code = b.custody_asset_code
FROM _ops_p3_repay_0612_custody_fix_backup b
WHERE r.id = b.id;

-- 审阅后 COMMIT；默认 ROLLBACK
ROLLBACK;
