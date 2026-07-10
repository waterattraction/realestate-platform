-- Spatial P0: asset_locations + geocode run log (no changes to existing tables)

CREATE TABLE IF NOT EXISTS asset_locations (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trust_product_id    BIGINT NOT NULL REFERENCES trust_products (id),
    asset_code          VARCHAR(64) NOT NULL,
    property_id         BIGINT NULL,
    raw_address         TEXT NULL,
    city                VARCHAR(64) NULL,
    province            VARCHAR(64) NULL,
    district            VARCHAR(64) NULL,
    formatted_address   TEXT NULL,
    latitude            DOUBLE PRECISION NULL,
    longitude           DOUBLE PRECISION NULL,
    geocode_status      VARCHAR(16) NOT NULL DEFAULT 'pending',
    geocode_provider    VARCHAR(32) NULL,
    geocode_level       VARCHAR(32) NULL,
    geocode_error       TEXT NULL,
    geocoded_at         TIMESTAMPTZ NULL,
    location_source     VARCHAR(32) NOT NULL DEFAULT 'ISSUANCE',
    source_issuance_id  BIGINT NULL,
    address_hash        VARCHAR(64) NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_asset_locations_product_asset UNIQUE (trust_product_id, asset_code),
    CONSTRAINT chk_asset_locations_geocode_status CHECK (
        geocode_status IN ('pending', 'success', 'failed', 'skipped')
    )
);

CREATE INDEX IF NOT EXISTS idx_asset_locations_geocode_status
    ON asset_locations (geocode_status);

CREATE INDEX IF NOT EXISTS idx_asset_locations_city
    ON asset_locations (city);

CREATE INDEX IF NOT EXISTS idx_asset_locations_lat_lng
    ON asset_locations (latitude, longitude)
    WHERE geocode_status = 'success';

CREATE TABLE IF NOT EXISTS spatial_geocode_runs (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status          VARCHAR(16) NOT NULL DEFAULT 'running',
    triggered_by    VARCHAR(64) NOT NULL DEFAULT 'manual',
    pending_count   INT NOT NULL DEFAULT 0,
    success_count   INT NOT NULL DEFAULT 0,
    failed_count    INT NOT NULL DEFAULT 0,
    error_message   TEXT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ NULL,
    CONSTRAINT chk_spatial_geocode_runs_status CHECK (
        status IN ('running', 'completed', 'failed')
    )
);

CREATE INDEX IF NOT EXISTS idx_spatial_geocode_runs_started
    ON spatial_geocode_runs (started_at DESC);
