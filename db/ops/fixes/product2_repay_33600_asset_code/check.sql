-- repair_name: product2_repay_33600_asset_code
-- 只读：确认 id=33600 主编号与 trust_assets 不一致

\echo '=== id=33600 当前状态 ==='
SELECT
    r.id,
    r.trust_product_id,
    r.trust_asset_id,
    r.asset_code AS stored_asset_code,
    ta.asset_code AS canonical_asset_code,
    r.custody_asset_code,
    r.repayment_date,
    r.actual_repayment_amount
FROM trust_repayment_detail_records r
JOIN trust_assets ta ON ta.id = r.trust_asset_id
WHERE r.id = 33600;

\echo '=== 不一致行数（期望 1）==='
SELECT COUNT(*) AS mismatch_count
FROM trust_repayment_detail_records r
JOIN trust_assets ta ON ta.id = r.trust_asset_id
WHERE r.id = 33600
  AND r.asset_code IS DISTINCT FROM ta.asset_code;

\echo '=== 跨表差额预览（107113281945）==='
SELECT
    (
        SELECT SUM(repaid_amount)
        FROM trust_asset_monitor_records
        WHERE trust_product_id = 2
          AND data_date = '2026-07-03'
          AND asset_code = '107113281945'
    ) AS monitor_repaid,
    (
        SELECT COALESCE(SUM(actual_repayment_amount), 0)
        FROM trust_repayment_detail_records
        WHERE trust_product_id = 2
          AND asset_code = '107113281945'
    ) AS repay_by_r_asset_code;
