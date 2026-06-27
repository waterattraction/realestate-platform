-- ============================================================
-- Excel 导入 V2 — Schema Migration
-- 执行顺序：… → users_schema.sql → 本文件
-- 不删除数据，不 TRUNCATE
-- ============================================================

-- 1. 扩展导入批次审计
ALTER TABLE assetinfo_pipeline_runs
    ADD COLUMN IF NOT EXISTS skipped_sheet_count INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS failed_sheet_count INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS error_message TEXT;

-- 2. Sheet 级审计
CREATE TABLE IF NOT EXISTS assetinfo_sheet_runs (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_run_id     BIGINT NOT NULL REFERENCES assetinfo_pipeline_runs (id),
    source_file_name    VARCHAR(500) NOT NULL,
    source_sheet_name   VARCHAR(200) NOT NULL,
    sheet_type          VARCHAR(32)  NOT NULL,
    data_date           DATE,
    row_count           INT NOT NULL DEFAULT 0,
    amount_sum          NUMERIC(18, 2),
    action              VARCHAR(32)  NOT NULL,
    message             TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_assetinfo_sheet_runs_pipeline
    ON assetinfo_sheet_runs (pipeline_run_id);

CREATE INDEX IF NOT EXISTS idx_assetinfo_sheet_runs_source
    ON assetinfo_sheet_runs (source_file_name, source_sheet_name);

-- 3. 查询加速索引（非 UNIQUE）
CREATE INDEX IF NOT EXISTS idx_repayment_source_scope
    ON trust_repayment_detail_records (trust_product_id, source_file_name, source_sheet_name);

CREATE INDEX IF NOT EXISTS idx_monitor_product_date_sheet
    ON trust_asset_monitor_records (trust_product_id, data_date, source_sheet_name);

CREATE INDEX IF NOT EXISTS idx_monitor_product_date_asset
    ON trust_asset_monitor_records (trust_product_id, data_date, asset_code);

CREATE INDEX IF NOT EXISTS idx_repayment_business_key
    ON trust_repayment_detail_records (trust_product_id, repayment_date, asset_code, period_no);

-- 4. 无还款明细时 overdue_days 允许 NULL
ALTER TABLE trust_asset_monitor_records
    ALTER COLUMN overdue_days DROP NOT NULL;
