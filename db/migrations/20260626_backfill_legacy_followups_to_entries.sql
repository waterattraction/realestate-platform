-- Backfill legacy trust_overdue_followups → V2 cases + entries (Scheme A).
-- Idempotent: entries tagged note = 'legacy_followup_id:{id}'.

INSERT INTO trust_overdue_followup_cases (
    trust_product_id,
    custody_asset_code,
    data_date,
    status,
    owner_name,
    opened_at,
    closed_at,
    last_follow_up_at,
    created_by,
    updated_by,
    created_at,
    updated_at
)
SELECT DISTINCT ON (f.trust_product_id, ta.custody_asset_code)
    f.trust_product_id,
    ta.custody_asset_code,
    f.data_date,
    f.status,
    f.owner_name,
    f.created_at,
    CASE WHEN f.status IN ('resolved', 'closed') THEN f.updated_at ELSE NULL END,
    f.last_follow_up_at,
    'migration',
    'migration',
    f.created_at,
    f.updated_at
FROM trust_overdue_followups f
INNER JOIN trust_assets ta ON ta.id = f.trust_asset_id
WHERE ta.custody_asset_code IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM trust_overdue_followup_cases c
      WHERE c.trust_product_id = f.trust_product_id
        AND c.custody_asset_code = ta.custody_asset_code
  )
ORDER BY f.trust_product_id, ta.custody_asset_code, f.id DESC;

INSERT INTO trust_overdue_followup_entries (
    case_id,
    entry_type,
    status_snapshot,
    overdue_reason,
    follow_up_plan,
    trust_feedback,
    note,
    owner_name,
    created_by,
    created_at
)
SELECT
    c.id,
    CASE WHEN f.trigger_source = 'system' THEN 'system' ELSE 'manual' END,
    f.status,
    f.overdue_reason,
    f.follow_up_plan,
    f.trust_feedback,
    'legacy_followup_id:' || f.id::text,
    f.owner_name,
    'migration',
    COALESCE(f.last_follow_up_at, f.created_at)
FROM trust_overdue_followups f
INNER JOIN trust_assets ta ON ta.id = f.trust_asset_id
INNER JOIN LATERAL (
    SELECT c2.id
    FROM trust_overdue_followup_cases c2
    WHERE c2.trust_product_id = f.trust_product_id
      AND c2.custody_asset_code = ta.custody_asset_code
    ORDER BY
        CASE WHEN c2.status IN ('open', 'in_progress') THEN 0 ELSE 1 END,
        c2.id DESC
    LIMIT 1
) c ON TRUE
WHERE ta.custody_asset_code IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM trust_overdue_followup_entries e
      WHERE e.note = 'legacy_followup_id:' || f.id::text
  );

UPDATE trust_overdue_followup_cases c
SET last_follow_up_at = sub.last_at,
    updated_at = NOW(),
    updated_by = 'migration'
FROM (
    SELECT
        e.case_id,
        MAX(e.created_at) AS last_at
    FROM trust_overdue_followup_entries e
    WHERE e.note LIKE 'legacy_followup_id:%'
    GROUP BY e.case_id
) sub
WHERE c.id = sub.case_id
  AND (c.last_follow_up_at IS NULL OR c.last_follow_up_at < sub.last_at);
