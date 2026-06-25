-- ============================================================
-- 信托资产逾期管理 V0.1 — Overdue Module Schema
-- 执行顺序：schema.sql → seed.sql → 本文件
-- ============================================================

-- ------------------------------------------------------------
-- 1. 信托底层房源
-- ------------------------------------------------------------
CREATE TABLE trust_assets (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trust_product_id        BIGINT NOT NULL REFERENCES trust_products (id),
    asset_code              VARCHAR(64)  NOT NULL,
    asset_name              VARCHAR(200),
    initial_transfer_amount NUMERIC(18, 2) NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_trust_assets_product_code UNIQUE (trust_product_id, asset_code),
    CONSTRAINT chk_trust_assets_initial CHECK (initial_transfer_amount >= 0)
);

CREATE INDEX idx_trust_assets_trust_product_id ON trust_assets (trust_product_id);

-- ------------------------------------------------------------
-- 2. 资产监控记录（更新的资产数据表）
-- ------------------------------------------------------------
CREATE TABLE trust_asset_monitor_records (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trust_product_id        BIGINT NOT NULL REFERENCES trust_products (id),
    trust_asset_id          BIGINT NOT NULL REFERENCES trust_assets (id),
    asset_code              VARCHAR(64)  NOT NULL,
    data_date               DATE NOT NULL,
    initial_transfer_amount NUMERIC(18, 2) NOT NULL DEFAULT 0,
    repaid_amount           NUMERIC(18, 2) NOT NULL DEFAULT 0,
    remaining_amount        NUMERIC(18, 2) NOT NULL DEFAULT 0,
    overdue_days            INT NOT NULL DEFAULT 0,
    last_payment_date       DATE,
    max_payment_date        DATE,
    source_file_name        VARCHAR(500),
    source_sheet_name       VARCHAR(200),
    synced_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_trust_asset_monitor_product_date
    ON trust_asset_monitor_records (trust_product_id, data_date DESC);
CREATE INDEX idx_trust_asset_monitor_asset_date
    ON trust_asset_monitor_records (trust_asset_id, data_date DESC);

-- ------------------------------------------------------------
-- 3. 还款明细记录（全量还款明细汇总）
-- ------------------------------------------------------------
CREATE TABLE trust_repayment_detail_records (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trust_product_id        BIGINT NOT NULL REFERENCES trust_products (id),
    trust_asset_id          BIGINT NOT NULL REFERENCES trust_assets (id),
    asset_code              VARCHAR(64)  NOT NULL,
    data_date               DATE NOT NULL,
    period_no               VARCHAR(32),
    actual_repayment_amount NUMERIC(18, 2) NOT NULL DEFAULT 0,
    repayment_date          DATE,
    source_file_name        VARCHAR(500),
    source_sheet_name       VARCHAR(200),
    synced_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_trust_repayment_product_date
    ON trust_repayment_detail_records (trust_product_id, data_date DESC);
CREATE INDEX idx_trust_repayment_asset_date
    ON trust_repayment_detail_records (trust_asset_id, data_date);

-- ------------------------------------------------------------
-- 4. 逾期跟进台账
-- ------------------------------------------------------------
CREATE TABLE trust_overdue_followups (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trust_product_id    BIGINT NOT NULL REFERENCES trust_products (id),
    trust_asset_id      BIGINT NOT NULL REFERENCES trust_assets (id),
    data_date           DATE NOT NULL,
    trigger_source      VARCHAR(32) NOT NULL DEFAULT 'system',
    overdue_reason      TEXT,
    follow_up_plan      TEXT,
    status              VARCHAR(32) NOT NULL DEFAULT 'open',
    owner_name          VARCHAR(100),
    last_follow_up_at   TIMESTAMPTZ,
    trust_feedback      TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_trust_overdue_followups_status ON trust_overdue_followups (status);
CREATE INDEX idx_trust_overdue_followups_product_asset
    ON trust_overdue_followups (trust_product_id, trust_asset_id);

-- ------------------------------------------------------------
-- 自动更新 updated_at（复用 schema.sql 中的 set_updated_at）
-- ------------------------------------------------------------
CREATE TRIGGER trg_trust_assets_updated_at
    BEFORE UPDATE ON trust_assets FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_trust_overdue_followups_updated_at
    BEFORE UPDATE ON trust_overdue_followups FOR EACH ROW EXECUTE FUNCTION set_updated_at();
