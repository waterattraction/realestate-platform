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
-- 2. 扩展跟进台账 → 风险案件（Case）
-- ------------------------------------------------------------
ALTER TABLE trust_overdue_followups
    ADD COLUMN IF NOT EXISTS risk_score INT,
    ADD COLUMN IF NOT EXISTS risk_level VARCHAR(2),
    ADD COLUMN IF NOT EXISTS sla_due_date TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS sla_status VARCHAR(32),
    ADD COLUMN IF NOT EXISTS alert_source VARCHAR(32) DEFAULT 'system',
    ADD COLUMN IF NOT EXISTS case_priority VARCHAR(8),
    ADD COLUMN IF NOT EXISTS next_action_date DATE;

CREATE INDEX IF NOT EXISTS idx_trust_overdue_followups_sla_status
    ON trust_overdue_followups (sla_status);

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
