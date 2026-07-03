-- ============================================================
-- 信托风控数据准入管道 V1 — Schema 补充
-- 执行顺序：… → overdue_schema.sql → risk_v2_schema.sql → 本文件
-- ============================================================

ALTER TABLE trust_assets
    ADD COLUMN IF NOT EXISTS custody_asset_code VARCHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS uq_trust_assets_product_custody
    ON trust_assets (trust_product_id, custody_asset_code)
    WHERE custody_asset_code IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_trust_assets_product_source
    ON trust_assets (trust_product_id, source_asset_code)
    WHERE source_asset_code IS NOT NULL;

CREATE TABLE IF NOT EXISTS data_mapping_config (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    config_version      VARCHAR(32)  NOT NULL DEFAULT 'v1.0',
    sheet_name          VARCHAR(200) NOT NULL,
    sheet_type          VARCHAR(32)  NOT NULL,
    excel_column        VARCHAR(200) NOT NULL,
    target_table        VARCHAR(64)  NOT NULL,
    target_column       VARCHAR(64)  NOT NULL,
    field_semantic      VARCHAR(32)  NOT NULL DEFAULT 'asset',
    transform_rule      VARCHAR(200),
    is_required         BOOLEAN NOT NULL DEFAULT FALSE,
    is_business_key     BOOLEAN NOT NULL DEFAULT FALSE,
    priority            INT NOT NULL DEFAULT 100,
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_data_mapping_config_key
    ON data_mapping_config (sheet_name, excel_column, target_table, target_column);
