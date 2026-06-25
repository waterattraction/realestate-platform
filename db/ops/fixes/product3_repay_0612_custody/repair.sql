-- repair_name: product3_repay_0612_custody
-- orchestrator: db/ops/fixes/product3_repay_0612_custody/repair.py
-- 默认 ROLLBACK — 审阅后改 COMMIT

\echo '=== PRE: trust_assets source_asset_code 唯一性 ==='
SELECT source_asset_code, COUNT(*), array_agg(id ORDER BY id)
FROM trust_assets
WHERE trust_product_id = 3 AND source_asset_code IS NOT NULL
GROUP BY source_asset_code
HAVING COUNT(*) > 1;

BEGIN;

DROP TABLE IF EXISTS _ops_p3_repay_0612_custody_fix_backup;

CREATE TABLE _ops_p3_repay_0612_custody_fix_backup AS
SELECT r.*, NOW() AS backed_up_at
FROM trust_repayment_detail_records r
WHERE r.trust_product_id = 3
  AND r.source_file_name = '美好生活3号-还款明细披露信息_20260612.xlsx'
  AND r.source_sheet_name = '0612已还款'
  AND regexp_replace(COALESCE(r.custody_asset_code, ''), '\.0$', '')
   <> regexp_replace(COALESCE(r.source_asset_code, ''), '\.0$', '');

DO $$
DECLARE v_backup INT;
BEGIN
  SELECT COUNT(*) INTO v_backup FROM _ops_p3_repay_0612_custody_fix_backup;
  IF v_backup <> 71 THEN
    RAISE EXCEPTION 'backup rows % <> 71', v_backup;
  END IF;
END $$;

UPDATE trust_repayment_detail_records r
SET
  custody_asset_code = regexp_replace(COALESCE(r.source_asset_code, r.asset_code), '\.0$', ''),
  asset_code         = regexp_replace(COALESCE(r.source_asset_code, r.asset_code), '\.0$', ''),
  trust_asset_id     = ta.id
FROM trust_assets ta
WHERE r.trust_product_id = 3
  AND r.source_file_name = '美好生活3号-还款明细披露信息_20260612.xlsx'
  AND r.source_sheet_name = '0612已还款'
  AND regexp_replace(COALESCE(r.custody_asset_code, ''), '\.0$', '')
   <> regexp_replace(COALESCE(r.source_asset_code, ''), '\.0$', '')
  AND ta.trust_product_id = 3
  AND regexp_replace(COALESCE(ta.source_asset_code, ta.asset_code), '\.0$', '')
    = regexp_replace(COALESCE(r.source_asset_code, r.asset_code), '\.0$', '');

ROLLBACK;
