-- verify: product2_repay_33600_asset_code

\echo '=== id=33600 修正后 ==='
SELECT id, asset_code, custody_asset_code, repayment_date, actual_repayment_amount
FROM trust_repayment_detail_records
WHERE id = 33600;

\echo '=== 产品2 编码不一致（期望 0）==='
SELECT COUNT(*) AS mismatch_count
FROM trust_repayment_detail_records r
JOIN trust_assets ta ON ta.id = r.trust_asset_id
WHERE r.trust_product_id = 2
  AND r.asset_code IS DISTINCT FROM ta.asset_code;

\echo '=== 跨表对齐 107113281945（期望 cross_diff=0）==='
SELECT
    m.repaid AS monitor_repaid,
    r.total AS repay_by_r_asset_code,
    m.repaid - r.total AS cross_diff
FROM (
    SELECT SUM(repaid_amount) AS repaid
    FROM trust_asset_monitor_records
    WHERE trust_product_id = 2
      AND data_date = '2026-07-03'
      AND asset_code = '107113281945'
) m,
(
    SELECT COALESCE(SUM(actual_repayment_amount), 0) AS total
    FROM trust_repayment_detail_records
    WHERE trust_product_id = 2
      AND asset_code = '107113281945'
) r;
