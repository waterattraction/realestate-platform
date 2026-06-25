-- 发行资产明细 — 新增 migration_type 字段
-- 执行：psql -f issuance_migration_type_schema.sql

ALTER TABLE trust_product_issuance_asset_records
    ADD COLUMN IF NOT EXISTS migration_type VARCHAR(32) NULL;

CREATE INDEX IF NOT EXISTS idx_issuance_migration_type
    ON trust_product_issuance_asset_records (migration_type);
