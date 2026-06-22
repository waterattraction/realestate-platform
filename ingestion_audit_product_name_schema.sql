-- ============================================================
-- ingestion_audit_product_name_schema.sql
-- 导入审计 — 补充 trust_product_id / trust_product_name 快照
-- 执行顺序：… → trust_product_seed_v2.sql → 本文件
-- 不删除数据，不 TRUNCATE
-- ============================================================

-- 1. pipeline 批次审计：补充产品名称快照
ALTER TABLE ingestion_pipeline_runs
    ADD COLUMN IF NOT EXISTS trust_product_name VARCHAR(200);

-- 2. sheet 级审计：补充产品 ID + 名称（trust_product_id 可空，兼容历史/异常记录）
ALTER TABLE ingestion_sheet_runs
    ADD COLUMN IF NOT EXISTS trust_product_id BIGINT REFERENCES trust_products (id),
    ADD COLUMN IF NOT EXISTS trust_product_name VARCHAR(200);

CREATE INDEX IF NOT EXISTS idx_ingestion_sheet_runs_product
    ON ingestion_sheet_runs (trust_product_id);

-- 3. 回填历史 pipeline 记录
UPDATE ingestion_pipeline_runs r
SET trust_product_name = tp.name
FROM trust_products tp
WHERE r.trust_product_id = tp.id
  AND r.trust_product_name IS NULL;

-- 4. 回填历史 sheet 记录
UPDATE ingestion_sheet_runs sr
SET
    trust_product_id   = pr.trust_product_id,
    trust_product_name = COALESCE(pr.trust_product_name, tp.name)
FROM ingestion_pipeline_runs pr
JOIN trust_products tp ON tp.id = pr.trust_product_id
WHERE sr.pipeline_run_id = pr.id
  AND sr.trust_product_id IS NULL;
