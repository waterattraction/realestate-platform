-- repair_name: product1_repay_33841_asset_code
-- 只读：确认 id=33841 主编号与 trust_assets 不一致

\echo '=== id=33841 当前状态 ==='
SELECT
    r.id,
    r.trust_product_id,
    r.trust_asset_id,
    r.asset_code AS stored_asset_code,
    ta.asset_code AS canonical_asset_code,
    r.custody_asset_code,
    r.source_asset_code,
    r.repayment_date,
    r.actual_repayment_amount,
    r.source_file_name,
    r.source_sheet_name
FROM trust_repayment_detail_records r
JOIN trust_assets ta ON ta.id = r.trust_asset_id
WHERE r.id = 33841;

\echo '=== 不一致行数（期望 1）==='
SELECT COUNT(*) AS mismatch_count
FROM trust_repayment_detail_records r
JOIN trust_assets ta ON ta.id = r.trust_asset_id
WHERE r.id = 33841
  AND r.asset_code IS DISTINCT FROM ta.asset_code;

\echo '=== 产品1 全量不一致（期望含本条）==='
SELECT COUNT(*) AS product1_mismatch
FROM trust_repayment_detail_records r
JOIN trust_assets ta ON ta.id = r.trust_asset_id
WHERE r.trust_product_id = 1
  AND r.asset_code IS DISTINCT FROM ta.asset_code;
