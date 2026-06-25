-- type: ops/fix
-- status: executed
-- executed_at: 2026-06-12
-- safe_to_rerun: no
-- scope: trust_product_id=1 还款明细全量重灌
-- ============================================================
-- 美好生活1号 · 还款明细全量重灌（仅 product_id=1）
-- 权威文件：美好生活1号-还款明细披露信息_20260612.xlsx
-- 不删除：trust_assets / trust_asset_monitor_records /
--         trust_overdue_followups / risk_alerts / 其他产品还款明细
-- ============================================================

BEGIN;

SELECT '=== 重灌前统计 ===' AS section;

SELECT '删除前 product1 总行数' AS metric, COUNT(*) AS cnt
FROM trust_repayment_detail_records WHERE trust_product_id = 1;

SELECT source_file_name, COUNT(*) AS cnt
FROM trust_repayment_detail_records WHERE trust_product_id = 1
GROUP BY source_file_name ORDER BY cnt DESC;

DROP TABLE IF EXISTS backup_repayment_product1_full_20260623;

CREATE TABLE backup_repayment_product1_full_20260623 AS
SELECT * FROM trust_repayment_detail_records WHERE trust_product_id = 1;

SELECT '备份行数' AS metric, COUNT(*) AS cnt
FROM backup_repayment_product1_full_20260623;

DELETE FROM trust_repayment_detail_records WHERE trust_product_id = 1;

SELECT '删除后 product1 行数（预期 0）' AS metric, COUNT(*) AS cnt
FROM trust_repayment_detail_records WHERE trust_product_id = 1;

COMMIT;

-- 回滚（事务外执行）：
-- DELETE FROM trust_repayment_detail_records WHERE trust_product_id = 1;
-- INSERT INTO trust_repayment_detail_records
-- SELECT * FROM backup_repayment_product1_full_20260623;
