-- Overdue workbench aggregate root: trust_product_id + asset_code
-- Marks + followup cases migrate from custody_asset_code to asset_code.

-- ── 1. trust_asset_trust_marks ─────────────────────────────────────────────

ALTER TABLE trust_asset_trust_marks
    ADD COLUMN IF NOT EXISTS asset_code VARCHAR(128);

UPDATE trust_asset_trust_marks tm
SET asset_code = src.asset_code
FROM (
    SELECT
        tm2.id,
        COALESCE(
            (
                SELECT m.asset_code
                FROM trust_asset_monitor_records m
                INNER JOIN trust_assets ta ON ta.id = m.trust_asset_id
                WHERE m.trust_product_id = tm2.trust_product_id
                  AND m.data_date = tm2.data_date
                  AND COALESCE(m.custody_asset_code, ta.custody_asset_code, m.asset_code)
                      = tm2.custody_asset_code
                LIMIT 1
            ),
            tm2.custody_asset_code
        ) AS asset_code
    FROM trust_asset_trust_marks tm2
    WHERE tm2.asset_code IS NULL
) src
WHERE tm.id = src.id;

UPDATE trust_asset_trust_marks SET asset_code = custody_asset_code WHERE asset_code IS NULL;

-- Keep row with latest updated_at per (trust_product_id, asset_code, data_date)
DELETE FROM trust_asset_trust_marks tm
WHERE tm.id IN (
    SELECT id FROM (
        SELECT
            id,
            ROW_NUMBER() OVER (
                PARTITION BY trust_product_id, asset_code, data_date
                ORDER BY updated_at DESC, id DESC
            ) AS rn
        FROM trust_asset_trust_marks
    ) ranked
    WHERE rn > 1
);

ALTER TABLE trust_asset_trust_marks
    ALTER COLUMN asset_code SET NOT NULL;

ALTER TABLE trust_asset_trust_marks
    DROP CONSTRAINT IF EXISTS uq_trust_asset_trust_marks;

ALTER TABLE trust_asset_trust_marks
    ADD CONSTRAINT uq_trust_asset_trust_marks
        UNIQUE (trust_product_id, asset_code, data_date);

DROP INDEX IF EXISTS idx_trust_asset_trust_marks_lookup;

CREATE INDEX IF NOT EXISTS idx_trust_asset_trust_marks_lookup
    ON trust_asset_trust_marks (trust_product_id, asset_code, data_date DESC);

-- custody_asset_code retained for audit; no longer part of uniqueness

-- ── 2. trust_overdue_followup_cases ────────────────────────────────────────

ALTER TABLE trust_overdue_followup_cases
    ADD COLUMN IF NOT EXISTS asset_code VARCHAR(128);

UPDATE trust_overdue_followup_cases c
SET asset_code = COALESCE(
    (
        SELECT m.asset_code
        FROM trust_asset_monitor_records m
        INNER JOIN trust_assets ta ON ta.id = m.trust_asset_id
        WHERE m.trust_product_id = c.trust_product_id
          AND COALESCE(m.custody_asset_code, ta.custody_asset_code, m.asset_code)
              = c.custody_asset_code
        ORDER BY m.data_date DESC
        LIMIT 1
    ),
    c.custody_asset_code
)
WHERE c.asset_code IS NULL;

UPDATE trust_overdue_followup_cases SET asset_code = custody_asset_code WHERE asset_code IS NULL;

-- Repoint entries to canonical case per (trust_product_id, asset_code)
WITH ranked AS (
    SELECT
        id,
        trust_product_id,
        asset_code,
        ROW_NUMBER() OVER (
            PARTITION BY trust_product_id, asset_code
            ORDER BY
                CASE WHEN status IN ('open', 'in_progress') THEN 0 ELSE 1 END,
                COALESCE(last_follow_up_at, updated_at, created_at) DESC NULLS LAST,
                id DESC
        ) AS rn
    FROM trust_overdue_followup_cases
),
keepers AS (
    SELECT trust_product_id, asset_code, id AS keeper_id
    FROM ranked
    WHERE rn = 1
),
dupes AS (
    SELECT r.id AS dupe_id, k.keeper_id
    FROM ranked r
    INNER JOIN keepers k
        ON k.trust_product_id = r.trust_product_id
       AND k.asset_code = r.asset_code
    WHERE r.rn > 1
)
UPDATE trust_overdue_followup_entries e
SET case_id = d.keeper_id
FROM dupes d
WHERE e.case_id = d.dupe_id;

DELETE FROM trust_overdue_followup_cases c
WHERE c.id IN (
    SELECT id FROM (
        SELECT
            id,
            ROW_NUMBER() OVER (
                PARTITION BY trust_product_id, asset_code
                ORDER BY
                    CASE WHEN status IN ('open', 'in_progress') THEN 0 ELSE 1 END,
                    COALESCE(last_follow_up_at, updated_at, created_at) DESC NULLS LAST,
                    id DESC
            ) AS rn
        FROM trust_overdue_followup_cases
    ) ranked
    WHERE rn > 1
);

ALTER TABLE trust_overdue_followup_cases
    ALTER COLUMN asset_code SET NOT NULL;

DROP INDEX IF EXISTS uq_followup_cases_active_custody;

CREATE UNIQUE INDEX IF NOT EXISTS uq_followup_cases_active_asset
    ON trust_overdue_followup_cases (trust_product_id, asset_code)
    WHERE status IN ('open', 'in_progress');

DROP INDEX IF EXISTS idx_followup_cases_product_custody;

CREATE INDEX IF NOT EXISTS idx_followup_cases_product_asset
    ON trust_overdue_followup_cases (trust_product_id, asset_code);
