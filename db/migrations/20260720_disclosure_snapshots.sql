-- 披露快照：还款明细披露 / 资产监控披露
-- 执行：按 db/manifest.txt

CREATE TABLE IF NOT EXISTS disclosure_snapshots (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_type       VARCHAR(32) NOT NULL,
    as_of_date          DATE NOT NULL,
    frozen_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by          VARCHAR(100) NULL,
    note                TEXT NULL,
    product_ids         BIGINT[] NOT NULL,
    product_names       TEXT NULL,
    detail_row_count    INT NOT NULL DEFAULT 0,
    plan_row_count      INT NOT NULL DEFAULT 0,
    monitor_row_count   INT NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_disclosure_snapshot_type
        CHECK (snapshot_type IN ('repayment', 'monitor'))
);

CREATE INDEX IF NOT EXISTS idx_disclosure_snapshots_type_frozen
    ON disclosure_snapshots (snapshot_type, frozen_at DESC);

CREATE INDEX IF NOT EXISTS idx_disclosure_snapshots_as_of
    ON disclosure_snapshots (snapshot_type, as_of_date DESC);

CREATE TABLE IF NOT EXISTS disclosure_repayment_rows (
    id                          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id                 BIGINT NOT NULL
        REFERENCES disclosure_snapshots (id) ON DELETE CASCADE,
    trust_product_id            BIGINT NOT NULL,
    trust_product_name          VARCHAR(200) NULL,
    asset_pool_code             VARCHAR(64) NULL,
    current_payer               VARCHAR(100) NULL,
    custody_asset_code          VARCHAR(64) NULL,
    planned_repayment_amount    NUMERIC(18, 2) NULL,
    initial_renovation_amount   NUMERIC(18, 2) NULL,
    cumulative_repaid_amount    NUMERIC(18, 2) NULL,
    remaining_balance           NUMERIC(18, 2) NULL,
    actual_repayment_amount     NUMERIC(18, 2) NULL,
    overdue_days                INT NULL,
    source_record_id            BIGINT NULL
);

CREATE INDEX IF NOT EXISTS idx_disclosure_repay_snap
    ON disclosure_repayment_rows (snapshot_id);

CREATE TABLE IF NOT EXISTS disclosure_repayment_plan_rows (
    id                              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id                     BIGINT NOT NULL
        REFERENCES disclosure_snapshots (id) ON DELETE CASCADE,
    trust_product_id                BIGINT NOT NULL,
    trust_product_name              VARCHAR(200) NULL,
    asset_pool_code                 VARCHAR(64) NULL,
    source_asset_code               VARCHAR(64) NULL,
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
    source_record_id                BIGINT NULL
);

CREATE INDEX IF NOT EXISTS idx_disclosure_plan_snap
    ON disclosure_repayment_plan_rows (snapshot_id);

CREATE TABLE IF NOT EXISTS disclosure_monitor_rows (
    id                              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id                     BIGINT NOT NULL
        REFERENCES disclosure_snapshots (id) ON DELETE CASCADE,
    trust_product_id                BIGINT NOT NULL,
    trust_product_name              VARCHAR(200) NULL,
    asset_pool_code                 VARCHAR(64) NULL,
    source_asset_code               VARCHAR(64) NULL,
    renovation_vendor               VARCHAR(200) NULL,
    data_date                       DATE NULL,
    initial_transfer_amount         NUMERIC(18, 2) NULL,
    repaid_amount                   NUMERIC(18, 2) NULL,
    remaining_amount                NUMERIC(18, 2) NULL,
    asset_status                    VARCHAR(100) NULL,
    last_renovation_payment_date    DATE NULL,
    community_name                  VARCHAR(200) NULL,
    city                            VARCHAR(64) NULL,
    collection_contract_code        VARCHAR(100) NULL,
    custody_agreement_sign_date     DATE NULL,
    collection_contract_years       NUMERIC(10, 2) NULL,
    owner_code                      VARCHAR(200) NULL,
    withholding_ratio               NUMERIC(10, 6) NULL,
    actual_monthly_rent             NUMERIC(18, 2) NULL,
    source_record_id                BIGINT NULL
);

CREATE INDEX IF NOT EXISTS idx_disclosure_mon_snap
    ON disclosure_monitor_rows (snapshot_id);
