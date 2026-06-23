-- 监控记录增加 updated_at / overdue_days_as_of，供逾期天数重算与页面展示
ALTER TABLE trust_asset_monitor_records
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

ALTER TABLE trust_asset_monitor_records
    ADD COLUMN IF NOT EXISTS overdue_days_as_of DATE;
