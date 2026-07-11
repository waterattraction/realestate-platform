-- ============================================================
-- 信托资产风险中台 V2 — Risk Control Hub Schema
-- 执行顺序：schema.sql → seed.sql → overdue_schema.sql → overdue_seed.sql → 本文件
-- ============================================================

-- ------------------------------------------------------------
-- 1. 扩展资产监控记录：风险评分
-- ------------------------------------------------------------
ALTER TABLE trust_asset_monitor_records
    ADD COLUMN IF NOT EXISTS risk_score INT,
    ADD COLUMN IF NOT EXISTS risk_level VARCHAR(2);

CREATE INDEX IF NOT EXISTS idx_trust_asset_monitor_risk_level
    ON trust_asset_monitor_records (risk_level);

-- ------------------------------------------------------------
-- 2. 风险案件（分笔维度）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trust_risk_cases (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trust_product_id    BIGINT NOT NULL REFERENCES trust_products (id),
    trust_asset_id      BIGINT NOT NULL REFERENCES trust_assets (id),
    data_date           DATE NOT NULL,
    trigger_source      VARCHAR(32) NOT NULL DEFAULT 'system',
    alert_source        VARCHAR(32) DEFAULT 'system',
    status              VARCHAR(32) NOT NULL DEFAULT 'open',
    owner_name          VARCHAR(100),
    overdue_reason      TEXT,
    follow_up_plan      TEXT,
    trust_feedback      TEXT,
    last_follow_up_at   TIMESTAMPTZ,
    risk_score          INT,
    risk_level          VARCHAR(2),
    sla_due_date        TIMESTAMPTZ,
    sla_status          VARCHAR(32),
    case_priority       VARCHAR(8),
    next_action_date    DATE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_trust_risk_cases_status
        CHECK (status IN ('open', 'in_progress', 'resolved', 'closed'))
);

CREATE INDEX IF NOT EXISTS idx_trust_risk_cases_product_status
    ON trust_risk_cases (trust_product_id, status);

CREATE INDEX IF NOT EXISTS idx_trust_risk_cases_asset_status
    ON trust_risk_cases (trust_asset_id, status);

CREATE INDEX IF NOT EXISTS idx_trust_risk_cases_sla
    ON trust_risk_cases (sla_status)
    WHERE status IN ('open', 'in_progress');

CREATE INDEX IF NOT EXISTS idx_trust_risk_cases_asset_date
    ON trust_risk_cases (trust_asset_id, data_date DESC);

CREATE TRIGGER trg_trust_risk_cases_updated_at
    BEFORE UPDATE ON trust_risk_cases
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ------------------------------------------------------------
-- 3. 风险预警
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS risk_alerts (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trust_product_id    BIGINT NOT NULL REFERENCES trust_products (id),
    trust_asset_id      BIGINT NOT NULL REFERENCES trust_assets (id),
    data_date           DATE NOT NULL,
    risk_type           VARCHAR(64) NOT NULL,
    risk_level          VARCHAR(2) NOT NULL,
    trigger_rule        VARCHAR(200) NOT NULL,
    status              VARCHAR(32) NOT NULL DEFAULT 'open',
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_alerts_status ON risk_alerts (status);
CREATE INDEX IF NOT EXISTS idx_risk_alerts_asset ON risk_alerts (trust_asset_id, data_date);
CREATE UNIQUE INDEX IF NOT EXISTS uq_risk_alerts_open_rule
    ON risk_alerts (trust_asset_id, data_date, risk_type)
    WHERE status IN ('open', 'acknowledged');

CREATE TRIGGER trg_risk_alerts_updated_at
    BEFORE UPDATE ON risk_alerts FOR EACH ROW EXECUTE FUNCTION set_updated_at();
