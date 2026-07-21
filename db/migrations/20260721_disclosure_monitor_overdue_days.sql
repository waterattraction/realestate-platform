-- type: migration
-- created_at: 2026-07-21
-- author: ops
-- purpose: 资产监控披露快照增加逾期天数列（冻结时物化）
-- dependencies: 20260720_disclosure_snapshots.sql
-- idempotent: yes

ALTER TABLE disclosure_monitor_rows
    ADD COLUMN IF NOT EXISTS overdue_days INT NULL;
