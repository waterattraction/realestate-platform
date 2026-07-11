-- Drop legacy split-level followup table; risk → trust_risk_cases, ops → followup_cases/entries.

DROP TRIGGER IF EXISTS trg_trust_overdue_followups_updated_at ON trust_overdue_followups;
DROP TABLE IF EXISTS trust_overdue_followups CASCADE;
