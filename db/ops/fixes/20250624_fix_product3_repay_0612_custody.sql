-- type: ops/fix
-- status: pending
-- safe_to_rerun: no
-- scope: trust_product_id=3 · 0612已还款 · 71 行 custody/trust_asset_id 修正
-- orchestrator: scripts/ops/fix_product3_repay_0612_custody.py
-- ============================================================
-- 美好生活3号 · 还款明细 · 0612已还款 · 托管编码归属修正
--
-- 权威字段：资产编号(房源) = source_asset_code
-- 修正：custody_asset_code, trust_asset_id, asset_code（幂等）
-- 不改：金额、期次、日期、source_file_name、source_sheet_name、审计时间戳
--
-- 推荐：使用 Python orchestrator（含 dry-run / 行数断言 / verify）
--   python3 scripts/ops/fix_product3_repay_0612_custody.py dry-run
--   python3 scripts/ops/fix_product3_repay_0612_custody.py apply
-- ============================================================

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

DO $$
DECLARE v_updated INT;
BEGIN
  GET DIAGNOSTICS v_updated = ROW_COUNT;
  IF v_updated <> 71 THEN
    RAISE EXCEPTION 'updated rows % <> 71 — ROLLBACK', v_updated;
  END IF;
END $$;

-- 默认不提交：审阅后改为 COMMIT
ROLLBACK;
