-- ============================================================
-- 资产监控快照重复记录清理
-- 目标表：trust_asset_monitor_records
-- 规则：同一 (trust_product_id, data_date, trust_asset_id) 只保留 id 最大的一条
--
-- 原则：
--   - 不使用 TRUNCATE
--   - 不删除还款明细 / 资产主表 / 跟进台账
--   - 删除前备份到 backup_duplicate_monitor_records_20260623
--
-- 预计删除：412 行（产品 1 · 2026-06-12 · 824 行 → 412 资产）
-- 根因：同一 data_date 从不同 source_sheet_name 各导入一次
--
-- 执行：psql -U admin -d realestate -f cleanup_duplicate_monitor_records.sql
-- 回滚：见文件末尾 rollback 段
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- 1. 删除前统计
-- ------------------------------------------------------------
SELECT '=== 删除前统计 ===' AS section;

SELECT
    trust_product_id,
    data_date,
    COUNT(*) AS row_count,
    COUNT(DISTINCT trust_asset_id) AS asset_count,
    COUNT(*) - COUNT(DISTINCT trust_asset_id) AS duplicate_count
FROM trust_asset_monitor_records
GROUP BY trust_product_id, data_date
HAVING COUNT(*) > COUNT(DISTINCT trust_asset_id)
ORDER BY duplicate_count DESC;

SELECT '待删除重复行数' AS metric, COUNT(*) AS cnt
FROM (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY trust_product_id, data_date, trust_asset_id
            ORDER BY id DESC
        ) AS rn
    FROM trust_asset_monitor_records
) t
WHERE rn > 1;

SELECT '全表 monitor 行数（删除前）' AS metric, COUNT(*) AS cnt
FROM trust_asset_monitor_records;

-- ------------------------------------------------------------
-- 2. 备份重复记录（回滚用）
-- ------------------------------------------------------------
DROP TABLE IF EXISTS backup_duplicate_monitor_records_20260623;

CREATE TABLE backup_duplicate_monitor_records_20260623 AS
SELECT *
FROM trust_asset_monitor_records
WHERE id IN (
    SELECT id
    FROM (
        SELECT
            id,
            ROW_NUMBER() OVER (
                PARTITION BY trust_product_id, data_date, trust_asset_id
                ORDER BY id DESC
            ) AS rn
        FROM trust_asset_monitor_records
    ) t
    WHERE rn > 1
);

SELECT '备份表行数' AS metric, COUNT(*) AS cnt
FROM backup_duplicate_monitor_records_20260623;

-- ------------------------------------------------------------
-- 3. 删除重复记录（保留 id 最大）
-- ------------------------------------------------------------
DELETE FROM trust_asset_monitor_records
WHERE id IN (
    SELECT id
    FROM (
        SELECT
            id,
            ROW_NUMBER() OVER (
                PARTITION BY trust_product_id, data_date, trust_asset_id
                ORDER BY id DESC
            ) AS rn
        FROM trust_asset_monitor_records
    ) t
    WHERE rn > 1
);

SELECT '本次删除行数' AS metric, COUNT(*) AS cnt
FROM backup_duplicate_monitor_records_20260623 b
WHERE NOT EXISTS (
    SELECT 1 FROM trust_asset_monitor_records m WHERE m.id = b.id
);

-- ------------------------------------------------------------
-- 4. 删除后校验
-- ------------------------------------------------------------
SELECT '=== 删除后校验 ===' AS section;

SELECT
    trust_product_id,
    data_date,
    COUNT(*) AS row_count,
    COUNT(DISTINCT trust_asset_id) AS asset_count,
    COUNT(*) - COUNT(DISTINCT trust_asset_id) AS duplicate_count
FROM trust_asset_monitor_records
GROUP BY trust_product_id, data_date
HAVING COUNT(*) > COUNT(DISTINCT trust_asset_id);

SELECT '全表 monitor 行数（删除后）' AS metric, COUNT(*) AS cnt
FROM trust_asset_monitor_records;

-- 期望：上一条 HAVING 查询无结果；删除后全表约 1130 行（原 1542 - 412）

COMMIT;

-- ============================================================
-- 回滚（如需撤销删除，在单独事务中执行）
-- ============================================================
-- BEGIN;
-- INSERT INTO trust_asset_monitor_records
-- SELECT * FROM backup_duplicate_monitor_records_20260623;
-- SELECT '回滚后全表行数' AS metric, COUNT(*) AS cnt FROM trust_asset_monitor_records;
-- COMMIT;
