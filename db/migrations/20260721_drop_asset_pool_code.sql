-- type: migration
-- purpose: DROP asset_pool_code（监控/还款/回款计划/披露/置换快照）；停用该字段导入
-- note: source_asset_code 列保留（死列），仅停导入与展示；不回填/不改写已有 asset_code
-- dependencies: 20260720_monitor_repayment_template_columns.sql,
--               20260720_disclosure_snapshots.sql,
--               20260720_asset_swap_orders.sql
-- idempotent: 是（ADD 无；DROP IF EXISTS）
-- 执行：按 db/manifest.txt

ALTER TABLE trust_asset_monitor_records
    DROP COLUMN IF EXISTS asset_pool_code;

ALTER TABLE trust_repayment_detail_records
    DROP COLUMN IF EXISTS asset_pool_code;

ALTER TABLE trust_repayment_plan_records
    DROP COLUMN IF EXISTS asset_pool_code;

ALTER TABLE disclosure_monitor_rows
    DROP COLUMN IF EXISTS asset_pool_code;

ALTER TABLE disclosure_repayment_rows
    DROP COLUMN IF EXISTS asset_pool_code;

ALTER TABLE disclosure_repayment_plan_rows
    DROP COLUMN IF EXISTS asset_pool_code;

ALTER TABLE asset_swap_monitor_snapshots
    DROP COLUMN IF EXISTS asset_pool_code;
