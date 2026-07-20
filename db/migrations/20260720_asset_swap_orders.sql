-- 资产置换域：仅新表落库，不改监控/发行事实表
-- 执行：按 db/manifest.txt

CREATE TABLE IF NOT EXISTS asset_swap_orders (
    id                              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_trust_product_id         BIGINT NOT NULL REFERENCES trust_products (id),
    source_trust_product_name       VARCHAR(200) NOT NULL,
    counterparty_trust_product_id   BIGINT NOT NULL REFERENCES trust_products (id),
    counterparty_trust_product_name VARCHAR(200) NOT NULL,
    scheme_id                       VARCHAR(32) NOT NULL,
    swap_business_date              DATE NOT NULL,
    status                          VARCHAR(32) NOT NULL DEFAULT 'completed',
    executed_at                     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    executed_by                     VARCHAR(100) NULL,
    voided_at                       TIMESTAMPTZ NULL,
    voided_by                       VARCHAR(100) NULL,
    void_blocked_reason             TEXT NULL,
    note                            TEXT NULL,
    source_total_remaining          NUMERIC(18, 2) NULL,
    candidate_total_remaining       NUMERIC(18, 2) NULL,
    source_asset_count              INT NOT NULL DEFAULT 0,
    candidate_asset_count           INT NOT NULL DEFAULT 0,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_asset_swap_order_status
        CHECK (status IN ('completed', 'voided')),
    CONSTRAINT chk_asset_swap_scheme
        CHECK (scheme_id IN ('a', 'b', 'c', 'manual'))
);

CREATE INDEX IF NOT EXISTS idx_asset_swap_orders_executed
    ON asset_swap_orders (executed_at DESC);

CREATE INDEX IF NOT EXISTS idx_asset_swap_orders_source
    ON asset_swap_orders (source_trust_product_id, swap_business_date DESC);

CREATE TABLE IF NOT EXISTS asset_swap_assets (
    id                          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    swap_order_id               BIGINT NOT NULL
        REFERENCES asset_swap_orders (id) ON DELETE CASCADE,
    direction                   VARCHAR(8) NOT NULL,
    asset_code                  VARCHAR(64) NOT NULL,
    custody_asset_code          VARCHAR(64) NULL,
    source_asset_code           VARCHAR(64) NULL,
    from_trust_product_id       BIGINT NOT NULL,
    from_trust_product_name     VARCHAR(200) NULL,
    to_trust_product_id         BIGINT NOT NULL,
    to_trust_product_name       VARCHAR(200) NULL,
    monitor_data_date           DATE NULL,
    source_monitor_record_id    BIGINT NULL,
    remaining_amount            NUMERIC(18, 2) NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_asset_swap_direction
        CHECK (direction IN ('out', 'in'))
);

CREATE INDEX IF NOT EXISTS idx_asset_swap_assets_order
    ON asset_swap_assets (swap_order_id, direction);

CREATE TABLE IF NOT EXISTS asset_swap_monitor_snapshots (
    id                              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    swap_asset_id                   BIGINT NOT NULL
        REFERENCES asset_swap_assets (id) ON DELETE CASCADE,
    swap_order_id                   BIGINT NOT NULL
        REFERENCES asset_swap_orders (id) ON DELETE CASCADE,
    snapshot_role                   VARCHAR(8) NOT NULL,
    trust_product_id                BIGINT NOT NULL,
    trust_product_name              VARCHAR(200) NULL,
    source_monitor_record_id        BIGINT NULL,
    asset_code                      VARCHAR(64) NULL,
    custody_asset_code              VARCHAR(64) NULL,
    source_asset_code               VARCHAR(64) NULL,
    data_date                       DATE NULL,
    asset_pool_code                 VARCHAR(64) NULL,
    renovation_vendor               VARCHAR(200) NULL,
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
    overdue_days                    INT NULL,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_asset_swap_snapshot_role
        CHECK (snapshot_role IN ('exit', 'entry'))
);

CREATE INDEX IF NOT EXISTS idx_asset_swap_mon_snap_asset
    ON asset_swap_monitor_snapshots (swap_asset_id, snapshot_role);

CREATE INDEX IF NOT EXISTS idx_asset_swap_mon_snap_order
    ON asset_swap_monitor_snapshots (swap_order_id);
