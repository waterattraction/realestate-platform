-- 资产主编号信托标记 / 内部状态（独立于监控快照）
CREATE TABLE IF NOT EXISTS trust_asset_trust_marks (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trust_product_id    BIGINT NOT NULL REFERENCES trust_products (id),
    asset_code          VARCHAR(128) NOT NULL,
    custody_asset_code  VARCHAR(128),
    data_date           DATE NOT NULL,
    trust_marker        VARCHAR(64) NOT NULL DEFAULT '未标记',
    internal_status     VARCHAR(32) NOT NULL DEFAULT '待跟进',
    marker_note         TEXT,
    created_by          VARCHAR(64),
    updated_by          VARCHAR(64),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_trust_asset_trust_marks UNIQUE (trust_product_id, asset_code, data_date)
);

CREATE INDEX IF NOT EXISTS idx_trust_asset_trust_marks_lookup
    ON trust_asset_trust_marks (trust_product_id, asset_code, data_date DESC);

CREATE TRIGGER trg_trust_asset_trust_marks_updated_at
    BEFORE UPDATE ON trust_asset_trust_marks
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
