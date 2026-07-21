-- type: migration
-- created_at: 2026-07-21
-- author: ops
-- purpose: 手工结算独立账本 + 附件（读路径 overlay，不写还款/监控事实表）
-- dependencies: baseline
-- idempotent: yes

CREATE TABLE IF NOT EXISTS trust_asset_manual_settlements (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trust_product_id    BIGINT NOT NULL REFERENCES trust_products (id),
    asset_code          VARCHAR(128) NOT NULL,
    custody_asset_code  VARCHAR(128) NULL,
    settlement_date     DATE NOT NULL,
    settled_by          VARCHAR(100) NOT NULL,
    payer               VARCHAR(100) NOT NULL,
    amount              NUMERIC(18, 2) NOT NULL,
    description         TEXT NULL,
    created_by          VARCHAR(64) NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    voided_at           TIMESTAMPTZ NULL,
    voided_by           VARCHAR(64) NULL,
    CONSTRAINT chk_manual_settlement_amount_positive CHECK (amount > 0)
);

CREATE INDEX IF NOT EXISTS idx_manual_settlements_product_asset
    ON trust_asset_manual_settlements (trust_product_id, asset_code)
    WHERE voided_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_manual_settlements_product_date
    ON trust_asset_manual_settlements (trust_product_id, settlement_date DESC)
    WHERE voided_at IS NULL;

CREATE TABLE IF NOT EXISTS trust_asset_manual_settlement_attachments (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    settlement_id       BIGINT NOT NULL
        REFERENCES trust_asset_manual_settlements (id) ON DELETE CASCADE,
    file_name           VARCHAR(500) NOT NULL,
    stored_path         VARCHAR(1000) NOT NULL,
    content_type        VARCHAR(200) NULL,
    file_size           BIGINT NULL,
    attachment_type     VARCHAR(32) NOT NULL DEFAULT 'file',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_manual_settlement_attachments_settlement
    ON trust_asset_manual_settlement_attachments (settlement_id);
