-- ============================================================
-- 房地产资产证券化平台 V0.1 — Real Estate Securitization Platform — PostgreSQL Schema
-- ============================================================

-- ------------------------------------------------------------
-- 1. 资产包
-- ------------------------------------------------------------
CREATE TABLE asset_pools (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code                VARCHAR(32)  NOT NULL,
    name                VARCHAR(200) NOT NULL,
    status              VARCHAR(32)  NOT NULL DEFAULT 'pending',
    appraised_value     NUMERIC(18, 2) NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_asset_pools_code UNIQUE (code),
    CONSTRAINT chk_asset_pools_value CHECK (appraised_value >= 0)
);

CREATE INDEX idx_asset_pools_status ON asset_pools (status);

-- ------------------------------------------------------------
-- 2. 信托产品
-- ------------------------------------------------------------
CREATE TABLE trust_products (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asset_pool_id           BIGINT NOT NULL REFERENCES asset_pools (id),
    code                    VARCHAR(32)  NOT NULL,
    name                    VARCHAR(200) NOT NULL,
    status                  VARCHAR(32)  NOT NULL DEFAULT 'draft',
    expected_return_rate    NUMERIC(8, 4),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_trust_products_code UNIQUE (code)
);

CREATE INDEX idx_trust_products_asset_pool_id ON trust_products (asset_pool_id);
CREATE INDEX idx_trust_products_status ON trust_products (status);

-- ------------------------------------------------------------
-- 自动更新 updated_at
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_asset_pools_updated_at
    BEFORE UPDATE ON asset_pools FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_trust_products_updated_at
    BEFORE UPDATE ON trust_products FOR EACH ROW EXECUTE FUNCTION set_updated_at();
