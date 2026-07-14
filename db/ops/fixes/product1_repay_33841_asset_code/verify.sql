-- verify: product1_repay_33841_asset_code

\echo '=== id=33841 修正后 ==='
SELECT
    r.id,
    r.asset_code,
    ta.asset_code AS canonical_asset_code,
    r.custody_asset_code,
    r.source_asset_code,
    r.repayment_date,
    r.actual_repayment_amount
FROM trust_repayment_detail_records r
JOIN trust_assets ta ON ta.id = r.trust_asset_id
WHERE r.id = 33841;

\echo '=== 产品1 编码不一致（期望 0）==='
SELECT COUNT(*) AS mismatch_count
FROM trust_repayment_detail_records r
JOIN trust_assets ta ON ta.id = r.trust_asset_id
WHERE r.trust_product_id = 1
  AND r.asset_code IS DISTINCT FROM ta.asset_code;

\echo '=== 全库编码不一致（期望 0）==='
SELECT COUNT(*) AS global_mismatch
FROM trust_repayment_detail_records r
JOIN trust_assets ta ON ta.id = r.trust_asset_id
WHERE r.asset_code IS DISTINCT FROM ta.asset_code;
