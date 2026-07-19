-- 发行资产明细 — 全列导入：拟转入计划独立字段 + 结算/首期转让业务列
-- 执行：按 db/manifest.txt 顺序 apply

ALTER TABLE trust_product_issuance_asset_records
    ADD COLUMN IF NOT EXISTS planned_trust_product_id BIGINT NULL
        REFERENCES trust_products (id),
    ADD COLUMN IF NOT EXISTS planned_trust_product_name VARCHAR(200) NULL,
    ADD COLUMN IF NOT EXISTS brand VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS product_style VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS property_status VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS original_creditor VARCHAR(200) NULL,
    ADD COLUMN IF NOT EXISTS agreed_repayment_periods INT NULL,
    ADD COLUMN IF NOT EXISTS installment_payable_amount NUMERIC(18, 2) NULL,
    ADD COLUMN IF NOT EXISTS withheld_unpaid_amount NUMERIC(18, 2) NULL,
    ADD COLUMN IF NOT EXISTS withheld_repaid_amount NUMERIC(18, 2) NULL,
    ADD COLUMN IF NOT EXISTS transferred_receipt_total NUMERIC(18, 2) NULL,
    ADD COLUMN IF NOT EXISTS rent_withholding_received_total NUMERIC(18, 2) NULL,
    ADD COLUMN IF NOT EXISTS expected_last_rent_payment_date_initial DATE NULL,
    ADD COLUMN IF NOT EXISTS expected_receivable_due_date DATE NULL;

CREATE INDEX IF NOT EXISTS idx_issuance_planned_product
    ON trust_product_issuance_asset_records (planned_trust_product_id);
