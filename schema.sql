-- ============================================================
-- 房地产资产管理平台 V0.1 — PostgreSQL Schema
-- ============================================================

-- ------------------------------------------------------------
-- 1. 装修项目
-- ------------------------------------------------------------
CREATE TABLE projects (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code                VARCHAR(32)  NOT NULL,
    name                VARCHAR(200) NOT NULL,
    description         TEXT,
    status              VARCHAR(32)  NOT NULL DEFAULT 'draft',
    address             VARCHAR(500),
    city                VARCHAR(100),
    total_budget        NUMERIC(18, 2) NOT NULL DEFAULT 0,
    planned_start_date  DATE,
    planned_end_date    DATE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_projects_code UNIQUE (code),
    CONSTRAINT chk_projects_budget CHECK (total_budget >= 0)
);

CREATE INDEX idx_projects_status ON projects (status);
CREATE INDEX idx_projects_city ON projects (city);

-- ------------------------------------------------------------
-- 2. 资产包
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
-- 3. 项目-资产包关联（多对多）
-- ------------------------------------------------------------
CREATE TABLE project_asset_pools (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id          BIGINT NOT NULL REFERENCES projects (id),
    asset_pool_id       BIGINT NOT NULL REFERENCES asset_pools (id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_project_asset_pools UNIQUE (project_id, asset_pool_id)
);

CREATE INDEX idx_project_asset_pools_project_id ON project_asset_pools (project_id);
CREATE INDEX idx_project_asset_pools_asset_pool_id ON project_asset_pools (asset_pool_id);

-- ------------------------------------------------------------
-- 4. 信托产品
-- ------------------------------------------------------------
CREATE TABLE trust_products (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asset_pool_id           BIGINT NOT NULL REFERENCES asset_pools (id),
    code                    VARCHAR(32)  NOT NULL,
    name                    VARCHAR(200) NOT NULL,
    status                  VARCHAR(32)  NOT NULL DEFAULT 'draft',
    target_amount           NUMERIC(18, 2) NOT NULL,
    raised_amount           NUMERIC(18, 2) NOT NULL DEFAULT 0,
    expected_return_rate    NUMERIC(8, 4),
    open_date               DATE,
    close_date              DATE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_trust_products_code UNIQUE (code),
    CONSTRAINT chk_trust_products_target CHECK (target_amount > 0),
    CONSTRAINT chk_trust_products_raised CHECK (raised_amount >= 0)
);

CREATE INDEX idx_trust_products_asset_pool_id ON trust_products (asset_pool_id);
CREATE INDEX idx_trust_products_status ON trust_products (status);

-- ------------------------------------------------------------
-- 5. 投资人
-- ------------------------------------------------------------
CREATE TABLE investors (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code            VARCHAR(32)  NOT NULL,
    name            VARCHAR(200) NOT NULL,
    investor_type   VARCHAR(32)  NOT NULL DEFAULT 'individual',
    kyc_status      VARCHAR(32)  NOT NULL DEFAULT 'pending',
    phone           VARCHAR(20),
    email           VARCHAR(200),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_investors_code UNIQUE (code)
);

CREATE INDEX idx_investors_type ON investors (investor_type);
CREATE INDEX idx_investors_kyc_status ON investors (kyc_status);

-- ------------------------------------------------------------
-- 6. 投资记录
-- ------------------------------------------------------------
CREATE TABLE investments (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    investor_id         BIGINT NOT NULL REFERENCES investors (id),
    trust_product_id    BIGINT NOT NULL REFERENCES trust_products (id),
    subscription_no     VARCHAR(32) NOT NULL,
    amount              NUMERIC(18, 2) NOT NULL,
    status              VARCHAR(32) NOT NULL DEFAULT 'pending',
    invested_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_investments_subscription_no UNIQUE (subscription_no),
    CONSTRAINT chk_investments_amount CHECK (amount > 0)
);

CREATE INDEX idx_investments_investor_id ON investments (investor_id);
CREATE INDEX idx_investments_trust_product_id ON investments (trust_product_id);
CREATE INDEX idx_investments_status ON investments (status);
CREATE INDEX idx_investments_invested_at ON investments (invested_at DESC);

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

CREATE TRIGGER trg_projects_updated_at
    BEFORE UPDATE ON projects FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_asset_pools_updated_at
    BEFORE UPDATE ON asset_pools FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_project_asset_pools_updated_at
    BEFORE UPDATE ON project_asset_pools FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_trust_products_updated_at
    BEFORE UPDATE ON trust_products FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_investors_updated_at
    BEFORE UPDATE ON investors FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_investments_updated_at
    BEFORE UPDATE ON investments FOR EACH ROW EXECUTE FUNCTION set_updated_at();
