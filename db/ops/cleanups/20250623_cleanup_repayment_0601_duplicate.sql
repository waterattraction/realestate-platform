-- type: ops/cleanup
-- status: executed
-- executed_at: 2026-06-23
-- safe_to_rerun: no
-- scope: trust_product_id=1 还款明细 0601_1 重复批次
-- ============================================================
-- 美好生活1号 · 还款明细 · 0601_1 重复批次最小安全清理
-- 目标表：trust_repayment_detail_records
--
-- 删除范围（仅此文件）：
--   trust_product_id = 1
--   source_file_name = '美好生活1号-还款明细披露信息_20260529_已更新0601_1.xlsx'
--
-- 不删除：0608更新、0605、20260612 无扩展名等其他小批次
--
-- 业务依据：
--   0601_1 全部 4,097 行在 20260612.xlsx 中均有
--   「托管房源 + 资产分笔 + 还款日 + 金额」四字段匹配（独有 = 0）。
--   注：0601_1 由 V1 导入，period_no 全为 NULL；20260612 保留期数，
--   故按五字段（含 period_no）统计时会出现“伪独有”，不代表真实新付款。
--
-- 执行前统计（2026-06-23 查询）：
--   删除前总行数 .............. 8,771
--   0601_1 行数 ............... 4,097
--   20260612 主文件行数 ....... 4,386
--   0601_1 独有（五字段）....... 2,647 键 / 3,128 行（period_no NULL 导致）
--   0601_1 独有（四字段）....... 0 键 / 0 行
--   预计删除行数 .............. 4,097
--   删除后预计总行数 .......... 4,674
--
-- 执行：docker compose exec -T postgres psql -U <user> -d <db> -f cleanup_repayment_0601_duplicate.sql
-- 或：  psql -U admin -d realestate -f cleanup_repayment_0601_duplicate.sql
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- 1. 执行前统计
-- ------------------------------------------------------------
SELECT '=== 执行前统计 ===' AS section;

SELECT '删除前总行数 (product 1)' AS metric, COUNT(*) AS cnt
FROM trust_repayment_detail_records
WHERE trust_product_id = 1;

SELECT '0601_1 行数' AS metric, COUNT(*) AS cnt
FROM trust_repayment_detail_records
WHERE trust_product_id = 1
  AND source_file_name = '美好生活1号-还款明细披露信息_20260529_已更新0601_1.xlsx';

SELECT '20260612 主文件行数' AS metric, COUNT(*) AS cnt
FROM trust_repayment_detail_records
WHERE trust_product_id = 1
  AND source_file_name = '美好生活1号-还款明细披露信息_20260612.xlsx';

-- 独有记录（五字段：含 period_no）
SELECT '0601_1 独有业务键数 (五字段含 period_no)' AS metric, COUNT(*) AS cnt
FROM (
    SELECT DISTINCT
        custody_asset_code,
        source_asset_code,
        repayment_date,
        actual_repayment_amount,
        period_no
    FROM trust_repayment_detail_records
    WHERE trust_product_id = 1
      AND source_file_name = '美好生活1号-还款明细披露信息_20260529_已更新0601_1.xlsx'
) a
WHERE NOT EXISTS (
    SELECT 1
    FROM trust_repayment_detail_records b
    WHERE b.trust_product_id = 1
      AND b.source_file_name = '美好生活1号-还款明细披露信息_20260612.xlsx'
      AND b.custody_asset_code = a.custody_asset_code
      AND b.source_asset_code IS NOT DISTINCT FROM a.source_asset_code
      AND b.repayment_date = a.repayment_date
      AND b.actual_repayment_amount = a.actual_repayment_amount
      AND b.period_no IS NOT DISTINCT FROM a.period_no
);

-- 独有记录（四字段：付款实质，不含 period_no）
SELECT '0601_1 独有业务键数 (四字段不含 period_no)' AS metric, COUNT(*) AS cnt
FROM (
    SELECT DISTINCT
        custody_asset_code,
        source_asset_code,
        repayment_date,
        actual_repayment_amount
    FROM trust_repayment_detail_records
    WHERE trust_product_id = 1
      AND source_file_name = '美好生活1号-还款明细披露信息_20260529_已更新0601_1.xlsx'
) a
WHERE NOT EXISTS (
    SELECT 1
    FROM trust_repayment_detail_records b
    WHERE b.trust_product_id = 1
      AND b.source_file_name = '美好生活1号-还款明细披露信息_20260612.xlsx'
      AND b.custody_asset_code = a.custody_asset_code
      AND b.source_asset_code IS NOT DISTINCT FROM a.source_asset_code
      AND b.repayment_date = a.repayment_date
      AND b.actual_repayment_amount = a.actual_repayment_amount
);

SELECT '0601_1 在 0612 有四字段匹配的行数' AS metric, COUNT(*) AS cnt
FROM trust_repayment_detail_records r
WHERE r.trust_product_id = 1
  AND r.source_file_name = '美好生活1号-还款明细披露信息_20260529_已更新0601_1.xlsx'
  AND EXISTS (
    SELECT 1
    FROM trust_repayment_detail_records b
    WHERE b.trust_product_id = 1
      AND b.source_file_name = '美好生活1号-还款明细披露信息_20260612.xlsx'
      AND b.custody_asset_code = r.custody_asset_code
      AND b.source_asset_code IS NOT DISTINCT FROM r.source_asset_code
      AND b.repayment_date = r.repayment_date
      AND b.actual_repayment_amount = r.actual_repayment_amount
  );

-- ------------------------------------------------------------
-- 2. 备份（回滚用）
-- ------------------------------------------------------------
DROP TABLE IF EXISTS backup_repayment_product1_0601_20260623;

CREATE TABLE backup_repayment_product1_0601_20260623 AS
SELECT *
FROM trust_repayment_detail_records
WHERE trust_product_id = 1
  AND source_file_name = '美好生活1号-还款明细披露信息_20260529_已更新0601_1.xlsx';

SELECT '备份表行数' AS metric, COUNT(*) AS cnt
FROM backup_repayment_product1_0601_20260623;

-- ------------------------------------------------------------
-- 3. 删除 0601_1 批次
-- ------------------------------------------------------------
DELETE FROM trust_repayment_detail_records
WHERE trust_product_id = 1
  AND source_file_name = '美好生活1号-还款明细披露信息_20260529_已更新0601_1.xlsx';

SELECT '本次删除行数' AS metric, COUNT(*) AS cnt
FROM backup_repayment_product1_0601_20260623;

-- ------------------------------------------------------------
-- 4. 执行后验证
-- ------------------------------------------------------------
SELECT '=== 执行后验证 ===' AS section;

SELECT '删除后总行数 (product 1)' AS metric, COUNT(*) AS cnt
FROM trust_repayment_detail_records
WHERE trust_product_id = 1;

SELECT '0601_1 剩余行数 (预期 0)' AS metric, COUNT(*) AS cnt
FROM trust_repayment_detail_records
WHERE trust_product_id = 1
  AND source_file_name = '美好生活1号-还款明细披露信息_20260529_已更新0601_1.xlsx';

-- 完全重复：五字段完全相同的多条流水
SELECT '完全重复流水组数 (五字段)' AS metric, COUNT(*) AS cnt
FROM (
    SELECT
        custody_asset_code,
        source_asset_code,
        repayment_date,
        actual_repayment_amount,
        period_no
    FROM trust_repayment_detail_records
    WHERE trust_product_id = 1
    GROUP BY
        custody_asset_code,
        source_asset_code,
        repayment_date,
        actual_repayment_amount,
        period_no
    HAVING COUNT(*) > 1
) t;

SELECT '完全重复流水多余行数 (五字段)' AS metric, COUNT(*) AS cnt
FROM (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY
                custody_asset_code,
                source_asset_code,
                repayment_date,
                actual_repayment_amount,
                period_no
            ORDER BY id
        ) AS rn
    FROM trust_repayment_detail_records
    WHERE trust_product_id = 1
) g
WHERE rn > 1;

-- 疑似重复：四字段相同但 period_no 不同（含 NULL vs 有值）
SELECT '疑似重复流水组数 (四字段相同多行)' AS metric, COUNT(*) AS cnt
FROM (
    SELECT
        custody_asset_code,
        source_asset_code,
        repayment_date,
        actual_repayment_amount
    FROM trust_repayment_detail_records
    WHERE trust_product_id = 1
    GROUP BY
        custody_asset_code,
        source_asset_code,
        repayment_date,
        actual_repayment_amount
    HAVING COUNT(*) > 1
) t;

SELECT '疑似重复流水多余行数 (四字段)' AS metric, COUNT(*) AS cnt
FROM (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY
                custody_asset_code,
                source_asset_code,
                repayment_date,
                actual_repayment_amount
            ORDER BY id
        ) AS rn
    FROM trust_repayment_detail_records
    WHERE trust_product_id = 1
) g
WHERE rn > 1;

COMMIT;

-- ============================================================
-- 回滚（如需恢复 0601_1 批次，在事务外单独执行）
-- ============================================================
-- INSERT INTO trust_repayment_detail_records
-- SELECT *
-- FROM backup_repayment_product1_0601_20260623;
--
-- 验证回滚：
-- SELECT COUNT(*) FROM trust_repayment_detail_records
-- WHERE trust_product_id = 1
--   AND source_file_name = '美好生活1号-还款明细披露信息_20260529_已更新0601_1.xlsx';
-- 预期：4097
