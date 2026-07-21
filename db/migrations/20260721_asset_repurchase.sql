-- type: migration
-- purpose: 资产回购域 — 回购单位主数据 + 回购单 + 资产明细（含冻结监控快照与历史房源号）
--          仅新表落库，不修改监控/发行/还款事实表
-- dependencies: baseline/001_schema.sql（trust_products）
-- idempotent: 是（CREATE TABLE IF NOT EXISTS）
-- 执行：按 db/manifest.txt

-- 回购单位主数据：每单位一套公司/联系人/邮箱
CREATE TABLE IF NOT EXISTS asset_repurchase_units (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_name    VARCHAR(200) NOT NULL UNIQUE,
    contact_name    VARCHAR(100) NOT NULL,
    contact_email   VARCHAR(200) NOT NULL,
    status          VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_asset_repurchase_unit_status
        CHECK (status IN ('active', 'inactive'))
);

-- 回购单头：单位信息落历史快照，后续单位资料修改不影响已成单
CREATE TABLE IF NOT EXISTS asset_repurchase_orders (
    id                          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trust_product_id            BIGINT NOT NULL REFERENCES trust_products (id),
    trust_product_name          VARCHAR(200) NOT NULL,
    repurchase_unit_id          BIGINT NOT NULL REFERENCES asset_repurchase_units (id),
    unit_company_name           VARCHAR(200) NOT NULL,
    unit_contact_name           VARCHAR(100) NULL,
    unit_contact_email          VARCHAR(200) NULL,
    repurchase_business_date    DATE NOT NULL,
    asset_count                 INT NOT NULL DEFAULT 0,
    total_remaining             NUMERIC(18, 2) NULL,
    total_repurchase_amount     NUMERIC(18, 2) NULL,
    status                      VARCHAR(32) NOT NULL DEFAULT 'completed',
    note                        TEXT NULL,
    executed_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    executed_by                 VARCHAR(100) NULL,
    voided_at                   TIMESTAMPTZ NULL,
    voided_by                   VARCHAR(100) NULL,
    void_blocked_reason         TEXT NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_asset_repurchase_order_status
        CHECK (status IN ('completed', 'voided'))
);

CREATE INDEX IF NOT EXISTS idx_asset_repurchase_orders_executed
    ON asset_repurchase_orders (executed_at DESC);

CREATE INDEX IF NOT EXISTS idx_asset_repurchase_orders_product
    ON asset_repurchase_orders (trust_product_id, repurchase_business_date DESC);

-- 回购资产明细（合并冻结监控快照）：
-- 一行 = 一张回购单里的一个资产主编号；快照字段按主编号聚合，确认时一次性写入
-- historical_property_codes = 该资产涉及的全部 distinct custody/source 编号（逗号分隔）
CREATE TABLE IF NOT EXISTS asset_repurchase_assets (
    repurchase_order_id         BIGINT NOT NULL
        REFERENCES asset_repurchase_orders (id) ON DELETE CASCADE,
    asset_code                  VARCHAR(64) NOT NULL,
    trust_product_id            BIGINT NOT NULL,
    trust_product_name          VARCHAR(200) NULL,
    historical_property_codes   TEXT NULL,
    monitor_data_date           DATE NULL,
    initial_transfer_amount     NUMERIC(18, 2) NULL,
    repaid_amount               NUMERIC(18, 2) NULL,
    remaining_amount            NUMERIC(18, 2) NULL,
    repurchase_amount           NUMERIC(18, 2) NULL,
    overdue_days                INT NULL,
    delinquency_bucket          VARCHAR(16) NULL,
    asset_status                VARCHAR(100) NULL,
    split_count                 INT NOT NULL DEFAULT 0,
    city                        VARCHAR(64) NULL,
    community_name              VARCHAR(200) NULL,
    source_monitor_record_ids   TEXT NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (repurchase_order_id, asset_code)
);

CREATE INDEX IF NOT EXISTS idx_asset_repurchase_assets_code
    ON asset_repurchase_assets (trust_product_id, asset_code);
