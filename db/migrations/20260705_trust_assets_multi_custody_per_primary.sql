-- 一主编号多托管：schema 声明（不修改历史行数据）
-- asset_code（主编号）允许同一产品下多行；持久化锚点为 custody / source

ALTER TABLE trust_assets
    DROP CONSTRAINT IF EXISTS uq_trust_assets_product_code;

CREATE INDEX IF NOT EXISTS idx_trust_assets_product_asset_code
    ON trust_assets (trust_product_id, asset_code);

CREATE UNIQUE INDEX IF NOT EXISTS uq_trust_assets_product_source
    ON trust_assets (trust_product_id, source_asset_code)
    WHERE source_asset_code IS NOT NULL;
