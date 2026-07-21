-- type: migration
-- created_at: 2026-07-21
-- author: ops
-- purpose: 手工结算增加还款方；payer 语义为结算主体
-- dependencies: migrations/20260721_manual_settlements.sql
-- idempotent: yes

ALTER TABLE trust_asset_manual_settlements
    ADD COLUMN IF NOT EXISTS repayer VARCHAR(200) NULL;

COMMENT ON COLUMN trust_asset_manual_settlements.payer IS '结算主体';
COMMENT ON COLUMN trust_asset_manual_settlements.repayer IS '还款方';
