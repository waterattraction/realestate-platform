-- 监控/还款按披露模版补全列 + 回款计划事实表
-- 执行：按 db/manifest.txt 顺序 apply

ALTER TABLE trust_repayment_detail_records
    ADD COLUMN IF NOT EXISTS asset_pool_code VARCHAR(64) NULL,
    ADD COLUMN IF NOT EXISTS current_payer VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS planned_repayment_amount NUMERIC(18, 2) NULL,
    ADD COLUMN IF NOT EXISTS initial_renovation_amount NUMERIC(18, 2) NULL,
    ADD COLUMN IF NOT EXISTS cumulative_repaid_amount NUMERIC(18, 2) NULL,
    ADD COLUMN IF NOT EXISTS remaining_balance NUMERIC(18, 2) NULL;

ALTER TABLE trust_asset_monitor_records
    ADD COLUMN IF NOT EXISTS asset_pool_code VARCHAR(64) NULL,
    ADD COLUMN IF NOT EXISTS renovation_vendor VARCHAR(200) NULL,
    ADD COLUMN IF NOT EXISTS asset_status VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS community_name VARCHAR(200) NULL,
    ADD COLUMN IF NOT EXISTS city VARCHAR(64) NULL,
    ADD COLUMN IF NOT EXISTS collection_contract_code VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS custody_agreement_sign_date DATE NULL,
    ADD COLUMN IF NOT EXISTS collection_contract_years NUMERIC(10, 2) NULL,
    ADD COLUMN IF NOT EXISTS owner_code VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS withholding_ratio NUMERIC(10, 6) NULL,
    ADD COLUMN IF NOT EXISTS actual_monthly_rent NUMERIC(18, 2) NULL;

CREATE TABLE IF NOT EXISTS trust_repayment_plan_records (
    id                              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trust_product_id                BIGINT NOT NULL REFERENCES trust_products (id),
    trust_asset_id                  BIGINT NULL REFERENCES trust_assets (id),
    asset_code                      VARCHAR(64) NOT NULL,
    custody_asset_code              VARCHAR(64) NULL,
    source_asset_code               VARCHAR(64) NULL,
    asset_pool_code                 VARCHAR(64) NULL,
    renovation_vendor               VARCHAR(200) NULL,
    data_date                       DATE NULL,
    initial_transfer_amount         NUMERIC(18, 2) NULL,
    repaid_amount                   NUMERIC(18, 2) NULL,
    remaining_amount                NUMERIC(18, 2) NULL,
    community_name                  VARCHAR(200) NULL,
    city                            VARCHAR(64) NULL,
    current_bill_date               DATE NULL,
    repayment_amount_detail         TEXT NULL,
    planned_monthly_repayment_amount NUMERIC(18, 2) NULL,
    final_planned_repayment_amount  NUMERIC(18, 2) NULL,
    source_file_name                VARCHAR(500) NOT NULL,
    source_sheet_name               VARCHAR(200) NOT NULL,
    source_row_number               INT NULL,
    synced_at                       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_repayment_plan_product
    ON trust_repayment_plan_records (trust_product_id);

CREATE INDEX IF NOT EXISTS idx_repayment_plan_scope
    ON trust_repayment_plan_records (
        trust_product_id, source_file_name, source_sheet_name
    );

CREATE INDEX IF NOT EXISTS idx_repayment_plan_custody
    ON trust_repayment_plan_records (
        trust_product_id, custody_asset_code, source_asset_code
    );
