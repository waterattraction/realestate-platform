-- Overdue followup cases + entries (V2.2 Phase 2)
-- trust_product_id + custody_asset_code case subject; entries append-only.

CREATE TABLE IF NOT EXISTS trust_overdue_followup_cases (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trust_product_id    BIGINT NOT NULL REFERENCES trust_products (id),
    custody_asset_code  VARCHAR(128) NOT NULL,
    data_date           DATE NOT NULL,
    status              VARCHAR(32) NOT NULL DEFAULT 'open',
    owner_name          VARCHAR(100),
    opened_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at           TIMESTAMPTZ,
    last_follow_up_at   TIMESTAMPTZ,
    created_by          VARCHAR(64),
    updated_by          VARCHAR(64),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_followup_cases_status
        CHECK (status IN ('open', 'in_progress', 'resolved', 'closed'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_followup_cases_active_custody
    ON trust_overdue_followup_cases (trust_product_id, custody_asset_code)
    WHERE status IN ('open', 'in_progress');

CREATE INDEX IF NOT EXISTS idx_followup_cases_product_custody
    ON trust_overdue_followup_cases (trust_product_id, custody_asset_code);

CREATE TABLE IF NOT EXISTS trust_overdue_followup_entries (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    case_id             BIGINT NOT NULL REFERENCES trust_overdue_followup_cases (id),
    entry_type          VARCHAR(32) NOT NULL DEFAULT 'manual',
    status_snapshot     VARCHAR(32),
    overdue_reason      TEXT,
    follow_up_plan      TEXT,
    trust_feedback      TEXT,
    note                TEXT,
    owner_name          VARCHAR(100),
    created_by          VARCHAR(64),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_followup_entries_type
        CHECK (entry_type IN ('manual', 'system', 'trust_request'))
);

CREATE INDEX IF NOT EXISTS idx_followup_entries_case_created
    ON trust_overdue_followup_entries (case_id, created_at DESC);

CREATE TRIGGER trg_trust_overdue_followup_cases_updated_at
    BEFORE UPDATE ON trust_overdue_followup_cases
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
