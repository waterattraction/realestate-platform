-- ============================================================
-- 发行资产明细数据修正 — 美好生活1号
-- 产品：trust_product_id = 1
-- 文件：附件1：基础资产清单（美好生活1号）.xlsx
-- 修正：issue_date 2025-12-24 → 2025-09-25，business_asset_key，city（地址规则）
--
-- 注意：本脚本仅生成，请人工审阅后在 psql 中执行。
-- city 若需 100% 准确（京北/京南/上海 所属区域），建议代码增强后
--       以 issue_date=2025-09-25 重导同一 Excel。
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- 1. 执行前统计
-- ------------------------------------------------------------
SELECT
    trust_product_id,
    issue_date,
    source_file_name,
    COUNT(*) AS row_count,
    COUNT(*) FILTER (WHERE city IS NULL OR city = '') AS city_blank_count
FROM trust_product_issuance_asset_records
WHERE trust_product_id = 1
  AND source_file_name = '附件1：基础资产清单（美好生活1号）.xlsx'
GROUP BY trust_product_id, issue_date, source_file_name;

-- ------------------------------------------------------------
-- 2. 备份
-- ------------------------------------------------------------
DROP TABLE IF EXISTS backup_issuance_product1_before_fix_20260624;

CREATE TABLE backup_issuance_product1_before_fix_20260624 AS
SELECT *
FROM trust_product_issuance_asset_records
WHERE trust_product_id = 1
  AND issue_date = DATE '2025-12-24'
  AND source_file_name = '附件1：基础资产清单（美好生活1号）.xlsx';

-- ------------------------------------------------------------
-- 3. 修正发行日期与 business_asset_key
-- ------------------------------------------------------------
UPDATE trust_product_issuance_asset_records
SET
    issue_date = DATE '2025-09-25',
    business_asset_key = trust_product_id || ':2025-09-25:' || custody_asset_code,
    updated_at = NOW()
WHERE trust_product_id = 1
  AND issue_date = DATE '2025-12-24'
  AND source_file_name = '附件1：基础资产清单（美好生活1号）.xlsx';

-- ------------------------------------------------------------
-- 4. 修正 city（地址 + 区名规则；无法从所属区域恢复）
-- ------------------------------------------------------------
UPDATE trust_product_issuance_asset_records
SET
    city = CASE
        WHEN property_address LIKE '%上海%' THEN '上海'
        WHEN property_address LIKE '%北京%' THEN '北京'
        WHEN property_address LIKE '%海淀%' THEN '北京'
        WHEN property_address LIKE '%朝阳%' THEN '北京'
        WHEN property_address LIKE '%丰台%' THEN '北京'
        WHEN property_address LIKE '%西城%' THEN '北京'
        WHEN property_address LIKE '%东城%' THEN '北京'
        WHEN property_address LIKE '%石景山%' THEN '北京'
        WHEN property_address LIKE '%通州%' THEN '北京'
        WHEN property_address LIKE '%昌平%' THEN '北京'
        WHEN property_address LIKE '%大兴%' THEN '北京'
        WHEN property_address LIKE '%顺义%' THEN '北京'
        WHEN property_address LIKE '%房山%' THEN '北京'
        WHEN property_address LIKE '%门头沟%' THEN '北京'
        WHEN property_address LIKE '%徐汇%' THEN '上海'
        WHEN property_address LIKE '%静安%' THEN '上海'
        WHEN property_address LIKE '%浦东%' THEN '上海'
        WHEN property_address LIKE '%闵行%' THEN '上海'
        WHEN property_address LIKE '%长宁%' THEN '上海'
        WHEN property_address LIKE '%普陀%' THEN '上海'
        WHEN property_address LIKE '%杨浦%' THEN '上海'
        WHEN property_address LIKE '%虹口%' THEN '上海'
        WHEN property_address LIKE '%黄浦%' THEN '上海'
        WHEN property_address LIKE '%宝山%' THEN '上海'
        WHEN property_address LIKE '%松江%' THEN '上海'
        WHEN property_address LIKE '%嘉定%' THEN '上海'
        WHEN property_address LIKE '%青浦%' THEN '上海'
        ELSE city
    END,
    updated_at = NOW()
WHERE trust_product_id = 1
  AND issue_date = DATE '2025-09-25'
  AND source_file_name = '附件1：基础资产清单（美好生活1号）.xlsx'
  AND (city IS NULL OR city = '');

-- ------------------------------------------------------------
-- 5. 审计表同步
-- ------------------------------------------------------------
UPDATE issuance_import_runs
SET issue_date = DATE '2025-09-25'
WHERE trust_product_id = 1
  AND issue_date = DATE '2025-12-24'
  AND source_file = '附件1：基础资产清单（美好生活1号）.xlsx';

UPDATE issuance_import_sheet_runs
SET issue_date = DATE '2025-09-25'
WHERE trust_product_id = 1
  AND issue_date = DATE '2025-12-24'
  AND source_file_name = '附件1：基础资产清单（美好生活1号）.xlsx';

-- ------------------------------------------------------------
-- 6. 执行后验证
-- ------------------------------------------------------------
SELECT
    issue_date,
    COUNT(*) AS row_count,
    COUNT(*) FILTER (WHERE city IS NULL OR city = '') AS city_blank_count,
    COUNT(*) FILTER (WHERE city = '北京') AS beijing_count,
    COUNT(*) FILTER (WHERE city = '上海') AS shanghai_count
FROM trust_product_issuance_asset_records
WHERE trust_product_id = 1
  AND source_file_name = '附件1：基础资产清单（美好生活1号）.xlsx'
GROUP BY issue_date;

SELECT business_asset_key
FROM trust_product_issuance_asset_records
WHERE trust_product_id = 1
  AND source_file_name = '附件1：基础资产清单（美好生活1号）.xlsx'
LIMIT 5;

-- 若 city_blank_count > 0，请考虑代码增强后以 2025-09-25 重导同一 Excel。

COMMIT;

-- ------------------------------------------------------------
-- 7. 回滚说明
-- ------------------------------------------------------------
-- 如需回滚（请先 ROLLBACK 上述事务若尚未 COMMIT，或在新事务中执行）：
--
-- DELETE FROM trust_product_issuance_asset_records
-- WHERE trust_product_id = 1
--   AND issue_date = DATE '2025-09-25'
--   AND source_file_name = '附件1：基础资产清单（美好生活1号）.xlsx';
--
-- INSERT INTO trust_product_issuance_asset_records
-- SELECT * FROM backup_issuance_product1_before_fix_20260624;
--
-- UPDATE issuance_import_runs
-- SET issue_date = DATE '2025-12-24'
-- WHERE trust_product_id = 1
--   AND issue_date = DATE '2025-09-25'
--   AND source_file = '附件1：基础资产清单（美好生活1号）.xlsx';
--
-- UPDATE issuance_import_sheet_runs
-- SET issue_date = DATE '2025-12-24'
-- WHERE trust_product_id = 1
--   AND issue_date = DATE '2025-09-25'
--   AND source_file_name = '附件1：基础资产清单（美好生活1号）.xlsx';
