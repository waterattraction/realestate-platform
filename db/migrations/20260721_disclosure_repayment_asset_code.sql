-- type: migration
-- purpose: 披露还款明细冻结行增加 asset_code，供模版「资产编号(房源)」= 主编号展示/导出
-- dependencies: 20260720_disclosure_snapshots.sql
-- idempotent: 是（ADD COLUMN IF NOT EXISTS）
-- 执行：按 db/manifest.txt

ALTER TABLE disclosure_repayment_rows
    ADD COLUMN IF NOT EXISTS asset_code VARCHAR(64) NULL;
