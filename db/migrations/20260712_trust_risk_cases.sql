-- Risk cases domain: trust_risk_cases (split-level), migrated from trust_overdue_followups.

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

-- Preserve legacy ids when migrating from trust_overdue_followups.
DO $$
BEGIN
    IF to_regclass('public.trust_overdue_followups') IS NOT NULL THEN
        INSERT INTO trust_risk_cases (
            id,
            trust_product_id,
            trust_asset_id,
            data_date,
            trigger_source,
            alert_source,
            status,
            owner_name,
            overdue_reason,
            follow_up_plan,
            trust_feedback,
            last_follow_up_at,
            risk_score,
            risk_level,
            sla_due_date,
            sla_status,
            case_priority,
            next_action_date,
            created_at,
            updated_at
        )
        OVERRIDING SYSTEM VALUE
        SELECT
            f.id,
            f.trust_product_id,
            f.trust_asset_id,
            f.data_date,
            f.trigger_source,
            f.alert_source,
            f.status,
            f.owner_name,
            f.overdue_reason,
            f.follow_up_plan,
            f.trust_feedback,
            f.last_follow_up_at,
            f.risk_score,
            f.risk_level,
            f.sla_due_date,
            f.sla_status,
            f.case_priority,
            f.next_action_date,
            f.created_at,
            f.updated_at
        FROM trust_overdue_followups f
        WHERE NOT EXISTS (SELECT 1 FROM trust_risk_cases rc WHERE rc.id = f.id);

        PERFORM setval(
            pg_get_serial_sequence('trust_risk_cases', 'id'),
            COALESCE((SELECT MAX(id) FROM trust_risk_cases), 1)
        );
    END IF;
END $$;
