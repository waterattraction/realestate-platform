-- ============================================================
-- 还款明细导入防重复 — 查询加速索引（非 UNIQUE）
-- 覆盖单元：trust_product_id + source_file_name + source_sheet_name
-- 业务重复检查：custody + source + repayment_date + amount + period_no
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_repayment_import_scope
    ON trust_repayment_detail_records (
        trust_product_id,
        source_file_name,
        source_sheet_name
    );

CREATE INDEX IF NOT EXISTS idx_repayment_business_check
    ON trust_repayment_detail_records (
        trust_product_id,
        custody_asset_code,
        source_asset_code,
        repayment_date,
        actual_repayment_amount,
        period_no
    );
