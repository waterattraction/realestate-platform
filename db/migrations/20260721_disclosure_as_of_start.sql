-- 还款明细披露：披露开始日（日期范围）；监控披露仍仅用 as_of_date
-- dependencies: 20260720_disclosure_snapshots.sql

ALTER TABLE disclosure_snapshots
    ADD COLUMN IF NOT EXISTS as_of_start_date DATE NULL;

COMMENT ON COLUMN disclosure_snapshots.as_of_start_date IS
    '还款披露开始日；NULL 表示历史单日快照或监控快照';
