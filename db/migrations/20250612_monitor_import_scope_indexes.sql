-- ============================================================
-- 资产监控快照导入范围索引（普通索引，非 UNIQUE）
-- 执行：cat monitor_import_scope_indexes.sql | docker compose exec -T postgres psql -U admin -d realestate
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_monitor_import_scope
ON trust_asset_monitor_records (
    trust_product_id,
    data_date,
    source_sheet_name
);

CREATE INDEX IF NOT EXISTS idx_monitor_asset_check
ON trust_asset_monitor_records (
    trust_product_id,
    data_date,
    trust_asset_id,
    source_sheet_name
);
