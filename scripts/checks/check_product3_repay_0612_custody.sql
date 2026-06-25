-- ============================================================
-- 只读检查：美好生活3号 · 0612已还款 · 托管编码错挂
-- trust_product_id = 3
-- ============================================================

\echo '=== 1. Sheet 行数与错挂行数 ==='
SELECT COUNT(*) AS sheet_total,
       COUNT(*) FILTER (
         WHERE regexp_replace(COALESCE(custody_asset_code,''), '\.0$', '')
            <> regexp_replace(COALESCE(source_asset_code,''), '\.0$', '')
       ) AS mismatch_rows
FROM trust_repayment_detail_records
WHERE trust_product_id = 3
  AND source_file_name = '美好生活3号-还款明细披露信息_20260612.xlsx'
  AND source_sheet_name = '0612已还款';

\echo '=== 2. trust_assets.source_asset_code 唯一性（不得一对多） ==='
SELECT source_asset_code, COUNT(*) AS cnt, array_agg(id ORDER BY id) AS trust_asset_ids
FROM trust_assets
WHERE trust_product_id = 3
  AND source_asset_code IS NOT NULL
GROUP BY source_asset_code
HAVING COUNT(*) > 1;

\echo '=== 3. 错挂行是否缺目标 trust_assets ==='
SELECT COUNT(*) AS missing_target_asset
FROM trust_repayment_detail_records r
WHERE r.trust_product_id = 3
  AND r.source_file_name = '美好生活3号-还款明细披露信息_20260612.xlsx'
  AND r.source_sheet_name = '0612已还款'
  AND regexp_replace(COALESCE(r.custody_asset_code,''), '\.0$', '')
   <> regexp_replace(COALESCE(r.source_asset_code,''), '\.0$', '')
  AND NOT EXISTS (
    SELECT 1 FROM trust_assets ta
    WHERE ta.trust_product_id = 3
      AND regexp_replace(COALESCE(ta.source_asset_code, ta.asset_code), '\.0$', '')
        = regexp_replace(COALESCE(r.source_asset_code, r.asset_code), '\.0$', '')
  );

\echo '=== 4. 错挂行 trust_asset_id 错误数 ==='
SELECT COUNT(*) AS wrong_trust_asset_id
FROM trust_repayment_detail_records r
JOIN trust_assets ta ON ta.id = r.trust_asset_id
WHERE r.trust_product_id = 3
  AND r.source_file_name = '美好生活3号-还款明细披露信息_20260612.xlsx'
  AND r.source_sheet_name = '0612已还款'
  AND regexp_replace(COALESCE(r.custody_asset_code,''), '\.0$', '')
   <> regexp_replace(COALESCE(r.source_asset_code,''), '\.0$', '')
  AND regexp_replace(COALESCE(ta.source_asset_code, ta.asset_code), '\.0$', '')
   <> regexp_replace(COALESCE(r.source_asset_code, r.asset_code), '\.0$', '');
