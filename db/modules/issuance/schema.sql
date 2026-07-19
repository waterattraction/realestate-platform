-- ============================================================
-- 信托产品发行资产明细 — Issuance Asset Schema
-- 执行顺序：… → asset_code_semantics_v2_schema.sql → 本文件
-- 注意：本模块无 data_date 字段，业务时间维度仅为 issue_date
-- ============================================================

CREATE TABLE IF NOT EXISTS trust_product_issuance_asset_records (
    id                                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trust_product_id                        BIGINT NOT NULL REFERENCES trust_products (id),
    trust_product_name                      VARCHAR(200) NOT NULL,
    from_trust_product_id                   BIGINT NULL REFERENCES trust_products (id),
    from_trust_product_name                 VARCHAR(200) NULL,
    planned_trust_product_id                BIGINT NULL REFERENCES trust_products (id),
    planned_trust_product_name              VARCHAR(200) NULL,
    migration_type                          VARCHAR(32) NULL,
    trust_asset_id                          BIGINT NULL REFERENCES trust_assets (id),
    issue_date                              DATE NOT NULL,
    business_asset_key                      VARCHAR(128) NOT NULL,
    custody_asset_code                      VARCHAR(64) NOT NULL,
    issuance_weight                         NUMERIC(10, 6) NULL,
    migration_reason                        VARCHAR(500) NULL,
    contract_name                           VARCHAR(200) NULL,
    debtor_name                             VARCHAR(100) NULL,
    property_address                        TEXT NULL,
    city                                    VARCHAR(64) NULL,
    contractor_name                         VARCHAR(200) NULL,
    brand                                   VARCHAR(100) NULL,
    product_style                           VARCHAR(100) NULL,
    property_status                         VARCHAR(100) NULL,
    original_creditor                       VARCHAR(200) NULL,
    receivable_contract_amount              NUMERIC(18, 2) NOT NULL,
    asset_transfer_discount_rate            NUMERIC(10, 6) NULL,
    receivable_transfer_amount              NUMERIC(18, 2) NOT NULL,
    min_institution_transferable_amount     NUMERIC(18, 2) NULL,
    remaining_unpaid_amount_beike_not_withheld NUMERIC(18, 2) NULL,
    rental_price                            NUMERIC(18, 2) NULL,
    total_rent_withholding_amount           NUMERIC(18, 2) NULL,
    rent_withheld_amount_before_pooling     NUMERIC(18, 2) NULL,
    withholding_periods_at_pooling          INT NULL,
    initial_expected_withholding_cycle      VARCHAR(64) NULL,
    renovation_payment_method               VARCHAR(100) NULL,
    rent_withholding_ratio                  NUMERIC(10, 6) NULL,
    calculated_rent_withholding_per_period  NUMERIC(18, 2) NULL,
    agreed_repayment_periods                INT NULL,
    installment_payable_amount              NUMERIC(18, 2) NULL,
    withheld_unpaid_amount                  NUMERIC(18, 2) NULL,
    withheld_repaid_amount                  NUMERIC(18, 2) NULL,
    transferred_receipt_total               NUMERIC(18, 2) NULL,
    rent_withholding_received_total         NUMERIC(18, 2) NULL,
    first_rent_withholding_date             DATE NULL,
    signing_date                            DATE NULL,
    rental_contract_end_date                DATE NULL,
    expected_last_rent_payment_date_initial DATE NULL,
    expected_receivable_due_date            DATE NULL,
    source_file_name                        VARCHAR(500) NOT NULL,
    source_sheet_name                       VARCHAR(200) NOT NULL,
    source_row_number                       INT NULL,
    created_at                              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_issuance_receivable_contract_nonneg
        CHECK (receivable_contract_amount >= 0),
    CONSTRAINT chk_issuance_receivable_transfer_nonneg
        CHECK (receivable_transfer_amount >= 0)
);

CREATE INDEX IF NOT EXISTS idx_issuance_product
    ON trust_product_issuance_asset_records (trust_product_id);

CREATE INDEX IF NOT EXISTS idx_issuance_product_issue
    ON trust_product_issuance_asset_records (trust_product_id, issue_date);

CREATE INDEX IF NOT EXISTS idx_issuance_source_scope
    ON trust_product_issuance_asset_records (
        trust_product_id, issue_date, source_file_name, source_sheet_name
    );

CREATE INDEX IF NOT EXISTS idx_issuance_business_key
    ON trust_product_issuance_asset_records (business_asset_key);

CREATE INDEX IF NOT EXISTS idx_issuance_cross_file_check
    ON trust_product_issuance_asset_records (
        trust_product_id, issue_date, custody_asset_code
    );

CREATE INDEX IF NOT EXISTS idx_issuance_from_product
    ON trust_product_issuance_asset_records (from_trust_product_id);

CREATE INDEX IF NOT EXISTS idx_issuance_planned_product
    ON trust_product_issuance_asset_records (planned_trust_product_id);

CREATE INDEX IF NOT EXISTS idx_issuance_migration_type
    ON trust_product_issuance_asset_records (migration_type);

CREATE INDEX IF NOT EXISTS idx_issuance_custody
    ON trust_product_issuance_asset_records (trust_product_id, custody_asset_code);

CREATE TABLE IF NOT EXISTS issuance_import_runs (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trust_product_id    BIGINT NOT NULL REFERENCES trust_products (id),
    trust_product_name  VARCHAR(200) NOT NULL,
    issue_date          DATE NOT NULL,
    source_file         VARCHAR(500) NOT NULL,
    created_by          BIGINT NOT NULL REFERENCES users (id),
    inserted_row_count  INT NOT NULL DEFAULT 0,
    deleted_row_count   INT NOT NULL DEFAULT 0,
    skipped_sheet_count INT NOT NULL DEFAULT 0,
    failed_sheet_count  INT NOT NULL DEFAULT 0,
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_issuance_import_runs_product_issue
    ON issuance_import_runs (trust_product_id, issue_date DESC);

CREATE TABLE IF NOT EXISTS issuance_import_sheet_runs (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    import_run_id       BIGINT NOT NULL REFERENCES issuance_import_runs (id),
    trust_product_id    BIGINT NOT NULL REFERENCES trust_products (id),
    trust_product_name  VARCHAR(200) NOT NULL,
    issue_date          DATE NOT NULL,
    source_file_name    VARCHAR(500) NOT NULL,
    source_sheet_name   VARCHAR(200) NOT NULL,
    sheet_type          VARCHAR(32) NOT NULL DEFAULT 'issuance_asset',
    row_count           INT NOT NULL DEFAULT 0,
    amount_sum          NUMERIC(18, 2),
    action              VARCHAR(32) NOT NULL,
    message             TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_issuance_import_sheet_runs_scope
    ON issuance_import_sheet_runs (
        trust_product_id, issue_date, source_file_name, source_sheet_name
    );

CREATE TRIGGER trg_issuance_assets_updated_at
    BEFORE UPDATE ON trust_product_issuance_asset_records
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
