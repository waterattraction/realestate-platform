-- 资产监控快照：Excel「最后一期装修款付款时间」

ALTER TABLE trust_asset_monitor_records
    ADD COLUMN IF NOT EXISTS last_renovation_payment_date DATE NULL;

COMMENT ON COLUMN trust_asset_monitor_records.last_renovation_payment_date IS
    'Excel：最后一期装修款付款时间（监控快照事实，非计算字段）';
