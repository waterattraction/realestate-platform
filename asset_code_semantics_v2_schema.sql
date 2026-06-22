-- ============================================================
-- 托管房源号 / 资产分笔号 — 兼容迁移 V2
-- 执行顺序：… → ingestion_audit_product_name_schema.sql → 本文件
-- 原则：只加列 + 回填；不修改 asset_code 历史值；不删旧索引/约束
-- ============================================================

-- ------------------------------------------------------------
-- 1. Schema：新增字段
-- ------------------------------------------------------------
ALTER TABLE trust_assets
    ADD COLUMN IF NOT EXISTS source_asset_code VARCHAR(64);

ALTER TABLE trust_repayment_detail_records
    ADD COLUMN IF NOT EXISTS custody_asset_code VARCHAR(64),
    ADD COLUMN IF NOT EXISTS source_asset_code VARCHAR(64);

ALTER TABLE trust_asset_monitor_records
    ADD COLUMN IF NOT EXISTS custody_asset_code VARCHAR(64),
    ADD COLUMN IF NOT EXISTS source_asset_code VARCHAR(64);

-- ------------------------------------------------------------
-- 2. 数据回填：trust_assets
--    source_asset_code = asset_code（分笔号）
--    custody_asset_code 保持现状；asset_code 不变
-- ------------------------------------------------------------
UPDATE trust_assets
SET source_asset_code = asset_code
WHERE source_asset_code IS NULL;

-- FY 演示数据（custody 为 NULL）：仅回填 source_asset_code，不生成托管号

-- ------------------------------------------------------------
-- 3. 数据回填：trust_repayment_detail_records
-- ------------------------------------------------------------
UPDATE trust_repayment_detail_records r
SET
    custody_asset_code = ta.custody_asset_code,
    source_asset_code = r.asset_code
FROM trust_assets ta
WHERE ta.id = r.trust_asset_id
  AND r.source_asset_code IS NULL;

-- FY 等无 custody 的资产：source_asset_code 仍等于 asset_code
UPDATE trust_repayment_detail_records r
SET source_asset_code = r.asset_code
FROM trust_assets ta
WHERE ta.id = r.trust_asset_id
  AND ta.custody_asset_code IS NULL
  AND r.source_asset_code IS NULL;

-- ------------------------------------------------------------
-- 4. 数据回填：trust_asset_monitor_records
-- ------------------------------------------------------------
UPDATE trust_asset_monitor_records m
SET
    custody_asset_code = ta.custody_asset_code,
    source_asset_code = m.asset_code
FROM trust_assets ta
WHERE ta.id = m.trust_asset_id
  AND m.source_asset_code IS NULL;

UPDATE trust_asset_monitor_records m
SET source_asset_code = m.asset_code
FROM trust_assets ta
WHERE ta.id = m.trust_asset_id
  AND ta.custody_asset_code IS NULL
  AND m.source_asset_code IS NULL;

-- ------------------------------------------------------------
-- 5. 新增查询索引（保留旧索引）
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_repayment_custody_source
    ON trust_repayment_detail_records (
        trust_product_id,
        repayment_date,
        custody_asset_code,
        source_asset_code
    );

CREATE INDEX IF NOT EXISTS idx_monitor_custody_source
    ON trust_asset_monitor_records (
        trust_product_id,
        data_date,
        custody_asset_code,
        source_asset_code
    );
