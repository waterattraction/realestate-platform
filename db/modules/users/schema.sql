-- ============================================================
-- 用户与导入审计 — Auth Schema
-- 执行顺序：… → assetinfo_schema.sql → 本文件
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username        VARCHAR(64)  NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(32)  NOT NULL DEFAULT 'operator',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_users_role CHECK (role IN ('admin', 'operator'))
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);

-- 每次资产数据导入管道执行记录（created_by 关联操作人）
CREATE TABLE IF NOT EXISTS assetinfo_pipeline_runs (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trust_product_id    BIGINT NOT NULL REFERENCES trust_products (id),
    data_date           DATE,
    trust_plan_alias    VARCHAR(200),
    source_file         VARCHAR(500),
    created_by          BIGINT NOT NULL REFERENCES users (id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    inserted_monitor_count INT NOT NULL DEFAULT 0,
    inserted_repayment_count INT NOT NULL DEFAULT 0,
    upsert_asset_count  INT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_assetinfo_pipeline_runs_created_by
    ON assetinfo_pipeline_runs (created_by, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_assetinfo_pipeline_runs_product_date
    ON assetinfo_pipeline_runs (trust_product_id, data_date DESC);
