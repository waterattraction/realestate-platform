-- 数据准入管道 V1 — 字段映射配置
-- 执行：ingestion_schema.sql → 本文件

BEGIN;

INSERT INTO data_mapping_config (
    config_version, sheet_name, sheet_type, excel_column,
    target_table, target_column, field_semantic, transform_rule,
    is_required, is_business_key, priority
)
VALUES
    ('v1.0', '2更新的资产数据表', 'asset_monitor', '托管房源编码',
     'trust_asset_monitor_records', 'custody_asset_code', 'asset', 'to_custody_code', TRUE, TRUE, 10),
    ('v1.0', '2更新的资产数据表', 'asset_monitor', '统计日期',
     'trust_asset_monitor_records', 'data_date', 'asset', 'to_date', TRUE, FALSE, 20),
    ('v1.0', '2更新的资产数据表', 'asset_monitor', '初始受让金额',
     'trust_asset_monitor_records', 'initial_transfer_amount', 'asset', 'to_numeric', TRUE, FALSE, 30),
    ('v1.0', '2更新的资产数据表', 'asset_monitor', '已还款金额',
     'trust_asset_monitor_records', 'repaid_amount', 'repayment', 'to_numeric', TRUE, FALSE, 40),
    ('v1.0', '2更新的资产数据表', 'asset_monitor', '剩余还款金额',
     'trust_asset_monitor_records', 'remaining_amount', 'asset', 'to_numeric', TRUE, FALSE, 50),
    ('v1.0', '2更新的资产数据表', 'asset_monitor', '文件名',
     'trust_asset_monitor_records', 'source_file_name', 'asset', NULL, FALSE, FALSE, 60),
    ('v1.0', '2更新的资产数据表', 'asset_monitor', '当前信托计划（已发行）',
     'trust_asset_monitor_records', 'trust_plan_alias', 'asset', 'filter_alias', FALSE, FALSE, 5),

    ('v1.0', '1全量还款明细汇总', 'repayment_detail', '托管房源编号',
     'trust_repayment_detail_records', 'custody_asset_code', 'asset', 'to_custody_code', TRUE, TRUE, 10),
    ('v1.0', '1全量还款明细汇总', 'repayment_detail', '当期实际还款金额',
     'trust_repayment_detail_records', 'actual_repayment_amount', 'repayment', 'to_numeric', TRUE, FALSE, 20),
    ('v1.0', '1全量还款明细汇总', 'repayment_detail', '还款日期',
     'trust_repayment_detail_records', 'repayment_date', 'repayment', 'to_date', TRUE, FALSE, 30),
    ('v1.0', '1全量还款明细汇总', 'repayment_detail', '所属文件名称',
     'trust_repayment_detail_records', 'source_file_name', 'asset', NULL, FALSE, FALSE, 40),
    ('v1.0', '1全量还款明细汇总', 'repayment_detail', '所属Sheet名称',
     'trust_repayment_detail_records', 'source_sheet_name', 'asset', NULL, FALSE, FALSE, 50),
    ('v1.0', '1全量还款明细汇总', 'repayment_detail', '当前信托计划（已发行）',
     'trust_repayment_detail_records', 'trust_plan_alias', 'asset', 'filter_alias', FALSE, FALSE, 5)
ON CONFLICT (sheet_name, excel_column, target_table, target_column) DO NOTHING;

COMMIT;
